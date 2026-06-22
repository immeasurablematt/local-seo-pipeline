#!/usr/bin/env python3
"""
market_intel.py — Scrape competitor reviews and extract market intelligence.

Implements the 3-step competitive intelligence framework:
  Step 1: Pull reviews for each competitor from DataForSEO Business Data API
  Step 2: Feed reviews to Claude for market analysis
  Step 3: Sort insights into 10 customer-value buckets

Reads competitor list from .competitors.json (written by audit.py --save-competitors),
or you can supply competitors manually with --competitor flags.

Usage:
    # After running audit.py (auto-loads .competitors.json):
    python scripts/market_intel.py --keyword "plumber toronto"

    # Specify competitors manually:
    python scripts/market_intel.py \
        --keyword "plumber toronto" \
        --competitor "Acme Plumbing" \
        --competitor "Fast Flow Plumbing" \
        --competitor "Toronto Plumbing Pro"

    # Mock mode (no API calls):
    python scripts/market_intel.py --keyword "plumber toronto" --mock

Output:
    .market_intel.json  — full bucket analysis (read by copy_gen.py)
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent
COMPETITORS_FILE = REPO_ROOT / ".competitors.json"
MARKET_INTEL_FILE = REPO_ROOT / ".market_intel.json"

DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"
LOCATION_CODE_CANADA = 2124

BUCKETS = [
    "reliability",
    "communication",
    "price_transparency",
    "quality_of_work",
    "speed",
    "facility_space",
    "staff_attitude",
    "process_ease",
    "results_outcome",
    "value_for_money",
]

BUCKET_LABELS = {
    "reliability": "Reliability (shows up on time, follows through)",
    "communication": "Communication (keeps clients informed, responsive)",
    "price_transparency": "Price Transparency (clear quotes, no surprises)",
    "quality_of_work": "Quality of Work (craftsmanship, attention to detail)",
    "speed": "Speed (fast turnaround, on-time completion)",
    "facility_space": "Facility / Space (cleanliness, professional environment)",
    "staff_attitude": "Staff Attitude (friendly, professional, polite)",
    "process_ease": "Process / Ease (easy to book, smooth workflow)",
    "results_outcome": "Results / Outcome (measurable improvement, before/after)",
    "value_for_money": "Value for Money (worth what they paid)",
}

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
    """Fetch Google reviews for a business via DataForSEO Business Data API."""
    if mock:
        return MOCK_REVIEWS.get(business_name, [
            f"Mock review 1 for {business_name}.",
            f"Mock review 2 for {business_name}.",
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


def analyse_with_claude(all_reviews: dict[str, list[str]], keyword: str) -> dict:
    """
    Send all competitor reviews to Claude and get back a 10-bucket market analysis.
    Returns structured JSON with bucket-level insights.
    """
    review_blob = ""
    for biz, reviews in all_reviews.items():
        if reviews:
            review_blob += f"\n\n### {biz}\n"
            for i, r in enumerate(reviews, 1):
                review_blob += f"{i}. {r}\n"

    if not review_blob.strip():
        print("⚠️  No reviews to analyse.", file=sys.stderr)
        return {}

    prompt = f"""You are a local market research analyst. I'm going to give you Google reviews for the top competitors in the **{keyword}** market.

Your job is to analyse these reviews and extract structured market intelligence across 10 customer-value buckets. For each bucket, identify:
- How often this theme appears (frequency: low / medium / high)
- What customers LOVE (top praise — specific phrases or patterns)
- What customers HATE or complain about (top complaints)
- The dominant sentiment for this market (positive / negative / mixed)
- One-sentence market gap summary (what's missing that a new entrant could own)

The 10 buckets are:
1. reliability — shows up on time, follows through on promises
2. communication — keeps clients informed, responsive, proactive updates
3. price_transparency — clear quotes, no surprise charges, upfront pricing
4. quality_of_work — craftsmanship, attention to detail, professional results
5. speed — fast turnaround, completes on schedule
6. facility_space — clean work area, tidy, professional environment
7. staff_attitude — friendly, polite, professional, puts clients at ease
8. process_ease — easy to book, smooth workflow, minimal friction
9. results_outcome — measurable improvement, problem actually solved, before/after
10. value_for_money — clients feel they got what they paid for

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{
  "keyword": "{keyword}",
  "total_reviews_analysed": <number>,
  "buckets": {{
    "<bucket_key>": {{
      "frequency": "low|medium|high",
      "sentiment": "positive|negative|mixed",
      "top_praise": ["phrase 1", "phrase 2", "phrase 3"],
      "top_complaints": ["complaint 1", "complaint 2"],
      "market_gap": "One sentence describing the gap a new entrant could own."
    }}
  }}
}}

Here are the competitor reviews:
{review_blob}
"""

    client = anthropic.Anthropic()

    print("🤖 Sending reviews to Claude for bucket analysis...")

    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    raw = ""
    for block in message.content:
        if block.type == "text":
            raw = block.text
            break

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⚠️  Claude returned invalid JSON: {e}", file=sys.stderr)
        print(f"   Raw output: {raw[:500]}", file=sys.stderr)
        return {}


def print_intel_summary(intel: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  MARKET INTELLIGENCE — {intel.get('keyword', '')}")
    print(f"  {intel.get('total_reviews_analysed', 0)} reviews analysed across all competitors")
    print(f"{'=' * 60}")

    buckets = intel.get("buckets", {})
    for key in BUCKETS:
        if key not in buckets:
            continue
        b = buckets[key]
        label = BUCKET_LABELS[key]
        freq = b.get("frequency", "?")
        sentiment = b.get("sentiment", "?")
        gap = b.get("market_gap", "")
        praise = b.get("top_praise", [])
        complaints = b.get("top_complaints", [])

        freq_icon = {"high": "🔥", "medium": "🌤️", "low": "❄️"}.get(freq, "")
        sent_icon = {"positive": "✅", "negative": "❌", "mixed": "⚠️"}.get(sentiment, "")

        print(f"\n  {freq_icon} {label}")
        print(f"     Frequency: {freq}  |  Sentiment: {sent_icon} {sentiment}")
        if praise:
            print(f"     Customers love: {praise[0]}")
        if complaints:
            print(f"     Customers hate: {complaints[0]}")
        print(f"     Gap: {gap}")

    print()


def load_competitors(manual: list[str] | None, city: str) -> list[dict]:
    """Load competitors from .competitors.json or from manual --competitor flags."""
    if manual:
        return [{"title": name, "city": city} for name in manual]

    if COMPETITORS_FILE.exists():
        data = json.loads(COMPETITORS_FILE.read_text())
        print(f"📂 Loaded {len(data)} competitors from {COMPETITORS_FILE.name}")
        return data

    print("⚠️  No .competitors.json found. Run audit.py first, or pass --competitor flags.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Market intelligence from competitor reviews")
    parser.add_argument("--keyword", required=True, help="Target keyword (e.g. 'plumber toronto')")
    parser.add_argument("--city", default="", help="City (used when fetching reviews if not in competitor data)")
    parser.add_argument("--competitor", action="append", dest="competitors", metavar="NAME",
                        help="Competitor business name (repeat for each, up to 5)")
    parser.add_argument("--reviews-per-biz", type=int, default=50, dest="depth",
                        help="Max reviews to fetch per competitor (default: 50)")
    parser.add_argument("--mock", action="store_true", help="Skip live API calls, use mock data")
    parser.add_argument("--output", help="Output JSON path (default: .market_intel.json)")
    args = parser.parse_args()

    city = args.city or args.keyword.split()[-1]
    output_file = Path(args.output) if args.output else MARKET_INTEL_FILE

    competitors = load_competitors(args.competitors, city)

    if not competitors:
        print("❌ No competitors found.", file=sys.stderr)
        sys.exit(1)

    if args.mock:
        print("  ⚠️  MOCK MODE — using dummy reviews\n")

    # Step 1: Fetch reviews for each competitor
    all_reviews: dict[str, list[str]] = {}
    for c in competitors[:5]:
        name = c.get("title") or c.get("name", "Unknown")
        biz_city = c.get("city", city)
        print(f"📡 Fetching reviews: {name}...")
        reviews = fetch_reviews(name, biz_city, depth=args.depth, mock=args.mock)
        all_reviews[name] = reviews
        total = len(reviews)
        print(f"   → {total} review{'s' if total != 1 else ''} fetched")

    total_reviews = sum(len(v) for v in all_reviews.values())
    print(f"\n📊 Total reviews: {total_reviews} across {len(all_reviews)} competitors")

    if total_reviews == 0:
        print("❌ No reviews to analyse. Check competitor names or use --mock.", file=sys.stderr)
        sys.exit(1)

    # Steps 2-3: Claude analyses and buckets the reviews
    intel = analyse_with_claude(all_reviews, args.keyword)

    if not intel:
        print("❌ Analysis failed.", file=sys.stderr)
        sys.exit(1)

    # Ensure total count is accurate
    intel["total_reviews_analysed"] = total_reviews
    intel["competitors"] = [c.get("title") or c.get("name") for c in competitors[:5]]

    output_file.write_text(json.dumps(intel, indent=2))
    print(f"\n✅ Market intel saved → {output_file}")

    print_intel_summary(intel)

    print(f"  Next step: python scripts/copy_gen.py --keyword \"{args.keyword}\"")
    print()


if __name__ == "__main__":
    main()
