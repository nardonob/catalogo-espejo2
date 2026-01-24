"""
Scraper para Odoo eCommerce (Plan Standard sin API)
Extrae categorías y productos mediante web scraping
"""
import httpx
from bs4 import BeautifulSoup
import re
import json
import os
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

class OdooScraper:
    def __init__(self):
        self.base_url = os.getenv("ODOO_SHOP_URL", "https://italsteeldistribuidora.odoo.com")
        self.shop_url = f"{self.base_url}/shop"
        
        # Headers que simulan navegador real
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        
        self.client: Optional[httpx.Client] = None
    
    def connect(self) -> bool:
        """Inicializar cliente HTTP con sesión"""
        try:
            self.client = httpx.Client(
                headers=self.headers,
                follow_redirects=True,
                timeout=30.0
            )
            
            # Test de conexión
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
        """Cerrar cliente HTTP"""
        if self.client:
            self.client.close()
    
    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        """Obtener BeautifulSoup de una URL"""
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                return BeautifulSoup(response.text, 'html.parser')
            else:
                print(f"  Error {response.status_code} en {url}")
                return None
        except Exception as e:
            print(f"  Error obteniendo {url}: {e}")
            return None
    
    def get_categories(self) -> list:
        """Obtener todas las categorías del menú del shop"""
        print("→ Obteniendo categorías...")
        categories = []
        
        soup = self._get_soup(self.shop_url)
        if not soup:
            return categories
        
        # Buscar enlaces de categorías en el sidebar o menú
        # Odoo usa diferentes estructuras según el tema
        
        # Método 1: Sidebar con categorías
        category_links = soup.select('aside a[href*="/shop/category/"], .o_wsale_categories a[href*="/shop/category/"]')
        
        # Método 2: Menú de navegación
        if not category_links:
            category_links = soup.select('nav a[href*="/shop/category/"], .navbar a[href*="/shop/category/"]')
        
        # Método 3: Cualquier enlace a categoría
        if not category_links:
            category_links = soup.select('a[href*="/shop/category/"]')
        
        seen_ids = set()
        
        for link in category_links:
            href = link.get('href', '')
            name = link.get_text(strip=True)
            
            # Extraer ID de categoría de la URL
            # Formato: /shop/category/nombre-categoria-ID
            match = re.search(r'/shop/category/.*?-(\d+)$', href)
            if not match:
                match = re.search(r'/shop/category/(\d+)', href)
            
            if match and name:
                cat_id = int(match.group(1))
                if cat_id not in seen_ids:
                    seen_ids.add(cat_id)
                    
                    # Determinar si tiene padre (por indentación o clase)
                    parent_id = None
                    parent_el = link.find_parent(class_=re.compile(r'(subcategor|child|level-2)'))
                    
                    categories.append({
                        'id': cat_id,
                        'name': name,
                        'url': urljoin(self.base_url, href),
                        'parent_id': parent_id
                    })
        
        print(f"  Encontradas: {len(categories)} categorías")
        return categories
    
    def get_category_hierarchy(self) -> dict:
        """Obtener jerarquía completa de categorías navegando cada una"""
        print("→ Construyendo jerarquía de categorías...")
        
        categories = self.get_categories()
        
        # Estructura para almacenar jerarquía
        hierarchy = {
            "parents": [],
            "children": {},
            "all": {}
        }
        
        # Detectar padres e hijos analizando las URLs y páginas
        parent_candidates = {}
        
        for cat in categories:
            soup = self._get_soup(cat['url'])
            if not soup:
                continue
            
            # Buscar breadcrumb para determinar jerarquía
            breadcrumb = soup.select('.breadcrumb a, nav[aria-label="breadcrumb"] a')
            
            parent_id = None
            if len(breadcrumb) > 2:  # Home > Padre > Actual
                for bc_link in breadcrumb[1:-1]:  # Excluir home y actual
                    bc_href = bc_link.get('href', '')
                    bc_match = re.search(r'/shop/category/.*?-(\d+)', bc_href)
                    if bc_match:
                        parent_id = int(bc_match.group(1))
            
            cat_data = {
                "id": cat['id'],
                "name": cat['name'],
                "url": cat['url'],
                "parent_id": parent_id,
                "parent_name": None
            }
            
            hierarchy["all"][cat['id']] = cat_data
            
            if parent_id is None:
                hierarchy["parents"].append(cat_data)
            else:
                if parent_id not in hierarchy["children"]:
                    hierarchy["children"][parent_id] = []
                hierarchy["children"][parent_id].append(cat_data)
                
                # Actualizar nombre del padre si lo tenemos
                if parent_id in hierarchy["all"]:
                    cat_data["parent_name"] = hierarchy["all"][parent_id]["name"]
        
        # Si no detectamos jerarquía, asumir que todas son principales
        if not hierarchy["parents"]:
            hierarchy["parents"] = list(hierarchy["all"].values())
        
        print(f"  Categorías principales: {len(hierarchy['parents'])}")
        return hierarchy
    
    def get_products_from_page(self, url: str) -> tuple[list, Optional[str]]:
        """
        Obtener productos de una página del shop
        Retorna: (lista_productos, url_siguiente_pagina)
        """
        products = []
        next_page = None
        
        soup = self._get_soup(url)
        if not soup:
            return products, next_page
        
        # Buscar contenedor de productos (varios selectores para diferentes temas)
        product_cards = soup.select('''
            .oe_product, 
            .o_wsale_product_grid_wrapper .card,
            .oe_product_cart,
            [itemtype*="Product"],
            .product_price
        ''')
        
        # Método alternativo: buscar por estructura común
        if not product_cards:
            product_cards = soup.select('.o_wsale_products_grid_table_wrapper form')
        
        for card in product_cards:
            try:
                product = self._parse_product_card(card)
                if product:
                    products.append(product)
            except Exception as e:
                print(f"  Error parseando producto: {e}")
                continue
        
        # Buscar paginación
        next_link = soup.select_one('a.page-link[rel="next"], .pagination .next a, a[aria-label="Next"]')
        if next_link:
            next_href = next_link.get('href')
            if next_href:
                next_page = urljoin(self.base_url, next_href)
        
        return products, next_page
    
    def _parse_product_card(self, card) -> Optional[dict]:
        """Parsear una tarjeta de producto"""
        # Buscar enlace al producto
        link = card.select_one('a[href*="/shop/"]')
        if not link:
            link = card.find_parent('a')
        
        if not link:
            return None
        
        href = link.get('href', '')
        
        # Extraer ID del producto
        # Formatos posibles:
        # /shop/producto-nombre-123
        # /shop/product/producto-nombre-123
        match = re.search(r'/shop(?:/product)?/.*?-(\d+)(?:\?|$|#)', href)
        if not match:
            match = re.search(r'/shop(?:/product)?/(\d+)', href)
        
        if not match:
            return None
        
        product_id = int(match.group(1))
        
        # Nombre del producto
        name_el = card.select_one('.oe_product_name, h5, h6, .card-title, [itemprop="name"]')
        name = name_el.get_text(strip=True) if name_el else "Sin nombre"
        
        # Precio
        price = 0.0
        price_el = card.select_one('.oe_currency_value, .product_price .oe_price, [itemprop="price"]')
        if price_el:
            price_text = price_el.get_text(strip=True)
            # Limpiar precio: "$ 1,234.56" -> 1234.56
            price_clean = re.sub(r'[^\d.,]', '', price_text)
            price_clean = price_clean.replace(',', '')
            try:
                price = float(price_clean) if price_clean else 0.0
            except:
                price = 0.0
        
        # Imagen
        image_url = ""
        img_el = card.select_one('img[src*="/web/image"], img[data-src*="/web/image"]')
        if img_el:
            image_url = img_el.get('src') or img_el.get('data-src') or ""
            if image_url and not image_url.startswith('http'):
                image_url = urljoin(self.base_url, image_url)
        
        # Código/referencia (si está visible)
        code = ""
        code_el = card.select_one('.oe_product_code, .product_code, small')
        if code_el:
            code_text = code_el.get_text(strip=True)
            if re.match(r'^[A-Z0-9-]+$', code_text, re.IGNORECASE):
                code = code_text
        
        return {
            "id": product_id,
            "name": name,
            "code": code,
            "price": price,
            "image_url": image_url,
            "product_url": urljoin(self.base_url, href)
        }
    
    def get_all_products(self, category_url: Optional[str] = None) -> list:
        """Obtener todos los productos (de una categoría o del shop completo)"""
        all_products = []
        url = category_url or self.shop_url
        page = 1
        
        while url:
            print(f"  Página {page}...")
            products, next_url = self.get_products_from_page(url)
            all_products.extend(products)
            url = next_url
            page += 1
            
            # Límite de seguridad
            if page > 100:
                print("  ⚠ Límite de páginas alcanzado")
                break
        
        return all_products
    
    def get_products_by_category(self, category_id: int, category_url: str) -> list:
        """Obtener productos de una categoría específica"""
        return self.get_all_products(category_url)
    
    def download_image(self, image_url: str, product_id: int) -> str:
        """Descargar imagen y guardarla localmente"""
        if not image_url:
            return ""
        
        try:
            response = self.client.get(image_url)
            if response.status_code == 200:
                # Determinar extensión
                content_type = response.headers.get('content-type', '')
                ext = '.jpg'
                if 'png' in content_type:
                    ext = '.png'
                elif 'webp' in content_type:
                    ext = '.webp'
                
                filename = f"{product_id}{ext}"
                filepath = f"static/images/products/{filename}"
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                return f"/static/images/products/{filename}"
        except Exception as e:
            print(f"  Error descargando imagen {product_id}: {e}")
        
        return image_url  # Retornar URL original si falla


# Instancia global
odoo_scraper = OdooScraper()
