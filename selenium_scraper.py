"""
Selenium-based Browser Wrapper (Upgraded for Cloud/Railway Deployment)
Uses Headless Chrome to render SPAs, execute dynamic scrolling, and bypass anti-bot challenges.

This module is the SINGLE CHOKEPOINT for all browser-based scraping.
Every specialized scraper (Architonic, Italian, Universal) goes through this file.
"""

import os
import shutil
import time
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level availability flag & fallback helper
# These MUST be importable by other modules without triggering Chrome launch.
# ---------------------------------------------------------------------------
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium packages not installed — SELENIUM_AVAILABLE = False")


def scrape_with_fallback(*args, **kwargs):
    """Legacy helper stub — kept so old import lines don't crash."""
    logger.warning("scrape_with_fallback() is a no-op stub. Use SeleniumScraper directly.")
    return None


class SeleniumScraper:
    """
    Heavy-duty scraper for JavaScript-rendered websites (React, Vue, SPAs).
    Optimized for low-memory cloud environments (Railway / Linux containers).

    Also serves as a utility wrapper for other specialized scrapers
    via get_page(), scroll_to_bottom(), click_element(), close().

    IMPORTANT: The Chrome driver is created LAZILY — only when first needed.
    This prevents import-time crashes when Chrome isn't installed yet.
    """

    def __init__(self, headless: bool = True, timeout: int = 30, **kwargs):
        self.headless = headless
        self.timeout = timeout
        self.driver = None  # LAZY — created on first use

    # ------------------------------------------------------------------
    # LAZY DRIVER MANAGEMENT
    # ------------------------------------------------------------------

    def _ensure_driver(self):
        """Create the Chrome driver if it doesn't exist yet."""
        if self.driver is None:
            self.driver = self._get_lean_driver()
        return self.driver

    def _get_lean_driver(self) -> 'webdriver.Chrome':
        """
        Configures and returns a highly optimized, headless Chrome WebDriver.

        Fallback priority (Railway/Nix compatible):
          1. System-installed chromium + chromedriver (found via PATH / shutil.which)
          2. ChromeDriverManager auto-download (only if system binaries absent)
          3. Bare webdriver.Chrome() as last resort

        Status code 127 means the binary's shared-library deps are missing.
        That's why we MUST prefer the Nix-installed binaries (they carry their
        own deps in the Nix store) over independently-downloaded ones.
        """
        options = Options()

        # Cloud-Native & Stealth Flags
        if self.headless:
            options.add_argument("--headless=new")  # Modern headless mode

        options.add_argument("--no-sandbox")               # Mandatory for Linux containers
        options.add_argument("--disable-dev-shm-usage")    # Prevents /dev/shm memory crashes
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")  # Anti-bot
        options.add_argument("--js-flags=--max-old-space-size=512")            # Cap V8 RAM

        # Spoofer UA
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # RAM Saver: Block images, fonts, media
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.fonts": 2,
            "profile.default_content_setting_values.notifications": 2,
        }
        options.add_experimental_option("prefs", prefs)
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        # ----------------------------------------------------------------
        # STEP A: Discover system Chromium BROWSER binary
        # Nix puts binaries on PATH, but NOT in /usr/bin.
        # shutil.which() honours PATH so it finds Nix binaries correctly.
        # ----------------------------------------------------------------
        chromium_binary = None
        # 1. Explicit env var (highest priority)
        for env_key in ("CHROME_BIN", "CHROMIUM_BIN"):
            val = os.environ.get(env_key)
            if val and os.path.isfile(val):
                chromium_binary = val
                break

        # 2. shutil.which() — finds Nix-installed binary on PATH
        if not chromium_binary:
            for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
                found = shutil.which(name)
                if found:
                    chromium_binary = found
                    break

        # 3. Hardcoded well-known paths (rare fallback)
        if not chromium_binary:
            for path in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
                         "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                         "/usr/lib/chromium/chromium"):
                if os.path.isfile(path):
                    chromium_binary = path
                    break

        if chromium_binary:
            logger.info(f"✅ Found system Chromium binary: {chromium_binary}")
            options.binary_location = chromium_binary
        else:
            logger.warning("⚠️  No system Chromium binary found — driver may fail")

        # ----------------------------------------------------------------
        # STEP B: Discover system ChromeDriver binary
        # ----------------------------------------------------------------
        system_chromedriver = None
        for name in ("chromedriver",):
            found = shutil.which(name)
            if found:
                system_chromedriver = found
                break

        # ----------------------------------------------------------------
        # STRATEGY 1: System chromedriver (Nix-installed, compatible libs)
        # ----------------------------------------------------------------
        if system_chromedriver:
            try:
                logger.info(f"Trying Nix/system chromedriver: {system_chromedriver}")
                service = Service(executable_path=system_chromedriver)
                driver = webdriver.Chrome(service=service, options=options)
                driver.set_page_load_timeout(self.timeout)
                logger.info("✅ WebDriver initialized via SYSTEM chromedriver")
                return driver
            except Exception as e:
                logger.warning(f"System chromedriver failed: {e}")

        # ----------------------------------------------------------------
        # STRATEGY 2: ChromeDriverManager (auto-download — may fail in Nix)
        # ----------------------------------------------------------------
        try:
            logger.info("Falling back to ChromeDriverManager (auto-download)...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(self.timeout)
            logger.info("✅ WebDriver initialized via ChromeDriverManager")
            return driver
        except Exception as e:
            logger.warning(f"ChromeDriverManager failed: {e}")

        # ----------------------------------------------------------------
        # STRATEGY 3: Bare webdriver.Chrome() — Selenium's auto-detection
        # ----------------------------------------------------------------
        try:
            logger.info("Last resort: bare webdriver.Chrome()...")
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(self.timeout)
            logger.info("✅ WebDriver initialized via Selenium auto-detection")
            return driver
        except Exception as e:
            logger.error(f"All Chrome init strategies failed: {e}")
            raise RuntimeError(
                "Cannot initialize Chrome WebDriver. "
                "Ensure chromium + chromedriver Nix packages are installed "
                "and on PATH. Check nixpacks.toml configuration."
            ) from e

    # ------------------------------------------------------------------
    # BROWSER UTILITY WRAPPERS (used by ArchitonicScraper, ItalianScraper)
    # ------------------------------------------------------------------

    def get_page(self, url: str, wait_for_selector: str = None, wait_time: int = 15) -> Optional[BeautifulSoup]:
        """Navigate to a URL and return the parsed BeautifulSoup DOM."""
        try:
            driver = self._ensure_driver()
            driver.get(url)

            if wait_for_selector:
                try:
                    WebDriverWait(driver, wait_time).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                    )
                except TimeoutException:
                    logger.warning(f"Timeout waiting for selector '{wait_for_selector}' on {url}")
            else:
                time.sleep(3)

            return BeautifulSoup(driver.page_source, "html.parser")
        except Exception as e:
            logger.error(f"Error loading page {url}: {e}")
            return None

    def scroll_to_bottom(self, pause_time: float = 2.0, max_scrolls: int = 25):
        """Staggered scroll to trigger lazy-loading and AJAX pagination."""
        try:
            driver = self._ensure_driver()
            last_height = driver.execute_script("return document.body.scrollHeight")
            stable_cycles = 0

            for _ in range(max_scrolls):
                driver.execute_script("window.scrollBy(0, 1500);")
                time.sleep(pause_time)

                new_height = driver.execute_script("return document.body.scrollHeight")
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
        """Wrapper for finding elements."""
        return self._ensure_driver().find_elements(by, value)

    def click_element(self, by, value) -> bool:
        """Find and click an element safely."""
        try:
            driver = self._ensure_driver()
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                driver.execute_script("arguments[0].scrollIntoView(true);", elements[0])
                time.sleep(0.5)
                elements[0].click()
                return True
            return False
        except Exception as e:
            logger.debug(f"Error clicking element {value}: {e}")
            return False

    def close(self):
        """Safely shut down the browser to prevent zombie processes."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Closed WebDriver successfully.")
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")
            finally:
                self.driver = None

    def __del__(self):
        """Ensure the driver quits when the object is garbage-collected."""
        self.close()

    # ------------------------------------------------------------------
    # STANDALONE SCRAPING (called by orchestrator strategy='selenium')
    # ------------------------------------------------------------------

    def scrape_brand_website(self, website: str, brand_name: str) -> Dict:
        """Scrape a brand website directly using Selenium."""
        logger.info(f"🚀 Starting Standalone Selenium scrape for {brand_name} at {website}")

        result = {
            "brand": brand_name,
            "source": "Brand Website (Selenium Engine)",
            "scraped_at": datetime.now().isoformat(),
            "total_products": 0,
            "total_collections": 0,
            "collections": {},
            "all_products": [],
        }

        try:
            soup = self.get_page(website, wait_time=20)
            if not soup:
                return result

            self._dismiss_popups()
            self.scroll_to_bottom(pause_time=1.5, max_scrolls=15)

            # Refresh DOM after scrolling
            soup = BeautifulSoup(self._ensure_driver().page_source, "html.parser")

            logger.info("DOM extracted. Parsing products...")
            products = self._extract_products(soup, website, brand_name)

            for prod in products:
                cat = prod.get("category", "Products")
                sub = prod.get("subcategory", "General")
                coll_key = f"{cat} > {sub}"

                if coll_key not in result["collections"]:
                    result["collections"][coll_key] = {
                        "url": website,
                        "category": cat,
                        "subcategory": sub,
                        "product_count": 0,
                        "products": [],
                    }

                result["collections"][coll_key]["products"].append(prod)
                result["all_products"].append(prod)

            for key in result["collections"]:
                result["collections"][key]["product_count"] = len(result["collections"][key]["products"])

            result["total_products"] = len(result["all_products"])
            result["total_collections"] = len(result["collections"])

            logger.info(f"✅ Extracted {result['total_products']} products across {result['total_collections']} collections.")
            return result

        except Exception as e:
            logger.error(f"❌ Critical Selenium Error on {website}: {e}")
            return result
        finally:
            self.close()

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _dismiss_popups(self):
        """Attempt to clear cookie banners and newsletters."""
        try:
            driver = self._ensure_driver()
            keywords = ["accept", "agree", "close", "got it", "allow"]
            xpath_query = " | ".join(
                [f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{k}')]"
                 for k in keywords]
            )
            buttons = driver.find_elements(By.XPATH, xpath_query)
            for btn in buttons:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
                    break
        except Exception:
            pass

    def _extract_products(self, soup: BeautifulSoup, base_url: str, brand_name: str) -> List[Dict]:
        """Parse the fully rendered DOM to extract product nodes."""
        products = []
        seen = set()

        selectors = [
            ".product", ".product-item", ".product-card", ".grid-item",
            "article", "[data-product]", ".collection-item",
        ]

        candidates = []
        for sel in selectors:
            found = soup.select(sel)
            if len(found) > len(candidates):
                candidates = found

        if len(candidates) < 3:
            candidates = [a.parent for a in soup.find_all("a") if a.find("img")]

        for el in candidates:
            title_el = el.find(["h2", "h3", "h4", "div", "span"], class_=re.compile(r"title|name|heading", re.I))
            title = title_el.get_text(strip=True) if title_el else ""

            if not title:
                a_tag = el.find("a")
                title = a_tag.get_text(strip=True) if a_tag else ""

            title = re.sub(rf"\b{re.escape(brand_name)}\b", "", title, flags=re.IGNORECASE).strip()

            if not title or len(title) < 3 or title.lower() in seen:
                continue

            link_el = el.find("a", href=True)
            if not link_el:
                continue

            product_url = urljoin(base_url, link_el["href"])
            if any(x in product_url.lower() for x in ["/cart", "/wishlist", "/login", "/category/"]):
                continue

            img_el = el.find("img")
            image_url = ""
            if img_el:
                image_url = img_el.get("data-src") or img_el.get("data-lazy-src") or img_el.get("src") or ""
                if image_url:
                    image_url = urljoin(base_url, image_url)

            if not image_url or "placeholder" in image_url.lower():
                continue

            seen.add(title.lower())
            products.append({
                "name": title,
                "model": title,
                "description": title,
                "image_url": image_url,
                "source_url": product_url,
                "brand": brand_name,
                "price": None,
                "category": "Products",
                "subcategory": "General",
            })

        return products