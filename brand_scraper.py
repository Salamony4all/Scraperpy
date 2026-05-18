"""
Web scraper for furniture brand websites
Extracts product information, images, and descriptions
Enhanced with Selenium and Architonic support
"""

import requests
from bs4 import BeautifulSoup
import logging
import time
import re
import json
import os
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlencode
import urllib.robotparser

logger = logging.getLogger(__name__)

# Import enhanced scrapers
try:
    from utils.selenium_scraper import SeleniumScraper, SELENIUM_AVAILABLE, scrape_with_fallback
except ImportError:
    SELENIUM_AVAILABLE = False
    SeleniumScraper = None
    scrape_with_fallback = None
    logger.warning("Selenium scraper not available")

try:
    from utils.architonic_scraper import ArchitonicScraper
    ARCHITONIC_AVAILABLE = True
except ImportError:
    ARCHITONIC_AVAILABLE = False
    ArchitonicScraper = None
    logger.warning("Architonic scraper not available")


class BrandScraper:
    """Web scraper for furniture brand websites with intelligent product detection"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.rate_limit_delay = 1  # Reduced delay for faster scraping
        
    def scrape_brand_website(self, website: str, brand_name: str, use_selenium: bool = True) -> Dict:
        """
        Intelligently scrape a brand's website to discover products
        Automatically detects if site needs Selenium or is Architonic
        Returns structured data matching the Architonic reference model
        """
        try:
            logger.info(f"Starting intelligent scrape of {brand_name} ({website})")
            
            # Check if URL is Architonic
            if ARCHITONIC_AVAILABLE and ArchitonicScraper:
                architonic_scraper = ArchitonicScraper(use_selenium=use_selenium)
                if architonic_scraper.is_architonic_url(website):
                    logger.info(f"Detected Architonic URL, using ArchitonicScraper")
                    return architonic_scraper.scrape_collection(website, brand_name)
            
            # Check robots.txt (non-blocking, just warning)
            if not self.check_robots_allowed(website):
                logger.warning(f"Scraping not allowed by robots.txt for {website}, continuing anyway")
            
            # Check if URL looks like a product/category page (modern sites usually need Selenium)
            from urllib.parse import urlparse
            parsed_url = urlparse(website)
            path = parsed_url.path.lower()
            product_page_indicators = ['/products', '/product', '/category', '/categories', '/catalog', '/shop']
            
            # Force Selenium for product/category pages or if explicitly requested
            force_selenium = any(indicator in path for indicator in product_page_indicators)
            
            # Detect if Selenium is needed
            needs_selenium = False
            if use_selenium and SELENIUM_AVAILABLE:
                if force_selenium:
                    logger.info(f"Detected product/category page, using Selenium")
                    needs_selenium = True
                else:
                    needs_selenium = self._detect_javascript_required(website)
            
            if needs_selenium and SELENIUM_AVAILABLE:
                logger.info(f"Using Selenium for JavaScript-heavy site")
                return self._scrape_with_selenium(website, brand_name)
            elif force_selenium and not SELENIUM_AVAILABLE:
                return {'error': 'Selenium is required for this page but is not available. Please install Selenium: pip install selenium webdriver-manager'}
            else:
                # Use traditional requests/BeautifulSoup
                logger.info(f"Using requests/BeautifulSoup for static site")
                return self._scrape_with_requests(website, brand_name)
                
        except Exception as e:
            logger.exception(f"Error scraping {brand_name}: {e}")
            return {'error': f'Scraping failed: {str(e)}'}
    
    def _detect_javascript_required(self, website: str) -> bool:
        """Detect if website requires JavaScript rendering"""
        try:
            response = self.session.get(website, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check for common JavaScript indicators
            scripts = soup.find_all('script')
            js_indicators = [
                'react', 'vue', 'angular', 'next.js', 'nuxt',
                'data-react', 'data-vue', 'ng-', 'v-bind',
                'application/json', 'window.__INITIAL_STATE__'
            ]
            
            page_text = response.text.lower()
            for indicator in js_indicators:
                if indicator in page_text:
                    logger.info(f"Detected JavaScript framework: {indicator}")
                    return True
            
            # Check if page has minimal content (suggesting JS rendering)
            text_content = soup.get_text(strip=True)
            if len(text_content) < 500:
                logger.info("Page has minimal content, likely requires JavaScript")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error detecting JavaScript requirement: {e}")
            return False
    
    def _scrape_with_requests(self, website: str, brand_name: str) -> Dict:
        """Scrape using requests/BeautifulSoup with enhanced structure"""
        try:
            response = self.session.get(website, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Detect collections with hierarchy
            brand_logo = self._extract_brand_logo(soup, website)
            collections_map = self.detect_collections_with_hierarchy(soup, website)
            product_links = self.find_product_pages(soup, website)
            
            # Initialize result structure matching reference JSON
            from datetime import datetime
            result = {
                'brand': brand_name,
                'source': 'Brand Website',
                'scraped_at': datetime.now().isoformat(),
                'total_products': 0,
                'total_collections': len(collections_map),
                'logo': brand_logo,
                'collections': {},
                'all_products': []
            }
            
            all_products_list = []
            
            # Scrape collections
            for collection_name, collection_info in collections_map.items():
                collection_url = collection_info['url']
                category = collection_info.get('category')
                subcategory = collection_info.get('subcategory')
                
                logger.info(f"Scraping collection: {collection_name}")
                time.sleep(self.rate_limit_delay)
                
                collection_products = self.scrape_category_page(collection_url, brand_name, limit=None)
                
                if collection_products:
                    # Enrich products with collection info
                    for prod in collection_products:
                        prod['collection'] = collection_name
                        prod['category'] = category
                        prod['subcategory'] = subcategory
                        all_products_list.append(prod)
                    
                    result['collections'][collection_name] = {
                        'url': collection_url,
                        'category': category,
                        'subcategory': subcategory,
                        'product_count': len(collection_products),
                        'products': collection_products
                    }
            
            # Scrape direct product links
            seen_urls = {p.get('source_url') for p in all_products_list}
            direct_products = []
            
            for product_url in product_links[:50]:
                if product_url in seen_urls:
                    continue
                    
                logger.info(f"Scraping product: {product_url}")
                time.sleep(self.rate_limit_delay)
                
                product = self.scrape_product_page(product_url, brand_name)
                if product:
                    product['collection'] = 'Uncategorized'
                    direct_products.append(product)
                    all_products_list.append(product)
                    seen_urls.add(product_url)
            
            if direct_products:
                result['collections']['Uncategorized'] = {
                    'url': website,
                    'product_count': len(direct_products),
                    'products': direct_products
                }
            
            result['total_products'] = len(all_products_list)
            result['all_products'] = all_products_list
            
            return result
            
        except Exception as e:
            logger.error(f"Error in requests scraping: {e}")
            return {'error': str(e)}
    
    def _scrape_with_selenium(self, website: str, brand_name: str) -> Dict:
        """Scrape using Selenium with enhanced structure and pagination"""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available, falling back to requests")
            return self._scrape_with_requests(website, brand_name)
        
        scraper = SeleniumScraper(headless=True, timeout=60)
        
        try:
            logger.info(f"Loading page with Selenium: {website}")
            soup = scraper.get_page(website, wait_for_selector='body', wait_time=15)
            
            # Scroll to load dynamic content
            scraper.scroll_to_bottom(pause_time=2.0)
            time.sleep(3)
            
            # Get updated page source
            soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
            
            # Detect collections
            brand_logo = self._extract_brand_logo(soup, website)
            collections_map = self.detect_collections_with_hierarchy(soup, website)
            product_links = self.find_product_pages(soup, website)
            
            from datetime import datetime
            result = {
                'brand': brand_name,
                'source': 'Brand Website (Selenium)',
                'scraped_at': datetime.now().isoformat(),
                'total_products': 0,
                'total_collections': len(collections_map),
                'logo': brand_logo,
                'collections': {},
                'all_products': []
            }
            
            all_products_list = []
            
            # Scrape collections
            for collection_name, collection_info in collections_map.items():
                collection_url = collection_info['url']
                category = collection_info.get('category')
                subcategory = collection_info.get('subcategory')
                
                logger.info(f"Scraping collection with Selenium: {collection_name}")
                time.sleep(self.rate_limit_delay)
                
                # Load category page with Selenium
                cat_soup = scraper.get_page(collection_url, wait_time=10)
                scraper.scroll_to_bottom(pause_time=1.5)
                time.sleep(2)
                
                # Check if this category page has subcategories listed
                current_soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
                subcategories_found = self._detect_subcategories_on_page(current_soup, collection_url, collection_name)
                
                # If not found, try discovery from products
                if not subcategories_found:
                    temp_products = self.scrape_category_page_from_soup(current_soup, collection_url, brand_name)
                    if temp_products:
                        subcategories_found = self._discover_subcategories_from_products(scraper, temp_products, collection_name)
                
                if subcategories_found:

                    # This is a parent category with subcategories
                    # Scrape each subcategory instead
                    logger.info(f"Found {len(subcategories_found)} subcategories under {collection_name}")
                    for subcat_name, subcat_url in subcategories_found.items():
                        logger.info(f"Scraping subcategory: {collection_name} > {subcat_name}")
                        time.sleep(self.rate_limit_delay)
                        
                        # Load subcategory page
                        subcat_soup = scraper.get_page(subcat_url, wait_time=10)
                        
                        # Scrape products from subcategory
                        subcat_products = []
                        page_count = 0
                        max_pages = 5
                        
                        while page_count < max_pages:
                            page_count += 1
                            scraper.scroll_to_bottom(pause_time=1.5)
                            time.sleep(2)
                            
                            current_soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
                            page_products = self.scrape_category_page_from_soup(current_soup, subcat_url, brand_name, limit=None)
                            
                            existing_ids = {p.get('source_url') for p in subcat_products}
                            for prod in page_products:
                                if prod.get('source_url') not in existing_ids:
                                    subcat_products.append(prod)
                            
                            # Try pagination
                            try:
                                next_selectors = [
                                    "a[rel='next']", "a.next", "button.next", 
                                    "a:contains('Next')", "button:contains('Next')",
                                    "a:contains('Load More')", "button:contains('Load More')",
                                    ".pagination a:last-child"
                                ]
                                
                                clicked_next = False
                                for selector in next_selectors:
                                    try:
                                        found = scraper.driver.execute_script(f"""
                                            var el = document.querySelector("{selector}");
                                            if (el && el.offsetParent !== null) {{
                                                el.click();
                                                return true;
                                            }}
                                            return false;
                                        """)
                                        if found:
                                            logger.info(f"Clicked pagination/load more: {selector}")
                                            time.sleep(3)
                                            clicked_next = True
                                            break
                                    except:
                                        continue
                                
                                if not clicked_next:
                                    break
                            except Exception as e:
                                logger.warning(f"Pagination error: {e}")
                                break
                        
                        if subcat_products:
                            full_name = f"{collection_name} > {subcat_name}"
                            for prod in subcat_products:
                                prod['collection'] = full_name
                                prod['category'] = collection_name
                                prod['subcategory'] = subcat_name
                                all_products_list.append(prod)
                            
                            result['collections'][full_name] = {
                                'url': subcat_url,
                                'category': collection_name,
                                'subcategory': subcat_name,
                                'product_count': len(subcat_products),
                                'products': subcat_products
                            }
                    
                    # Skip scraping the parent category itself
                    continue
                
                
                # Handle Pagination / Infinite Scroll
                collection_products = []
                page_count = 0
                max_pages = 5  # Limit pages per category to avoid infinite loops
                
                while page_count < max_pages:
                    page_count += 1
                    scraper.scroll_to_bottom(pause_time=1.5)
                    time.sleep(2)
                    
                    # Extract products from current view
                    current_soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
                    page_products = self.scrape_category_page_from_soup(current_soup, collection_url, brand_name, limit=None)
                    
                    # Add new products (avoid duplicates)
                    existing_ids = {p.get('source_url') for p in collection_products}
                    for prod in page_products:
                        if prod.get('source_url') not in existing_ids:
                            collection_products.append(prod)
                    
                    # Try to find and click "Next" or "Load More" button
                    try:
                        # Common next button selectors
                        next_selectors = [
                            "a[rel='next']", 
                            "a.next", 
                            "button.next", 
                            "a:contains('Next')", 
                            "button:contains('Next')",
                            "a:contains('Load More')",
                            "button:contains('Load More')",
                            ".pagination a:last-child"
                        ]
                        
                        clicked_next = False
                        for selector in next_selectors:
                            try:
                                # Use JS to find and click to avoid interception
                                found = scraper.driver.execute_script(f"""
                                    var el = document.querySelector("{selector}");
                                    if (el && el.offsetParent !== null) {{
                                        el.click();
                                        return true;
                                    }}
                                    return false;
                                """)
                                if found:
                                    logger.info(f"Clicked pagination/load more: {selector}")
                                    time.sleep(3) # Wait for load
                                    clicked_next = True
                                    break
                            except:
                                continue
                        
                        if not clicked_next:
                            break # No next button found, stop pagination
                            
                    except Exception as e:
                        logger.warning(f"Pagination error: {e}")
                        break
                
                if collection_products:
                    for prod in collection_products:
                        prod['collection'] = collection_name
                        prod['category'] = category
                        prod['subcategory'] = subcategory
                        all_products_list.append(prod)
                        
                    result['collections'][collection_name] = {
                        'url': collection_url,
                        'category': category,
                        'subcategory': subcategory,
                        'product_count': len(collection_products),
                        'products': collection_products
                    }
            
            # Scrape direct products
            seen_urls = {p.get('source_url') for p in all_products_list}
            direct_products = []
            
            for product_url in product_links[:50]:
                if product_url in seen_urls:
                    continue
                    
                logger.info(f"Scraping product with Selenium: {product_url}")
                time.sleep(self.rate_limit_delay)
                
                prod_soup = scraper.get_page(product_url, wait_time=15)
                product = self.scrape_product_page_from_soup(prod_soup, product_url, brand_name)
                
                if product:
                    product['collection'] = 'Uncategorized'
                    direct_products.append(product)
                    all_products_list.append(product)
                    seen_urls.add(product_url)
            
            if direct_products:
                result['collections']['Uncategorized'] = {
                    'url': website,
                    'product_count': len(direct_products),
                    'products': direct_products
                }
            
            result['total_products'] = len(all_products_list)
            result['all_products'] = all_products_list
            
            return result
            
        except Exception as e:
            logger.error(f"Error in Selenium scraping: {e}")
            return {'error': str(e)}
        finally:
            scraper.close()
    
    def find_product_pages(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find product page URLs using various heuristics"""
        product_urls = set()
        
        # Common product URL patterns
        product_patterns = [
            r'/product[s]?/',
            r'/item[s]?/',
            r'/chair[s]?/',
            r'/desk[s]?/',
            r'/seating/',
            r'/furniture/',
            r'/catalog/',
            r'/collection[s]?/'
        ]
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(base_url, href)
            
            # Check if URL matches product patterns
            if any(re.search(pattern, full_url, re.I) for pattern in product_patterns):
                product_urls.add(full_url)
        
        return list(product_urls)
    
    def _detect_subcategories_on_page(self, soup: BeautifulSoup, base_url: str, parent_category: str) -> Dict[str, str]:
        """
        Detect subcategories listed on a category page
        Returns dict: {subcategory_name: subcategory_url}
        """
        subcategories = {}
        
        # Common patterns for subcategory listings on category pages
        # Look for category grids, lists, or navigation elements
        selectors = [
            # WooCommerce product categories
            ('ul', {'class': re.compile(r'product.*categor', re.I)}),
            ('div', {'class': re.compile(r'product.*categor', re.I)}),
            # Generic category listings
            ('div', {'class': re.compile(r'categor.*list|categor.*grid', re.I)}),
            ('ul', {'class': re.compile(r'sub.*categor|child.*categor', re.I)}),
            # Sidebar categories
            ('aside', {'class': re.compile(r'categor|sidebar', re.I)}),
            ('div', {'class': re.compile(r'widget.*categor', re.I)}),
        ]
        
        for tag, attrs in selectors:
            containers = soup.find_all(tag, attrs)
            for container in containers:
                # Find links in this container
                links = container.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '').strip()
                    name = link.get_text(strip=True)
                    
                    if not href or not name or len(name) < 2:
                        continue
                    
                    # Check if this looks like a subcategory URL
                    # Typically: /category/parent/subcategory/ or similar
                    if '/product-category/' in href or '/category/' in href:
                        full_url = urljoin(base_url, href)
                        # Make sure it's not the same as the parent
                        if full_url != base_url:
                            clean_name = self._clean_category_name(name)
                            if clean_name and clean_name != parent_category:
                                subcategories[clean_name] = full_url
        
        return subcategories
    
    def _discover_subcategories_from_products(self, scraper, products: List[Dict], parent_category: str) -> Dict[str, str]:
        """
        Visit a few products to discover subcategories via breadcrumbs
        Returns {subcategory_name: subcategory_url}
        """
        discovered = {}
        # Limit to first 3 products to save time
        for prod in products[:3]:
            url = prod.get('source_url')
            if not url: continue
            
            try:
                logger.info(f"Checking product for subcategories: {url}")
                soup = scraper.get_page(url, wait_time=5)
                breadcrumbs = self.extract_breadcrumb_links(soup)
                
                # Look for parent_category in breadcrumbs and take the next item
                for i, (name, link) in enumerate(breadcrumbs):
                    # loose match for parent category
                    clean_name = self._clean_category_name(name).lower()
                    clean_parent = parent_category.lower()
                    
                    if clean_name in clean_parent or clean_parent in clean_name:
                        # Check if there is a next item that is NOT the product itself
                        if i + 1 < len(breadcrumbs):
                            sub_name, sub_link = breadcrumbs[i+1]
                            # Verify it's not the product name (approximate check)
                            # And not just "Home" or "Products"
                            if sub_link and sub_link != url:
                                clean_sub = self._clean_category_name(sub_name)
                                if clean_sub and clean_sub.lower() != clean_parent:
                                    discovered[clean_sub] = sub_link
            except Exception as e:
                logger.warning(f"Error discovering subcategories from {url}: {e}")
                
        return discovered

    
    def _clean_category_name(self, name: str) -> str:
        """Clean up category name (e.g. 'Open submenu (Chairs)' -> 'Chairs')"""
        if not name:
            return ""
        
        # Normalize whitespace
        name = " ".join(name.split())
        
        # Remove "Open/Close submenu" prefixes/suffixes
        # Matches: "Open submenu", "Close submenu", "Open submenu (Chairs)", "Close submenu [Chairs]"
        name = re.sub(r'^(Open|Close)\s+submenu\s*[\(\[]?', '', name, flags=re.I)
        name = re.sub(r'[\)\]]$', '', name)
        
        # Remove "Toggle" prefix
        name = re.sub(r'^Toggle\s+', '', name, flags=re.I)
        
        # Remove counts (e.g. "Chairs (10)")
        name = re.sub(r'\s*\(\d+\)$', '', name)
        
        return name.strip()

    def detect_collections_with_hierarchy(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Dict]:
        """
        Detect product collections/categories with hierarchy (Category -> Subcategory)
        Returns dict: { 'Full Name': {'url': '...', 'category': '...', 'subcategory': '...'} }
        """
        collections = {}
        seen_urls = set()
        
        skip_texts = ['home', 'about', 'contact', 'blog', 'news', 'login', 'register', 
                     'cart', 'checkout', 'account', 'search', 'menu', 'close', 'more',
                     'view all', 'see all', 'all products', 'shop', 'store', 'back',
                     'close submenu', 'open submenu']
        
        # Strategy 1: Dropdowns (Parent -> Child)
        # Look for nav items that contain sub-menus
        # Expanded selectors to catch more generic structures
        nav_containers = soup.find_all(['nav', 'header', 'div'], class_=re.compile(r'(nav|menu|header)', re.I))
        
        for nav in nav_containers:
            # Find potential top-level items (li or div)
            # Use recursive=False to get only direct children, then check each one
            direct_children = nav.find_all(['li'], recursive=False)
            if not direct_children:
                # If no direct li children, look for ul first
                top_ul = nav.find('ul', recursive=False)
                if top_ul:
                    direct_children = top_ul.find_all('li', recursive=False)
            
            for item in direct_children:
                # Check if this item has a nested ul/div (submenu)
                # Try multiple strategies to find submenu
                submenu = None
                
                # Strategy 1: Look for ul/div with submenu-related classes
                submenu = item.find(['ul', 'div'], class_=re.compile(r'(sub|dropdown|children|menu)', re.I), recursive=False)
                
                # Strategy 2: Any nested ul (common pattern)
                if not submenu:
                    submenu = item.find('ul', recursive=False)
                
                # Strategy 3: Look deeper - sometimes submenu is wrapped
                if not submenu:
                    # Check if there's a nested ul anywhere in this item
                    all_uls = item.find_all('ul')
                    if all_uls:
                        # Take the first one that's not the parent
                        for ul in all_uls:
                            # Make sure it has links (actual submenu content)
                            if ul.find('a', href=True):
                                submenu = ul
                                break
                
                
                if submenu:
                    # This item is a parent - find its name from direct children only
                    parent_name = ""
                    
                    # Strategy 1: Find direct child link (not in submenu)
                    parent_link = None
                    for child in item.children:
                        if hasattr(child, 'name') and child.name == 'a':
                            parent_link = child
                            break
                    
                    if parent_link:
                        parent_name = parent_link.get_text(strip=True)
                    else:
                        # Strategy 2: Look for button or span as direct child
                        for child in item.children:
                            if hasattr(child, 'name') and child.name in ['button', 'span', 'div']:
                                # Make sure it's not the submenu itself
                                if child != submenu:
                                    parent_name = child.get_text(strip=True)
                                    if parent_name:
                                        break
                    
                    # Clean up name
                    raw_parent_name = parent_name
                    parent_name = self._clean_category_name(parent_name)
                    
                    # Skip if name is empty or in skip list (check both raw and cleaned)
                    if not parent_name or len(parent_name) < 2:
                        continue
                    if parent_name.lower() in skip_texts or raw_parent_name.lower() in skip_texts:
                        continue
                    if "close submenu" in parent_name.lower():
                        continue
                    
                    logger.debug(f"Found parent category: {parent_name}")
                        
                    # Find sub-links in the submenu
                    sub_links = submenu.find_all('a', href=True)
                    for sub_link in sub_links:
                        raw_sub_name = sub_link.get_text(strip=True)
                        sub_name = self._clean_category_name(raw_sub_name)
                        sub_href = sub_link.get('href', '').strip()
                        
                        if not sub_name or not sub_href or len(sub_name) < 2:
                            continue
                        if sub_name.lower() in skip_texts or raw_sub_name.lower() in skip_texts:
                            continue
                        if "close submenu" in sub_name.lower():
                            continue
                            
                        sub_url = urljoin(base_url, sub_href)
                        if sub_url in seen_urls:
                            continue
                            
                        # Construct hierarchical name
                        full_name = f"{parent_name} > {sub_name}"
                        seen_urls.add(sub_url)
                        
                        collections[full_name] = {
                            'url': sub_url,
                            'category': parent_name,
                            'subcategory': sub_name
                        }
                        logger.debug(f"Found hierarchical collection: {full_name}")


        # Strategy 2: Flat Categories (if no hierarchy found or as supplement)
        # Use existing detection logic but format as collections
        flat_categories = self._detect_flat_categories(soup, base_url)
        
        for name, url in flat_categories.items():
            if url not in seen_urls:
                # Clean name again just in case
                clean_name = self._clean_category_name(name)
                if not clean_name or clean_name.lower() in skip_texts or "close submenu" in clean_name.lower():
                    continue

                # Check if this name is already part of a hierarchy
                is_covered = False
                for existing_name in collections:
                    if clean_name in existing_name:
                        is_covered = True
                        break
                
                if not is_covered:
                    seen_urls.add(url)
                    collections[clean_name] = {
                        'url': url,
                        'category': clean_name,
                        'subcategory': None
                    }
        
        logger.info(f"Detected {len(collections)} collections with hierarchy")
        return collections

    def _detect_flat_categories(self, soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
        """
        Dynamically detect product categories from website navigation structure
        Extracts categories exactly as they appear on the website
        """
        categories = {}
        seen_urls = set()
        
        # Common non-category navigation items to skip
        skip_texts = ['home', 'about', 'contact', 'blog', 'news', 'login', 'register', 
                     'cart', 'checkout', 'account', 'search', 'menu', 'close', 'more',
                     'view all', 'see all', 'all products', 'shop', 'store']
        
        # Category URL indicators
        category_indicators = ['/category/', '/categories/', '/collection/', '/collections/',
                             '/shop/', '/products/', '/catalog/', '/browse/']
        
        # Strategy 1: Look for main navigation menus (header, primary nav)
        # Common navigation selectors for different CMS/platforms
        nav_selectors = [
            # Standard HTML5 nav elements
            ('nav', {}),
            # WordPress/WooCommerce
            ('nav', {'class': re.compile(r'(main|primary|header|menu|navigation)', re.I)}),
            ('ul', {'class': re.compile(r'(menu|nav|navigation|main-menu|primary-menu)', re.I)}),
            # Shopify
            ('ul', {'class': re.compile(r'(site-nav|main-menu)', re.I)}),
            # Custom/Generic
            ('div', {'class': re.compile(r'(nav|menu|navigation|header-menu)', re.I)}),
            # Header navigation
            ('header', {}),
            # Sidebar navigation
            ('aside', {'class': re.compile(r'(sidebar|nav|menu)', re.I)}),
        ]
        
        for tag, attrs in nav_selectors:
            nav_elements = soup.find_all(tag, attrs) if attrs else soup.find_all(tag)
            
            for nav in nav_elements:
                # Find all links in navigation
                links = nav.find_all('a', href=True)
                
                for link in links:
                    href = link.get('href', '').strip()
                    if not href:
                        continue
                    
                    # Get link text (category name)
                    category_name = link.get_text(strip=True)
                    
                    # Skip if empty, too short, or common non-category links
                    if not category_name or len(category_name) < 2:
                        continue
                    
                    # Skip common non-category navigation items
                    if category_name.lower() in skip_texts:
                        continue
                    
                    # Build full URL
                    category_url = urljoin(base_url, href)
                    
                    # Skip if we've seen this URL or it's the homepage
                    if category_url in seen_urls or category_url.rstrip('/') == base_url.rstrip('/'):
                        continue
                    
                    # Skip external links (different domain)
                    try:
                        parsed_base = urlparse(base_url)
                        parsed_link = urlparse(category_url)
                        base_domain = parsed_base.netloc
                        link_domain = parsed_link.netloc
                        if link_domain and link_domain != base_domain:
                            continue
                    except:
                        pass
                    
                    # Check if URL looks like a category page (not a product page)
                    # Category pages typically have patterns like /category/, /shop/, /products/, etc.
                    # but not /product/123/ or specific product slugs
                    parsed_url = urlparse(category_url)
                    url_path = parsed_url.path.lower()
                    
                    # Skip if it looks like a product page (has product ID or specific product slug)
                    product_indicators = ['/product/', '/item/', '/p/', '/detail/', '/view/']
                    if any(indicator in url_path for indicator in product_indicators):
                        # Check if it has a numeric ID (likely a product)
                        if re.search(r'/\d+/?$', url_path):
                            continue
                    
                    # If URL has category indicators, it's likely a category
                    is_category_url = any(indicator in url_path for indicator in category_indicators)
                    
                    # Also accept if link is in a navigation menu and has reasonable text length
                    # (navigation links are usually categories)
                    is_nav_link = nav.name in ['nav', 'ul', 'header', 'aside']
                    reasonable_length = 2 <= len(category_name) <= 50
                    
                    if is_category_url or (is_nav_link and reasonable_length):
                        seen_urls.add(category_url)
                        categories[category_name] = category_url
                        logger.debug(f"Found category: {category_name} -> {category_url}")
        
        # Strategy 2: Look for category links in dropdown menus (nested navigation)
        # Many sites use dropdowns for categories
        dropdown_selectors = [
            ('ul', {'class': re.compile(r'(dropdown|submenu|sub-menu|mega-menu)', re.I)}),
            ('div', {'class': re.compile(r'(dropdown|submenu|sub-menu)', re.I)}),
        ]
        
        for tag, attrs in dropdown_selectors:
            dropdowns = soup.find_all(tag, attrs)
            for dropdown in dropdowns:
                links = dropdown.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '').strip()
                    if not href:
                        continue
                    
                    category_name = link.get_text(strip=True)
                    if not category_name or len(category_name) < 2:
                        continue
                    
                    # Skip non-category items
                    if category_name.lower() in skip_texts:
                        continue
                    
                    category_url = urljoin(base_url, href)
                    
                    if category_url not in seen_urls:
                        seen_urls.add(category_url)
                        categories[category_name] = category_url
                        logger.debug(f"Found category from dropdown: {category_name} -> {category_url}")
        
        # Strategy 3: Look for category links in product filters/sidebars
        filter_selectors = [
            ('div', {'class': re.compile(r'(filter|sidebar|facet|categories)', re.I)}),
            ('aside', {'class': re.compile(r'(filter|sidebar|categories)', re.I)}),
        ]
        
        for tag, attrs in filter_selectors:
            filters = soup.find_all(tag, attrs)
            for filter_elem in filters:
                links = filter_elem.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '').strip()
                    if not href:
                        continue
                    
                    category_name = link.get_text(strip=True)
                    if not category_name or len(category_name) < 2:
                        continue
                    
                    # Skip non-category items
                    if category_name.lower() in skip_texts:
                        continue
                    
                    category_url = urljoin(base_url, href)
                    
                    if category_url not in seen_urls:
                        seen_urls.add(category_url)
                        categories[category_name] = category_url
                        logger.debug(f"Found category from filter: {category_name} -> {category_url}")
        
        # Strategy 4: Look for breadcrumb navigation (shows category hierarchy)
        breadcrumbs = soup.find_all(['nav', 'ol', 'ul'], class_=re.compile(r'breadcrumb', re.I))
        for breadcrumb in breadcrumbs:
            links = breadcrumb.find_all('a', href=True)
            for link in links:
                href = link.get('href', '').strip()
                if not href:
                    continue
                
                category_name = link.get_text(strip=True)
                if not category_name or len(category_name) < 2:
                    continue
                
                # Skip common breadcrumb items
                if category_name.lower() in ['home', 'main', 'index']:
                    continue
                
                category_url = urljoin(base_url, href)
                
                if category_url not in seen_urls:
                    seen_urls.add(category_url)
                    categories[category_name] = category_url
                    logger.debug(f"Found category from breadcrumb: {category_name} -> {category_url}")
        
        # Strategy 5: Look for category links in footer (some sites list categories there)
        footer = soup.find('footer')
        if footer:
            # Only get top-level category links from footer (not subcategories)
            footer_links = footer.find_all('a', href=True, limit=20)  # Limit to avoid too many
            for link in footer_links:
                href = link.get('href', '').strip()
                if not href:
                    continue
                
                category_name = link.get_text(strip=True)
                if not category_name or len(category_name) < 2:
                    continue
                
                # Skip non-category items
                if category_name.lower() in skip_texts:
                    continue
                
                category_url = urljoin(base_url, href)
                
                # Only add if URL looks like a category page
                parsed_url = urlparse(category_url)
                url_path = parsed_url.path.lower()
                category_indicators = ['/category/', '/categories/', '/collection/', '/collections/',
                                     '/shop/', '/products/', '/catalog/', '/browse/']
                if any(indicator in url_path for indicator in category_indicators):
                    if category_url not in seen_urls:
                        seen_urls.add(category_url)
                        categories[category_name] = category_url
                        logger.debug(f"Found category from footer: {category_name} -> {category_url}")
        
        # Remove duplicates (same URL, different text) - keep the first one
        url_to_name = {}
        for name, url in categories.items():
            if url not in url_to_name:
                url_to_name[url] = name
        
        # Rebuild categories dict with unique URLs
        final_categories = {name: url for url, name in url_to_name.items()}
        
        logger.info(f"Detected {len(final_categories)} categories: {list(final_categories.keys())}")
        
        return final_categories
    
    def scrape_category_page(self, url: str, brand_name: str, limit: Optional[int] = None) -> List[Dict]:
        """Scrape products from a category page (unlimited by default)"""
        products = []
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            return self.scrape_category_page_from_soup(soup, url, brand_name, limit)
            
        except Exception as e:
            logger.error(f"Error scraping category {url}: {e}")
            return []
    
    def scrape_category_page_from_soup(self, soup: BeautifulSoup, url: str, brand_name: str, limit: Optional[int] = None) -> List[Dict]:
        """Scrape products from a BeautifulSoup object (unlimited by default)"""
        products = []
        
        try:
            # Find product cards/items
            product_containers = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'(product|item|card)', re.I))
            
            # Apply limit if specified, otherwise unlimited
            containers = product_containers[:limit] if limit else product_containers
            
            for container in containers:
                product = self.extract_product_from_container(container, url, brand_name)
                if product:
                    products.append(product)
            
            return products
            
        except Exception as e:
            logger.error(f"Error extracting products from soup: {e}")
            return []
    
    def scrape_product_page(self, url: str, brand_name: str) -> Optional[Dict]:
        """Scrape detailed product information from product page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            return self.scrape_product_page_from_soup(soup, url, brand_name)
            
        except Exception as e:
            logger.error(f"Error scraping product {url}: {e}")
            return None
    
    def scrape_product_page_from_soup(self, soup: BeautifulSoup, url: str, brand_name: str) -> Optional[Dict]:
        """Extract product information from BeautifulSoup object"""
        try:
            # Extract product information
            title = self.extract_product_title(soup)
            description = self.extract_product_description(soup)
            image_url = self.extract_product_image(soup, url)
            price = self.extract_product_price(soup)
            features = self.extract_product_features(soup)
            breadcrumbs = self.extract_breadcrumbs(soup)
            
            if title:
                return {
                    'brand': brand_name,
                    'model': title,
                    'description': description,
                    'image_url': image_url,
                    'price': price,
                    'features': features,
                    'source_url': url,
                    'category_path': breadcrumbs
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error scraping product from soup {url}: {e}")
            return None

    def extract_breadcrumbs(self, soup: BeautifulSoup) -> List[str]:
        """Extract breadcrumb path from product page"""
        breadcrumbs = []
        
        # Common breadcrumb selectors
        selectors = [
            (['nav', 'div', 'ul', 'ol'], {'class': re.compile(r'(breadcrumb|bread-crumb|path)', re.I)}),
            ('div', {'id': re.compile(r'(breadcrumb)', re.I)}),
        ]
        
        for tag, attrs in selectors:
            container = soup.find(tag, attrs)
            if container:
                # Extract links or text items
                items = container.find_all(['a', 'span', 'li'])
                for item in items:
                    text = item.get_text(strip=True)
                    # Skip separators like '>', '/', 'Home'
                    if text and len(text) > 1 and text not in ['>', '/', '»', 'Home']:
                        # Avoid duplicates (sometimes span is inside a)
                        if not breadcrumbs or text != breadcrumbs[-1]:
                            breadcrumbs.append(text)
                
                if breadcrumbs:
                    return breadcrumbs
        
        return []

    def extract_breadcrumb_links(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """Extract breadcrumb links (name, url) from product page"""
        
        # Common breadcrumb selectors
        selectors = [
            (['nav', 'div', 'ul', 'ol'], {'class': re.compile(r'(breadcrumb|bread-crumb|path)', re.I)}),
            ('div', {'id': re.compile(r'(breadcrumb)', re.I)}),
        ]
        
        for tag, attrs in selectors:
            # Use find_all to get all potential containers
            containers = soup.find_all(tag, attrs)
            for container in containers:
                breadcrumbs = []
                links = container.find_all('a', href=True)
                for link in links:
                    text = link.get_text(strip=True)
                    href = link.get('href')
                    if text and href and text not in ['Home', '>', '/', '»']:
                        breadcrumbs.append((text, href))
                
                # If we found a container with links, return it
                if breadcrumbs:
                    return breadcrumbs
        
        return []


    
    def save_brand_data(self, brand_data: Dict, tier: str, output_dir: str = 'brands_data') -> str:
        """
        Save brand data to separate JSON file in brands_data folder
        
        Args:
            brand_data: Dictionary with brand products data
            tier: Budget tier (budgetary, mid_range, high_end)
            output_dir: Output directory (default: brands_data)
            
        Returns:
            Path to saved file
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename from brand name and tier
            brand_name = brand_data.get('brand', 'unknown').replace(' ', '_').replace('/', '_')
            safe_brand_name = re.sub(r'[^\w\-_]', '', brand_name)
            safe_tier = tier.replace('-', '_').lower()
            
            filename = f"{safe_brand_name}_{safe_tier}.json"
            filepath = os.path.join(output_dir, filename)
            
            # Save to JSON file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(brand_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Brand data saved to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving brand data: {e}")
            raise
    
    def extract_product_from_container(self, container: BeautifulSoup, base_url: str, brand_name: str) -> Optional[Dict]:
        """Extract product info from a container element"""
        try:
            # Find link first (most reliable)
            link_elem = container.find('a', href=True)
            product_url = urljoin(base_url, link_elem['href']) if link_elem else None
            
            # Find title - try multiple strategies
            title = None
            
            # Strategy 1: Look for title/name/product class
            title_elem = container.find(['h2', 'h3', 'h4', 'a', 'span', 'div'], class_=re.compile(r'(title|name|product.*name|woocommerce-loop-product__title)', re.I))
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            # Strategy 2: If no title found, try any heading in the container
            if not title:
                for tag in ['h2', 'h3', 'h4', 'h5']:
                    heading = container.find(tag)
                    if heading:
                        title = heading.get_text(strip=True)
                        break
            
            # Strategy 3: If still no title, use the link text
            if not title and link_elem:
                title = link_elem.get_text(strip=True)
            
            # Strategy 4: Try to find any text in the container (last resort)
            if not title:
                # Get all text but limit length
                all_text = container.get_text(strip=True)
                if all_text and len(all_text) < 200:  # Reasonable title length
                    title = all_text
            
            # Find image
            img = container.find('img')
            image_url = None
            if img:
                image_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
                if image_url:
                    image_url = urljoin(base_url, image_url)
            
            # Find price
            price_elem = container.find(['span', 'div'], class_=re.compile(r'price', re.I))
            price = self.parse_price(price_elem.get_text(strip=True)) if price_elem else None
            
            # Only return if we have at least a title or a product URL
            if title or product_url:
                return {
                    'brand': brand_name,
                    'model': title or 'Unknown Product',
                    'image_url': image_url,
                    'price': price,
                    'source_url': product_url or base_url
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting product from container: {e}")
            return None
    
    def extract_product_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from page"""
        # Try common title patterns
        selectors = [
            ('h1', {'class_': re.compile(r'(product|title|name)', re.I)}),
            ('h1', {}),
            ('meta', {'property': 'og:title'}),
            ('title', {})
        ]
        
        for tag, attrs in selectors:
            if tag == 'meta':
                elem = soup.find(tag, attrs)
                if elem:
                    return elem.get('content')
            else:
                elem = soup.find(tag, attrs)
                if elem:
                    return elem.get_text(strip=True)
        
        return None
    
    def extract_product_description(self, soup: BeautifulSoup) -> str:
        """Extract product description"""
        # Try meta description first
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '').strip()
        
        # Try common description containers
        desc_containers = soup.find_all(['div', 'p'], class_=re.compile(r'(description|detail|overview)', re.I))
        
        for container in desc_containers[:3]:
            text = container.get_text(strip=True)
            if len(text) > 50:  # Minimum length for valid description
                return text[:500]  # Limit length
        
        return ""
    
    def extract_product_image(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Extract main product image URL"""
        # Try various image sources
        img_selectors = [
            soup.find('img', class_=re.compile(r'(product|main|primary|hero)', re.I)),
            soup.find('meta', property='og:image'),
            soup.find('img', {'itemprop': 'image'}),
            soup.find('img')
        ]
        
        for selector in img_selectors:
            if selector:
                if selector.name == 'meta':
                    img_url = selector.get('content')
                else:
                    img_url = selector.get('src') or selector.get('data-src') or selector.get('data-lazy-src')
                
                if img_url:
                    return urljoin(base_url, img_url)
        
        return None
    
    def extract_product_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract product price"""
        price_selectors = [
            soup.find(['span', 'div', 'p'], class_=re.compile(r'price', re.I)),
            soup.find(['span', 'div', 'p'], {'itemprop': 'price'})
        ]
        
        for elem in price_selectors:
            if elem:
                price_text = elem.get_text(strip=True)
                price = self.parse_price(price_text)
                if price:
                    return price
        
        return None
    
    def extract_product_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract product features/specifications"""
        features = []
        
        # Look for feature lists
        feature_lists = soup.find_all(['ul', 'ol'], class_=re.compile(r'(feature|spec|benefit)', re.I))
        
        for feature_list in feature_lists[:2]:  # Limit to 2 lists
            for item in feature_list.find_all('li')[:5]:  # Max 5 features per list
                text = item.get_text(strip=True)
                if text and len(text) < 100:
                    features.append(text)
        
        return features
    
    def parse_price(self, text: str) -> Optional[float]:
        """Parse price from text"""
        try:
            # Remove currency symbols and extract numbers
            price_match = re.search(r'[\d,]+\.?\d*', text.replace(',', ''))
            if price_match:
                return float(price_match.group())
        except:
            pass
        return None
    
    def check_robots_allowed(self, website: str) -> bool:
        """Check if scraping is allowed by robots.txt"""
        try:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = urljoin(website, '/robots.txt')
            rp.set_url(robots_url)
            rp.read()
            
            # Check if our user agent can fetch the site
            return rp.can_fetch(self.headers['User-Agent'], website)
        except Exception as e:
            logger.warning(f"Could not read robots.txt: {e}")
            return True  # Allow by default if robots.txt is not accessible
    
    def get_product_image(self, brand_name: str, model_name: str, website: str) -> Optional[str]:
        """
        Search for product image on brand website
        """
        try:
            logger.info(f"Searching image for {brand_name} - {model_name}")
            
            # Build search query
            search_terms = f"{brand_name} {model_name}"
            
            # Try to find product page
            response = self.session.get(website, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Search for product link containing model name
            for link in soup.find_all('a', href=True):
                if model_name.lower() in link.get_text().lower():
                    product_url = urljoin(website, link['href'])
                    product = self.scrape_product_page(product_url, brand_name)
                    if product and product.get('image_url'):
                        return product['image_url']
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching image: {e}")
            return None
    
    def get_product_description(self, brand_name: str, model_name: str, website: str) -> str:
        """
        Get detailed product description from brand website
        """
        try:
            logger.info(f"Fetching description for {brand_name} - {model_name}")
            
            # Try to find and scrape product page
            response = self.session.get(website, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Search for product link
            for link in soup.find_all('a', href=True):
                if model_name.lower() in link.get_text().lower():
                    product_url = urljoin(website, link['href'])
                    product = self.scrape_product_page(product_url, brand_name)
                    if product and product.get('description'):
                        return product['description']
            
            # Fallback to generic description
            return f"{brand_name} {model_name} - Premium office furniture with superior ergonomics and modern design"
            
        except Exception as e:
            logger.error(f"Error fetching description: {e}")
            return f"{brand_name} {model_name}"

    def _extract_brand_logo(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
        """Extract brand logo from website"""
        try:
            # Priority 0: Check og:image meta tag
            logo_meta = soup.find('meta', property='og:image')
            if logo_meta and logo_meta.get('content') and 'logo' in logo_meta.get('content').lower():
                logo_url = logo_meta.get('content')
                if '?' in logo_url: logo_url = logo_url.split('?')[0]
                return logo_url
            
            # Priority 1: Specific logo selectors from updated scraper logic
            logo_selectors = [
                '.custom-logo', '.site-logo img', '.logo img', 'a.logo img',
                'header img[src*="logo"]', '.navbar-brand img', '[class*="logo"] img',
                'img[alt*="logo" i]', 'img[class*="logo" i]',
                '#logo img', '.header-logo img'
            ]
            
            for selector in logo_selectors:
                elements = soup.select(selector)
                if elements:
                    el = elements[0]
                    src = el.get('src') or el.get('data-src') or el.get('srcset')
                    if src:
                        logo_url = urljoin(base_url, src.split()[0])
                        # Clean up WebP parameters or other query strings if needed
                        if '?' in logo_url:
                            logo_url = logo_url.split('?')[0]
                        return logo_url

            # Priority 2: Try specific selectors for brand logo (fallback search)
            logo_img = soup.find('img', class_=re.compile(r'brand.*logo|logo.*brand|site-logo', re.I))
            if logo_img:
                src = logo_img.get('src') or logo_img.get('data-src') or logo_img.get('srcset')
                if src: return urljoin(base_url, src.split()[0])
            
            # Priority 3: Look in header or logo-related containers
            logo_container = soup.find(['div', 'span', 'header', 'a'], class_=re.compile(r'brand|logo', re.I))
            if logo_container:
                img = logo_container.find('img')
                if img:
                    src = img.get('src') or img.get('data-src') or img.get('srcset')
                    if src: return urljoin(base_url, src.split()[0])
            
            # Priority 4: Try any image with 'logo' in the filename or alt text (excluding common false positives)
            for img in soup.find_all('img'):
                alt = img.get('alt', '').lower()
                src = img.get('src', '').lower()
                if ('logo' in alt or 'logo' in src) and len(src) < 255:
                    if not any(x in src for x in ['placeholder', 'spinner', 'loading']):
                        logo_url = urljoin(base_url, img.get('src'))
                        if '?' in logo_url: logo_url = logo_url.split('?')[0]
                        return logo_url
            
            # Fallback: check if the first image in the header is the logo
            header = soup.find('header')
            if header:
                first_img = header.find('img')
                if first_img:
                    src = first_img.get('src')
                    if src: return urljoin(base_url, src)
                    
            return None
        except Exception as e:
            logger.debug(f"Error extracting logo: {e}")
            return None
