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
        
        products_list = result.get("all_products", result.get("products", []))
        logo_url = result.get("logo", "")
        
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