"""
Scraper para Odoo eCommerce (Plan Standard sin API)
Extrae categorías y productos mediante web scraping
"""
import httpx
from bs4 import BeautifulSoup
import re
import os
from typing import Optional
from urllib.parse import urljoin
from dotenv import load_dotenv

load_dotenv()

# Estructura de categorías fija (basada en tu menú de Odoo)
CATEGORIES_STRUCTURE = {
    "parents": [
        {"id": 1, "name": "Baño de Oro", "slug": "bano-de-oro"},
        {"id": 2, "name": "Acero", "slug": "acero"},
        {"id": 3, "name": "Plata", "slug": "plata"},
    ],
    "children": {
        1: [  # Baño de Oro
            {"id": 5, "name": "Pulseras", "slug": "bano-de-oro-pulseras-5"},
            {"id": 6, "name": "Aretes", "slug": "bano-de-oro-aretes-6"},
            {"id": 7, "name": "Anillos", "slug": "bano-de-oro-anillos-7"},
            {"id": 8, "name": "Cadenas", "slug": "bano-de-oro-cadenas-8"},
            {"id": 9, "name": "Cadenas con Dije", "slug": "bano-de-oro-cadenas-con-dije-9"},
            {"id": 10, "name": "Juegos", "slug": "bano-de-oro-juegos-10"},
            {"id": 11, "name": "Tobilleras", "slug": "bano-de-oro-tobilleras-11"},
        ],
        2: [  # Acero
            {"id": 12, "name": "Pulseras", "slug": "acero-pulseras-12"},
            {"id": 13, "name": "Aretes", "slug": "acero-aretes-13"},
            {"id": 14, "name": "Anillos", "slug": "acero-anillos-14"},
            {"id": 15, "name": "Cadenas", "slug": "acero-cadenas-15"},
            {"id": 16, "name": "Cadenas con Dijes", "slug": "acero-cadenas-con-dijes-16"},
            {"id": 17, "name": "Tobilleras", "slug": "acero-tobilleras-17"},
            {"id": 18, "name": "Rosarios", "slug": "acero-rosarios-18"},
            {"id": 19, "name": "Piercing", "slug": "acero-piercing-19"},
            {"id": 20, "name": "Juegos", "slug": "acero-juegos-20"},
            {"id": 21, "name": "Dijes", "slug": "acero-dijes-21"},
        ],
        3: [  # Plata
            {"id": 22, "name": "Pulseras", "slug": "plata-pulseras-22"},
            {"id": 23, "name": "Anillos", "slug": "plata-anillos-23"},
            {"id": 24, "name": "Aretes", "slug": "plata-aretes-24"},
            {"id": 25, "name": "Cadenas", "slug": "plata-cadenas-25"},
            {"id": 26, "name": "Cadenas con Dijes", "slug": "plata-cadenas-con-dijes-26"},
            {"id": 27, "name": "Dijes", "slug": "plata-dijes-27"},
            {"id": 28, "name": "Juegos", "slug": "plata-juegos-28"},
            {"id": 29, "name": "Tobilleras", "slug": "plata-tobilleras-29"},
            {"id": 30, "name": "Rosarios", "slug": "plata-rosarios-30"},
        ],
    }
}


class OdooScraper:
    def __init__(self):
        self.base_url = os.getenv("ODOO_SHOP_URL", "https://italsteeldistribuidora.odoo.com")
        self.shop_url = f"{self.base_url}/shop"
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        
        self.client: Optional[httpx.Client] = None
    
    def connect(self) -> bool:
        try:
            self.client = httpx.Client(
                headers=self.headers,
                follow_redirects=True,
                timeout=30.0
            )
            response = self.client.get(self.shop_url)
            if response.status_code == 200:
                print(f"✓ Conectado a {self.base_url}")
                return True
            else:
                print(f"✗ Error de conexión: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Error de conexión: {e}")
            return False
    
    def close(self):
        if self.client:
            self.client.close()
    
    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                return BeautifulSoup(response.text, 'html.parser')
            return None
        except Exception as e:
            print(f"  Error obteniendo {url}: {e}")
            return None
    
    def get_category_hierarchy(self) -> dict:
        """Retornar estructura de categorías fija y ordenada"""
        hierarchy = {
            "parents": [],
            "children": {},
            "all": {}
        }
        
        for parent in CATEGORIES_STRUCTURE["parents"]:
            parent_data = {
                "id": parent["id"],
                "name": parent["name"],
                "slug": parent["slug"],
                "url": f"{self.base_url}/shop/category/{parent['slug']}",
                "parent_id": None,
                "parent_name": None
            }
            hierarchy["parents"].append(parent_data)
            hierarchy["all"][parent["id"]] = parent_data
        
        for parent_id, children in CATEGORIES_STRUCTURE["children"].items():
            hierarchy["children"][parent_id] = []
            parent_name = next((p["name"] for p in CATEGORIES_STRUCTURE["parents"] if p["id"] == parent_id), None)
            
            for child in children:
                child_data = {
                    "id": child["id"],
                    "name": child["name"],
                    "slug": child["slug"],
                    "url": f"{self.base_url}/shop/category/{child['slug']}",
                    "parent_id": parent_id,
                    "parent_name": parent_name
                }
                hierarchy["children"][parent_id].append(child_data)
                hierarchy["all"][child["id"]] = child_data
        
        return hierarchy
    
    def get_products_from_page(self, url: str) -> tuple[list, Optional[str], int]:
        """
        Obtener productos de una página del shop
        Retorna: (lista_productos, url_siguiente_pagina, total_productos)
        """
        products = []
        next_page = None
        total = 0
        
        soup = self._get_soup(url)
        if not soup:
            return products, next_page, total
        
        # Obtener total de productos de la página
        total_el = soup.select_one('.o_wsale_products_count, .products_pager strong, .text-muted')
        if total_el:
            total_text = total_el.get_text()
            match = re.search(r'(\d+)\s*producto', total_text, re.IGNORECASE)
            if match:
                total = int(match.group(1))
        
        # Buscar todos los formularios de producto (estructura Odoo estándar)
        product_forms = soup.select('form[action*="/shop/cart/update"]')
        
        for form in product_forms:
            try:
                product = self._parse_product_form(form, soup)
                if product:
                    products.append(product)
            except Exception as e:
                print(f"  Error parseando producto: {e}")
                continue
        
        # Buscar paginación - múltiples selectores
        # Método 1: Link directo "Next" o "Siguiente"
        next_link = soup.select_one('.pagination a[rel="next"], a.page-link[rel="next"], .pagination .next a')
        if next_link:
            next_href = next_link.get('href')
            if next_href:
                next_page = urljoin(self.base_url, next_href)
        
        # Método 2: Si no hay link next, buscar por número de página
        if not next_page:
            current_page = 1
            # Detectar página actual
            active_page = soup.select_one('.pagination .active a, .pagination .active span')
            if active_page:
                try:
                    current_page = int(active_page.get_text(strip=True))
                except:
                    pass
            
            # Buscar si hay más páginas
            page_links = soup.select('.pagination a[href*="page="], .pagination a.page-link')
            max_page = current_page
            for link in page_links:
                href = link.get('href', '')
                page_match = re.search(r'page[=/-](\d+)', href)
                if page_match:
                    page_num = int(page_match.group(1))
                    if page_num > max_page:
                        max_page = page_num
            
            if max_page > current_page:
                # Construir URL de siguiente página
                if '?' in url:
                    if 'page=' in url:
                        next_page = re.sub(r'page=\d+', f'page={current_page + 1}', url)
                    else:
                        next_page = f"{url}&page={current_page + 1}"
                else:
                    next_page = f"{url}?page={current_page + 1}"
        
        return products, next_page, total
    
    def _parse_product_form(self, form, soup=None) -> Optional[dict]:
        container = form.find_parent('div', class_='oe_product') or form.find_parent('td') or form
        
        link = container.select_one('a[href*="/shop/"]')
        if not link:
            return None
        
        href = link.get('href', '')
        match = re.search(r'-(\d+)(?:\?|$|#)', href)
        if not match:
            return None
        
        product_id = int(match.group(1))
        
        # Nombre
        name_el = container.select_one('h5, h6, .card-title, [itemprop="name"]')
        name = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)
        name = re.sub(r'\s+', ' ', name).strip() or "Sin nombre"
        
        # Precio - FIX: el precio viene multiplicado por 100 en el HTML
        price = 0.0
        price_el = container.select_one('.oe_currency_value')
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_clean = re.sub(r'[^\d.]', '', price_text)
            try:
                raw_price = float(price_clean) if price_clean else 0.0
                # Dividir entre 100 para obtener precio real
                price = raw_price / 100.0
            except:
                price = 0.0
        
        # Imagen
        image_url = ""
        img_el = container.select_one('img[src*="/web/image"]')
        if img_el:
            image_url = img_el.get('src', '')
            if image_url and not image_url.startswith('http'):
                image_url = urljoin(self.base_url, image_url)
        
        # Código
        code = ""
        for el in container.select('small, .text-muted, span'):
            text = el.get_text(strip=True)
            if re.match(r'^[A-Z]{1,3}-?[A-Z0-9]+$', text, re.IGNORECASE):
                code = text
                break
        
        # Cantidad disponible - buscar en el contenedor o en atributos
        qty_available = 0
        # Intentar obtener de data attributes
        qty_el = container.select_one('[data-qty-available], .availability')
        if qty_el:
            qty_text = qty_el.get('data-qty-available') or qty_el.get_text(strip=True)
            qty_match = re.search(r'(\d+)', str(qty_text))
            if qty_match:
                qty_available = int(qty_match.group(1))
        
        return {
            "id": product_id,
            "name": name,
            "code": code,
            "price": price,
            "image_url": image_url,
            "product_url": urljoin(self.base_url, href),
            "qty_available": qty_available
        }
    
    def get_all_products(self, category_url: Optional[str] = None) -> list:
        all_products = []
        url = category_url or self.shop_url
        page = 1
        total_expected = 0
        
        while url:
            print(f"    Página {page}...")
            products, next_url, total = self.get_products_from_page(url)
            
            if total > 0 and total_expected == 0:
                total_expected = total
                print(f"    (Total esperado: {total_expected})")
            
            all_products.extend(products)
            
            # Si ya tenemos todos los productos esperados, parar
            if total_expected > 0 and len(all_products) >= total_expected:
                break
            
            # Si no hay productos nuevos en esta página, intentar forzar siguiente
            if not products and page < 50:
                # Intentar construir URL de siguiente página manualmente
                base = category_url or self.shop_url
                if '?' in base:
                    next_url = f"{base}&page={page + 1}"
                else:
                    next_url = f"{base}?page={page + 1}"
                
                # Verificar si hay productos en esa página
                test_products, _, _ = self.get_products_from_page(next_url)
                if not test_products:
                    break  # No hay más productos
                products = test_products
                all_products.extend(products)
            
            url = next_url
            page += 1
            
            if page > 100:
                print("    ⚠ Límite de páginas alcanzado")
                break
        
        return all_products
    
    def get_products_by_category(self, category_id: int, category_url: str) -> list:
        return self.get_all_products(category_url)
    
    def download_image(self, image_url: str, product_id: int) -> str:
        if not image_url:
            return ""
        try:
            response = self.client.get(image_url)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                ext = '.png' if 'png' in content_type else '.webp' if 'webp' in content_type else '.jpg'
                filename = f"{product_id}{ext}"
                filepath = f"static/images/products/{filename}"
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return f"/static/images/products/{filename}"
        except Exception as e:
            print(f"  Error descargando imagen {product_id}: {e}")
        return image_url


odoo_scraper = OdooScraper()
