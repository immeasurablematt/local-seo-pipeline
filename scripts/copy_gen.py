#!/usr/bin/env python3
"""
copy_gen.py — Generate a copy skeleton from market intelligence + client strengths.

Implements the 2-step copy framework:
  Step 4: Interactive bucket-by-bucket strength classification (what can YOU own?)
  Step 5: Claude builds the copy skeleton — headline, hooks, FAQ, CTAs

Reads .market_intel.json (written by market_intel.py).

Usage:
    python scripts/copy_gen.py --keyword "plumber toronto"

    # With client info (used in copy output):
    python scripts/copy_gen.py \
        --keyword "plumber toronto" \
        --name "Joe's Plumbing" \
        --city "Toronto" \
        --phone "416-555-1234" \
        --website "https://joesplumbing.com"

    # Skip interactive prompts (useful for testing):
    python scripts/copy_gen.py --keyword "plumber toronto" --mock

Output:
    .copy_skeleton.md  — ready-to-use copy for landing page / ads / email
"""

import argparse
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent
MARKET_INTEL_FILE = REPO_ROOT / ".market_intel.json"
COPY_SKELETON_FILE = REPO_ROOT / ".copy_skeleton.md"

BUCKET_LABELS = {
    "reliability": "Reliability (shows up on time, follows through)",
    "communication": "Communication (responsive, keeps you informed)",
    "price_transparency": "Price Transparency (clear quotes, no surprises)",
    "quality_of_work": "Quality of Work (craftsmanship, detail, professional finish)",
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


def ask_bucket_strengths(intel: dict, mock: bool = False) -> dict[str, dict]:
    """
    Walk the user through each bucket and collect:
    - Is this a strength? (yes / no / skip)
    - If yes: what's your proof point / unique claim?
    Returns dict keyed by bucket with user answers.
    """
    buckets = intel.get("buckets", {})
    strengths: dict[str, dict] = {}
    bucket_order = list(BUCKET_LABELS.keys())

    print("\n" + "=" * 60)
    print("  STEP 4 — CLASSIFY YOUR STRENGTHS")
    print("  For each bucket, tell me if it's a strength you can claim.")
    print("  Answer: yes / no / skip  (or press Enter for no)")
    print("=" * 60)

    for key in bucket_order:
        label = BUCKET_LABELS[key]
        b = buckets.get(key, {})
        gap = b.get("market_gap", "")
        sentiment = b.get("sentiment", "")
        praise = b.get("top_praise", [])

        print(f"\n  ── {label}")
        if gap:
            print(f"     Market gap: {gap}")
        if sentiment:
            sent_icon = {"positive": "✅", "negative": "❌", "mixed": "⚠️"}.get(sentiment, "")
            print(f"     Competitor sentiment: {sent_icon} {sentiment}")
        if praise:
            print(f"     Customers praise: {praise[0]}")

        if mock:
            answer, proof = MOCK_STRENGTHS.get(key, ("no", ""))
            print(f"     [MOCK] Is this a strength? → {answer}")
            if answer == "yes" and proof:
                print(f"     [MOCK] Proof point → {proof}")
        else:
            answer = input("     Is this a strength for your business? (yes/no/skip) [no]: ").strip().lower() or "no"
            proof = ""
            if answer in ("yes", "y"):
                answer = "yes"
                proof = input("     What's your proof point or unique claim? ").strip()

        strengths[key] = {"answer": answer, "proof": proof}

    return strengths


def build_copy_with_claude(
    keyword: str,
    name: str,
    city: str,
    phone: str,
    website: str,
    intel: dict,
    strengths: dict[str, dict],
) -> str:
    """
    Send market intel + client strengths to Claude.
    Returns the complete copy skeleton as markdown.
    """
    # Build strengths summary for the prompt
    owned_buckets = []
    for key, s in strengths.items():
        if s["answer"] == "yes":
            label = BUCKET_LABELS[key]
            proof = s.get("proof", "")
            line = f"- **{label}**"
            if proof:
                line += f": {proof}"
            owned_buckets.append(line)

    strengths_block = "\n".join(owned_buckets) if owned_buckets else "None specified"

    # Build competitor gap summary
    gap_block = ""
    for key in BUCKET_LABELS:
        b = intel.get("buckets", {}).get(key, {})
        gap = b.get("market_gap", "")
        if gap:
            gap_block += f"- {BUCKET_LABELS[key]}: {gap}\n"

    business_info = f"Business: {name or 'the client'}"
    if city:
        business_info += f" — {city}"
    if phone:
        business_info += f" | Phone: {phone}"
    if website:
        business_info += f" | Website: {website}"

    prompt = f"""You are an expert local business copywriter. Your job is to write a **copy skeleton** for a local business that will be used to build their website, Google Ads, and email campaign.

{business_info}
Target keyword: {keyword}

## Market Intelligence (from competitor review analysis)

### Gaps competitors are failing to fill:
{gap_block}

### What this business does well (their owned differentiators):
{strengths_block}

## Your Task

Write a complete **copy skeleton** in markdown. Include all of the following sections:

### 1. Homepage Headline (h1)
A punchy, benefit-led headline that positions against competitor weaknesses.
Write 3 variations — mark the strongest with ⭐.

### 2. Homepage Subheadline
One or two sentences that expand the headline and include the target keyword naturally.

### 3. Feature Bullets (3–5 items)
Short, scannable bullets. Each should reference a real strength the business owns.
Format: **Claim** — brief supporting detail.

### 4. Social Proof Prompt
Suggest the exact type of testimonial to collect (what to ask for, what the customer should mention).

### 5. Google Ads Hook (2 variations)
30-character headline + 90-character description for each.
Lead with the biggest gap competitors are missing.

### 6. Email Subject Line (3 variations)
For a cold outreach email to a homeowner in {city or "the target city"}.
Curiosity-led or problem-led — no spam triggers.

### 7. FAQ (4 questions)
Questions real customers ask in this market. Answers should be 2-3 sentences, keyword-natural, and reassuring.

### 8. CTA Copy
Primary CTA button text (5 words max) + secondary CTA (if applicable).

---
Keep the tone: direct, local, trust-building. Avoid corporate fluff.
Use real specifics from the strengths listed above — don't be generic.
"""

    client = anthropic.Anthropic()

    print("\n🤖 Claude is writing your copy skeleton...")

    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    copy_text = ""
    for block in message.content:
        if block.type == "text":
            copy_text = block.text
            break

    return copy_text


def main():
    parser = argparse.ArgumentParser(description="Generate copy skeleton from market intel + client strengths")
    parser.add_argument("--keyword", required=True, help="Target keyword (e.g. 'plumber toronto')")
    parser.add_argument("--name", default="", help="Business name")
    parser.add_argument("--city", default="", help="City")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument("--website", default="", help="Website URL")
    parser.add_argument("--intel", help="Path to market_intel.json (default: .market_intel.json)")
    parser.add_argument("--output", help="Output path for copy skeleton (default: .copy_skeleton.md)")
    parser.add_argument("--mock", action="store_true", help="Skip interactive prompts, use mock strengths")
    args = parser.parse_args()

    intel_file = Path(args.intel) if args.intel else MARKET_INTEL_FILE
    output_file = Path(args.output) if args.output else COPY_SKELETON_FILE

    if not intel_file.exists():
        print(f"❌ {intel_file} not found. Run market_intel.py first.", file=sys.stderr)
        sys.exit(1)

    intel = json.loads(intel_file.read_text())
    print(f"📂 Loaded market intel: {intel.get('keyword', '')} ({intel.get('total_reviews_analysed', 0)} reviews)")

    if args.mock:
        print("  ⚠️  MOCK MODE — using pre-set strengths\n")

    # Step 4: Interactive strength classification
    strengths = ask_bucket_strengths(intel, mock=args.mock)

    owned = sum(1 for s in strengths.values() if s["answer"] == "yes")
    print(f"\n  → {owned} strengths claimed across {len(strengths)} buckets")

    # Step 5: Claude generates copy
    city = args.city or args.keyword.split()[-1]
    copy_text = build_copy_with_claude(
        keyword=args.keyword,
        name=args.name,
        city=city,
        phone=args.phone,
        website=args.website,
        intel=intel,
        strengths=strengths,
    )

    if not copy_text:
        print("❌ Copy generation failed.", file=sys.stderr)
        sys.exit(1)

    # Add header to the output file
    header = f"# Copy Skeleton — {args.name or args.keyword}\n\n"
    header += f"**Keyword:** {args.keyword}  \n"
    if args.name:
        header += f"**Business:** {args.name}  \n"
    if args.city or city:
        header += f"**City:** {city}  \n"
    header += "\n---\n\n"

    output_file.write_text(header + copy_text)
    print(f"\n✅ Copy skeleton saved → {output_file}")
    print(f"\n  Next step: use /landing-page skill to build the website from this copy.")
    print(f"  Or open {output_file} and paste copy into your CMS / ad platform.\n")


if __name__ == "__main__":
    main()
