#!/usr/env/bin/python3
import os
import scrapy
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.crawler import CrawlerProcess
from urllib.parse import urlparse

class HistoryScraper(CrawlSpider):
    name = 'history_bot'
    
    # Custom settings to optimize efficiency and minimize 4xx errors
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) USHistoryBot/1.0',
        'CONCURRENT_REQUESTS': 16,      # Number of parallel requests
        'DOWNLOAD_DELAY': 1.0,          # 1 second delay between requests to avoid 429/403
        'ROBOTSTXT_OBEY': True,         # Respect the site's scraping rules
        'RETRY_HTTP_CODES': [408, 429, 500, 502, 503, 504], # Retry on these codes
        'LOG_LEVEL': 'INFO'
    }

    def __init__(self, start_urls=None, *args, **kwargs):
        super(HistoryScraper, self).__init__(*args, **kwargs)
        self.start_urls = start_urls
        # Restrict crawling to the domain of the starting URLs
        self.allowed_domains = [urlparse(url).netloc for url in start_urls]
        
        # Rule: Follow all links that stay within the same domain
        self.rules = (
            Rule(LinkExtractor(allow_domains=self.allowed_domains), callback='parse_item', follow=True),
        )
        self._compile_rules()

    def parse_item(self, response):
        """Processes each page found during the crawl."""
        # Clean the URL to create a safe filename
        page_name = urlparse(response.url).path.strip('/').replace('/', '_') or 'index'
        domain_name = urlparse(response.url).netloc
        filename = f"{domain_name}_{page_name}.txt"

        # Logic to extract the main article text
        # We prioritize <article> tags, then <body>, excluding script/style tags
        paragraphs = response.xpath('//article//p//text() | //main//p//text() | //body//p//text()').getall()
        text_content = "\n".join([p.strip() for p in paragraphs if len(p.strip()) > 20])

        if text_content:
            # Ensure the output directory exists
            os.makedirs('scraped_history', exist_ok=True)
            with open(f'scraped_history/{filename}', 'w', encoding='utf-8') as f:
                f.write(f"SOURCE: {response.url}\n\n")
                f.write(text_content)
        
        yield {
            'url': response.url,
            'file': filename
        }

def run_history_scraper(url_list):
    """
    Entry point to invoke the scraper from a script or CLI.
    :param url_list: List of strings (URLs)
    """
    process = CrawlerProcess()
    process.crawl(HistoryScraper, start_urls=url_list)
    process.start()

if __name__ == "__main__":
    # Example usage: Replace with your actual list of history sites
    targets = [
        "https://www.archives.gov/education/lessons/constitution-day",
        "https://worldhistory.org/United_States_of_America/"
    ]
    run_history_scraper(targets)