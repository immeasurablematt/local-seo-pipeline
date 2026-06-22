#!/usr/bin/env python3
"""
hot_lead_eval.py — Score a local business as a potential SEO client.

Pull the info from their Google Maps listing (name, rating, review count,
website) and this script returns Hot / Warm / Cold with a breakdown.

Usage:
    python scripts/hot_lead_eval.py \
        --name "Joe's Plumbing" \
        --city "Toronto" \
        --rating 3.8 \
        --reviews 12 \
        --website "https://joesplumbing.com" \
        --keyword "plumber toronto"

    # No website listed on GBP:
    python scripts/hot_lead_eval.py \
        --name "Joe's Plumbing" --city "Toronto" \
        --rating 3.8 --reviews 12

    # Skip live website fetch (mock on-page checks):
    python scripts/hot_lead_eval.py ... --mock

    # Write verdict row to Google Sheets Sites Dashboard:
    python scripts/hot_lead_eval.py ... --sheets-id <ID>
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent

# --- Scoring thresholds ----------------------------------------------------

REVIEW_SCORES = [
    (10,  35),   # ≤ 10 reviews
    (25,  25),   # ≤ 25 reviews
    (75,  12),   # ≤ 75 reviews
    (150,  5),   # ≤ 150 reviews
]
REVIEW_SCORE_DEFAULT = 0

RATING_SCORES = [
    (3.5, 20),   # < 3.5 stars
    (4.0, 14),   # < 4.0 stars
    (4.3,  7),   # < 4.3 stars
]
RATING_SCORE_DEFAULT = 0

NO_WEBSITE_SCORE   = 20
NO_SCHEMA_SCORE    = 10
NO_KW_TITLE_SCORE  =  6
NO_KW_H1_SCORE     =  4
NO_PHONE_SCORE     =  5
NO_VIEWPORT_SCORE  =  3

HOT_THRESHOLD  = 60
WARM_THRESHOLD = 35


@dataclass
class EvalResult:
    name: str
    city: str
    rating: float | None
    reviews: int | None
    website: str | None
    keyword: str | None
    score: int = 0
    breakdown: list[tuple[str, int]] = field(default_factory=list)
    verdict: str = ""
    on_page: dict = field(default_factory=dict)

    def add(self, label: str, points: int) -> None:
        if points:
            self.breakdown.append((label, points))
            self.score += points


# ---------------------------------------------------------------------------

def score_reviews(result: EvalResult) -> None:
    if result.reviews is None:
        result.add("Review count unknown (assume low)", 15)
        return
    for threshold, pts in REVIEW_SCORES:
        if result.reviews <= threshold:
            result.add(f"Only {result.reviews} reviews (≤ {threshold})", pts)
            return
    result.add("", REVIEW_SCORE_DEFAULT)


def score_rating(result: EvalResult) -> None:
    if result.rating is None:
        result.add("Rating unknown (assume weak)", 10)
        return
    for threshold, pts in RATING_SCORES:
        if result.rating < threshold:
            result.add(f"Rating {result.rating} (< {threshold}★)", pts)
            return
    result.add("", RATING_SCORE_DEFAULT)


def score_website(result: EvalResult, mock: bool) -> None:
    if not result.website:
        result.add("No website on GBP listing", NO_WEBSITE_SCORE)
        return

    if mock:
        result.on_page = {
            "title_has_keyword": False,
            "h1_has_keyword": False,
            "has_local_schema": False,
            "phone_in_page": True,
            "has_viewport": True,
            "error": None,
        }
    else:
        result.on_page = fetch_on_page(result.website, result.keyword or "")

    op = result.on_page
    if op.get("error"):
        result.add(f"Website unreachable ({op['error'][:60]})", 12)
        return

    if not op.get("has_local_schema"):
        result.add("No LocalBusiness schema", NO_SCHEMA_SCORE)
    if result.keyword and not op.get("title_has_keyword"):
        result.add("Keyword missing from <title>", NO_KW_TITLE_SCORE)
    if result.keyword and not op.get("h1_has_keyword"):
        result.add("Keyword missing from <h1>", NO_KW_H1_SCORE)
    if not op.get("phone_in_page"):
        result.add("Phone not found on homepage", NO_PHONE_SCORE)
    if not op.get("has_viewport"):
        result.add("No viewport meta (not mobile-friendly)", NO_VIEWPORT_SCORE)


def fetch_on_page(website: str, keyword: str) -> dict:
    url = website if website.startswith("http") else f"https://{website}"
    checks = {
        "title_has_keyword": False,
        "h1_has_keyword": False,
        "has_local_schema": False,
        "phone_in_page": False,
        "has_viewport": False,
        "error": None,
    }
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; LocalSEOBot/1.0)"},
            timeout=15,
            allow_redirects=True,
        )
        soup = BeautifulSoup(resp.text, "lxml")
        kw = keyword.lower()

        title = soup.find("title")
        if title and kw and kw in title.get_text().lower():
            checks["title_has_keyword"] = True

        h1 = soup.find("h1")
        if h1 and kw and kw in h1.get_text().lower():
            checks["h1_has_keyword"] = True

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                schema = json.loads(script.string or "")
                stype = schema.get("@type", "")
                if "LocalBusiness" in stype or (
                    isinstance(stype, list) and any("LocalBusiness" in t for t in stype)
                ):
                    checks["has_local_schema"] = True
                    break
            except (json.JSONDecodeError, AttributeError):
                continue

        page_text = soup.get_text(" ").lower()
        # Phone: look for any 10-digit sequence appearing on the page
        if re.search(r"\d[\d\s\-().]{7,}\d", page_text):
            checks["phone_in_page"] = True

        if soup.find("meta", attrs={"name": re.compile("viewport", re.I)}):
            checks["has_viewport"] = True

    except requests.RequestException as e:
        checks["error"] = str(e)

    return checks


def determine_verdict(score: int) -> str:
    if score >= HOT_THRESHOLD:
        return "HOT"
    if score >= WARM_THRESHOLD:
        return "WARM"
    return "COLD"


def gog_append(spreadsheet_id: str, sheet: str, row: list[str]) -> None:
    cmd = ["gog", "--json", "sheets", "append", spreadsheet_id, f"{sheet}!A1"] + row
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️  gog append failed: {result.stderr}", file=sys.stderr)


def get_sheets_id(provided: str | None) -> str | None:
    if provided:
        return provided
    id_file = REPO_ROOT / ".sheets_id"
    if id_file.exists():
        return id_file.read_text().strip()
    return None


def evaluate(
    name: str,
    city: str,
    rating: float | None,
    reviews: int | None,
    website: str | None,
    keyword: str | None,
    mock: bool = False,
) -> EvalResult:
    result = EvalResult(
        name=name, city=city, rating=rating,
        reviews=reviews, website=website, keyword=keyword,
    )
    score_reviews(result)
    score_rating(result)
    score_website(result, mock=mock)
    result.verdict = determine_verdict(result.score)
    return result


def print_result(result: EvalResult) -> None:
    verdict_icon = {"HOT": "🔥", "WARM": "🌤️", "COLD": "❄️"}.get(result.verdict, "")
    print(f"\n{'=' * 52}")
    print(f"  {verdict_icon}  {result.verdict} LEAD  —  score {result.score}/100")
    print(f"{'=' * 52}")
    print(f"  Business : {result.name}")
    print(f"  City     : {result.city}")
    print(f"  Rating   : {result.rating or 'n/a'}")
    print(f"  Reviews  : {result.reviews if result.reviews is not None else 'n/a'}")
    print(f"  Website  : {result.website or '(none)'}")
    if result.keyword:
        print(f"  Keyword  : {result.keyword}")

    if result.breakdown:
        print(f"\n  Scoring breakdown:")
        for label, pts in result.breakdown:
            print(f"    +{pts:2d}  {label}")

    if result.on_page and not result.on_page.get("error"):
        op = result.on_page
        print(f"\n  On-page checks:")
        print(f"    Title has keyword:    {'✅' if op.get('title_has_keyword') else '❌'}")
        print(f"    H1 has keyword:       {'✅' if op.get('h1_has_keyword') else '❌'}")
        print(f"    LocalBusiness schema: {'✅' if op.get('has_local_schema') else '❌'}")
        print(f"    Phone in page:        {'✅' if op.get('phone_in_page') else '❌'}")
        print(f"    Mobile viewport:      {'✅' if op.get('has_viewport') else '❌'}")

    print()

    if result.verdict == "HOT":
        print("  ✅ Strong candidate — pitch local SEO package.")
    elif result.verdict == "WARM":
        print("  ⚡ Decent opportunity — worth a follow-up call.")
    else:
        print("  ⏭️  Low opportunity — move on or revisit later.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Score a local business as an SEO lead")
    parser.add_argument("--name",     required=True, help="Business name (from GBP listing)")
    parser.add_argument("--city",     required=True, help="City")
    parser.add_argument("--rating",   type=float,    help="Google star rating (e.g. 3.8)")
    parser.add_argument("--reviews",  type=int,      help="Number of Google reviews")
    parser.add_argument("--website",  help="Website URL from GBP (omit if none listed)")
    parser.add_argument("--keyword",  help="Target keyword for on-page checks (e.g. 'plumber toronto')")
    parser.add_argument("--mock",     action="store_true", help="Skip live website fetch")
    parser.add_argument("--sheets-id", dest="sheets_id", help="Write result to Google Sheets")
    args = parser.parse_args()

    if args.mock:
        print("  ⚠️  MOCK MODE — on-page checks use dummy data\n")

    result = evaluate(
        name=args.name,
        city=args.city,
        rating=args.rating,
        reviews=args.reviews,
        website=args.website,
        keyword=args.keyword,
        mock=args.mock,
    )

    print_result(result)

    sheets_id = get_sheets_id(args.sheets_id)
    if sheets_id:
        today = date.today().isoformat()
        gog_append(sheets_id, "Sites Dashboard", [
            args.website or "",
            args.name,
            args.keyword or "",
            args.city,
            f"{result.verdict} Lead",
            today,
            f"Score {result.score}/100 — " + "; ".join(l for l, _ in result.breakdown[:3]),
            "Hackerman",
        ])
        print(f"📊 Appended to Sheets: https://docs.google.com/spreadsheets/d/{sheets_id}")


if __name__ == "__main__":
    main()
