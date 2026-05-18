"""
Product Data Enrichment Utility
Fetches and adds product images and descriptions to BOQ data
"""

import logging
from typing import Dict, List
from utils.universal_brand_scraper import UniversalBrandScraper
from utils.image_helper import download_image
import os

logger = logging.getLogger(__name__)


class ProductEnricher:
    """Enriches product data with images and descriptions"""
    
    def __init__(self):
        self.scraper = UniversalBrandScraper()
        self.cache = {}  # Cache fetched product details
    
    def enrich_boq_data(self, boq_data: Dict, session_id: str, use_selenium: bool = False) -> Dict:
        """
        Enrich BOQ data with product images and descriptions
        
        Args:
            boq_data: BOQ data structure with tables
            session_id: Session ID for file storage
            use_selenium: Whether to use Selenium for fetching details
            
        Returns:
            Enriched BOQ data with image_url and description fields
        """
        logger.info("Starting product data enrichment...")
        
        enriched_data = boq_data.copy()
        
        if 'tables' not in enriched_data:
            logger.warning("No tables found in BOQ data")
            return enriched_data
        
        total_enriched = 0
        
        for table_idx, table in enumerate(enriched_data['tables']):
            if 'rows' not in table:
                continue
            
            for row_idx, row in enumerate(table['rows']):
                # Look for product URL or brand/model info
                product_url = self._extract_product_url(row)
                
                if product_url:
                    # Fetch product details
                    details = self._get_product_details(product_url, use_selenium)
                    
                    if details:
                        # Add image
                        if details.get('image_url'):
                            # Download and cache image
                            cached_image = download_image(details['image_url'])
                            if cached_image:
                                row['image_path'] = cached_image
                                row['image_url'] = details['image_url']
                        
                        # Add description
                        if details.get('description'):
                            row['description'] = details['description']
                        
                        # Add features if available
                        if details.get('features'):
                            row['features'] = details['features']
                        
                        # Add price if available
                        if details.get('price'):
                            row['manufacturer_price'] = details['price']
                        
                        total_enriched += 1
                        logger.info(f"Enriched product {row_idx + 1} in table {table_idx + 1}")
        
        logger.info(f"Enrichment complete. Enriched {total_enriched} products.")
        return enriched_data
    
    def _extract_product_url(self, row: Dict) -> str:
        """Extract product URL from row data"""
        # Look for common URL field names
        url_fields = ['source_url', 'product_url', 'url', 'link', 'product_link']
        
        for field in url_fields:
            if field in row and row[field]:
                url = str(row[field]).strip()
                if url.startswith('http'):
                    return url
        
        # Look in any field that might contain a URL
        for key, value in row.items():
            if isinstance(value, str) and value.startswith('http'):
                return value
        
        return None
    
    def _get_product_details(self, product_url: str, use_selenium: bool = False) -> Dict:
        """Get product details from cache or fetch"""
        # Check cache
        if product_url in self.cache:
            return self.cache[product_url]
        
        # Fetch details
        try:
            details = self.scraper.fetch_product_details(product_url, use_selenium)
            self.cache[product_url] = details
            return details
        except Exception as e:
            logger.error(f"Error fetching details for {product_url}: {e}")
            return {}
    
    def enrich_product_selection_data(self, products: List[Dict], use_selenium: bool = False) -> List[Dict]:
        """
        Enrich product selection data with images and descriptions
        
        Args:
            products: List of product dicts with source_url
            use_selenium: Whether to use Selenium
            
        Returns:
            Enriched product list
        """
        enriched_products = []
        
        for product in products:
            enriched = product.copy()
            
            # If product already has image and description, skip
            if enriched.get('image_url') and enriched.get('description'):
                enriched_products.append(enriched)
                continue
            
            # Get product URL
            product_url = product.get('source_url') or product.get('url')
            
            if product_url:
                details = self._get_product_details(product_url, use_selenium)
                
                # Add missing fields
                if not enriched.get('image_url') and details.get('image_url'):
                    # Download image
                    cached_image = download_image(details['image_url'])
                    if cached_image:
                        enriched['image_path'] = cached_image
                        enriched['image_url'] = details['image_url']
                
                if not enriched.get('description') and details.get('description'):
                    enriched['description'] = details['description']
                
                if details.get('features'):
                    enriched['features'] = details['features']
                
                if details.get('price'):
                    enriched['manufacturer_price'] = details['price']
            
            enriched_products.append(enriched)
        
        return enriched_products


def enrich_session_data(session: Dict, use_selenium: bool = False) -> Dict:
    """
    Enrich all uploaded files in a session with product data
    
    Args:
        session: Flask session dict
        use_selenium: Whether to use Selenium for fetching
        
    Returns:
        Updated session dict
    """
    enricher = ProductEnricher()
    session_id = session.get('session_id', '')
    
    uploaded_files = session.get('uploaded_files', [])
    
    for file_info in uploaded_files:
        # Enrich costed_data if present
        if 'costed_data' in file_info:
            file_info['costed_data'] = enricher.enrich_boq_data(
                file_info['costed_data'],
                session_id,
                use_selenium
            )
        
        # Enrich extracted_data if present
        if 'extracted_data' in file_info:
            file_info['extracted_data'] = enricher.enrich_boq_data(
                file_info['extracted_data'],
                session_id,
                use_selenium
            )
    
    return session
