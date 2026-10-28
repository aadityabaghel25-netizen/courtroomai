"""
Indian Kanoon API Fetcher
Fetches judgments across criminal, civil, and corporate law.
API docs: https://api.indiankanoon.org/
"""

import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("INDIANKANOON_API_TOKEN")
BASE_URL = "https://api.indiankanoon.org"
RAW_DATA_DIR = Path("data/raw")
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Comprehensive Legal Search Queries (40+ Categories)
SEARCH_QUERIES = [
    # Criminal Law
    "murder IPC 302 bail", "culpable homicide IPC 304",
    "rape IPC 376 conviction", "kidnapping IPC 363",
    "robbery IPC 392", "dacoity IPC 395",
    "dowry death IPC 304B", "dowry harassment IPC 498A",
    "cheating IPC 420", "forgery IPC 465",
    "defamation IPC 499", "assault IPC 351",
    "house trespass IPC 448", "extortion IPC 383",
    
    # Bail & Procedure
    "anticipatory bail Section 438 CrPC",
    "regular bail Section 437 CrPC",
    "bail cancellation Supreme Court",
    "FIR quashing Section 482 CrPC",
    "chargesheet delay default bail",
    "NDPS bail stringent conditions",
    
    # Constitutional
    "Article 21 right to life personal liberty",
    "Article 14 equality before law",
    "Article 22 arrest detention rights",
    "habeas corpus petition High Court",
    
    # Civil & Corporate
    "SEBI insider trading penalty",
    "Companies Act fraud Section 447",
    "cheque bounce Section 138 NI Act",
    "consumer forum deficiency service",
    "specific performance contract",
    "injunction civil suit",
    
    # Supreme Court landmark
    "landmark Supreme Court criminal judgment",
    "constitutional bench five judges",
    "three judges bench bail",
    
    # High Court specific
    "Bombay High Court bail murder",
    "Delhi High Court FIR quash",
    "Allahabad High Court 498A",
    "Madras High Court anticipatory bail",
    "Calcutta High Court criminal appeal",
    "Karnataka High Court conviction appeal",
]


def search_judgments(query: str, page: int = 1) -> dict:
    """Search Indian Kanoon for judgments matching query."""
    url = f"{BASE_URL}/search/"
    params = {
        "formInput": query,
        "pagenum": page,
    }
    headers = {"Authorization": f"Token {API_TOKEN}"}

    response = requests.post(url, data=params, headers=headers)
    response.raise_for_status()
    return response.json()


def fetch_document(doc_id: str) -> dict:
    """Fetch full text of a single judgment by its ID."""
    url = f"{BASE_URL}/doc/{doc_id}/"
    headers = {"Authorization": f"Token {API_TOKEN}"}

    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()


def save_document(doc: dict, doc_id: str):
    """Save raw judgment JSON to disk."""
    filepath = RAW_DATA_DIR / f"{doc_id}.json"
    if filepath.exists():
        print(f"  [SKIP] {doc_id} already exists")
        return
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"  [SAVED] {doc_id}")


def fetch_bulk(queries: list = SEARCH_QUERIES, docs_per_query: int = 20):
    """
    Main function — fetches N judgments per query category.
    """
    if not API_TOKEN:
        raise ValueError("INDIANKANOON_API_TOKEN not set in .env")

    total_fetched = 0

    for query in queries:
        print(f"\n[QUERY] {query}")
        try:
            results = search_judgments(query)
            docs = results.get("docs", [])[:docs_per_query]

            for doc_meta in docs:
                doc_id = str(doc_meta.get("tid"))
                try:
                    full_doc = fetch_document(doc_id)
                    # Attach metadata from search result to full doc
                    full_doc["_meta"] = {
                        "query_category": query,
                        "title": doc_meta.get("title", ""),
                        "court": doc_meta.get("court", ""),
                        "date": doc_meta.get("date", ""),
                        "doc_id": doc_id,
                    }
                    save_document(full_doc, doc_id)
                    total_fetched += 1
                    time.sleep(0.3)  # be polite to the API
                except Exception as e:
                    print(f"  [ERROR] doc {doc_id}: {e}")

        except Exception as e:
            print(f"[ERROR] query '{query}': {e}")

    print(f"\n[DONE] Total documents fetched: {total_fetched}")
    return total_fetched


if __name__ == "__main__":
    fetch_bulk(docs_per_query=20)
