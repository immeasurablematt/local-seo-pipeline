#!/usr/bin/env python3
"""
audit.py — Local SEO audit using DataForSEO + on-page checks.

Pulls top-5 Local Pack competitors for a keyword + city,
runs basic on-page checks on the input domain, and populates
Google Sheets Tabs 1 (Sites Dashboard) and 3 (Competitor Audit).

Usage:
    python scripts/audit.py \
        --domain example.com \
        --name "Business Name" \
        --address "123 Main St, Toronto, ON M1A 1A1" \
        --phone "416-555-1234" \
        --keyword "plumber toronto" \
        --city "Toronto"

    # Test without API calls:
    python scripts/audit.py --domain example.com --name "Test Biz" \
        --address "1 Test St" --phone "555-0000" \
        --keyword "plumber toronto" --city "Toronto" --mock
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent
DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"
LOCATION_CODE_CANADA = 2124


def get_auth_headers() -> dict:
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        print("❌ DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set.", file=sys.stderr)
        print("   export DATAFORSEO_LOGIN=\"$(security find-generic-password -s openclaw -a dataforseo-login -w)\"", file=sys.stderr)
        print("   export DATAFORSEO_PASSWORD=\"$(security find-generic-password -s openclaw -a dataforseo-password -w)\"", file=sys.stderr)
        sys.exit(1)
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def fetch_local_pack(keyword: str, mock: bool = False) -> list[dict]:
    """Return top-5 Local Pack results for keyword."""
    if mock:
        return [
            {"title": f"Mock Competitor {i}", "domain": f"mock-competitor-{i}.com",
             "rating": round(4.0 + i * 0.1, 1), "rating_count": 50 + i * 10}
            for i in range(1, 6)
        ]

    payload = [{
        "keyword": keyword,
        "location_code": LOCATION_CODE_CANADA,
        "language_code": "en",
        "device": "desktop",
        "depth": 10,
    }]

    try:
        resp = requests.post(
            f"{DATAFORSEO_BASE_URL}/serp/google/local_pack/live/regular",
            headers=get_auth_headers(),
            json={"data": payload},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"❌ DataForSEO request failed: {e}", file=sys.stderr)
        return []

    results = []
    try:
        items = data["tasks"][0]["result"][0]["items"]
        for item in items:
            if item.get("type") == "local_pack":
                results.append({
                    "title": item.get("title", ""),
                    "domain": item.get("domain", item.get("url", "")),
                    "rating": item.get("rating", {}).get("value") if isinstance(item.get("rating"), dict) else item.get("rating"),
                    "rating_count": item.get("rating", {}).get("votes_count", 0) if isinstance(item.get("rating"), dict) else 0,
                })
    except (KeyError, IndexError, TypeError) as e:
        print(f"⚠️  Could not parse DataForSEO response: {e}", file=sys.stderr)

    return results[:5]


def check_on_page(domain: str, keyword: str, address: str, phone: str, mock: bool = False) -> dict:
    """Run basic on-page checks against a domain homepage."""
    if mock:
        return {
            "title_has_keyword": False,
            "h1_has_keyword": False,
            "has_local_schema": False,
            "phone_in_page": True,
            "address_in_page": False,
            "has_viewport": True,
            "error": None,
        }

    url = domain if domain.startswith("http") else f"https://{domain}"
    checks = {
        "title_has_keyword": False,
        "h1_has_keyword": False,
        "has_local_schema": False,
        "phone_in_page": False,
        "address_in_page": False,
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
        page_text = soup.get_text(" ").lower()
        kw_lower = keyword.lower()

        # Title tag
        title_tag = soup.find("title")
        if title_tag and kw_lower in title_tag.get_text().lower():
            checks["title_has_keyword"] = True

        # H1
        h1 = soup.find("h1")
        if h1 and kw_lower in h1.get_text().lower():
            checks["h1_has_keyword"] = True

        # LocalBusiness schema
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                schema = json.loads(script.string or "")
                schema_type = schema.get("@type", "")
                if "LocalBusiness" in schema_type or (
                    isinstance(schema_type, list) and any("LocalBusiness" in t for t in schema_type)
                ):
                    checks["has_local_schema"] = True
                    break
            except (json.JSONDecodeError, AttributeError):
                continue

        # Phone in page (strip non-digits for fuzzy match)
        phone_digits = re.sub(r"\D", "", phone)
        page_digits = re.sub(r"\D", "", page_text)
        if phone_digits and phone_digits in page_digits:
            checks["phone_in_page"] = True

        # Address fragment in page
        addr_parts = [p.strip().lower() for p in address.split(",") if p.strip()]
        if addr_parts and any(part in page_text for part in addr_parts[:2]):
            checks["address_in_page"] = True

        # Viewport meta
        if soup.find("meta", attrs={"name": re.compile("viewport", re.I)}):
            checks["has_viewport"] = True

    except requests.RequestException as e:
        checks["error"] = str(e)

    return checks


def gog_append(spreadsheet_id: str, sheet: str, row: list[str]) -> None:
    """Append a row to a Google Sheet via gog CLI."""
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


def main():
    parser = argparse.ArgumentParser(description="Local SEO audit via DataForSEO")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--name", required=True, help="Business name")
    parser.add_argument("--address", required=True, help="Full address")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--keyword", required=True, help="Primary keyword (e.g. 'plumber toronto')")
    parser.add_argument("--city", required=True)
    parser.add_argument("--sheets-id", dest="sheets_id", help="Google Sheets ID (reads .sheets_id if omitted)")
    parser.add_argument("--mock", action="store_true", help="Skip API calls, use mock data")
    args = parser.parse_args()

    sheets_id = get_sheets_id(args.sheets_id)

    print(f"\n🔍 Auditing: {args.domain}")
    print(f"   Keyword: {args.keyword} | City: {args.city}")
    if args.mock:
        print("   ⚠️  MOCK MODE — no real API calls\n")

    # 1. Local pack competitors
    print("📡 Fetching Local Pack competitors...")
    competitors = fetch_local_pack(args.keyword, mock=args.mock)

    if competitors:
        print(f"✅ Found {len(competitors)} Local Pack competitors:")
        for i, c in enumerate(competitors, 1):
            print(f"   {i}. {c['title']} ({c['domain']}) — ⭐ {c['rating']} ({c['rating_count']} reviews)")
    else:
        print("⚠️  No Local Pack results found.")

    # 2. On-page checks
    print(f"\n🌐 Running on-page checks for {args.domain}...")
    onpage = check_on_page(args.domain, args.keyword, args.address, args.phone, mock=args.mock)

    print(f"   Title has keyword:    {'✅' if onpage['title_has_keyword'] else '❌'}")
    print(f"   H1 has keyword:       {'✅' if onpage['h1_has_keyword'] else '❌'}")
    print(f"   LocalBusiness schema: {'✅' if onpage['has_local_schema'] else '❌'}")
    print(f"   Phone in page:        {'✅' if onpage['phone_in_page'] else '❌'}")
    print(f"   Address in page:      {'✅' if onpage['address_in_page'] else '❌'}")
    print(f"   Mobile viewport:      {'✅' if onpage['has_viewport'] else '❌'}")
    if onpage["error"]:
        print(f"   ⚠️  Fetch error: {onpage['error']}")

    # 3. Write to Sheets
    if sheets_id:
        today = date.today().isoformat()
        issues = []
        if not onpage["title_has_keyword"]: issues.append("title tag missing keyword")
        if not onpage["has_local_schema"]: issues.append("no LocalBusiness schema")
        if not onpage["phone_in_page"]: issues.append("phone not found on page")
        next_action = "; ".join(issues) if issues else "Review competitor gaps"

        print(f"\n📊 Writing to Google Sheets ({sheets_id})...")

        # Tab 1: Sites Dashboard
        gog_append(sheets_id, "Sites Dashboard", [
            args.domain, args.name, args.keyword, args.city,
            "Audit", today, next_action, "Hackerman",
        ])

        # Tab 3: Competitor Audit
        for c in competitors:
            gog_append(sheets_id, "Competitor Audit", [
                c["domain"], "", "", "", "", "",
                "Y",  # In Local Pack
                "",   # Title tag keyword (would need separate check)
                c["title"],
            ])

        print(f"✅ Sheets updated: https://docs.google.com/spreadsheets/d/{sheets_id}")
    else:
        print("\n⚠️  No Sheets ID found — run setup_sheets.py first or pass --sheets-id")

    print("\n✅ Audit complete.")


if __name__ == "__main__":
    main()
