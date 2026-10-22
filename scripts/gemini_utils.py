import time
import logging

def query_gemini(client, model, contents, config=None, retries=5, delay=20):
    """
    Wrapper for client.models.generate_content that adds automatic retries
    and a mandatory delay after querying to handle rate limits.
    """
    try:
        for attempt in range(1, retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                time.sleep(delay)  # 5s delay after each time it queries data
                return response
            except Exception as e:
                logging.warning(f"[Attempt {attempt}/{retries}] Gemini query failed: {e}")
                if attempt < retries:
                    time.sleep(delay * attempt)  # Backoff before retry
                else:
                    raise e
    except Exception as e:
        logging.error(f"query_gemini error: {e}")
        raise e

