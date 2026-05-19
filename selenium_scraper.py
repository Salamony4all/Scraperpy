"""
Selenium-based Brand Scraper (Upgraded for Cloud/Railway Deployment)
Uses Headless Chrome to render SPAs, execute dynamic scrolling, and bypass anti-bot challenges.
"""

import os
import time
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# Expose availability flags and helpers to prevent import errors in orchestrators
SELENIUM_AVAILABLE = True

def scrape_with_fallback(*args, **kwargs):
    """Fallback helper, defined to prevent import errors in brand_scraper.py"""
    logger.warning("scrape_with_fallback called, but is a dummy function. Use SeleniumScraper directly.")
    return None

class SeleniumScraper:
    """
    Heavy-duty scraper for JavaScript-rendered websites (React, Vue, SPAs).
    Optimized for low-memory cloud environments.
    """
    
    def __init__(self, headless: bool = True, timeout: int = 20, *args, **kwargs):
        self.timeout = timeout
        self.headless = headless
        
    def _get_lean_driver(self) -> webdriver.Chrome:
        """
        Configures and returns a highly optimized, headless Chrome WebDriver.
        CRITICAL: These flags are mandatory for running in Linux/Railway containers.
        """
        options = Options()
        
        # Cloud-Native & Stealth Flags
        options.add_argument("--headless=new")  # Modern headless mode
        options.add_argument("--no-sandbox")    # Mandatory for Linux containers
        options.add_argument("--disable-dev-shm-usage") # Prevents /dev/shm memory crashes
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled") # Anti-bot evasion
        options.add_argument("--js-flags=--max-old-space-size=512") # Cap V8 Engine RAM
        
        # Spoofer
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # RAM Saver: Block Images, Fonts, and Media
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.fonts": 2,
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        # Suppress DevTools logging
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        try:
            # First try: Use ChromeDriverManager to download/manage the driver
            logger.info("Initializing WebDriver using ChromeDriverManager...")
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)
        except Exception as e:
            logger.warning(f"ChromeDriverManager initialization failed: {e}. Trying system Chromium/ChromeDriver fallback...")
            
            # Second try: Check common system Chromium paths for Linux/Railway containers
            for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/lib/chromium/chromium"]:
                if os.path.exists(path):
                    logger.info(f"Setting Chrome binary location to system Chromium path: {path}")
                    options.binary_location = path
                    break
                    
            try:
                # Direct initialization relies on chromedriver being present in the PATH (standard for nix/apt packages)
                return webdriver.Chrome(options=options)
            except Exception as direct_e:
                logger.error(f"Direct system Chrome initialization failed: {direct_e}")
                raise direct_e

    def scrape_brand_website(self, website: str, brand_name: str) -> Dict:
        """
        Main orchestration method to scrape a brand website using Selenium.
        """
        logger.info(f"🚀 Starting Open-Source Selenium scrape for {brand_name} at {website}")
        
        result = {
            'brand': brand_name,
            'source': 'Brand Website (Selenium Engine)',
            'scraped_at': datetime.now().isoformat(),
            'total_products': 0,
            'total_collections': 0,
            'collections': {},
            'all_products': []
        }
        
        driver = None
        try:
            driver = self._get_lean_driver()
            driver.set_page_load_timeout(30)
            
            logger.info(f"Navigating to {website}...")
            driver.get(website)
            
            # Dismiss generic cookie banners
            self._dismiss_popups(driver)
            
            # Execute infinite scroll to force lazy-loaded items into the DOM
            self._scroll_to_bottom(driver)
            
            # Extract the fully rendered DOM
            html_source = driver.page_source
            soup = BeautifulSoup(html_source, 'html.parser')
            
            logger.info("DOM extracted. Parsing products...")
            products = self._extract_products(soup, website, brand_name)
            
            # Structure the data
            for prod in products:
                cat = prod.get('category', 'Products')
                sub = prod.get('subcategory', 'General')
                coll_key = f"{cat} > {sub}"
                
                if coll_key not in result['collections']:
                    result['collections'][coll_key] = {
                        'url': website,
                        'category': cat,
                        'subcategory': sub,
                        'product_count': 0,
                        'products': []
                    }
                
                result['collections'][coll_key]['products'].append(prod)
                result['all_products'].append(prod)
                
            # Finalize counts
            for key in result['collections']:
                result['collections'][key]['product_count'] = len(result['collections'][key]['products'])
            
            result['total_products'] = len(result['all_products'])
            result['total_collections'] = len(result['collections'])
            
            logger.info(f"✅ Extracted {result['total_products']} products across {result['total_collections']} collections.")
            return result

        except Exception as e:
            logger.error(f"❌ Critical Selenium Error on {website}: {str(e)}")
            return result
            
        finally:
            if driver:
                logger.info("Sweeping up: Closing WebDriver instance.")
                driver.quit()

    def _scroll_to_bottom(self, driver: webdriver.Chrome):
        """
        Executes a staggered scroll to trigger lazy-loading and AJAX pagination.
        """
        logger.info("Executing deep scroll...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        stable_cycles = 0
        
        for i in range(25): # Cap iterations to prevent infinite traps
            # Scroll down
            driver.execute_script("window.scrollBy(0, 1500);")
            time.sleep(1.2) # Wait for network requests
            
            # Attempt to click "Load More" buttons
            try:
                load_more_buttons = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]")
                for btn in load_more_buttons:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1.5)
            except:
                pass

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                stable_cycles += 1
                if stable_cycles >= 3:
                    break
            else:
                stable_cycles = 0
                last_height = new_height

    def _dismiss_popups(self, driver: webdriver.Chrome):
        """
        Attempts to clear cookie banners and newsletters that block interactions.
        """
        try:
            keywords = ["accept", "agree", "close", "got it", "allow"]
            xpath_query = " | ".join([f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{k}')]" for k in keywords])
            
            buttons = driver.find_elements(By.XPATH, xpath_query)
            for btn in buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
                    break # Usually only one main cookie banner
        except:
            pass

    def _extract_products(self, soup: BeautifulSoup, base_url: str, brand_name: str) -> List[Dict]:
        """
        Parses the fully rendered DOM to extract product nodes.
        Uses universal selector logic similar to your JS architecture.
        """
        products = []
        seen = set()
        
        # Universal product container selectors
        selectors = [
            '.product', '.product-item', '.product-card', '.grid-item', 
            'article', '[data-product]', '.collection-item'
        ]
        
        candidates = []
        for sel in selectors:
            found = soup.select(sel)
            if len(found) > len(candidates):
                candidates = found
                
        # Fallback: if no clear containers, just look for anchor tags with images
        if len(candidates) < 3:
            candidates = [a.parent for a in soup.find_all('a') if a.find('img')]

        for el in candidates:
            # 1. Get Title
            title_el = el.find(['h2', 'h3', 'h4', 'div', 'span'], class_=re.compile(r'title|name|heading', re.I))
            title = title_el.get_text(strip=True) if title_el else ""
            
            if not title:
                # Fallback to link text
                a_tag = el.find('a')
                title = a_tag.get_text(strip=True) if a_tag else ""
                
            title = re.sub(rf'\b{re.escape(brand_name)}\b', '', title, flags=re.IGNORECASE).strip()
            
            if not title or len(title) < 3 or title.lower() in seen:
                continue
                
            # 2. Get Link
            link_el = el.find('a', href=True)
            if not link_el:
                continue
                
            product_url = urljoin(base_url, link_el['href'])
            
            # Skip utility links
            if any(x in product_url.lower() for x in ['/cart', '/wishlist', '/login', '/category/']):
                continue

            # 3. Get Image
            img_el = el.find('img')
            image_url = ""
            if img_el:
                # Check standard and lazy-loaded attributes
                image_url = img_el.get('data-src') or img_el.get('data-lazy-src') or img_el.get('src') or ""
                if image_url:
                    image_url = urljoin(base_url, image_url)
                    
            if not image_url or 'placeholder' in image_url.lower():
                continue

            seen.add(title.lower())
            products.append({
                'name': title,
                'model': title,
                'description': title,
                'image_url': image_url,
                'source_url': product_url,
                'brand': brand_name,
                'price': None,
                'category': 'Products',
                'subcategory': 'General'
            })
            
        return products