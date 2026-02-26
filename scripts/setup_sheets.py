#!/usr/bin/env python3
"""
setup_sheets.py — Create the Local SEO Pipeline Google Sheets template.
Run once per client or to initialize a fresh tracker.

Usage:
    python scripts/setup_sheets.py
    python scripts/setup_sheets.py --title "Jetta Grove SEO Tracker"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def run_gog(args: list[str]) -> dict:
    """Run a gog CLI command and return parsed JSON output."""
    cmd = ["gog", "--json"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ gog error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Some gog commands return non-JSON even with --json; return raw
        return {"raw": result.stdout.strip()}


def append_rows(spreadsheet_id: str, sheet_name: str, rows: list[list[str]]) -> None:
    """Append rows to a sheet tab."""
    for row in rows:
        args = ["sheets", "append", spreadsheet_id, f"{sheet_name}!A1"] + row
        run_gog(args)


def update_cell(spreadsheet_id: str, range_: str, *values: str) -> None:
    """Update a range with values."""
    args = ["sheets", "update", spreadsheet_id, range_] + list(values)
    run_gog(args)


def main():
    parser = argparse.ArgumentParser(description="Create Local SEO Pipeline Google Sheets template")
    parser.add_argument("--title", default="Local SEO Pipeline", help="Spreadsheet title")
    args = parser.parse_args()

    print(f"📊 Creating spreadsheet: {args.title}")

    # Step 1: Create spreadsheet
    result = run_gog(["sheets", "create", args.title])
    spreadsheet_id = result.get("spreadsheetId") or result.get("id")
    if not spreadsheet_id:
        # Try to extract from raw output
        raw = result.get("raw", "")
        for line in raw.splitlines():
            if "spreadsheetId" in line or "/d/" in line:
                print(f"Raw output: {raw}")
                break
        print("❌ Could not extract spreadsheet ID from gog output. Check gog sheets create --help.", file=sys.stderr)
        sys.exit(1)

    print(f"✅ Spreadsheet created: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")

    # Step 2: Rename default Sheet1 → Sites Dashboard
    print("📝 Setting up Tab 1: Sites Dashboard")
    # Get sheet ID for Sheet1
    info_result = run_gog(["sheets", "sheet", "list", spreadsheet_id])
    sheets = info_result if isinstance(info_result, list) else info_result.get("sheets", [])
    sheet1_id = None
    for s in sheets:
        title = s.get("properties", {}).get("title") or s.get("title", "")
        if title == "Sheet1":
            sheet1_id = s.get("properties", {}).get("sheetId") or s.get("sheetId")
            break

    if sheet1_id is not None:
        run_gog(["sheets", "sheet", "rename", spreadsheet_id, str(sheet1_id), "Sites Dashboard"])

    # Tab 1 headers
    update_cell(spreadsheet_id, "Sites Dashboard!A1",
                "Domain", "Business Name", "Primary Keyword", "City/Region",
                "Pipeline Stage", "Last Updated", "Next Action", "Assigned To")

    # Tab 2: SEO Checklist
    print("📝 Setting up Tab 2: SEO Checklist")
    run_gog(["sheets", "sheet", "add", spreadsheet_id, "SEO Checklist"])
    update_cell(spreadsheet_id, "SEO Checklist!A1",
                "Section", "Task", "Status", "Notes", "Agent", "Date Completed")

    checklist_items = [
        # Google Business Profile
        ("Google Business Profile", "Claim and Verify Your Google Business Profile (GBP)"),
        ("Google Business Profile", "Provide a Real Address (consistent everywhere)"),
        ("Google Business Profile", "Use a Local Phone Number"),
        ("Google Business Profile", "Cull Duplicate or Wrong GBP Listings"),
        ("Google Business Profile", "Choose the Best Primary Category"),
        ("Google Business Profile", "Add Secondary Categories (Up to 9)"),
        ("Google Business Profile", "Complete Every Section of Your Profile"),
        ("Google Business Profile", "List Your Products and Services"),
        ("Google Business Profile", "Add Plenty of High Quality Photos (and Videos)"),
        ("Google Business Profile", "Set a Cover Photo and Logo"),
        ("Google Business Profile", "Keep Hours Accurate (Including Holidays)"),
        ("Google Business Profile", "Use Google Posts"),
        ("Google Business Profile", "Monitor and Answer Q&A"),
        ("Google Business Profile", "Link to the Correct Website URL"),
        ("Google Business Profile", "Maintain Profile Health Over Time"),
        # Website & On-Page SEO
        ("Website & On-Page SEO", "NAP + Schema on Your Site"),
        ("Website & On-Page SEO", "Create a Dedicated Contact/Location Page"),
        ("Website & On-Page SEO", "Incorporate Local Keywords in Key Elements"),
        ("Website & On-Page SEO", "Include Location Info Site-Wide"),
        ("Website & On-Page SEO", "Use LocalBusiness Schema Markup"),
        ("Website & On-Page SEO", "Embed a Google Map on Your Site"),
        ("Website & On-Page SEO", "Publish Location-Specific Content"),
        ("Website & On-Page SEO", "Optimize for Mobile and Speed"),
        ("Website & On-Page SEO", "Implement Clear Calls to Action (CTAs)"),
        ("Website & On-Page SEO", "Use Testimonials and Trust Indicators"),
        ("Website & On-Page SEO", "Regularly Update Website Content"),
        # Reviews & Reputation Management
        ("Reviews & Reputation", "ASK FOR REVIEWS"),
        ("Reviews & Reputation", "Make It Easy to Leave Reviews (QR code, pretty URLs)"),
        ("Reviews & Reputation", "Respond to All Reviews"),
        ("Reviews & Reputation", "Get Keywords in Reviews"),
        ("Reviews & Reputation", "Monitor Your Reputation Beyond Google"),
        ("Reviews & Reputation", "Avoid Review Gating and Incentives"),
        # Citations & Local Listings
        ("Citations & Local Listings", "Audit Your Existing Citations and Listings"),
        ("Citations & Local Listings", "Maintain NAP Consistency Across the Web"),
        ("Citations & Local Listings", "Get Listed on Major Directories and Map Services"),
        ("Citations & Local Listings", "Build Citations on Niche and Local Directories"),
        ("Citations & Local Listings", "Use Consistent Categories and Descriptions"),
        # Local Link Building
        ("Local Link Building", "Build Local Backlinks with NAP"),
        ("Local Link Building", "Sponsor Local Events or Organizations"),
        ("Local Link Building", "Earn Local Press Coverage and PR"),
        ("Local Link Building", "Link Exchange with Local Businesses"),
        ("Local Link Building", "Create Local Resource Content for Backlinks"),
        ("Local Link Building", "Awards Link Building"),
        # Behavioral Signals
        ("Behavioral Signals", "Fill Out Your Title Tags & Meta Descriptions"),
        ("Behavioral Signals", "Make Sure UX is Good"),
        ("Behavioral Signals", "Make Your Google Profile Clickable"),
        ("Behavioral Signals", "Use Google Booking & Reservation Features"),
        ("Behavioral Signals", "Monitor Behavioral Metrics in Analytics"),
        ("Behavioral Signals", "Encourage Brand Searches and Direct Traffic"),
        # Tracking & Reporting
        ("Tracking & Reporting", "Use a rank tracking tool"),
        ("Tracking & Reporting", "Monitor Google Business Profile Insights"),
        ("Tracking & Reporting", "Track Reviews and Mentions in One Dashboard"),
        ("Tracking & Reporting", "Set Up Google Search Console for Your Website"),
        ("Tracking & Reporting", "Regular Reporting and Analysis"),
        ("Tracking & Reporting", "Stay Informed on Local SEO Updates"),
    ]

    rows = [[section, task, "Not Started", "", "", ""] for section, task in checklist_items]
    append_rows(spreadsheet_id, "SEO Checklist", rows)

    # Tab 3: Competitor Audit
    print("📝 Setting up Tab 3: Competitor Audit")
    run_gog(["sheets", "sheet", "add", spreadsheet_id, "Competitor Audit"])
    update_cell(spreadsheet_id, "Competitor Audit!A1",
                "Competitor Domain", "DA", "Page Authority", "Backlinks",
                "Referring Domains", "Spam Score", "In Local Pack (Y/N)",
                "Title Tag Has Keyword (Y/N)", "Notes")

    # Tab 4: Citations Tracker
    print("📝 Setting up Tab 4: Citations Tracker")
    run_gog(["sheets", "sheet", "add", spreadsheet_id, "Citations Tracker"])
    update_cell(spreadsheet_id, "Citations Tracker!A1",
                "Directory", "URL", "Submitted Date", "Status", "Login Email", "Notes")

    citation_dirs = [
        "Google Business Profile", "Yelp", "Bing Places", "Apple Maps", "BBB",
        "YellowPages", "Foursquare", "Facebook Business", "LinkedIn Company",
        "TripAdvisor", "Angi", "HomeAdvisor", "Thumbtack", "Houzz", "Nextdoor",
        "Chamber of Commerce", "MapQuest", "Here WeGo", "Waze", "Trustpilot",
    ]
    citation_rows = [[d, "", "", "Not Checked", "", ""] for d in citation_dirs]
    append_rows(spreadsheet_id, "Citations Tracker", citation_rows)

    # Tab 5: Monthly Reports
    print("📝 Setting up Tab 5: Monthly Reports")
    run_gog(["sheets", "sheet", "add", spreadsheet_id, "Monthly Reports"])
    update_cell(spreadsheet_id, "Monthly Reports!A1",
                "Date", "Keyword", "Local Pack Position", "GBP Views",
                "Calls", "Direction Requests", "Website Clicks")

    # Save spreadsheet ID
    sheets_id_file = REPO_ROOT / ".sheets_id"
    sheets_id_file.write_text(spreadsheet_id)
    print(f"\n✅ All tabs created. Spreadsheet ID saved to .sheets_id")
    print(f"🔗 https://docs.google.com/spreadsheets/d/{spreadsheet_id}")


if __name__ == "__main__":
    main()
