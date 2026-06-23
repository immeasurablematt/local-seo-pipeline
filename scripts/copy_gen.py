#!/usr/bin/env python3
"""
copy_gen.py — Collect client strengths per bucket and prepare a copy brief for Claude.

Run this after you've pasted .reviews_raw.json into Claude and got the bucket analysis back.
Save Claude's bucket analysis as .market_intel.json first — this script will show
the market gap per bucket to help you answer the strength questions.

Usage:
    python scripts/copy_gen.py \
        --keyword "plumber toronto" \
        --name "Joe's Plumbing" \
        --city "Toronto" \
        --phone "416-555-1234" \
        --website "https://joesplumbing.com"

    # If you haven't saved .market_intel.json yet, it still works —
    # just shows bucket labels without gap context:
    python scripts/copy_gen.py --keyword "plumber toronto"

    # Skip interactive prompts (for testing):
    python scripts/copy_gen.py --keyword "plumber toronto" --mock

Output:
    .strengths.json     — your answers, ready to paste into Claude for copy generation
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MARKET_INTEL_FILE = REPO_ROOT / ".market_intel.json"
STRENGTHS_FILE = REPO_ROOT / ".strengths.json"

BUCKET_LABELS = {
    "reliability": "Reliability (shows up on time, follows through)",
    "communication": "Communication (responsive, keeps you informed)",
    "price_transparency": "Price Transparency (clear quotes, no surprises)",
    "quality_of_work": "Quality of Work (craftsmanship, attention to detail)",
    "speed": "Speed (fast turnaround, on-time completion)",
    "facility_space": "Facility / Space (clean, tidy, professional environment)",
    "staff_attitude": "Staff Attitude (friendly, professional, easy to deal with)",
    "process_ease": "Process / Ease (easy booking, smooth workflow, no hassle)",
    "results_outcome": "Results / Outcome (problem solved, measurable improvement)",
    "value_for_money": "Value for Money (clients feel they got more than they paid for)",
}

MOCK_STRENGTHS = {
    "reliability": ("yes", "We've never missed an appointment in 8 years of business."),
    "communication": ("yes", "Clients get a text update at every stage of the job."),
    "price_transparency": ("yes", "We give fixed-price quotes before any work starts."),
    "quality_of_work": ("yes", "All work comes with a 2-year workmanship guarantee."),
    "speed": ("no", ""),
    "facility_space": ("skip", ""),
    "staff_attitude": ("yes", "90% of our clients are referrals — people love our team."),
    "process_ease": ("yes", "Book online in 60 seconds, same-day confirmation."),
    "results_outcome": ("yes", "We fix it right the first time or return for free."),
    "value_for_money": ("no", ""),
}


def load_market_intel() -> dict:
    if MARKET_INTEL_FILE.exists():
        return json.loads(MARKET_INTEL_FILE.read_text())
    return {}


def ask_bucket_strengths(intel: dict, mock: bool = False) -> dict[str, dict]:
    buckets = intel.get("buckets", {})
    strengths: dict[str, dict] = {}

    print("\n" + "=" * 60)
    print("  STRENGTH CLASSIFIER")
    print("  For each bucket: is this something your business does")
    print("  better than competitors? (yes / no / skip)")
    print("=" * 60)

    for key, label in BUCKET_LABELS.items():
        b = buckets.get(key, {})
        gap = b.get("market_gap", "")
        sentiment = b.get("sentiment", "")
        praise = b.get("top_praise", [])

        print(f"\n  ── {label}")
        if gap:
            print(f"     Market gap : {gap}")
        if sentiment:
            icon = {"positive": "✅", "negative": "❌", "mixed": "⚠️"}.get(sentiment, "")
            print(f"     Competitors: {icon} {sentiment}")
        if praise:
            print(f"     Praised for: {praise[0]}")

        if mock:
            answer, proof = MOCK_STRENGTHS.get(key, ("no", ""))
            print(f"     [MOCK] Strength? → {answer}")
            if answer == "yes" and proof:
                print(f"     [MOCK] Proof   → {proof}")
        else:
            raw = input("     Strength? (yes/no/skip) [no]: ").strip().lower() or "no"
            answer = "yes" if raw in ("yes", "y") else ("skip" if raw == "skip" else "no")
            proof = ""
            if answer == "yes":
                proof = input("     Proof point / unique claim: ").strip()

        strengths[key] = {"answer": answer, "proof": proof}

    return strengths


def main():
    parser = argparse.ArgumentParser(description="Collect client strengths and prepare copy brief")
    parser.add_argument("--keyword", required=True, help="Target keyword (e.g. 'plumber toronto')")
    parser.add_argument("--name", default="", help="Business name")
    parser.add_argument("--city", default="", help="City")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument("--website", default="", help="Website URL")
    parser.add_argument("--intel", help="Path to market_intel.json (default: .market_intel.json)")
    parser.add_argument("--output", help="Output path (default: .strengths.json)")
    parser.add_argument("--mock", action="store_true", help="Use pre-set answers, skip prompts")
    args = parser.parse_args()

    intel_file = Path(args.intel) if args.intel else MARKET_INTEL_FILE
    output_file = Path(args.output) if args.output else STRENGTHS_FILE

    intel = json.loads(intel_file.read_text()) if intel_file.exists() else {}
    if intel:
        print(f"📂 Loaded market intel: {intel.get('keyword', '')} ({intel.get('total_reviews_analysed', 0)} reviews)")
    else:
        print("ℹ️  No .market_intel.json found — showing bucket labels only.")
        print("   Tip: paste .reviews_raw.json into Claude, get bucket analysis, save as .market_intel.json")

    if args.mock:
        print("  ⚠️  MOCK MODE\n")

    strengths = ask_bucket_strengths(intel, mock=args.mock)

    owned = sum(1 for s in strengths.values() if s["answer"] == "yes")

    output = {
        "keyword": args.keyword,
        "business": {
            "name": args.name,
            "city": args.city or args.keyword.split()[-1],
            "phone": args.phone,
            "website": args.website,
        },
        "owned_count": owned,
        "strengths": strengths,
    }
    output_file.write_text(json.dumps(output, indent=2))
    print(f"\n✅ {owned} strengths claimed → saved to {output_file}")

    # Print the paste-ready brief for Claude
    print("\n" + "=" * 60)
    print("  PASTE THE FOLLOWING INTO CLAUDE:")
    print("=" * 60)
    print(f"\nKeyword: {args.keyword}")
    if args.name:
        print(f"Business: {args.name}")
    city = args.city or args.keyword.split()[-1]
    if city:
        print(f"City: {city}")
    if args.phone:
        print(f"Phone: {args.phone}")
    if args.website:
        print(f"Website: {args.website}")
    print("\nStrengths this business owns:")
    for key, s in strengths.items():
        if s["answer"] == "yes":
            label = BUCKET_LABELS[key]
            proof = s.get("proof", "")
            line = f"  - {label}"
            if proof:
                line += f": {proof}"
            print(line)
    print("\nWrite a copy skeleton with: homepage headline (3 variants, mark strongest ⭐),")
    print("subheadline, 3-5 feature bullets, Google Ads hook (2 variants),")
    print("3 email subject lines, 4 FAQ items, and CTA copy.")
    print()


if __name__ == "__main__":
    main()
