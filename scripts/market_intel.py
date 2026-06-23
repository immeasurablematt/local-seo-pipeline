#!/usr/bin/env python3
"""
market_intel.py — Fetch competitor reviews and save them for analysis.

Reads competitor list from .competitors.json (written by audit.py),
or supply competitors manually with --competitor flags.

Usage:
    # After running audit.py:
    python scripts/market_intel.py --keyword "plumber toronto"

    # Specify competitors manually:
    python scripts/market_intel.py \
        --keyword "plumber toronto" \
        --competitor "Acme Plumbing" \
        --competitor "Fast Flow Plumbing"

    # Mock mode (no API calls):
    python scripts/market_intel.py --keyword "plumber toronto" --mock

Output:
    .reviews_raw.json  — all reviews per competitor, ready to paste into Claude
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent
COMPETITORS_FILE = REPO_ROOT / ".competitors.json"
REVIEWS_RAW_FILE = REPO_ROOT / ".reviews_raw.json"

DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"
LOCATION_CODE_CANADA = 2124

MOCK_REVIEWS = {
    "Mock Competitor 1": [
        "Great service, showed up on time and fixed the leak quickly.",
        "Very professional team. A bit pricey but worth it.",
        "Communication was poor, had to call three times to get an update.",
        "Did a fantastic job, highly recommend.",
        "Fast response, clean work area, no mess left behind.",
    ],
    "Mock Competitor 2": [
        "Friendly staff but the job took twice as long as quoted.",
        "Price was very reasonable. Would use again.",
        "They explained everything clearly before starting. Great experience.",
        "Showed up late but the quality of work was excellent.",
        "Booking was easy, online form worked great.",
    ],
    "Mock Competitor 3": [
        "Not happy with the result. Had to call them back to fix it.",
        "Cheap but you get what you pay for. Sloppy work.",
        "Very friendly guys. Made me feel at ease throughout.",
        "Took forever to get a quote. Eventually gave up and went elsewhere.",
        "Great outcome! My old issue is completely resolved.",
    ],
}


def get_auth_headers() -> dict:
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        print("❌ DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set.", file=sys.stderr)
        sys.exit(1)
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def fetch_reviews(business_name: str, city: str, depth: int = 50, mock: bool = False) -> list[str]:
    if mock:
        return MOCK_REVIEWS.get(business_name, [
            f"Great service from {business_name}.",
            f"Would recommend {business_name} to friends.",
        ])

    keyword = f"{business_name} {city}"
    payload = [{
        "keyword": keyword,
        "location_code": LOCATION_CODE_CANADA,
        "language_code": "en",
        "depth": depth,
    }]

    try:
        resp = requests.post(
            f"{DATAFORSEO_BASE_URL}/business_data/google/reviews/live/advanced",
            headers=get_auth_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  ⚠️  Reviews fetch failed for '{business_name}': {e}", file=sys.stderr)
        return []

    reviews = []
    try:
        items = data["tasks"][0]["result"][0]["items"] or []
        for item in items:
            text = item.get("review_text", "").strip()
            if text:
                reviews.append(text)
    except (KeyError, IndexError, TypeError):
        pass

    return reviews


def load_competitors(manual: list[str] | None, city: str) -> list[dict]:
    if manual:
        return [{"title": name, "city": city} for name in manual]

    if COMPETITORS_FILE.exists():
        data = json.loads(COMPETITORS_FILE.read_text())
        print(f"📂 Loaded {len(data)} competitors from {COMPETITORS_FILE.name}")
        return data

    print("⚠️  No .competitors.json found. Run audit.py first, or pass --competitor flags.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Fetch competitor reviews for market analysis")
    parser.add_argument("--keyword", required=True, help="Target keyword (e.g. 'plumber toronto')")
    parser.add_argument("--city", default="", help="City (used when fetching reviews)")
    parser.add_argument("--competitor", action="append", dest="competitors", metavar="NAME",
                        help="Competitor business name (repeat for each, up to 5)")
    parser.add_argument("--reviews-per-biz", type=int, default=50, dest="depth",
                        help="Max reviews to fetch per competitor (default: 50)")
    parser.add_argument("--mock", action="store_true", help="Skip live API calls, use mock data")
    parser.add_argument("--output", help="Output JSON path (default: .reviews_raw.json)")
    args = parser.parse_args()

    city = args.city or args.keyword.split()[-1]
    output_file = Path(args.output) if args.output else REVIEWS_RAW_FILE

    competitors = load_competitors(args.competitors, city)

    if args.mock:
        print("  ⚠️  MOCK MODE — using dummy reviews\n")

    all_reviews: dict[str, list[str]] = {}
    for c in competitors[:5]:
        name = c.get("title") or c.get("name", "Unknown")
        biz_city = c.get("city", city)
        print(f"📡 Fetching reviews: {name}...")
        reviews = fetch_reviews(name, biz_city, depth=args.depth, mock=args.mock)
        all_reviews[name] = reviews
        print(f"   → {len(reviews)} review(s)")

    total = sum(len(v) for v in all_reviews.values())
    print(f"\n📊 Total: {total} reviews across {len(all_reviews)} competitors")

    output = {
        "keyword": args.keyword,
        "city": city,
        "total_reviews": total,
        "competitors": all_reviews,
    }
    output_file.write_text(json.dumps(output, indent=2))
    print(f"✅ Saved → {output_file}")

    # Print all reviews in a paste-ready format
    print("\n" + "=" * 60)
    print("  PASTE THE FOLLOWING INTO CLAUDE AND ASK:")
    print('  "Analyse these competitor reviews for the {keyword} market.')
    print("   Sort insights into 10 buckets: reliability, communication,")
    print("   price_transparency, quality_of_work, speed, facility_space,")
    print("   staff_attitude, process_ease, results_outcome, value_for_money.")
    print("   For each bucket: frequency (low/medium/high), dominant sentiment,")
    print('   top praise phrases, top complaints, and one-sentence market gap."')
    print("=" * 60)

    for biz, reviews in all_reviews.items():
        print(f"\n### {biz}")
        for i, r in enumerate(reviews, 1):
            print(f"{i}. {r}")

    print()


if __name__ == "__main__":
    main()
