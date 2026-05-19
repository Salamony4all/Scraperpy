import logging
import os
import shutil
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# Import your existing orchestrator
from brand_scraper import ScrapingOrchestrator

# Set up basic logging so you can see what's happening in the Railway logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BOQ-FLOW Python Scraper API")
orchestrator = ScrapingOrchestrator()

# Define the expected JSON payload from your Node.js app
class ScrapeRequest(BaseModel):
    url: str
    brand_name: str
    strategy: Optional[str] = "universal" # Defaults to 'universal' if not provided
    js_scraper_url: Optional[str] = None

@app.post("/api/scrape")
async def scrape_brand(request: ScrapeRequest):
    """
    Main scraping endpoint. Receives the URL, brand name, and strategy,
    then delegates to the orchestrator.
    """
    logger.info(f"🚀 Received {request.strategy.upper()} scraping request for {request.brand_name} ({request.url})")
    
    try:
        # Pass the strategy to your orchestrator so it knows which Python script to trigger
        result = orchestrator.scrape_brand(
            url=request.url, 
            brand_name=request.brand_name, 
            strategy=request.strategy
        )
        
        logger.info(f"✅ Scraping completed for {request.brand_name}")
        
        raw_products = result.get("all_products", result.get("products", []))
        products_list = []
        for p in raw_products:
            # Standardize categories, hierarchy, and basic attributes
            main_cat = p.get('mainCategory') or p.get('category') or p.get('main_category') or 'Furniture'
            sub_cat = p.get('subCategory') or p.get('subcategory') or p.get('sub_category') or 'Featured'
            family = p.get('family') or p.get('collection') or p.get('brand') or request.brand_name
            model = p.get('model') or p.get('title') or p.get('modelName') or 'Unknown Product'
            description = p.get('description') or ''
            image_url = p.get('imageUrl') or p.get('image_url') or p.get('image') or ''
            product_url = p.get('productUrl') or p.get('product_url') or p.get('source_url') or p.get('url') or ''
            
            price = p.get('price')
            if price is None:
                price = 0
            else:
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    price = 0
            
            # Map/build normalization structure so frontend dropdowns map properly
            raw_norm = p.get('normalization')
            if isinstance(raw_norm, dict):
                norm = {
                    'category': raw_norm.get('category') or main_cat,
                    'subCategory': raw_norm.get('subCategory') or raw_norm.get('sub_category') or sub_cat,
                    'rank': raw_norm.get('rank') or 1,
                    'tags': raw_norm.get('tags') or [],
                    'dimensions': raw_norm.get('dimensions') or None
                }
            else:
                norm = {
                    'category': main_cat,
                    'subCategory': sub_cat,
                    'rank': 1,
                    'tags': [],
                    'dimensions': None
                }
            
            products_list.append({
                "mainCategory": main_cat,
                "subCategory": sub_cat,
                "family": family,
                "model": model,
                "description": description,
                "imageUrl": image_url,
                "productUrl": product_url,
                "price": price,
                "normalization": norm
            })
        logo_url = result.get("logo", "")
        
        # Determine the JS Scraper URL (either from request payload or environment)
        js_scraper_url = request.js_scraper_url or os.environ.get("JS_SCRAPER_SERVICE_URL")
        
        if js_scraper_url:
            try:
                import requests as py_requests
                import json
                from datetime import datetime
                
                # Trim trailing slash if present
                js_scraper_url = js_scraper_url.rstrip("/")
                upload_url = f"{js_scraper_url}/brands/upload"
                
                sanitized_name = request.brand_name.lower().replace(" ", "_")
                filename = f"{sanitized_name}-mid.json"
                
                final_brand = {
                    "id": request.brand_name.lower().replace(" ", "-"),
                    "name": request.brand_name,
                    "website": request.url,
                    "origin": "Railway-Python-Scraper",
                    "budgetTier": "mid",
                    "products": products_list,
                    "brandInfo": {
                        "name": request.brand_name,
                        "logo": logo_url
                    },
                    "logo": logo_url,
                    "lastScraped": datetime.utcnow().isoformat() + "Z"
                }
                
                logger.info(f"☁️ [Auto-Upload] Sending finished scrape for '{request.brand_name}' directly to Railway volume storage via {upload_url}...")
                headers = {
                    "Content-Type": "text/plain",
                    "X-Filename": filename
                }
                
                response_upload = py_requests.post(
                    upload_url,
                    data=json.dumps(final_brand, indent=2),
                    headers=headers,
                    timeout=30
                )
                
                if response_upload.status_code == 200:
                    logger.info(f"✅ [Auto-Upload Success] Brand '{request.brand_name}' successfully persisted on Railway volume backup!")
                else:
                    logger.warning(f"⚠️ [Auto-Upload Warning] JS Scraper service returned status {response_upload.status_code}: {response_upload.text}")
            except Exception as upload_err:
                logger.error(f"❌ [Auto-Upload Failed] Error replicating brand data to Railway volume: {str(upload_err)}")
        else:
            logger.info("ℹ️ No JS_SCRAPER_SERVICE_URL configured or passed. Skipping automatic volume replication.")
            
        return {
            "status": "success", 
            "products": products_list,
            "brandInfo": {
                "name": request.brand_name,
                "logo": logo_url
            },
            "data": result
        }
        
    except Exception as e:
        logger.error(f"❌ Scraping failed for {request.brand_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

@app.get("/health")
async def health_check():
    """
    Enhanced health check: reports Selenium/Chrome availability.
    Lets you diagnose Railway deployment issues from the outside.
    """
    # Check Selenium Python package availability
    try:
        from selenium_scraper import SELENIUM_AVAILABLE
        selenium_ok = SELENIUM_AVAILABLE
    except Exception:
        selenium_ok = False

    # Check if Chromium binary is discoverable (same logic as selenium_scraper)
    chrome_binary = None
    # 1. Env vars
    for env_key in ("CHROME_BIN", "CHROMIUM_BIN"):
        val = os.environ.get(env_key)
        if val and os.path.exists(val):
            chrome_binary = val
            break
    # 2. shutil.which (finds Nix binaries on PATH)
    if not chrome_binary:
        for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            found = shutil.which(name)
            if found:
                chrome_binary = found
                break

    # Check chromedriver on PATH
    chromedriver_path = shutil.which("chromedriver")

    return {
        "status": "online",
        "message": "Scraper API is running",
        "selenium_packages_installed": selenium_ok,
        "chrome_binary": chrome_binary or "NOT FOUND",
        "chromedriver": chromedriver_path or "NOT FOUND",
        "path_env": os.environ.get("PATH", "N/A")[:500],
        "strategies_available": ["universal", "architonic", "italian", "requests", "selenium", "firecrawl"]
    }