"""Scraper público del eCommerce, compatible con la estructura de Odoo 19."""

import os
import re
from typing import Optional
from urllib.parse import unquote, urljoin

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


# Estructura visible del menú del catálogo.
# "Plata / Rosarios" se retiró porque su URL actual devuelve HTTP 404.
CATEGORIES_STRUCTURE = {
    "parents": [
        {"id": 1, "name": "Baño de Oro", "slug": "bano-de-oro"},
        {"id": 2, "name": "Acero", "slug": "acero"},
        {"id": 3, "name": "Plata", "slug": "plata"},
    ],
    "children": {
        1: [
            {"id": 5, "name": "Pulseras", "slug": "bano-de-oro-pulseras-5"},
            {"id": 6, "name": "Aretes", "slug": "bano-de-oro-aretes-6"},
            {"id": 7, "name": "Anillos", "slug": "bano-de-oro-anillos-7"},
            {"id": 8, "name": "Cadenas", "slug": "bano-de-oro-cadenas-8"},
            {"id": 9, "name": "Cadenas con Dije", "slug": "bano-de-oro-cadenas-con-dije-9"},
            {"id": 10, "name": "Juegos", "slug": "bano-de-oro-juegos-10"},
            {"id": 11, "name": "Tobilleras", "slug": "bano-de-oro-tobilleras-11"},
        ],
        2: [
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
        3: [
            {"id": 22, "name": "Pulseras", "slug": "plata-pulseras-22"},
            {"id": 23, "name": "Anillos", "slug": "plata-anillos-23"},
            {"id": 24, "name": "Aretes", "slug": "plata-aretes-24"},
            {"id": 25, "name": "Cadenas", "slug": "plata-cadenas-25"},
            {"id": 26, "name": "Cadenas con Dijes", "slug": "plata-cadenas-con-dijes-26"},
            {"id": 27, "name": "Dijes", "slug": "plata-dijes-27"},
            {"id": 28, "name": "Juegos", "slug": "plata-juegos-28"},
            {"id": 29, "name": "Tobilleras", "slug": "plata-tobilleras-29"},
        ],
    },
}


class OdooScraper:
    def __init__(self):
        self.base_url = os.getenv(
            "ODOO_SHOP_URL",
            "https://italsteeldistribuidora.odoo.com",
        ).rstrip("/")
        self.shop_url = f"{self.base_url}/shop"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }
        self.client: Optional[httpx.Client] = None

    def connect(self) -> bool:
        try:
            self.close()
            self.client = httpx.Client(
                headers=self.headers,
                follow_redirects=True,
                timeout=30.0,
            )
            response = self.client.get(self.shop_url)
            if response.status_code == 200:
                print(f"✓ Conectado a {self.base_url}")
                return True
            print(f"✗ Error de conexión: HTTP {response.status_code}")
        except Exception as exc:
            print(f"✗ Error de conexión: {exc}")
        self.close()
        return False

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        if not self.client:
            return None
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
            print(f"  HTTP {response.status_code} obteniendo {url}")
        except Exception as exc:
            print(f"  Error obteniendo {url}: {exc}")
        return None

    def get_category_hierarchy(self) -> dict:
        hierarchy = {"parents": [], "children": {}, "all": {}}

        for parent in CATEGORIES_STRUCTURE["parents"]:
            parent_data = {
                "id": parent["id"],
                "name": parent["name"],
                "slug": parent["slug"],
                "url": f"{self.base_url}/shop/category/{parent['slug']}",
                "parent_id": None,
                "parent_name": None,
            }
            hierarchy["parents"].append(parent_data)
            hierarchy["all"][parent["id"]] = parent_data

        for parent_id, children in CATEGORIES_STRUCTURE["children"].items():
            hierarchy["children"][parent_id] = []
            parent_name = next(
                parent["name"]
                for parent in CATEGORIES_STRUCTURE["parents"]
                if parent["id"] == parent_id
            )
            for child in children:
                child_data = {
                    "id": child["id"],
                    "name": child["name"],
                    "slug": child["slug"],
                    "url": f"{self.base_url}/shop/category/{child['slug']}",
                    "parent_id": parent_id,
                    "parent_name": parent_name,
                }
                hierarchy["children"][parent_id].append(child_data)
                hierarchy["all"][child["id"]] = child_data

        return hierarchy

    @staticmethod
    def _next_page_url(soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Obtiene la siguiente página desde el paginador de Odoo 19."""
        active_item = soup.select_one(".pagination li.page-item.active")
        if active_item:
            next_item = active_item.find_next_sibling("li", class_="page-item")
            if next_item and "disabled" not in next_item.get("class", []):
                next_link = next_item.select_one("a.page-link[href]")
                if next_link:
                    return urljoin(current_url, next_link.get("href"))

        # Compatibilidad adicional con otras plantillas de Odoo.
        next_link = soup.select_one(
            '.pagination a[rel="next"], '
            '.pagination .next a[href], '
            'a.page-link[aria-label="Siguiente"][href]'
        )
        if next_link:
            return urljoin(current_url, next_link.get("href"))
        return None

    def get_products_from_page(self, url: str) -> tuple[list, Optional[str], int]:
        products = []
        soup = self._get_soup(url)
        if not soup:
            return products, None, 0

        # Odoo 19 ya no añade action="/shop/cart/update" a estas tarjetas.
        product_forms = soup.select(
            "form.oe_product_cart, "
            ".o_wsale_product_grid_wrapper form[role='article']"
        )

        seen_ids = set()
        for form in product_forms:
            try:
                product = self._parse_product_form(form)
                if product and product["id"] not in seen_ids:
                    seen_ids.add(product["id"])
                    products.append(product)
            except Exception as exc:
                print(f"  Error parseando producto: {exc}")

        return products, self._next_page_url(soup, url), len(products)

    @staticmethod
    def _parse_price(price_text: str) -> float:
        value = re.sub(r"[^\d,.-]", "", price_text or "")
        if "," in value and "." in value:
            # El último separador es el decimal.
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            value = value.replace(".", "").replace(",", ".")
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _parse_product_form(self, form) -> Optional[dict]:
        container = form
        link = container.select_one(
            '.oe_product_image_link[href*="/shop/"], '
            '.o_wsale_products_item_title a[href*="/shop/"], '
            'a[href*="/shop/"]'
        )
        if not link:
            return None

        href = link.get("href", "")
        match = re.search(r"-(\d+)(?:\?|$|#)", href)
        if not match:
            return None
        product_id = int(match.group(1))

        name_el = container.select_one(
            "h2.o_wsale_products_item_title, "
            ".o_wsale_product_information_text h2, "
            ".product_name, h5, h6, .card-title, [itemprop='name']"
        )
        if name_el:
            name = name_el.get_text(" ", strip=True)
        else:
            name = (
                form.get("aria-label", "").strip()
                or link.get("title", "").strip()
                or link.get_text(" ", strip=True)
            )
        name = re.sub(r"\s+", " ", name).strip() or "Sin nombre"

        price_el = container.select_one(".oe_currency_value")
        price = self._parse_price(price_el.get_text(strip=True) if price_el else "")

        image_url = ""
        img_el = container.select_one('img[src*="/web/image"]')
        if img_el:
            image_url = urljoin(self.base_url, img_el.get("src", ""))

        code = ""
        searchable_text = " ".join(
            [
                unquote(img_el.get("src", "")) if img_el else "",
                img_el.get("alt", "") if img_el else "",
                name,
                unquote(href),
            ]
        )
        code_match = re.search(
            r"(?:\[|/)([A-Z]{1,4}-[A-Z]{1,4}-\d+)(?:\]|-|/|\s)",
            searchable_text,
            re.IGNORECASE,
        )
        if code_match:
            code = code_match.group(1).upper()
            name = re.sub(
                rf"\s*\[{re.escape(code)}\]\s*",
                " ",
                name,
                flags=re.IGNORECASE,
            ).strip()

        qty_available = 0
        qty_el = container.select_one("[data-qty-available], .availability")
        if qty_el:
            qty_text = qty_el.get("data-qty-available") or qty_el.get_text(strip=True)
            qty_match = re.search(r"(\d+)", str(qty_text))
            if qty_match:
                qty_available = int(qty_match.group(1))

        return {
            "id": product_id,
            "name": name,
            "code": code,
            "price": price,
            "image_url": image_url,
            "product_url": urljoin(self.base_url, href),
            "qty_available": qty_available,
        }

    def get_all_products(self, category_url: Optional[str] = None) -> list:
        all_products = []
        seen_product_ids = set()
        visited_urls = set()
        url = category_url or self.shop_url
        page = 1

        while url and url not in visited_urls and page <= 100:
            visited_urls.add(url)
            print(f"    Página {page}...")
            products, next_url, _ = self.get_products_from_page(url)

            for product in products:
                if product["id"] not in seen_product_ids:
                    seen_product_ids.add(product["id"])
                    all_products.append(product)

            if not products:
                break
            url = next_url
            page += 1

        if page > 100:
            print("    ⚠ Límite de páginas alcanzado")
        return all_products

    def get_products_by_category(self, category_id: int, category_url: str) -> list:
        return self.get_all_products(category_url)

    def get_product_images(self, product_url: str, fallback_url: str = "") -> list[str]:
        images = []
        soup = self._get_soup(product_url)
        if soup:
            for img in soup.select('img.product_detail_img[src*="/web/image"]'):
                # La imagen de zoom tiene mayor resolución cuando está disponible.
                src = img.get("data-zoom-image") or img.get("src", "")
                if src:
                    image_url = urljoin(self.base_url, src)
                    if image_url not in images:
                        images.append(image_url)
        if not images and fallback_url:
            images.append(urljoin(self.base_url, fallback_url))
        return images

    def download_image(self, image_url: str, product_id: int, image_index: int = 0) -> str:
        if not image_url or not self.client:
            return ""
        try:
            response = self.client.get(image_url)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                ext = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
                suffix = "" if image_index == 0 else f"_{image_index}"
                filename = f"{product_id}{suffix}{ext}"
                filepath = f"static/images/products/{filename}"
                with open(filepath, "wb") as image_file:
                    image_file.write(response.content)
                return f"/static/images/products/{filename}"
        except Exception as exc:
            print(f"  Error descargando imagen {product_id}: {exc}")
        return image_url


odoo_scraper = OdooScraper()
