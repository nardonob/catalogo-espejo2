"""
Servicio de sincronización mediante web scraping
"""
import json
import os
from datetime import datetime
from pathlib import Path
from odoo_scraper import odoo_scraper
import time

DATA_DIR = Path("data")
IMAGES_DIR = Path("static/images/products")

def ensure_directories():
    """Crear directorios necesarios"""
    DATA_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def build_category_tree_from_scrape(categories: list) -> dict:
    """Construir árbol de categorías desde datos scrapeados"""
    tree = {
        "parents": [],
        "children": {},
        "all": {}
    }
    
    # Primera pasada: indexar todas
    for cat in categories:
        cat_id = cat['id']
        tree["all"][cat_id] = {
            "id": cat_id,
            "name": cat['name'],
            "url": cat.get('url', ''),
            "parent_id": cat.get('parent_id'),
            "parent_name": cat.get('parent_name'),
            "sequence": 0
        }
    
    # Segunda pasada: organizar jerarquía
    for cat_id, cat_data in tree["all"].items():
        parent_id = cat_data.get('parent_id')
        
        if parent_id is None:
            tree["parents"].append(cat_data)
        else:
            if parent_id not in tree["children"]:
                tree["children"][parent_id] = []
            tree["children"][parent_id].append(cat_data)
            
            # Actualizar nombre del padre
            if parent_id in tree["all"]:
                cat_data["parent_name"] = tree["all"][parent_id]["name"]
    
    return tree

def sync_catalog():
    """Sincronizar catálogo completo desde Odoo mediante scraping"""
    print(f"\n{'='*50}")
    print(f"Iniciando sincronización: {datetime.now().isoformat()}")
    print(f"{'='*50}")
    
    ensure_directories()
    
    # Conectar
    if not odoo_scraper.connect():
        print("✗ No se pudo conectar a Odoo")
        return False
    
    try:
        # Obtener categorías con jerarquía
        print("\n→ Obteniendo categorías...")
        category_tree = odoo_scraper.get_category_hierarchy()
        
        total_categories = len(category_tree["all"])
        print(f"  Total: {total_categories} categorías")
        
        # Obtener productos por categoría
        print("\n→ Obteniendo productos...")
        all_products = []
        products_by_category = {}
        seen_product_ids = set()
        
        # Si hay categorías, obtener productos de cada una
        if category_tree["all"]:
            for cat_id, cat_data in category_tree["all"].items():
                cat_url = cat_data.get('url')
                if not cat_url:
                    continue
                    
                print(f"  Categoría: {cat_data['name']}")
                products = odoo_scraper.get_products_by_category(cat_id, cat_url)
                
                products_by_category[cat_id] = []
                
                for prod in products:
                    prod_id = prod['id']
                    
                    # Agregar categoría al producto
                    if 'category_ids' not in prod:
                        prod['category_ids'] = []
                    if cat_id not in prod['category_ids']:
                        prod['category_ids'].append(cat_id)
                    
                    # Descargar imagen si no la tenemos
                    if prod.get('image_url') and prod_id not in seen_product_ids:
                        local_image = odoo_scraper.download_image(prod['image_url'], prod_id)
                        prod['image_url'] = local_image
                    
                    # Agregar a lista general si es nuevo
                    if prod_id not in seen_product_ids:
                        seen_product_ids.add(prod_id)
                        all_products.append(prod)
                    else:
                        # Actualizar categorías del producto existente
                        for p in all_products:
                            if p['id'] == prod_id:
                                if cat_id not in p.get('category_ids', []):
                                    p['category_ids'].append(cat_id)
                                break
                    
                    products_by_category[cat_id].append(prod)
                
                print(f"    → {len(products)} productos")
                
                # Pequeña pausa para no sobrecargar
                time.sleep(0.5)
        else:
            # Sin categorías, obtener todos los productos del shop
            print("  Obteniendo todos los productos...")
            all_products = odoo_scraper.get_all_products()
            
            # Descargar imágenes
            for prod in all_products:
                if prod.get('image_url'):
                    local_image = odoo_scraper.download_image(prod['image_url'], prod['id'])
                    prod['image_url'] = local_image
        
        print(f"\n✓ Total productos encontrados: {len(all_products)}")
        
        # Preparar datos del catálogo
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
        
        # Guardar en JSON
        catalog_path = DATA_DIR / "catalog.json"
        with open(catalog_path, 'w', encoding='utf-8') as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Sincronización completada")
        print(f"  - Productos: {catalog_data['stats']['total_products']}")
        print(f"  - Categorías: {catalog_data['stats']['total_categories']}")
        print(f"  - Categorías principales: {catalog_data['stats']['parent_categories']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error durante sincronización: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        odoo_scraper.close()

def load_catalog() -> dict:
    """Cargar catálogo desde archivo JSON"""
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
    except Exception as e:
        print(f"Error cargando catálogo: {e}")
        return {
            "last_sync": None,
            "categories": {"parents": [], "children": {}, "all": {}},
            "products": [],
            "products_by_category": {},
            "stats": {"total_products": 0, "total_categories": 0, "parent_categories": 0}
        }


if __name__ == "__main__":
    sync_catalog()
