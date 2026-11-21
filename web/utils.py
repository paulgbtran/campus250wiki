import os
import json
import logging
import time
import requests
from pathlib import Path
from google import genai

logging.basicConfig(level=logging.INFO)

def get_serper_client() -> str:
    """Returns the Serper API key from environment variables if present."""
    return os.environ.get("SERPER_API_KEY")

def get_google_client() -> genai.Client:
    """Returns the Google GenAI Client if GEMINI_API_KEY is present."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logging.error("GEMINI_API_KEY is not set.")
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logging.error(f"Failed to initialize Gemini Client: {e}")
        return None

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Wikimedia requires a descriptive User-Agent with contact info to prevent HTTP 429
_WIKIMEDIA_UA = (
    "Campus250WikiBot/1.0 (https://github.com/campus250wiki; tranb9@lasalle.edu) python-requests"
)


def make_request(url: str, method: str = "GET", headers: dict = None, body: dict = None) -> requests.Response:
    """Makes an HTTP request using requests and returns the response object."""
    if headers is None:
        headers = {}
    if "User-Agent" not in headers:
        if "wikimedia.org" in url or "wikipedia.org" in url:
            headers["User-Agent"] = _WIKIMEDIA_UA
        else:
            headers["User-Agent"] = _DEFAULT_UA
    try:
        if method.upper() == "POST":
            if body and isinstance(body, dict):
                res = requests.post(url, headers=headers, json=body, timeout=10.0, allow_redirects=True)
            else:
                res = requests.post(url, headers=headers, data=body, timeout=10.0, allow_redirects=True)
        else:
            res = requests.get(url, headers=headers, timeout=10.0, allow_redirects=True)
        return res
    except Exception as e:
        logging.error(f"Error making request to {url}: {e}")
        return None


def download_image(url: str, dest_path: Path, retries: int = 3, timeout: float = 30.0) -> bool:
    """
    Downloads a binary image from *url* to *dest_path* with chunked streaming,
    redirect following, retry logic, and a generous timeout.
    Returns True on success, False on failure.
    """
    is_wikimedia = "wikimedia.org" in url or "wikipedia.org" in url
    ua = _WIKIMEDIA_UA if is_wikimedia else _DEFAULT_UA

    headers = {
        "User-Agent": ua,
        # Wikimedia and some CDNs reject requests without Accept
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }
    if not is_wikimedia:
        headers["Referer"] = "https://www.google.com/"

    for attempt in range(1, retries + 1):
        try:
            if is_wikimedia:
                time.sleep(0.3)  # Polite delay to prevent triggering rate limits
            with requests.get(
                url,
                headers=headers,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
            ) as res:
                if res.status_code != 200:
                    logging.warning(
                        f"[Attempt {attempt}/{retries}] HTTP {res.status_code} for {url}"
                    )
                    if res.status_code == 429:
                        # Handle rate limiting: respect Retry-After or back off at least 5 seconds
                        retry_after = res.headers.get("Retry-After")
                        sleep_time = float(retry_after) + 1.0 if retry_after and retry_after.isdigit() else max(5.0, 2 ** (attempt + 1))
                        logging.info(f"Rate limited (HTTP 429) on {url}. Waiting {sleep_time:.1f}s before retry...")
                        time.sleep(sleep_time)
                        continue
                    if attempt < retries:
                        time.sleep(2 ** attempt)  # exponential back-off
                    continue
                content_type = res.headers.get("Content-Type", "")
                if "text/html" in content_type or "text/xml" in content_type:
                    logging.warning(
                        f"[Attempt {attempt}/{retries}] URL returned HTML/XML, not an image: {url}"
                    )
                    return False
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                if dest_path.stat().st_size < 512:
                    logging.warning(
                        f"[Attempt {attempt}/{retries}] Downloaded file suspiciously small ({dest_path.stat().st_size} bytes): {url}"
                    )
                    dest_path.unlink(missing_ok=True)
                    return False
                return True
        except requests.exceptions.Timeout:
            logging.warning(f"[Attempt {attempt}/{retries}] Timeout downloading {url}")
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"[Attempt {attempt}/{retries}] Connection error for {url}: {e}")
        except Exception as e:
            logging.error(f"[Attempt {attempt}/{retries}] Unexpected error downloading {url}: {e}")
        if attempt < retries:
            time.sleep(2 ** attempt)
    return False

def download_image_and_save_json(url: str, save_dir: str | Path, filename_prefix: str, topic: str = "") -> str:
    """
    Downloads an image from a URL, saves it to save_dir,
    and saves a JSON metadata file with the original URL.
    Returns the saved filename (with extension) on success, or None on failure.
    """
    import re
    # Sanitise: replace spaces with underscores, keep alphanumeric / _ / -
    safe_prefix = "".join(
        c if (c.isalnum() or c in ("_", "-")) else "_"
        for c in filename_prefix
    ).strip("_")
    safe_prefix = re.sub(r'_+', '_', safe_prefix)

    # Determine extension from URL, fall back to .jpg
    ext = ".jpg"
    lower_url = url.lower().split("?")[0]  # ignore query params for ext detection
    for possible_ext in (".png", ".jpeg", ".jpg", ".webp", ".gif"):
        if lower_url.endswith(possible_ext):
            ext = possible_ext
            break

    img_filename = f"{safe_prefix}{ext}"
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    img_filepath = save_path / img_filename
    json_filepath = save_path / f"{safe_prefix}.json"

    # If the file already exists and is non-empty, avoid redundant download
    if img_filepath.exists() and img_filepath.stat().st_size >= 512:
        logging.info(f"Image already exists: {img_filepath.name}")
        return img_filename

    # Download using the robust streaming helper
    success = download_image(url, img_filepath)
    if success:
        try:
            metadata = {
                "original_url": url,
                "local_path": img_filename,
                "topic": topic or filename_prefix
            }
            json_filepath.write_text(json.dumps(metadata, indent=4), encoding="utf-8")
            logging.info(f"Successfully downloaded image to {img_filepath}")
            return img_filename
        except Exception as e:
            logging.error(f"Failed to save metadata JSON for {img_filepath}: {e}")
            return img_filename  # image saved even if JSON failed
    else:
        logging.error(f"Failed to download image from {url}")

    return None
