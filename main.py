import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from pathlib import Path

from sync_service import sync_catalog, load_catalog

load_dotenv()

SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_HOURS", 6))
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando Catálogo Espejo...")
    
    Path("static/images/products").mkdir(parents=True, exist_ok=True)
    Path("static/css").mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    
    catalog = load_catalog()
    if not catalog.get("last_sync") or catalog.get("stats", {}).get("total_products", 0) == 0:
        print("📦 Primera ejecución - sincronizando catálogo...")
        sync_catalog()
    
    scheduler.add_job(
        sync_catalog,
        trigger=IntervalTrigger(hours=SYNC_INTERVAL),
        id="sync_catalog",
        replace_existing=True
    )
    scheduler.start()
    print(f"⏰ Sincronización programada cada {SYNC_INTERVAL} horas")
    
    yield
    
    scheduler.shutdown()


app = FastAPI(title="Catálogo Espejo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    catalog = load_catalog()
    # Mostrar últimos 24 productos en home
    return templates.TemplateResponse("index.html", {
        "request": request,
        "categories": catalog.get("categories", {}),
        "products": catalog.get("products", [])[:24],
        "stats": catalog.get("stats", {}),
        "last_sync": catalog.get("last_sync")
    })


@app.get("/categoria/{category_id}", response_class=HTMLResponse)
async def category_view(request: Request, category_id: int, sub: int = None):
    catalog = load_catalog()
    
    category = catalog.get("categories", {}).get("all", {}).get(str(category_id))
    if not category:
        category = catalog.get("categories", {}).get("all", {}).get(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    
    active_category_id = sub if sub else category_id
    
    products_by_cat = catalog.get("products_by_category", {})
    products = products_by_cat.get(str(active_category_id), [])
    if not products:
        products = products_by_cat.get(active_category_id, [])
    
    children = catalog.get("categories", {}).get("children", {})
    subcategories = children.get(str(category_id), [])
    if not subcategories:
        subcategories = children.get(category_id, [])
    
    active_sub = None
    if sub:
        active_sub = catalog.get("categories", {}).get("all", {}).get(str(sub))
        if not active_sub:
            active_sub = catalog.get("categories", {}).get("all", {}).get(sub)
    
    return templates.TemplateResponse("category.html", {
        "request": request,
        "category": category,
        "subcategories": subcategories,
        "active_sub": active_sub,
        "products": products,
        "categories": catalog.get("categories", {}),
        "total_products": len(products)
    })


@app.get("/todos", response_class=HTMLResponse)
async def all_products(request: Request):
    catalog = load_catalog()
    return templates.TemplateResponse("all_products.html", {
        "request": request,
        "products": catalog.get("products", []),
        "categories": catalog.get("categories", {}),
        "total_products": len(catalog.get("products", []))
    })


@app.get("/buscar", response_class=HTMLResponse)
async def search(request: Request, q: str = ""):
    catalog = load_catalog()
    results = []
    if q:
        q_lower = q.lower()
        for product in catalog.get("products", []):
            if (q_lower in product.get("name", "").lower() or 
                q_lower in product.get("code", "").lower()):
                results.append(product)
    
    return templates.TemplateResponse("search.html", {
        "request": request,
        "query": q,
        "products": results,
        "categories": catalog.get("categories", {}),
        "total_products": len(results)
    })


@app.post("/api/sync")
async def manual_sync():
    success = sync_catalog()
    return {"success": success, "message": "Sincronización completada" if success else "Error"}


@app.get("/api/stats")
async def get_stats():
    catalog = load_catalog()
    return {"last_sync": catalog.get("last_sync"), "stats": catalog.get("stats", {})}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
