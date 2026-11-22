#!/usr/bin/env python3
"""
imageSearch.py
Author: Paul Tran <tranb9@lasalle.edu>

Searches for images related to the context of each synthesized topic in /data/entries/{topic}.txt.
Finds 10-15 images per topic from Wikimedia Commons, Google Gemini (Search Grounding), and Serper.
Images and metadata JSONs for each topic are stored in dedicated per-topic folders (/data/web/{safe_topic}/).
Includes a 30-minute runtime cap, prioritization of topics lacking images, and prints elapsed time,
token usage, estimated API cost, and downloaded image counts.
"""

import sys
import re
import os
import time
import json
import logging
import argparse
from pathlib import Path
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv

# Add workspace root and scripts to sys.path
rootDir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(rootDir))
sys.path.append(str(rootDir / "scripts"))

import gemini_utils
from google import genai
from google.genai import types
from web.utils import (
    get_serper_client,
    get_google_client,
    download_image_and_save_json,
    make_request,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MODEL_NAME = "gemini-3.5-flash"
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_DISALLOWED_EXTS = (".ogg", ".ogv", ".oga", ".mp3", ".wav", ".webm", ".mp4", ".pdf", ".djvu", ".tif", ".tiff")


def _fmt_duration(seconds: float) -> str:
    """Formats seconds into human-readable duration."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def is_likely_image_url(url: str) -> bool:
    """Quick pre-check: accept URLs that likely point to a valid image."""
    try:
        parsed = urlparse(url)
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in _DISALLOWED_EXTS):
            return False
        if any(path.endswith(ext) for ext in _IMAGE_EXTS):
            return True
        if "wikimedia.org" in parsed.netloc or "wikipedia.org" in parsed.netloc:
            return True
        if path.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
            return False
        return True
    except Exception:
        return True


def sanitize_prefix(prefix: str) -> str:
    """Sanitizes topic prefix for consistent directory/file naming."""
    safe = "".join(c if (c.isalnum() or c in ("_", "-")) else "_" for c in prefix).strip("_")
    return re.sub(r'_+', '_', safe)


def parse_entry_context(filepath: Path) -> dict:
    """
    Parses a synthesized markdown entry file from data/entries/<topic>.txt.
    Extracts canonical title, metadata fields from the Infobox, lead section summary,
    and constructs targeted contextual search queries.
    """
    stem_clean = filepath.stem
    if " - " in stem_clean and ("(" in stem_clean or "`" in stem_clean):
        stem_clean = stem_clean.split(" - ")[0].strip()
    stem_clean = stem_clean.replace("`", "").strip(" '\"")

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logging.error(f"Error reading entry file {filepath}: {e}")
        return {
            "title": stem_clean,
            "summary": stem_clean,
            "infobox": [],
            "queries": [f"{stem_clean} Philadelphia"]
        }

    lines = content.splitlines()
    title = ""
    infobox_rows = []
    lead_lines = []
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("---", "===", "***")):
            continue

        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
        elif stripped.startswith("## ") or stripped.startswith("### "):
            header_text = stripped.lstrip("#").strip()
            if "infobox" in header_text.lower():
                current_section = "infobox"
            elif "lead" in header_text.lower():
                current_section = "lead"
            else:
                if current_section == "lead":
                    current_section = "other"
                elif current_section != "infobox":
                    current_section = "other"
        else:
            if current_section == "infobox":
                if stripped.startswith("|") and stripped.endswith("|"):
                    parts = [p.strip() for p in stripped.split("|")[1:-1]]
                    if len(parts) >= 2:
                        k = parts[0].replace("**", "").replace("*", "").strip()
                        v = parts[1].replace("<br>", " ").strip()
                        if k and v and not all(c in "-:" for c in k):
                            infobox_rows.append((k, v))
            elif current_section == "lead":
                lead_lines.append(line)
            elif stripped.startswith("|"):
                cell = stripped.strip("|").strip()
                cell_clean = re.sub(r'[*_`#]', '', cell).strip()
                if "infobox" in cell_clean.lower():
                    current_section = "infobox"
                    if ":" in cell_clean:
                        potential_title = cell_clean.split(":", 1)[1].strip()
                        if potential_title and not title:
                            title = potential_title
                elif not title and not cell_clean.startswith(":") and not cell_clean.startswith("-") and not any(h in cell_clean.lower() for h in ("key", "metadata", "factor", "detail")):
                    title = cell_clean

    if not title or len(title) < 2 or title.startswith(("-", "=", "*")):
        title = stem_clean

    title = re.sub(r'[*_`#]', '', title).strip()
    if " - " in title and ("(" in title or "`" in filepath.stem):
        title = title.split(" - ")[0].strip()

    lead_text = " ".join(lead_lines).strip()
    lead_clean = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', lead_text)
    lead_clean = re.sub(r'[*_`#]', '', lead_clean)
    lead_summary = lead_clean[:1200]

    # Build contextual queries
    queries = []
    if "philadelphia" in title.lower():
        queries.append(title)
    else:
        queries.append(f"{title} Philadelphia")

    key_entities = []
    for k, v in infobox_rows:
        k_lower = k.lower()
        v_clean = re.sub(r'[*_`#]', '', v).split("(")[0].strip()
        if any(term in k_lower for term in ("figure", "author", "artist", "host", "person", "founder", "architect", "name")):
            for name in re.split(r'[,;]|\band\b', v_clean):
                name = name.strip()
                if 2 < len(name) < 50:
                    key_entities.append(name)
        elif any(term in k_lower for term in ("location", "setting", "place", "facility", "headquarters")):
            for loc in re.split(r'[,;]', v_clean):
                loc = loc.strip()
                if 3 < len(loc) < 60:
                    key_entities.append(loc)

    for entity in key_entities[:2]:
        queries.append(f"{entity} {title}")
        queries.append(f"{entity} Philadelphia")

    seen = set()
    deduped_queries = []
    for q in queries:
        norm = q.lower().strip()
        if norm and norm not in seen:
            seen.add(norm)
            deduped_queries.append(q)

    return {
        "title": title,
        "summary": lead_summary or title,
        "infobox": infobox_rows,
        "queries": deduped_queries
    }


def search_images_via_wikimedia(queries: list[str], target_results: int = 25) -> list[str]:
    """
    Searches Wikimedia Commons using context-based queries.
    Returns direct image URLs (original or high-resolution thumb).
    """
    search_url = "https://commons.wikimedia.org/w/api.php"
    urls = []
    seen_urls = set()

    for query in queries:
        if len(urls) >= target_results:
            break
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "srlimit": str(min(target_results * 2, 50)),
        }
        try:
            query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in search_params.items())
            res = make_request(f"{search_url}?{query_string}")
            if not res or res.status_code != 200:
                continue
            data = res.json()
            titles = [
                item["title"]
                for item in data.get("query", {}).get("search", [])
                if not any(item["title"].lower().endswith(bad) for bad in _DISALLOWED_EXTS)
            ]
        except Exception as e:
            logging.error(f"Wikimedia search error for query '{query}': {e}")
            continue

        if not titles:
            continue

        for i in range(0, len(titles), 25):
            batch = titles[i:i+25]
            info_params = {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": "1200",
                "titles": "|".join(batch),
            }
            try:
                info_qs = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in info_params.items())
                res = make_request(f"{search_url}?{info_qs}")
                if not res or res.status_code != 200:
                    continue
                info_data = res.json()
                for page in info_data.get("query", {}).get("pages", {}).values():
                    for ii in page.get("imageinfo", []):
                        mime = ii.get("mime", "")
                        if mime.startswith("audio/") or mime.startswith("video/") or "pdf" in mime:
                            continue
                        img_url = ii.get("thumburl") or ii.get("url")
                        if img_url and img_url not in seen_urls and is_likely_image_url(img_url):
                            seen_urls.add(img_url)
                            urls.append(img_url)
                            if len(urls) >= target_results:
                                return urls
            except Exception as e:
                logging.error(f"Wikimedia imageinfo error: {e}")

    return urls


def search_images_via_gemini(client: genai.Client, topic: str, context_summary: str = "", target_count: int = 20) -> list[str]:
    """Queries Gemini with Search Grounding to find direct image URLs based on article context."""
    context_part = f"\nArticle Context:\n{context_summary}\n" if context_summary else ""
    prompt = (
        f"Search the web to find {target_count} real, active, direct image URLs (ending in .jpg, .jpeg, .png, or .webp) "
        f"related to the Philadelphia history topic: '{topic}'.{context_part}\n"
        f"Find images matching the context above (portraits of key figures, historic buildings/landmarks, maps, monuments, "
        f"or archival photos). Prioritize Wikimedia Commons, Wikipedia, Library of Congress, or historic archives.\n"
        f"Return ONLY direct image URLs, one per line. No markdown formatting, bullets, numbers, or commentary."
    )
    try:
        response = gemini_utils.query_gemini(
            client=client,
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
            delay=2,
        )
        urls = []
        if response and response.text:
            for line in response.text.splitlines():
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://"):
                    clean_url = line.split()[0].replace('"', '').replace("'", "").rstrip("),;]")
                    if is_likely_image_url(clean_url):
                        urls.append(clean_url)
        return urls
    except Exception as e:
        logging.error(f"Gemini image search failed for {topic}: {e}")
        return []


def search_images_via_serper(api_key: str, queries: list[str], target_count: int = 20) -> list[str]:
    """Queries Serper API with context queries to find image search result URLs."""
    url = "https://google.serper.dev/images"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    urls = []
    seen = set()
    for q in queries:
        if len(urls) >= target_count:
            break
        body = {
            "q": q,
            "num": min(target_count, 20)
        }
        res = make_request(url, method="POST", headers=headers, body=body)
        if res and res.status_code == 200:
            try:
                data = res.json()
                for item in data.get("images", []):
                    img_url = item.get("imageUrl")
                    if img_url and img_url not in seen and is_likely_image_url(img_url):
                        seen.add(img_url)
                        urls.append(img_url)
                        if len(urls) >= target_count:
                            return urls
            except Exception as e:
                logging.error(f"Failed to parse Serper response for query '{q}': {e}")
    return urls


def process_topic(
    entry_path: Path,
    client: genai.Client,
    serper_key: str,
    web_dir: Path,
    min_images: int = 10,
    max_images: int = 15,
) -> tuple[int, int]:
    """
    Processes a single topic from its synthesized entry file:
    1. Ensures a dedicated folder exists: data/web/{safe_topic}/
    2. Migrates any legacy images from data/web/ into data/web/{safe_topic}/
    3. Searches & downloads up to max_images (min_images target).
    4. Updates corresponding HTML file if present.

    Returns:
        (total_images_on_disk, newly_downloaded_count)
    """
    raw_topic = entry_path.stem
    context = parse_entry_context(entry_path)
    clean_title = context["title"]
    safe_topic = sanitize_prefix(raw_topic)

    # Dedicated topic folder
    topic_dir = web_dir / safe_topic
    topic_dir.mkdir(parents=True, exist_ok=True)

    # Migrate any legacy files located directly under web_dir into topic_dir
    for legacy_file in web_dir.glob(f"{safe_topic}_*.*"):
        if legacy_file.is_file() and legacy_file.parent == web_dir:
            target = topic_dir / legacy_file.name
            if not target.exists():
                legacy_file.rename(target)
            else:
                legacy_file.unlink()

    logging.info(f"Processing image search for: {clean_title} -> {topic_dir.name}/")

    # Discover existing valid image files inside topic_dir
    downloaded_files = []
    hero_matches = [
        f.name for f in topic_dir.glob(f"{safe_topic}_hero.*")
        if f.suffix != ".json" and f.stat().st_size >= 512
    ]
    if hero_matches:
        downloaded_files.append(hero_matches[0])

    for idx in range(1, max_images):
        matches = [
            f.name for f in topic_dir.glob(f"{safe_topic}_{idx}.*")
            if f.suffix != ".json" and f.stat().st_size >= 512
        ]
        if matches:
            downloaded_files.append(matches[0])

    initial_count = len(downloaded_files)
    newly_downloaded = 0
    logging.info(f"Found {initial_count} existing image(s) in {topic_dir.name}/")

    # Search and download if more images are needed
    if len(downloaded_files) < max_images:
        candidates = []
        needed_count = max_images - len(downloaded_files)
        search_target = max(needed_count * 2, 20)

        # 1. Serper API
        if serper_key:
            logging.info("Searching images via Serper API with context queries...")
            candidates.extend(search_images_via_serper(serper_key, context["queries"], target_count=search_target))

        # 2. Gemini Grounding
        if client and len(candidates) < search_target:
            logging.info("Searching images via Gemini Grounding with article context...")
            gemini_candidates = search_images_via_gemini(
                client=client,
                topic=clean_title,
                context_summary=context["summary"],
                target_count=search_target,
            )
            candidates.extend(gemini_candidates)

        # 3. Wikimedia Commons
        if len(candidates) < search_target:
            logging.info("Searching images via Wikimedia Commons with context queries...")
            wm_candidates = search_images_via_wikimedia(context["queries"], target_results=search_target)
            candidates.extend(wm_candidates)

        seen_cand = set()
        valid_candidates = []
        for url in candidates:
            if url not in seen_cand and is_likely_image_url(url):
                seen_cand.add(url)
                valid_candidates.append(url)

        logging.info(f"Found {len(valid_candidates)} candidate URL(s) for {raw_topic}.")

        for url in valid_candidates:
            if len(downloaded_files) >= max_images:
                break

            suffix = "hero" if len(downloaded_files) == 0 else str(len(downloaded_files))
            prefix = f"{safe_topic}_{suffix}"

            filename = download_image_and_save_json(url, topic_dir, prefix, topic=raw_topic)
            if filename:
                downloaded_files.append(filename)
                newly_downloaded += 1

    logging.info(f"Images in {topic_dir.name}/: {len(downloaded_files)} ({newly_downloaded} new)")
    if len(downloaded_files) < min_images:
        logging.warning(
            f"Could only obtain {len(downloaded_files)} images for {raw_topic} (target: {min_images}-{max_images})."
        )

    # Update HTML file if present
    html_file = web_dir / f"{raw_topic}.html"
    if not html_file.exists():
        logging.info(f"HTML file not found: {html_file.name}. Downloaded images stored in {topic_dir.name}/.")
        return len(downloaded_files), newly_downloaded

    if not downloaded_files:
        logging.warning(f"No downloaded images available to update {html_file.name}.")
        return 0, newly_downloaded

    try:
        html_content = html_file.read_text(encoding="utf-8")

        # 1. Hero image: points to ./{safe_topic}/{hero_img}
        hero_img = downloaded_files[0]
        html_content = re.sub(
            r'src=["\']\./(?:' + re.escape(safe_topic) + r'/)?(?:thumbnail_modified\.webp|' + re.escape(hero_img) + r')["\']',
            f'src="./{safe_topic}/{hero_img}"',
            html_content
        )
        html_content = re.sub(r'alt=["\']City Hall["\']', f'alt="{clean_title} Hero Image"', html_content)

        # 2. Article image 1
        img1 = downloaded_files[1] if len(downloaded_files) > 1 else hero_img
        html_content = re.sub(
            r'src=["\']\./(?:' + re.escape(safe_topic) + r'/)?(?:Philadelphia_City_Hall_7\.jpg|' + re.escape(img1) + r')["\']',
            f'src="./{safe_topic}/{img1}"',
            html_content
        )
        html_content = re.sub(r'alt=["\']Old City Hall["\']', f'alt="{clean_title} Image 1"', html_content)

        # 3. Article image 2
        img2 = downloaded_files[2] if len(downloaded_files) > 2 else img1
        html_content = re.sub(
            r'src=["\']\./(?:' + re.escape(safe_topic) + r'/)?(?:Philadelphia_city_hall\.jpg|' + re.escape(img2) + r')["\']',
            f'src="./{safe_topic}/{img2}"',
            html_content
        )
        html_content = re.sub(r'alt=["\']Tower View["\']', f'alt="{clean_title} Image 2"', html_content)

        # 4. Gallery section for remaining images (images 3+)
        gallery_images = downloaded_files[3:]
        if gallery_images:
            gallery_items = "\n".join(
                f'                    <img src="./{safe_topic}/{img}" alt="{clean_title} image" class="w-full h-36 object-cover rounded shadow-sm hover:scale-105 transition duration-300">'
                for img in gallery_images
            )
            gallery_html = (
                f'\n                <!-- Image Gallery -->\n'
                f'                <div id="gallery" class="border-t pt-6 mt-8 mb-6">\n'
                f'                    <h4 class="text-xl font-bold mb-4 text-slate-700">Image Gallery</h4>\n'
                f'                    <div class="grid grid-cols-2 md:grid-cols-3 gap-4">\n'
                f'{gallery_items}\n'
                f'                    </div>\n'
                f'                </div>\n'
            )
            if 'id="gallery"' in html_content:
                html_content = re.sub(r'<div id="gallery".*?</div>\s*</div>', gallery_html.strip(), html_content, flags=re.DOTALL)
            elif '<div class="border-t pt-4">' in html_content:
                html_content = html_content.replace(
                    '<div class="border-t pt-4">',
                    f'{gallery_html}                <div class="border-t pt-4">'
                )

        html_file.write_text(html_content, encoding="utf-8")
        logging.info(f"Updated HTML file for {raw_topic} with {len(downloaded_files)} image URLs from {topic_dir.name}/.")
    except Exception as e:
        logging.error(f"Error updating HTML file for {raw_topic}: {e}")

    return len(downloaded_files), newly_downloaded


def main():
    parser = argparse.ArgumentParser(description="Campus 250 Wiki Context-Aware Image Search")
    parser.add_argument("--topic", type=str, help="Filter to a specific topic name (substring match)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of topics to process")
    parser.add_argument("--min-images", type=int, default=10, help="Minimum images to find per topic (default 10)")
    parser.add_argument("--max-images", type=int, default=15, help="Maximum images to find per topic (default 15)")
    parser.add_argument("--timeout", type=int, default=1800, help="Maximum runtime in seconds (default: 1800, i.e. 30 minutes)")
    args = parser.parse_args()

    run_start = time.perf_counter()
    timeout_sec = int(os.environ.get("PIPELINE_TIMEOUT_SECONDS", args.timeout or 1800))

    try:
        google_client = get_google_client()
        if not google_client:
            logging.warning("Google GenAI client could not be created. Falling back to Serper/Wikimedia only.")

        serper_key = get_serper_client()

        entries_dir = rootDir / "data" / "entries"
        web_dir = rootDir / "data" / "web"
        web_dir.mkdir(parents=True, exist_ok=True)

        if not entries_dir.exists():
            logging.error(f"Entries directory does not exist: {entries_dir}")
            sys.exit(1)

        entry_files = sorted(list(entries_dir.glob("*.txt")), key=lambda p: p.name.lower())
        if not entry_files:
            logging.info("No entry files found in data/entries/.")
            return

        if args.topic:
            entry_files = [f for f in entry_files if args.topic.lower() in f.stem.lower()]
            logging.info(f"Filtered to {len(entry_files)} file(s) matching '{args.topic}'")

        # Prioritize topics that do not yet have at least min_images downloaded
        def topic_image_count(fp: Path) -> int:
            safe = sanitize_prefix(fp.stem)
            td = web_dir / safe
            count = 0
            if td.exists():
                count += len([f for f in td.glob(f"{safe}_*.*") if f.suffix != ".json" and f.stat().st_size >= 512])
            count += len([f for f in web_dir.glob(f"{safe}_*.*") if f.suffix != ".json" and f.stat().st_size >= 512])
            return count

        pending_topics = [f for f in entry_files if topic_image_count(f) < args.min_images]
        complete_topics = [f for f in entry_files if topic_image_count(f) >= args.min_images]
        ordered_files = pending_topics + complete_topics

        if args.limit:
            ordered_files = ordered_files[:args.limit]
            logging.info(f"Processing limited to first {len(ordered_files)} topic(s).")

        logging.info(
            f"Beginning image search across {len(ordered_files)} topic(s) "
            f"({len(pending_topics)} needing images, {len(complete_topics)} already complete). "
            f"Runtime cap: {_fmt_duration(timeout_sec)}."
        )

        ledger_before = gemini_utils.read_ledger()
        total_new_downloads = 0
        topics_processed = 0

        for filepath in ordered_files:
            # Check runtime cap
            elapsed_current = time.perf_counter() - run_start
            if timeout_sec and elapsed_current >= timeout_sec:
                logging.warning(
                    f"\n[!] Runtime cap reached ({_fmt_duration(timeout_sec)}). "
                    f"Stopping pipeline cleanly after {topics_processed} topic(s)."
                )
                break

            total_on_disk, newly_dl = process_topic(
                entry_path=filepath,
                client=google_client,
                serper_key=serper_key,
                web_dir=web_dir,
                min_images=args.min_images,
                max_images=args.max_images,
            )
            total_new_downloads += newly_dl
            topics_processed += 1

        # Summary computation
        total_elapsed = time.perf_counter() - run_start
        ledger_after = gemini_utils.read_ledger()
        delta_tokens = {
            "prompt_tokens": max(0, ledger_after["prompt_tokens"] - ledger_before["prompt_tokens"]),
            "output_tokens": max(0, ledger_after["output_tokens"] - ledger_before["output_tokens"]),
            "total_tokens":  max(0, ledger_after["total_tokens"]  - ledger_before["total_tokens"]),
        }
        est_cost = gemini_utils.tokens_to_usd(
            delta_tokens["prompt_tokens"], delta_tokens["output_tokens"], MODEL_NAME
        )

        # Print formatted summary matching pipeline standard
        print("\n" + "=" * 60)
        print("  IMAGE SEARCH PIPELINE COMPLETE -- SUMMARY")
        print("=" * 60)
        print(f"  Topics processed      : {topics_processed} of {len(ordered_files)}")
        print(f"  New images downloaded : {total_new_downloads}")
        print(f"  Total time elapsed    : {_fmt_duration(total_elapsed)}")
        print(
            f"  Gemini tokens used    : {delta_tokens['total_tokens']:,} "
            f"(prompt {delta_tokens['prompt_tokens']:,} / output {delta_tokens['output_tokens']:,})"
        )
        print(f"  Estimated Gemini cost : ${est_cost:.6f}")
        print("=" * 60 + "\n")

    except Exception as e:
        logging.error(f"Error in imageSearch main: {e}", exc_info=True)


if __name__ == "__main__":
    main()
