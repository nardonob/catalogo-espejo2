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
