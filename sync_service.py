"""
Servicio de sincronización mediante web scraping
"""
import json
from datetime import datetime
from pathlib import Path
from odoo_scraper import odoo_scraper
import time

DATA_DIR = Path("data")
IMAGES_DIR = Path("static/images/products")


def ensure_directories():
    DATA_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def sync_catalog():
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
                    
                    if 'category_ids' not in prod:
                        prod['category_ids'] = []
                    if cat_id not in prod['category_ids']:
                        prod['category_ids'].append(cat_id)
                    if parent_id not in prod['category_ids']:
                        prod['category_ids'].append(parent_id)
                    
                    # Descargar imagen si es nuevo
                    if prod.get('image_url') and prod_id not in seen_product_ids:
                        local_image = odoo_scraper.download_image(prod['image_url'], prod_id)
                        prod['image_url'] = local_image
                    
                    if prod_id not in seen_product_ids:
                        seen_product_ids.add(prod_id)
                        all_products.append(prod)
                    
                    products_by_category[cat_id].append(prod)
                
                print(f"      {len(products)} productos")
                time.sleep(0.3)
        
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
