#!/usr/bin/env python3
"""
imageSearch.py
Author: Paul Tran <tranb9@lasalle.edu>

Looks through /data/entries/{topic}.txt and /data/search/{topic}.txt, then performs a 
Google image search for a given topic, takes image link, then loads the links into 
the appropriate place in the template.
"""
from google import genai 
from google.genai import types

import logging
import os
import sys
from dotenv import load_dotenv

from web.utils import get_serper_client, get_google_client, download_image_and_save_json, make_request

load_dotenv()
logging.basicConfig(level=logging.INFO)


def main():
    serper = get_serper_client()
    google = get_google_client()
    if not google:
        sys.exit(1)
    make_request(
        google.get(os.environ.get("GOOGLE_IMAGE_REQUEST_URL"))
    )


if __name__ == "__main__":
    main()