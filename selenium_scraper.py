"""
Selenium-based Brand Scraper & Browser Wrapper (Upgraded for Cloud Deployment)
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
    """Fallback helper, defined to prevent import errors in older files"""
    logger.warning("scrape_with_fallback called, but is a dummy function. Use SeleniumScraper directly.")
    return None

class SeleniumScraper:
    """
    Heavy-duty scraper for JavaScript-rendered websites (React, Vue, SPAs).
    Optimized for low-memory cloud environments (Railway/Linux).
    Also serves as a utility wrapper for other specialized scrapers.
    """
    
    def __init__(self, headless: bool = True, timeout: int = 30, *args, **kwargs):
        self.headless = headless
        self.timeout = timeout
        self.driver = self._get_lean_driver()
        
    def _get_lean_driver(self) -> webdriver.Chrome:
        """
        Configures and returns a highly optimized, headless Chrome WebDriver.
        CRITICAL: These flags are mandatory for running in Linux/Railway containers.
        """
        options = Options()
        
        # Cloud-Native & Stealth Flags
        if self.headless:
            options.add_argument("--headless=new")
            
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
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(self.timeout)
        return driver

    # ==========================================
    # BROWSER UTILITY WRAPPERS (FOR OTHER FILES)
    # ==========================================

    def get_page(self, url: str, wait_for_selector: str = None, wait_time: int = 15) -> Optional[BeautifulSoup]:
        """Navigates to a URL and returns the parsed BeautifulSoup DOM."""
        try:
            self.driver.get(url)
            if wait_for_selector:
                try:
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                    )
                except TimeoutException:
                    logger.warning(f"Timeout waiting for selector '{wait_for_selector}' on {url}")
            else:
                time.sleep(3) # Give JS a moment to execute
                
            return BeautifulSoup(self.driver.page_source, 'html.parser')
        except Exception as e:
            logger.error(f"Error loading page {url}: {e}")
            return None

    def scroll_to_bottom(self, pause_time: float = 2.0, max_scrolls: int = 25):
        """Executes a staggered scroll to trigger lazy-loading and AJAX pagination."""
        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            stable_cycles = 0
            
            for _ in range(max_scrolls):
                self.driver.execute_script("window.scrollBy(0, 1500);")
                time.sleep(pause_time)
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    stable_cycles += 1
                    if stable_cycles >= 2:
                        break
                else:
                    stable_cycles = 0
                    last_height = new_height
        except Exception as e:
            logger.debug(f"Scroll interrupted: {e}")

    def find_elements(self, by, value):
        """Wrapper for finding elements"""
        return self.driver.find_elements(by, value)

    def click_element(self, by, value) -> bool:
        """Helper to find and click an element safely"""
        try:
            elements = self.find_elements(by, value)
            if elements and elements[0].is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView(true);", elements[0])
                time.sleep(0.5)
                elements[0].click()
                return True
            return False
        except Exception as e:
            logger.debug(f"Error clicking element {value}: {e}")
            return False

    def close(self):
        """Safely shuts down the browser to prevent zombie processes."""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                logger.info("Closed WebDriver successfully.")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")

    def __del__(self):
        """Ensures the driver quits when the object is destroyed."""
        self.close()

    # ==========================================
    # STANDALONE SCRAPING (FOR ORCHESTRATOR)
    # ==========================================

    def scrape_brand_website(self, website: str, brand_name: str) -> Dict:
        """
        Main orchestration method to scrape a brand website directly using Selenium.
        """
        logger.info(f"🚀 Starting Standalone Selenium scrape for {brand_name} at {website}")
        
        result = {
            'brand': brand_name,
            'source': 'Brand Website (Selenium Engine)',
            'scraped_at': datetime.now().isoformat(),
            'total_products': 0,
            'total_collections': 0,
            'collections': {},
            'all_products': []
        }
        
        try:
            soup = self.get_page(website, wait_time=20)
            if not soup:
                return result

            # Dismiss generic cookie banners
            self._dismiss_popups()
            
            # Execute infinite scroll to force lazy-loaded items into the DOM
            self.scroll_to_bottom(pause_time=1.5, max_scrolls=15)
            
            # Update soup after scrolling
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
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

    def _dismiss_popups(self):
        """Attempts to clear cookie banners and newsletters that block interactions."""
        try:
            keywords = ["accept", "agree", "close", "got it", "allow"]
            xpath_query = " | ".join([f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{k}')]" for k in keywords])
            
            buttons = self.driver.find_elements(By.XPATH, xpath_query)
            for btn in buttons:
                if btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
                    break 
        except:
            pass

    def _extract_products(self, soup: BeautifulSoup, base_url: str, brand_name: str) -> List[Dict]:
        """Parses the fully rendered DOM to extract product nodes."""
        products = []
        seen = set()
        
        selectors = [
            '.product', '.product-item', '.product-card', '.grid-item', 
            'article', '[data-product]', '.collection-item'
        ]
        
        candidates = []
        for sel in selectors:
            found = soup.select(sel)
            if len(found) > len(candidates):
                candidates = found
                
        if len(candidates) < 3:
            candidates = [a.parent for a in soup.find_all('a') if a.find('img')]

        for el in candidates:
            title_el = el.find(['h2', 'h3', 'h4', 'div', 'span'], class_=re.compile(r'title|name|heading', re.I))
            title = title_el.get_text(strip=True) if title_el else ""
            
            if not title:
                a_tag = el.find('a')
                title = a_tag.get_text(strip=True) if a_tag else ""
                
            title = re.sub(rf'\b{re.escape(brand_name)}\b', '', title, flags=re.IGNORECASE).strip()
            
            if not title or len(title) < 3 or title.lower() in seen:
                continue
                
            link_el = el.find('a', href=True)
            if not link_el:
                continue
                
            product_url = urljoin(base_url, link_el['href'])
            
            if any(x in product_url.lower() for x in ['/cart', '/wishlist', '/login', '/category/']):
                continue

            img_el = el.find('img')
            image_url = ""
            if img_el:
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