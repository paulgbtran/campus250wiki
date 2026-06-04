#!/usr/bin/env python3
"""
imageSearch.py
Author: Paul Tran <tranb9@lasalle.edu>

Looks through /data/entries/{topic}.txt and /data/search/{topic}.txt, then performs a 
Google image search for a given topic, takes image link, then loads the links into 
the appropriate place in the template (located /data/web/{topic}.html).
"""
import sys
from pathlib import Path
import logging
import os
import json
import requests
from dotenv import load_dotenv

# Add workspace root to sys.path to import web.utils
rootDir = Path(__file__).parent.parent.parent
sys.path.append(str(rootDir))

from google import genai 
from google.genai import types

from web.utils import get_serper_client, get_google_client, download_image_and_save_json, make_request

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Image extensions considered valid for download
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def is_likely_image_url(url: str) -> bool:
    """Quick pre-check: reject URLs that obviously don't point to an image."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.lower()
        # Accept if path ends with a known image extension
        if any(path.endswith(ext) for ext in _IMAGE_EXTS):
            return True
        # Accept Wikimedia thumb URLs (e.g., /thumb/.../.../500px-...)
        if "wikimedia.org" in parsed.netloc or "wikipedia.org" in parsed.netloc:
            return True
        # Reject obvious HTML pages
        if path.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
            return False
        # Accept URLs with no extension (might be dynamic image endpoints)
        return True
    except Exception:
        return True


def search_images_via_wikimedia(topic: str, num_results: int = 10) -> list[str]:
    """
    Searches Wikimedia Commons for images related to *topic* using the
    MediaWiki opensearch + imageinfo API. Returns direct image URLs.
    This is the most reliable source because the URLs are always real.
    """
    # Step 1: Search for matching file titles on Wikimedia Commons
    search_url = "https://commons.wikimedia.org/w/api.php"
    search_params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": f"{topic} Philadelphia",
        "srnamespace": "6",  # File namespace
        "srlimit": str(num_results),
    }
    try:
        res = make_request(
            search_url + "?" + "&".join(f"{k}={v}" for k, v in search_params.items())
        )
        if not res or res.status_code != 200:
            logging.warning(f"Wikimedia search failed for {topic}")
            return []
        data = res.json()
        titles = [
            item["title"]
            for item in data.get("query", {}).get("search", [])
        ]
    except Exception as e:
        logging.error(f"Wikimedia search error for {topic}: {e}")
        return []

    if not titles:
        return []

    # Step 2: Resolve each file title to a direct image URL via imageinfo
    info_params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": "1200",
        "titles": "|".join(titles),
    }
    try:
        res = make_request(
            search_url + "?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in info_params.items())
        )
        if not res or res.status_code != 200:
            return []
        data = res.json()
        urls = []
        for page in data.get("query", {}).get("pages", {}).values():
            for ii in page.get("imageinfo", []):
                url = ii.get("thumburl") or ii.get("url")
                if url:
                    urls.append(url)
        return urls
    except Exception as e:
        logging.error(f"Wikimedia imageinfo error for {topic}: {e}")
        return []


    """Queries Gemini to find direct image URLs for a topic."""
    prompt = (
        f"Search the web to find 5 real, active, direct image URLs (ending in .jpg, .jpeg, or .png) related to the "
        f"Philadelphia history topic '{topic}'. They should be from Wikimedia Commons or Wikipedia if possible. "
        f"Return ONLY the URLs, one per line. No commentary, no markdown, no other text."
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        urls = []
        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("http://") or line.startswith("https://"):
                # Clean up any trailing characters, brackets, or quotes
                clean_url = line.split()[0].replace('"', '').replace("'", "")
                urls.append(clean_url)
        return urls
    except Exception as e:
        logging.error(f"Gemini image search failed for {topic}: {e}")
        return []


def search_images_via_serper(api_key: str, topic: str) -> list[str]:
    """Queries Serper API to find image search result URLs."""
    url = "https://google.serper.dev/images"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    body = {
        "q": f"Philadelphia {topic}",
        "num": 10
    }
    res = make_request(url, method="POST", headers=headers, body=body)
    if res and res.status_code == 200:
        try:
            data = res.json()
            urls = []
            for item in data.get("images", []):
                img_url = item.get("imageUrl")
                if img_url:
                    urls.append(img_url)
            return urls
        except Exception as e:
            logging.error(f"Failed to parse Serper response for {topic}: {e}")
    return []


def process_topic(topic: str, client: genai.Client, serper_key: str, web_dir: Path):
    """Processes a single topic, searching and loading images into its HTML file."""
    html_file = web_dir / f"{topic}.html"
    if not html_file.exists():
        logging.warning(f"HTML file not found: {html_file}")
        return
        
    logging.info(f"Processing image search for: {topic}...")
    
    # Get candidate URLs
    candidates = []
    if serper_key:
        logging.info("Searching images via Serper API...")
        candidates = search_images_via_serper(serper_key, topic)
        
    if not candidates:
        logging.info("Searching/Generating images via Gemini...")
        candidates = search_images_via_serper(client, topic)
        
    logging.info(f"Found {len(candidates)} candidate image URLs.")
    
    # Attempt to download up to 3 images
    downloaded_files = []
    for url in candidates:
        if len(downloaded_files) >= 3:
            break
        suffix = "hero" if len(downloaded_files) == 0 else str(len(downloaded_files))
        prefix = f"{topic}_{suffix}"
        
        # Check if already downloaded/exists
        existing_files = list(web_dir.glob(f"{prefix}.*"))
        existing_files = [f for f in existing_files if f.suffix != ".json"]
        if existing_files:
            logging.info(f"Image for {prefix} already exists: {existing_files[0].name}")
            downloaded_files.append(existing_files[0].name)
            continue
            
        filename = download_image_and_save_json(url, web_dir, prefix)
        if filename:
            downloaded_files.append(filename)
            
    if len(downloaded_files) < 3:
        logging.warning(f"Could only download {len(downloaded_files)} images for {topic}. Falling back/duplicating if needed.")
        # If we got at least 1 image, reuse it to avoid broken image placeholders
        while len(downloaded_files) < 3 and downloaded_files:
            downloaded_files.append(downloaded_files[0])
            
    if not downloaded_files:
        logging.error(f"No images could be downloaded for {topic}.")
        return
        
    # Read HTML and update paths
    html_content = html_file.read_text(encoding="utf-8")
    
    # 1. Hero image: src="./thumbnail_modified.webp" -> src="./{hero_img}"
    hero_img = downloaded_files[0]
    html_content = html_content.replace('src="./thumbnail_modified.webp"', f'src="./{hero_img}"')
    html_content = html_content.replace('alt="City Hall"', f'alt="{topic} Hero Image"')
    
    # 2. Article image 1: src="./Philadelphia_City_Hall_7.jpg" -> src="./{img1}"
    img1 = downloaded_files[1] if len(downloaded_files) > 1 else hero_img
    html_content = html_content.replace('src="./Philadelphia_City_Hall_7.jpg"', f'src="./{img1}"')
    html_content = html_content.replace('alt="Old City Hall"', f'alt="{topic} Image 1"')
    
    # 3. Article image 2: src="./Philadelphia_city_hall.jpg" -> src="./{img2}"
    img2 = downloaded_files[2] if len(downloaded_files) > 2 else img1
    html_content = html_content.replace('src="./Philadelphia_city_hall.jpg"', f'src="./{img2}"')
    html_content = html_content.replace('alt="Tower View"', f'alt="{topic} Image 2"')
    
    # Write back updated HTML
    html_file.write_text(html_content, encoding="utf-8")
    logging.info(f"Updated HTML file for {topic} with new image URLs.")


def main():
    google = get_google_client()
    if not google:
        logging.error("Google client could not be created. Exiting.")
        sys.exit(1)
        
    serper_key = get_serper_client()
    
    entries_dir = rootDir / "data" / "entries"
    web_dir = rootDir / "data" / "web"
    
    if not entries_dir.exists():
        logging.error(f"Entries directory does not exist: {entries_dir}")
        sys.exit(1)
        
    # Process each entry file found in data/entries/
    entry_files = list(entries_dir.glob("*.txt"))
    if not entry_files:
        logging.info("No entry files found in data/entries/.")
        return
        
    for filepath in entry_files:
        topic_name = filepath.stem
        process_topic(topic_name, google, serper_key, web_dir)


if __name__ == "__main__":
    main()