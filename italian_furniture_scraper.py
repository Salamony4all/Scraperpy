"""
Italian Furniture Brand Website Scraper
Specialized for Italian furniture manufacturer websites like Martex.it, Manerba.it, etc.
These sites typically have:
- Category-based navigation
- Product detail pages
- Italian language content
- No direct product listings on main page
"""

import logging
import time
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class ItalianFurnitureScraper:
    """Scraper for Italian furniture manufacturer websites"""
    
    def __init__(self, delay: float = 1.0):
        """
        Initialize the scraper
        
        Args:
            delay: Delay between requests in seconds (default 1.0)
        """
        self.delay = delay
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,it;q=0.8',  # Prefer English
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def _convert_to_english_url(self, url: str) -> str:
        """Convert Italian URL to English version"""
        # Replace /it/ with /en/ in URL path
        url = url.replace('/it/', '/en/')
        url = url.replace('/IT/', '/EN/')
        
        # Also try adding ?lang=en parameter if no /en/ replacement happened
        if '/en/' not in url.lower() and '?' not in url:
            url = url + '?lang=en'
        
        return url
    
    def is_italian_furniture_site(self, url: str) -> bool:
        """Check if URL is an Italian furniture manufacturer site"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        
        # Check for .it domain and common furniture site patterns
        is_italian = domain.endswith('.it')
        has_products_path = any(keyword in path for keyword in ['prodotti', 'products', 'collezioni', 'collections'])
        
        # Common Italian furniture brands
        italian_brands = ['martex', 'manerba', 'las', 'frezza', 'fantoni', 'della valentina', 
                         'bralco', 'ibebi', 'estel', 'arcadia', 'unifor']
        is_known_brand = any(brand in domain for brand in italian_brands)
        
        return (is_italian and has_products_path) or is_known_brand
    
    def _ensure_italian_url(self, url: str) -> str:
        """Ensure URL uses Italian path structure"""
        # If URL has /products/ (English), convert to /it/prodotti/ (Italian)
        if '/products/' in url:
            url = url.replace('/products/', '/it/prodotti/')
        # If URL has /en/ language prefix, change to /it/
        if '/en/' in url:
            url = url.replace('/en/', '/it/')
        # If URL doesn't have /it/ prefix and has /prodotti/, add /it/
        if '/prodotti/' in url and '/it/prodotti/' not in url:
            url = url.replace('/prodotti/', '/it/prodotti/')
        return url
    
    def scrape_brand_website(self, website: str, brand_name: str, limit: Optional[int] = None) -> Dict:
        """
        Scrape an Italian furniture brand website
        
        Args:
            website: Brand website URL
            brand_name: Name of the brand
            limit: Maximum number of products to scrape (optional)
        
        Returns:
            Dictionary with scraped data
        """
        from utils.selenium_scraper import SeleniumScraper
        
        logger.info(f"🇮🇹 Starting Italian Furniture Scraper for {brand_name}")
        logger.info(f"Original Website: {website}")
        
        # First ensure correct Italian format, then try English
        website = self._ensure_italian_url(website)
        english_website = website.replace('/it/', '/en/')
        
        scraped_data = {
            'source': 'brand_website',
            'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_products': 0,
            'collections': {},
            'category_tree': {}
        }
        
        scraper = None
        use_selenium = True
        soup = None
        
        try:
            scraper = SeleniumScraper(headless=True, timeout=60)
        except (ImportError, Exception) as e:
            error_msg = str(e)
            if "Chrome browser not found" in error_msg or "Cannot initialize Chrome" in error_msg:
                logger.warning(f"Selenium not available (Chrome not found): {e}")
                logger.info("Falling back to requests-based scraping for Italian furniture site")
                use_selenium = False
                # Fall back to requests-based scraping
                import requests
                
                try:
                    response = requests.get(english_website, headers=self.base_headers, timeout=30)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.content, 'html.parser')
                    if not soup:
                        response = requests.get(website, headers=self.base_headers, timeout=30)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.content, 'html.parser')
                        english_website = website
                        website = english_website
                except Exception as req_e:
                    logger.error(f"Requests-based scraping also failed: {req_e}")
                    return scraped_data
            else:
                raise
        
        try:
            if use_selenium and scraper:
                # Try English version first for English content
                logger.info(f"Trying English URL: {english_website}")
                soup = scraper.get_page(english_website, wait_for_selector='body', wait_time=10)
                
                if not soup:
                    if use_selenium and scraper:
                        logger.warning("Failed to load English page, trying Italian...")
                        logger.info(f"Loading Italian URL: {website}")
                        soup = scraper.get_page(website, wait_for_selector='body', wait_time=10)
                        english_website = website  # Use Italian URL for remaining requests
                else:
                    # Already tried requests, no soup means failure
                    logger.error("Failed to load page with requests")
                    return scraped_data
            else:
                logger.info("✓ Successfully loaded English version")
                website = english_website  # Use English URL for remaining requests
            
            if not soup:
                logger.error("Failed to load both English and Italian pages")
                return scraped_data
            
            if use_selenium and scraper:
                # Enhanced scrolling to load ALL content (especially bottom categories)
                logger.info("Scrolling to load all categories...")
                
                # Multiple scrolls to ensure everything loads
                for i in range(3):
                    scraper.scroll_to_bottom(pause_time=2.0)
                    time.sleep(1.5)
                    logger.debug(f"  Scroll pass {i+1}/3 completed")
                
                # Final wait for any lazy-loaded content
                time.sleep(2)
                
                # Refresh soup after scrolling
            soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
            
            # Find category links (use the website URL that actually worked)
            category_links = self._find_category_links(soup, website)
            
            if website == english_website and '/en/' in website:
                logger.info(f"Found {len(category_links)} categories from English page")
            else:
                logger.info(f"Found {len(category_links)} categories from Italian page")
            
            # Scrape each category
            for cat_name, cat_url in category_links.items():
                logger.info(f"Scraping category: {cat_name}")
                
                try:
                    if use_selenium and scraper:
                        category_products = self._scrape_category(scraper, cat_url, cat_name, brand_name)
                    else:
                        # Use requests-based scraping for category
                        import requests
                        response = requests.get(cat_url, headers=self.base_headers, timeout=30)
                        response.raise_for_status()
                        cat_soup = BeautifulSoup(response.content, 'html.parser')
                        # Find product links
                        product_links = self._find_product_links(cat_soup, cat_url)
                        logger.info(f"  Found {len(product_links)} product links in {cat_name}")
                        
                        # Scrape each product
                        category_products = []
                        for product_url in product_links[:20]:  # Limit to 20 products per category
                            try:
                                prod_response = requests.get(product_url, headers=self.base_headers, timeout=30)
                                prod_response.raise_for_status()
                                prod_soup = BeautifulSoup(prod_response.content, 'html.parser')
                                product_data = self._scrape_product_page_requests(prod_soup, product_url, cat_name, brand_name)
                                if product_data:
                                    category_products.append(product_data)
                                time.sleep(self.delay)
                            except Exception as e:
                                logger.debug(f"Error scraping product {product_url}: {e}")
                                continue
                    
                    if category_products:
                        # Add to collections
                        scraped_data['collections'][cat_name] = {
                            'url': cat_url,
                            'product_count': len(category_products),
                            'products': category_products
                        }
                        
                        # Add to category_tree
                        if cat_name not in scraped_data['category_tree']:
                            scraped_data['category_tree'][cat_name] = {
                                'subcategories': {
                                    'General': {
                                        'products': []
                                    }
                                }
                            }
                        
                        scraped_data['category_tree'][cat_name]['subcategories']['General']['products'].extend(category_products)
                        scraped_data['total_products'] += len(category_products)
                        
                        logger.info(f"✓ Scraped {len(category_products)} products from {cat_name}")
                    
                    # Check limit
                    if limit and scraped_data['total_products'] >= limit:
                        logger.info(f"Reached product limit ({limit})")
                        break
                    
                    time.sleep(self.delay)
                    
                except Exception as e:
                    logger.error(f"Error scraping category {cat_name}: {e}")
                    continue
            
            logger.info(f"✅ Scraping complete: {scraped_data['total_products']} products from {len(scraped_data['collections'])} categories")
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            logger.exception("Full traceback:")
        
        finally:
            if scraper:
                try:
                    scraper.close()
                except:
                    pass
        
        return scraped_data
    
    def _find_category_links(self, soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
        """Find category links on the products page"""
        category_links = {}
        
        # Keywords to exclude (not product categories)
        exclude_keywords = ['newsletter', 'privacy', 'cookie', 'contatti', 'contact', 
                           'about', 'chi siamo', 'azienda', 'company', 'news', 
                           'eventi', 'events', 'download', 'catalogo', 'catalog']
        
        logger.info("Searching for category sections...")
        
        # Strategy 1: Look for divs with "Leggi di più" (Read more) links
        # Cast a wider net to catch all possible category containers
        category_sections = soup.find_all(['div', 'article', 'section'], 
                                         class_=re.compile(r'product|category|item|card|col|box|tile|grid', re.I))
        
        # Also look for sections without specific classes (Martex might use generic divs)
        if len(category_sections) < 5:  # If we found too few, expand search
            logger.debug(f"  Only found {len(category_sections)} sections with classes, expanding search...")
            all_divs = soup.find_all(['div', 'article', 'section'])
            category_sections.extend(all_divs)
            logger.debug(f"  Now searching through {len(category_sections)} total sections")
        else:
            logger.debug(f"  Found {len(category_sections)} potential category sections")
        
        for section in category_sections:
            # Find category name (usually in h2, h3, or strong tags)
            name_elem = section.find(['h2', 'h3', 'h4', 'strong', 'span'], class_=re.compile(r'title|name|heading', re.I))
            if not name_elem:
                name_elem = section.find(['h2', 'h3', 'h4'])
            
            # Find "Leggi di più" or similar links
            link_elem = section.find('a', string=re.compile(r'leggi|read|più|more|scopri|discover', re.I))
            if not link_elem:
                link_elem = section.find('a', href=True)
            
            if name_elem and link_elem:
                cat_name = name_elem.get_text(strip=True)
                cat_url = urljoin(base_url, link_elem.get('href', ''))
                
                # Clean category name
                cat_name = re.sub(r'\s+', ' ', cat_name).strip()
                
                # Skip if category name or URL contains excluded keywords
                if any(keyword in cat_name.lower() for keyword in exclude_keywords):
                    logger.debug(f"  Skipping non-product category: {cat_name}")
                    continue
                
                if any(keyword in cat_url.lower() for keyword in exclude_keywords):
                    logger.debug(f"  Skipping non-product URL: {cat_url}")
                    continue
                
                if cat_name and len(cat_name) > 1 and cat_url:
                    # Avoid duplicates
                    if cat_name not in category_links:
                        # Keep URL as-is (don't force English conversion here)
                        category_links[cat_name] = cat_url
                        logger.info(f"  ✓ Found category: {cat_name}")
                    else:
                        logger.debug(f"  ⊗ Duplicate category skipped: {cat_name}")
        
        # Strategy 2: Look for navigation menu links
        if not category_links:
            nav_sections = soup.find_all(['nav', 'ul', 'div'], class_=re.compile(r'menu|nav|category', re.I))
            for nav in nav_sections:
                links = nav.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    # Skip excluded keywords
                    if any(keyword in text.lower() for keyword in exclude_keywords):
                        continue
                    
                    if any(keyword in href.lower() for keyword in exclude_keywords):
                        continue
                    
                    # Filter for product-related links
                    if any(keyword in href.lower() for keyword in ['prodot', 'product', 'collezi', 'collection', 'categor']):
                        if text and len(text) > 1 and text not in category_links:
                            full_url = urljoin(base_url, href)
                            category_links[text] = full_url
                            logger.info(f"  ✓ Found nav category: {text}")
        
        # Log summary
        logger.info(f"📦 Category detection complete: {len(category_links)} categories found")
        if category_links:
            logger.info(f"Categories: {', '.join(category_links.keys())}")
        
        return category_links
    
    def _scrape_category(self, scraper, category_url: str, category_name: str, brand_name: str) -> List[Dict]:
        """Scrape products from a category page"""
        products = []
        
        try:
            # Load category page
            soup = scraper.get_page(category_url, wait_for_selector='body', wait_time=10)
            
            if not soup:
                return products
            
            # Enhanced scrolling to load all products
            logger.debug(f"  Scrolling category page to load all products...")
            for i in range(2):  # 2 passes for category pages
                scraper.scroll_to_bottom(pause_time=2.0)
                time.sleep(1.5)
            time.sleep(2)
            
            soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
            
            # Find product links
            product_links = self._find_product_links(soup, category_url)
            logger.info(f"  Found {len(product_links)} product links in {category_name}")
            
            # Scrape each product (limit to avoid too many requests)
            for product_url in product_links[:20]:  # Limit to 20 products per category for speed
                try:
                    product_data = self._scrape_product_page(scraper, product_url, category_name, brand_name)
                    if product_data:
                        products.append(product_data)
                    time.sleep(self.delay)
                except Exception as e:
                    logger.debug(f"Error scraping product {product_url}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error scraping category page {category_url}: {e}")
        
        return products
    
    def _find_product_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find product page links on a category page"""
        product_links = []
        seen_urls = set()
        
        # Look for product links
        # Italian sites often use: /prodotto/, /product/, or have product IDs in URLs
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            full_url = urljoin(base_url, href)
            
            # Filter for product links
            is_product = any(keyword in href.lower() for keyword in [
                '/prodotto/', '/product/', '/item/', 
                'detail', 'scheda', 'articolo'
            ])
            
            # Avoid navigation/menu links
            is_nav = any(keyword in href.lower() for keyword in [
                'menu', 'nav', 'categor', 'filter', 'sort', 
                'javascript:', '#', 'mailto:'
            ])
            
            if is_product and not is_nav and full_url not in seen_urls:
                product_links.append(full_url)
                seen_urls.add(full_url)
        
        # If no product links found, look for any links in product containers
        if not product_links:
            product_containers = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
            for container in product_containers:
                link = container.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    full_url = urljoin(base_url, href)
                    if full_url not in seen_urls and not any(skip in href for skip in ['#', 'javascript:', 'mailto:']):
                        product_links.append(full_url)
                        seen_urls.add(full_url)
        
        return product_links
    
    def _scrape_product_page(self, scraper, product_url: str, category: str, brand_name: str) -> Optional[Dict]:
        """Scrape individual product page"""
        try:
            soup = scraper.get_page(product_url, wait_for_selector='body', wait_time=8)
            
            if not soup:
                return None
            
            # Wait for images to load (common issue with lazy loading)
            time.sleep(1)
            
            # Refresh soup to get updated page with loaded images
            soup = BeautifulSoup(scraper.driver.page_source, 'html.parser')
            
            # Extract product name
            name = None
            name_elem = soup.find(['h1', 'h2'], class_=re.compile(r'product|title|name', re.I))
            if not name_elem:
                name_elem = soup.find(['h1', 'h2'])
            if name_elem:
                name = name_elem.get_text(strip=True)
            
            # Extract product ID from URL
            product_id = None
            id_match = re.search(r'/(\d+)/?$', product_url)
            if id_match:
                product_id = id_match.group(1)
            else:
                # Try to extract from slug
                slug_match = re.search(r'/([^/]+)/?$', product_url)
                if slug_match:
                    product_id = slug_match.group(1)
            
            # Extract image - Multiple strategies for better success
            image_url = None
            
            # Strategy 1: Look for product/featured images by class
            img = soup.find('img', class_=re.compile(r'product|main|primary|featured|attachment|wp-post-image', re.I))
            
            # Strategy 2: Look in product galleries or image containers
            if not img:
                gallery = soup.find(['div', 'figure', 'section'], class_=re.compile(r'gallery|image|photo|slider|carousel', re.I))
                if gallery:
                    img = gallery.find('img')
            
            # Strategy 3: Look in main content area
            if not img:
                content = soup.find(['div', 'section', 'article'], class_=re.compile(r'content|main|product|entry', re.I))
                if content:
                    img = content.find('img')
            
            # Strategy 4: Find any large image (avoid logos/icons)
            if not img:
                all_imgs = soup.find_all('img')
                for test_img in all_imgs:
                    # Skip small images (likely icons/logos)
                    width = test_img.get('width', '')
                    height = test_img.get('height', '')
                    if width and height:
                        try:
                            if int(width) > 200 and int(height) > 200:
                                img = test_img
                                break
                        except:
                            pass
                    # Also check src for product indicators
                    src = test_img.get('src', '') + test_img.get('data-src', '')
                    if any(keyword in src.lower() for keyword in ['product', 'gallery', 'upload', 'media']):
                        img = test_img
                        break
            
            # Strategy 5: Just take the first decent image
            if not img:
                all_imgs = soup.find_all('img')
                for test_img in all_imgs:
                    src = test_img.get('src', '') or test_img.get('data-src', '')
                    # Avoid logos, icons, and tracking pixels
                    if src and not any(skip in src.lower() for skip in ['logo', 'icon', 'favicon', 'tracking', 'pixel', '1x1']):
                        img = test_img
                        break
            
            # Extract image URL with multiple fallbacks
            if img:
                # Try all possible image attributes
                image_url = (
                    img.get('src') or 
                    img.get('data-src') or 
                    img.get('data-lazy-src') or
                    img.get('data-original') or
                    img.get('data-lazy') or
                    img.get('data-srcset', '').split(',')[0].strip().split(' ')[0] if img.get('data-srcset') else None
                )
                
                # Also check srcset attribute
                if not image_url and img.get('srcset'):
                    srcset = img.get('srcset', '')
                    # srcset format: "url1 1x, url2 2x" - take first URL
                    if srcset:
                        image_url = srcset.split(',')[0].strip().split(' ')[0]
                
                if image_url:
                    # Make absolute URL
                    image_url = urljoin(product_url, image_url)
                    logger.info(f"  ✓ Found image: {image_url[:80]}...")
                else:
                    logger.warning(f"  ✗ Image element found but no src/data-src attribute")
                    logger.debug(f"    Image tag attributes: {img.attrs}")
            else:
                logger.warning(f"  ✗ No image found on page: {product_url}")
            
            # Extract description
            description = ""
            desc_elem = soup.find(['div', 'p'], class_=re.compile(r'description|desc|content|text', re.I))
            if desc_elem:
                description = desc_elem.get_text(strip=True)[:500]
            
            if not name:
                name = "Unknown Product"
            
            # Log extraction results
            logger.debug(f"  ✓ Extracted: {name}")
            logger.debug(f"    Image: {'✓' if image_url else '✗'}")
            logger.debug(f"    Description: {len(description)} chars")
            
            return {
                'name': name,  # Changed from 'model' to 'name' for consistency
                'image_url': image_url,
                'source_url': product_url,
                'product_id': product_id or '',
                'description': description,
                'category_path': [category],
                'brand': brand_name,
                'price': None,
                'price_range': 'Contact for price',
                'features': [],
                'specifications': {}
            }
        
        except Exception as e:
            logger.debug(f"Error extracting product data from {product_url}: {e}")
            return None

    def _scrape_product_page_requests(self, soup: BeautifulSoup, product_url: str, category: str, brand_name: str) -> Optional[Dict]:
        """Scrape individual product page using requests (no Selenium)"""
        try:
            if not soup:
                return None
            
            # Extract product name
            name = None
            name_elem = soup.find(['h1', 'h2'], class_=re.compile(r'product|title|name', re.I))
            if not name_elem:
                name_elem = soup.find(['h1', 'h2'])
            if name_elem:
                name = name_elem.get_text(strip=True)
            
            # Extract product ID from URL
            product_id = None
            id_match = re.search(r'/(\d+)/?$', product_url)
            if id_match:
                product_id = id_match.group(1)
            else:
                # Try to extract from slug
                slug_match = re.search(r'/([^/]+)/?$', product_url)
                if slug_match:
                    product_id = slug_match.group(1)
            
            # Extract image - Same strategies as Selenium version
            image_url = None
            img = soup.find('img', class_=re.compile(r'product|main|primary|featured|attachment|wp-post-image', re.I))
            
            if not img:
                gallery = soup.find(['div', 'figure', 'section'], class_=re.compile(r'gallery|image|photo|slider|carousel', re.I))
                if gallery:
                    img = gallery.find('img')
            
            if not img:
                content = soup.find(['div', 'section', 'article'], class_=re.compile(r'content|main|product|entry', re.I))
                if content:
                    img = content.find('img')
            
            if not img:
                all_imgs = soup.find_all('img')
                for test_img in all_imgs:
                    width = test_img.get('width', '')
                    height = test_img.get('height', '')
                    if width and height:
                        try:
                            if int(width) > 200 and int(height) > 200:
                                img = test_img
                                break
                        except:
                            pass
                    src = test_img.get('src', '') + test_img.get('data-src', '')
                    if any(keyword in src.lower() for keyword in ['product', 'gallery', 'upload', 'media']):
                        img = test_img
                        break
            
            if not img:
                all_imgs = soup.find_all('img')
                for test_img in all_imgs:
                    src = test_img.get('src', '') or test_img.get('data-src', '')
                    if src and not any(skip in src.lower() for skip in ['logo', 'icon', 'favicon', 'tracking', 'pixel', '1x1']):
                        img = test_img
                        break
            
            if img:
                image_url = (
                    img.get('src') or 
                    img.get('data-src') or 
                    img.get('data-lazy-src') or
                    img.get('data-original') or
                    img.get('data-lazy') or
                    img.get('data-srcset', '').split(',')[0].strip().split(' ')[0] if img.get('data-srcset') else None
                )
                
                if not image_url and img.get('srcset'):
                    srcset = img.get('srcset', '')
                    if srcset:
                        image_url = srcset.split(',')[0].strip().split(' ')[0]
                
                if image_url:
                    image_url = urljoin(product_url, image_url)
            
            # Extract description
            description = ""
            desc_elem = soup.find(['div', 'p'], class_=re.compile(r'description|desc|content|text', re.I))
            if desc_elem:
                description = desc_elem.get_text(strip=True)[:500]
            
            if not name:
                name = "Unknown Product"
            
            return {
                'name': name,
                'url': product_url,
                'product_id': product_id or '',
                'category': category,
                'subcategory': 'General',
                'image_url': image_url,
                'description': description,
                'specifications': {}
            }
        
        except Exception as e:
            logger.debug(f"Error extracting product data from {product_url}: {e}")
            return None


