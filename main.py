from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
# Import your existing orchestrator and selenium scraper
from brand_scraper import ScrapingOrchestrator
from selenium_scraper import SeleniumScraper

app = FastAPI(title="Open Source Python Scraper")
orchestrator = ScrapingOrchestrator()
selenium_engine = SeleniumScraper()

class ScrapeRequest(BaseModel):
    url: str
    brand_name: str

@app.post("/api/scrape")
async def scrape_brand(request: ScrapeRequest):
    try:
        # You can use your orchestrator, or force it directly to Selenium
        # If your orchestrator was previously relying on Firecrawl as the fallback, 
        # make sure to update it to use selenium_engine instead!
        
        print(f"🚀 Launching Open-Source Extraction for {request.url}")
        result = orchestrator.scrape_brand(request.url, request.brand_name)
        
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "online"}