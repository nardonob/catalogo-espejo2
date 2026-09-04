"""
Servicio de sincronización mediante web scraping
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from odoo_scraper import odoo_scraper
import time

DATA_DIR = Path("data")
IMAGES_DIR = Path("static/images/products")
IMAGE_WORKERS = max(1, int(os.getenv("SYNC_IMAGE_WORKERS", 8)))
SYNC_LOCK = threading.Lock()


def ensure_directories():
    DATA_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def sync_catalog():
    """Evitar que el scheduler, el arranque y la ruta manual se solapen."""
    if not SYNC_LOCK.acquire(blocking=False):
        print("⚠ Ya hay una sincronización en curso")
        return False

    try:
        return _sync_catalog()
    finally:
        SYNC_LOCK.release()


def _sync_catalog():
    """Sincronizar catálogo completo desde Odoo mediante scraping"""
    print(f"\n{'='*50}")
    print(f"Iniciando sincronización: {datetime.now().isoformat()}")
    print(f"{'='*50}")
    
    ensure_directories()
    
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
        
        # Recorrer todas las subcategorías
        for parent_id, children in category_tree["children"].items():
            parent_name = category_tree["all"][parent_id]["name"]
            print(f"\n  [{parent_name}]")
            
            for child in children:
                cat_id = child["id"]
                cat_url = child["url"]
                print(f"    → {child['name']}...")
                
                products = odoo_scraper.get_products_by_category(cat_id, cat_url)
                products_by_category[cat_id] = []
                
                for prod in products:
                    prod_id = prod['id']

                    if prod_id not in seen_product_ids:
                        prod['category_ids'] = [cat_id, parent_id]
                        seen_product_ids.add(prod_id)
                        products_cache[prod_id] = prod
                        all_products.append(prod)
                    else:
                        prod = products_cache[prod_id]
                        if cat_id not in prod['category_ids']:
                            prod['category_ids'].append(cat_id)
                        if parent_id not in prod['category_ids']:
                            prod['category_ids'].append(parent_id)

                    products_by_category[cat_id].append(prod)
                
                print(f"      {len(products)} productos")
                time.sleep(0.3)

        print(f"\n→ Descargando galerías con {IMAGE_WORKERS} procesos paralelos...")

        def enrich_product_images(prod):
            try:
                remote_images = odoo_scraper.get_product_images(
                    prod.get('product_url', ''),
                    prod.get('image_url', '')
                )
                local_images = []
                for image_index, image_url in enumerate(remote_images):
                    local_image = odoo_scraper.download_image(
                        image_url,
                        prod['id'],
                        image_index
                    )
                    if local_image and local_image not in local_images:
                        local_images.append(local_image)

                # Mantener image_url para compatibilidad con el catálogo actual.
                if local_images:
                    prod['images'] = local_images
                    prod['image_url'] = local_images[0]
                else:
                    prod['images'] = [prod['image_url']] if prod.get('image_url') else []
            except Exception as e:
                print(f"  Error obteniendo galería del producto {prod['id']}: {e}")
                prod['images'] = [prod['image_url']] if prod.get('image_url') else []

        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as executor:
            for completed, _ in enumerate(executor.map(enrich_product_images, all_products), 1):
                if completed % 100 == 0 or completed == len(all_products):
                    print(f"  Galerías procesadas: {completed}/{len(all_products)}")
        
        # Ordenar productos por ID descendente (más recientes primero)
        all_products.sort(key=lambda x: x['id'], reverse=True)
        
        print(f"\n✓ Total productos encontrados: {len(all_products)}")
        
        catalog_data = {
            "last_sync": datetime.now().isoformat(),
            "categories": category_tree,
            "products": all_products,
            "products_by_category": products_by_category,
            "stats": {
                "total_products": len(all_products),
                "total_categories": total_categories,
                "parent_categories": len(category_tree["parents"])
            }
        }
        
        with open(DATA_DIR / "catalog.json", 'w', encoding='utf-8') as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Sincronización completada")
        print(f"  - Productos: {catalog_data['stats']['total_products']}")
        print(f"  - Categorías: {catalog_data['stats']['total_categories']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error durante sincronización: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        odoo_scraper.close()


def load_catalog() -> dict:
    catalog_path = DATA_DIR / "catalog.json"
    
    if not catalog_path.exists():
        return {
            "last_sync": None,
            "categories": {"parents": [], "children": {}, "all": {}},
            "products": [],
            "products_by_category": {},
            "stats": {"total_products": 0, "total_categories": 0, "parent_categories": 0}
        }
    
    try:
        with open(catalog_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            "last_sync": None,
            "categories": {"parents": [], "children": {}, "all": {}},
            "products": [],
            "products_by_category": {},
            "stats": {"total_products": 0, "total_categories": 0, "parent_categories": 0}
        }


if __name__ == "__main__":
    sync_catalog()
