import unittest
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

from odoo_scraper import OdooScraper


PROJECT_DIR = Path(__file__).resolve().parents[1]


class ProductImagesTest(unittest.TestCase):
    def test_extracts_large_carousel_images_without_thumbnails(self):
        scraper = OdooScraper()
        scraper._get_soup = lambda _: BeautifulSoup(
            """
            <div class="o-carousel-product">
                <img class="product_detail_img" src="/web/image/product.product/10/image_1024/main.jpg">
                <img class="product_detail_img" src="/web/image/product.image/20/image_1024/second.jpg">
                <img class="o_image_64_cover" src="/web/image/product.image/20/image_128/second.jpg">
            </div>
            """,
            "html.parser",
        )

        images = scraper.get_product_images("https://example.test/shop/product-1")

        self.assertEqual(
            images,
            [
                f"{scraper.base_url}/web/image/product.product/10/image_1024/main.jpg",
                f"{scraper.base_url}/web/image/product.image/20/image_1024/second.jpg",
            ],
        )

    def test_uses_listing_image_when_product_page_has_no_carousel(self):
        scraper = OdooScraper()
        scraper._get_soup = lambda _: BeautifulSoup("<html></html>", "html.parser")

        images = scraper.get_product_images(
            "https://example.test/shop/product-1",
            "/web/image/product.template/1/image_512/main.jpg",
        )

        self.assertEqual(
            images,
            [f"{scraper.base_url}/web/image/product.template/1/image_512/main.jpg"],
        )


class TemplateCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = Environment(
            loader=FileSystemLoader(PROJECT_DIR / "templates"),
            autoescape=select_autoescape(["html"]),
        )

    def render_index(self, product):
        return self.environment.get_template("index.html").render(
            categories={"parents": [], "children": {}},
            products=[product],
            stats={},
            last_sync=None,
        )

    def test_old_catalog_entries_keep_their_primary_image(self):
        html = self.render_index(
            {
                "id": 1,
                "name": "Producto anterior",
                "code": "P-AR-1",
                "image_url": "/static/images/products/1.jpg",
            }
        )

        self.assertIn("/static/images/products/1.jpg", html)

    def test_multiple_images_and_apostrophes_are_serialized_safely(self):
        product = {
            "id": 2,
            "name": "Arete d'Oro",
            "code": "G-AR-2",
            "image_url": "/static/images/products/2.jpg",
            "images": [
                "/static/images/products/2.jpg",
                "/static/images/products/2_1.jpg",
            ],
        }
        base_context = {
            "categories": {"parents": [], "children": {}, "all": {}},
            "products": [product],
        }
        cases = {
            "index.html": {**base_context, "stats": {}, "last_sync": None},
            "all_products.html": {**base_context, "total_products": 1},
            "category.html": {
                **base_context,
                "category": {"id": 1, "name": "Prueba"},
                "subcategories": [],
                "active_sub": None,
                "total_products": 1,
            },
            "search.html": {**base_context, "query": "arete", "total_products": 1},
        }

        for template_name, context in cases.items():
            with self.subTest(template=template_name):
                html = self.environment.get_template(template_name).render(**context)
                self.assertIn("/static/images/products/2_1.jpg", html)
                self.assertIn("Arete d\\u0027Oro", html)
                self.assertIn("styles.css?v=20260919-menu-touch-fix", html)
                self.assertIn("header-scroll.js?v=20260919-menu-touch-fix", html)
                self.assertIn("handleModalPointerDown", html)
                self.assertIn("handleModalPointerUp", html)

    def test_mobile_carousel_styles_are_present(self):
        css = (PROJECT_DIR / "static" / "css" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("touch-action: pan-y", css)

    def test_header_hides_and_reappears_according_to_scroll_direction(self):
        css = (PROJECT_DIR / "static" / "css" / "styles.css").read_text(encoding="utf-8")
        javascript = (PROJECT_DIR / "static" / "js" / "header-scroll.js").read_text(encoding="utf-8")

        self.assertIn("header.header-hidden", css)
        self.assertIn("translateY(-100%)", css)
        self.assertIn("movement > 0", javascript)
        self.assertIn("header.classList.add('header-hidden')", javascript)
        self.assertIn("header.classList.remove('header-hidden')", javascript)
        self.assertIn("{ passive: true }", javascript)
        self.assertIn("ignoreScrollUntil", javascript)
        self.assertIn("header.addEventListener('pointerdown'", javascript)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn(".modal-nav", css)


if __name__ == "__main__":
    unittest.main()
