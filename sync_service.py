"""Servicio de sincronización del catálogo público de Odoo."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from odoo_scraper import odoo_scraper

DATA_DIR = Path(os.getenv("CATALOG_DATA_DIR", "data"))
IMAGES_DIR = Path(os.getenv("CATALOG_IMAGES_DIR", "static/images/products"))
IMAGE_WORKERS = max(1, int(os.getenv("SYNC_IMAGE_WORKERS", 3)))
SYNC_LOCK = threading.Lock()


def empty_catalog() -> dict:
    return {
        "last_sync": None,
        "categories": {"parents": [], "children": {}, "all": {}},
        "products": [],
        "products_by_category": {},
        "stats": {
            "total_products": 0,
            "total_categories": 0,
            "parent_categories": 0,
        },
    }


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def load_catalog() -> dict:
    catalog_path = DATA_DIR / "catalog.json"
    if not catalog_path.exists():
        return empty_catalog()
    try:
        with catalog_path.open("r", encoding="utf-8") as catalog_file:
            return json.load(catalog_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"⚠ No se pudo leer el catálogo: {exc}")
        return empty_catalog()


def save_catalog(catalog_data: dict):
    """Escritura atómica para no dejar JSON incompleto."""
    catalog_path = DATA_DIR / "catalog.json"
    temporary_path = DATA_DIR / "catalog.json.tmp"
    with temporary_path.open("w", encoding="utf-8") as catalog_file:
        json.dump(catalog_data, catalog_file, ensure_ascii=False, indent=2)
        catalog_file.flush()
        os.fsync(catalog_file.fileno())
    os.replace(temporary_path, catalog_path)


def sync_catalog():
    if not SYNC_LOCK.acquire(blocking=False):
        print("⚠ Ya hay una sincronización en curso")
        return False
    try:
        return _sync_catalog()
    finally:
        SYNC_LOCK.release()


def _sync_catalog():
    print(f"\n{'=' * 50}")
    print(f"Iniciando sincronización: {datetime.now().isoformat()}")
    print(f"{'=' * 50}")
    ensure_directories()

    previous_catalog = load_catalog()
    previous_total = previous_catalog.get("stats", {}).get("total_products", 0)

    if not odoo_scraper.connect():
        print("✗ No se pudo conectar a Odoo")
        return False

    try:
        print("\n→ Cargando estructura de categorías...")
        category_tree = odoo_scraper.get_category_hierarchy()
        total_categories = len(category_tree["all"])
        print(f"  Total: {total_categories} categorías")

        print("\n→ Obteniendo productos por categoría...")
        all_products = []
        products_by_category = {}
        seen_product_ids = set()
        products_cache = {}

        for parent_id, children in category_tree["children"].items():
            parent_name = category_tree["all"][parent_id]["name"]
            print(f"\n  [{parent_name}]")

            for child in children:
                cat_id = child["id"]
                print(f"    → {child['name']}...")
                products = odoo_scraper.get_products_by_category(cat_id, child["url"])
                products_by_category[cat_id] = []

                for product in products:
                    product_id = product["id"]
                    if product_id not in seen_product_ids:
                        product["category_ids"] = [cat_id, parent_id]
                        seen_product_ids.add(product_id)
                        products_cache[product_id] = product
                        all_products.append(product)
                    else:
                        product = products_cache[product_id]
                        if cat_id not in product["category_ids"]:
                            product["category_ids"].append(cat_id)
                        if parent_id not in product["category_ids"]:
                            product["category_ids"].append(parent_id)
                    products_by_category[cat_id].append(product)

                print(f"      {len(products)} productos")
                time.sleep(0.3)

        new_total = len(all_products)

        # Nunca reemplazar un catálogo válido con una extracción vacía o
        # con una caída anormal de más del 50 %.
        if new_total == 0:
            print("✗ Odoo no devolvió productos")
            print("✗ Se conserva el catálogo anterior")
            return False

        if previous_total > 0 and new_total < previous_total * 0.5:
            print(
                f"✗ Resultado anormal: {new_total} productos; "
                f"el catálogo anterior tenía {previous_total}"
            )
            print("✗ Se conserva el catálogo anterior")
            return False

        # Publicar inmediatamente el catálogo con las imágenes remotas del
        # listado. La descarga de galerías puede tardar varios minutos y no
        # debe mantener la web vacía durante la primera sincronización.
        all_products.sort(key=lambda product: product["id"], reverse=True)
        catalog_data = {
            "last_sync": datetime.now().isoformat(),
            "categories": category_tree,
            "products": all_products,
            "products_by_category": products_by_category,
            "stats": {
                "total_products": new_total,
                "total_categories": total_categories,
                "parent_categories": len(category_tree["parents"]),
            },
        }
        save_catalog(catalog_data)
        print(f"\n✓ Catálogo publicado inicialmente: {new_total} productos")

        print(f"\n→ Descargando galerías con {IMAGE_WORKERS} procesos paralelos...")

        def enrich_product_images(product):
            try:
                remote_images = odoo_scraper.get_product_images(
                    product.get("product_url", ""),
                    product.get("image_url", ""),
                )
                local_images = []
                for image_index, image_url in enumerate(remote_images):
                    local_image = odoo_scraper.download_image(
                        image_url,
                        product["id"],
                        image_index,
                    )
                    if local_image and local_image not in local_images:
                        local_images.append(local_image)

                if local_images:
                    product["images"] = local_images
                    product["image_url"] = local_images[0]
                else:
                    product["images"] = (
                        [product["image_url"]] if product.get("image_url") else []
                    )
            except Exception as exc:
                print(f"  Error obteniendo galería del producto {product['id']}: {exc}")
                product["images"] = (
                    [product["image_url"]] if product.get("image_url") else []
                )

        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as executor:
            for completed, _ in enumerate(executor.map(enrich_product_images, all_products), 1):
                if completed % 100 == 0 or completed == new_total:
                    print(f"  Galerías procesadas: {completed}/{new_total}")

        print(f"\n✓ Total productos encontrados: {new_total}")
        catalog_data["last_sync"] = datetime.now().isoformat()
        save_catalog(catalog_data)
        print("\n✓ Sincronización completada")
        print(f"  - Productos: {new_total}")
        print(f"  - Categorías: {total_categories}")
        return True

    except Exception as exc:
        print(f"✗ Error durante sincronización: {exc}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        odoo_scraper.close()


if __name__ == "__main__":
    sync_catalog()
