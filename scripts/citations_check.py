#!/usr/bin/env python3
"""
citations_check.py — Check NAP consistency across top 20 directories.

Searches each directory for the business name and flags missing/unverified listings.
Updates Tab 4 (Citations Tracker) in Google Sheets.

Usage:
    python scripts/citations_check.py \
        --name "Business Name" \
        --address "123 Main St, Toronto, ON" \
        --phone "416-555-1234"

    # Test without real requests:
    python scripts/citations_check.py --name "Test Biz" --address "1 Test St" \
        --phone "555-0000" --mock
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent

DIRECTORIES = [
    {
        "name": "Google Business Profile",
        "search_url": "https://www.google.com/maps/search/?q={name}+{phone}",
        "row_index": 2,
    },
    {
        "name": "Yelp",
        "search_url": "https://www.yelp.com/search?find_desc={name}",
        "row_index": 3,
    },
    {
        "name": "Bing Places",
        "search_url": "https://www.bingplaces.com",
        "row_index": 4,
    },
    {
        "name": "Apple Maps",
        "search_url": "https://maps.apple.com/?q={name}",
        "row_index": 5,
    },
    {
        "name": "BBB",
        "search_url": "https://www.bbb.org/search?find_text={name}",
        "row_index": 6,
    },
    {
        "name": "YellowPages",
        "search_url": "https://www.yellowpages.ca/search/si/1/{name}/Canada",
        "row_index": 7,
    },
    {
        "name": "Foursquare",
        "search_url": "https://foursquare.com/explore?q={name}",
        "row_index": 8,
    },
    {
        "name": "Facebook Business",
        "search_url": "https://www.facebook.com/search/pages/?q={name}",
        "row_index": 9,
    },
    {
        "name": "LinkedIn Company",
        "search_url": "https://www.linkedin.com/search/results/companies/?keywords={name}",
        "row_index": 10,
    },
    {
        "name": "TripAdvisor",
        "search_url": "https://www.tripadvisor.com/Search?q={name}",
        "row_index": 11,
    },
    {
        "name": "Angi",
        "search_url": "https://www.angi.com/companylist/us/{name}.htm",
        "row_index": 12,
    },
    {
        "name": "HomeAdvisor",
        "search_url": "https://www.homeadvisor.com",
        "row_index": 13,
    },
    {
        "name": "Thumbtack",
        "search_url": "https://www.thumbtack.com/search?q={name}",
        "row_index": 14,
    },
    {
        "name": "Houzz",
        "search_url": "https://www.houzz.com/professionals/search?q={name}",
        "row_index": 15,
    },
    {
        "name": "Nextdoor",
        "search_url": "https://nextdoor.com",
        "row_index": 16,
    },
    {
        "name": "Chamber of Commerce",
        "search_url": "https://www.chamberofcommerce.com/search?q={name}",
        "row_index": 17,
    },
    {
        "name": "MapQuest",
        "search_url": "https://www.mapquest.com/search/results?query={name}",
        "row_index": 18,
    },
    {
        "name": "Here WeGo",
        "search_url": "https://wego.here.com",
        "row_index": 19,
    },
    {
        "name": "Waze",
        "search_url": "https://www.waze.com",
        "row_index": 20,
    },
    {
        "name": "Trustpilot",
        "search_url": "https://www.trustpilot.com/search?query={name}",
        "row_index": 21,
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def check_directory(directory: dict, name: str, phone: str, mock: bool = False) -> dict:
    """Check a single directory for the business listing."""
    name_encoded = quote_plus(name)
    phone_encoded = quote_plus(phone)
    url = directory["search_url"].format(name=name_encoded, phone=phone_encoded)

    if mock:
        import random
        status = random.choice(["Listed", "Listed", "Not Found", "Check Manually"])
        return {"name": directory["name"], "url": url, "status": status}

    # Directories that require JS or login — mark as manual
    manual_only = {"Apple Maps", "Bing Places", "Nextdoor", "Here WeGo", "Waze",
                   "Facebook Business", "LinkedIn Company"}
    if directory["name"] in manual_only:
        return {"name": directory["name"], "url": url, "status": "Check Manually"}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if resp.status_code == 200:
            # Case-insensitive name fragment search
            name_words = name.lower().split()
            page_lower = resp.text.lower()
            # Check if at least 2 significant words from the name appear on the page
            matches = sum(1 for word in name_words if len(word) > 3 and word in page_lower)
            if matches >= min(2, len([w for w in name_words if len(w) > 3])):
                status = "Listed"
            else:
                status = "Not Found"
        elif resp.status_code in (403, 429, 503):
            status = "Check Manually"
        else:
            status = "Not Found"
    except requests.RequestException:
        status = "Check Manually"

    return {"name": directory["name"], "url": url, "status": status}


def gog_update_row(spreadsheet_id: str, row_index: int, status: str, url: str) -> None:
    """Update Status (col D) and URL (col B) for a Citations Tracker row."""
    cmd_url = ["gog", "--json", "sheets", "update", spreadsheet_id,
               f"Citations Tracker!B{row_index}", url]
    cmd_status = ["gog", "--json", "sheets", "update", spreadsheet_id,
                  f"Citations Tracker!D{row_index}", status]
    for cmd in [cmd_url, cmd_status]:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️  gog update failed: {result.stderr}", file=sys.stderr)


def get_sheets_id(provided: str | None) -> str | None:
    if provided:
        return provided
    id_file = REPO_ROOT / ".sheets_id"
    if id_file.exists():
        return id_file.read_text().strip()
    return None


def main():
    parser = argparse.ArgumentParser(description="Check business citations across top 20 directories")
    parser.add_argument("--name", required=True, help="Business name")
    parser.add_argument("--address", required=True, help="Business address")
    parser.add_argument("--phone", required=True, help="Business phone")
    parser.add_argument("--sheets-id", dest="sheets_id")
    parser.add_argument("--mock", action="store_true", help="Use mock data, skip real requests")
    args = parser.parse_args()

    sheets_id = get_sheets_id(args.sheets_id)

    print(f"\n🔍 Citations check for: {args.name}")
    print(f"   Address: {args.address}")
    print(f"   Phone:   {args.phone}")
    if args.mock:
        print("   ⚠️  MOCK MODE\n")

    results = []
    for directory in DIRECTORIES:
        result = check_directory(directory, args.name, args.phone, mock=args.mock)
        results.append(result)

        icon = "✅" if result["status"] == "Listed" else ("⚠️ " if result["status"] == "Not Found" else "🔍")
        print(f"  {icon} {result['name']:<25} {result['status']}")

        # Rate limit — be gentle with directories
        if not args.mock:
            time.sleep(0.5)

    # Summary
    listed = sum(1 for r in results if r["status"] == "Listed")
    not_found = sum(1 for r in results if r["status"] == "Not Found")
    manual = sum(1 for r in results if r["status"] == "Check Manually")

    print(f"\n📊 Summary: {listed} listed | {not_found} not found | {manual} check manually")

    missing = [r["name"] for r in results if r["status"] == "Not Found"]
    if missing:
        print(f"\n⚠️  Missing citations ({len(missing)}):")
        for m in missing:
            print(f"   - {m}")

    # Write to Sheets
    if sheets_id:
        print(f"\n📊 Updating Google Sheets ({sheets_id})...")
        for directory, result in zip(DIRECTORIES, results):
            gog_update_row(sheets_id, directory["row_index"], result["status"], result["url"])
        print(f"✅ Citations Tracker updated: https://docs.google.com/spreadsheets/d/{sheets_id}")
    else:
        print("\n⚠️  No Sheets ID — run setup_sheets.py first or pass --sheets-id")

    print("\n✅ Citations check complete.")


if __name__ == "__main__":
    main()
