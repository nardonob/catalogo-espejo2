# Catálogo Espejo

Catálogo público que sincroniza automáticamente con tu eCommerce de Odoo mediante **web scraping** (funciona con plan Standard sin API).

## ⚠️ Importante

Este proyecto usa **web scraping** porque el plan Standard de Odoo **no permite acceso a la API externa (XML-RPC)**. El scraping extrae datos públicos de tu tienda.

## Configuración

### Variables de entorno en Railway:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `ODOO_SHOP_URL` | URL base de tu tienda Odoo (sin /shop) | `https://tutienda.odoo.com` |
| `SYNC_INTERVAL_HOURS` | Intervalo de sincronización | `6` |
| `PORT` | Puerto (Railway lo asigna) | `8000` |

### Deploy en Railway:

1. Sube el código a GitHub
2. Crea nuevo proyecto en Railway desde GitHub
3. Agrega las variables de entorno
4. Railway desplegará automáticamente

## Endpoints

| Ruta | Descripción |
|------|-------------|
| `/` | Página principal con categorías |
| `/todos` | Todos los productos |
| `/categoria/{id}` | Productos de una categoría |
| `/categoria/{id}?sub={sub_id}` | Productos de subcategoría |
| `/buscar?q=término` | Búsqueda de productos |
| `POST /api/sync` | Sincronización manual |
| `GET /api/stats` | Estadísticas del catálogo |
| `GET /health` | Health check |

## Estructura

```
catalogo-espejo/
├── main.py              # Aplicación FastAPI
├── odoo_scraper.py      # Scraper para Odoo eCommerce
├── sync_service.py      # Servicio de sincronización
├── templates/           # Templates HTML (Jinja2)
├── static/
│   ├── css/styles.css   # Estilos
│   └── images/products/ # Imágenes descargadas
├── data/
│   └── catalog.json     # Datos del catálogo
├── Dockerfile
├── requirements.txt
└── railway.json
```

## Sincronización

- **Automática:** Cada 6 horas (configurable)
- **Manual:** `POST /api/sync`
- **Primera ejecución:** Se sincroniza automáticamente al iniciar

## Notas sobre el scraping

- El scraper simula un navegador real con headers apropiados
- Respeta tiempos de espera entre requests para no sobrecargar el servidor
- Las imágenes se descargan localmente para no depender del servidor de Odoo
- Si Odoo cambia la estructura HTML, puede ser necesario ajustar los selectores en `odoo_scraper.py`
