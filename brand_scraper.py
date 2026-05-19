"""
Scraping Orchestrator (Microservice Router)
Delegates web scraping tasks to specialized modules based on the requested strategy.
"""

import logging
from typing import Dict, Any, Optional

# Set up logging for Railway
logger = logging.getLogger(__name__)

class ScrapingOrchestrator:
    """
    The main routing engine for the Python Microservice.
    """
    def __init__(self):
        # Lazy load scrapers to avoid unnecessary import or driver initialization issues
        self._universal_scraper = None
        self._italian_scraper = None
        self._architonic_scraper = None
        self._selenium_scraper = None
        self._requests_scraper = None

    def scrape_brand(self, url: str, brand_name: str, strategy: Optional[str] = "universal") -> Dict[str, Any]:
        strategy = (strategy or "universal").lower().strip()
        logger.info(f"Orchestrator routing scrape request for brand '{brand_name}' using strategy '{strategy}' to: {url}")
        
        try:
            # --- 1. UNIVERSAL STRATEGY ---
            if strategy == "universal":
                from universal_brand_scraper import UniversalBrandScraper
                if not self._universal_scraper:
                    self._universal_scraper = UniversalBrandScraper()
                return self._universal_scraper.scrape_brand_website(url, brand_name)
                
            # --- 2. ITALIAN STRATEGY ---
            elif strategy == "italian":
                from italian_furniture_scraper import ItalianFurnitureScraper
                if not self._italian_scraper:
                    self._italian_scraper = ItalianFurnitureScraper()
                return self._italian_scraper.scrape_brand_website(url, brand_name)
                
            # --- 3. ARCHITONIC STRATEGY ---
            elif strategy == "architonic":
                from architonic_scraper import ArchitonicScraper
                if not self._architonic_scraper:
                    self._architonic_scraper = ArchitonicScraper(use_selenium=True)
                # FIXED METHOD NAME & INDENTATION:
                return self._architonic_scraper.scrape_collection(url, brand_name)
                
            # --- 4. PURE SELENIUM STRATEGY ---
            elif strategy == "selenium":
                from selenium_scraper import SeleniumScraper
                if not self._selenium_scraper:
                    self._selenium_scraper = SeleniumScraper()
                return self._selenium_scraper.scrape_brand_website(url, brand_name)
                
            # --- 5. PURE REQUESTS STRATEGY ---
            elif strategy == "requests":
                from requests_brand_scraper import RequestsBrandScraper
                if not self._requests_scraper:
                    self._requests_scraper = RequestsBrandScraper()
                return self._requests_scraper.scrape_brand_website(url, brand_name)
                
            # --- 6. FIRECRAWL STRATEGY ---
            elif strategy == "firecrawl":
                from universal_brand_scraper import UniversalBrandScraper
                logger.info("Firecrawl strategy selected - using UniversalBrandScraper with Selenium force-enabled")
                if not self._universal_scraper:
                    self._universal_scraper = UniversalBrandScraper()
                return self._universal_scraper.scrape_brand_website(url, brand_name, use_selenium=True)
                
            # --- FALLBACK ---
            else:
                logger.warning(f"Unknown scraping strategy: '{strategy}'. Falling back to universal scraper.")
                from universal_brand_scraper import UniversalBrandScraper
                if not self._universal_scraper:
                    self._universal_scraper = UniversalBrandScraper()
                return self._universal_scraper.scrape_brand_website(url, brand_name)
                
        except Exception as e:
            logger.exception(f"Error in ScrapingOrchestrator executing strategy '{strategy}': {e}")
            raise e