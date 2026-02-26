#!/usr/bin/env python3
"""
schema_gen.py — Generate LocalBusiness JSON-LD schema markup.

Usage:
    python scripts/schema_gen.py \
        --name "Jetta Grove Consulting" \
        --address "123 Main St, Welland, ON L3B 1A1" \
        --phone "905-555-1234" \
        --website "https://jettagrove.com" \
        --type "ProfessionalService" \
        --hours "Mon-Fri 09:00-17:00" \
        --description "Business strategy consulting in Niagara Region."

    # Save to file:
    python scripts/schema_gen.py ... --output schema.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA_TYPES = [
    "LocalBusiness", "ProfessionalService", "MedicalBusiness", "Restaurant",
    "LegalService", "HomeAndConstructionBusiness", "HealthAndBeautyBusiness",
    "AutomotiveBusiness", "FinancialService", "RealEstateAgent", "Store",
    "FoodEstablishment", "TouristAttraction",
]


def parse_address(address: str) -> dict:
    """
    Parse address string into PostalAddress components.
    Handles formats like:
      "123 Main St, Toronto, ON M1A 1A1"
      "123 Main St, Toronto, Ontario, Canada"
    """
    parts = [p.strip() for p in address.split(",")]

    schema_address = {"@type": "PostalAddress"}

    if len(parts) >= 1:
        schema_address["streetAddress"] = parts[0]

    if len(parts) >= 2:
        schema_address["addressLocality"] = parts[1]

    # Remaining parts: could be Province, PostalCode, Country in various combos
    remaining = [p.strip() for p in parts[2:]]
    COUNTRY_MAP = {"canada": "CA", "united states": "US", "usa": "US", "us": "US", "ca": "CA"}
    POSTAL_RE = re.compile(r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$|^\d{5}(-\d{4})?$")  # Canadian or US postal

    for part in remaining:
        part_lower = part.lower()
        if part_lower in COUNTRY_MAP:
            schema_address["addressCountry"] = COUNTRY_MAP[part_lower]
        elif POSTAL_RE.match(part.upper()):
            schema_address["postalCode"] = part.upper()
        elif "addressRegion" not in schema_address:
            # Strip postal code from end if combined (e.g. "ON M8Y2C8")
            m = re.match(r"^([A-Za-z]{2,})\s+([A-Z]\d[A-Z]\s?\d[A-Z]\d|\d{5})$", part)
            if m:
                schema_address["addressRegion"] = m.group(1)
                schema_address["postalCode"] = m.group(2).replace(" ", "")
            else:
                schema_address["addressRegion"] = part

    if "addressCountry" not in schema_address:
        schema_address["addressCountry"] = "CA"

    return schema_address


def parse_hours(hours_str: str) -> list[str]:
    """
    Convert human-readable hours to schema.org openingHours format.
    Input:  "Mon-Fri 09:00-17:00" or "Mon-Sat 10:00-18:00, Sun 12:00-16:00"
    Output: ["Mo-Fr 09:00-17:00", "Mo-Sa 10:00-18:00", "Su 12:00-16:00"]
    """
    day_map = {
        "mon": "Mo", "monday": "Mo",
        "tue": "Tu", "tuesday": "Tu",
        "wed": "We", "wednesday": "We",
        "thu": "Th", "thursday": "Th",
        "fri": "Fr", "friday": "Fr",
        "sat": "Sa", "saturday": "Sa",
        "sun": "Su", "sunday": "Su",
    }

    result = []
    segments = [s.strip() for s in hours_str.split(",")]

    for seg in segments:
        # Match "DayRange HH:MM-HH:MM" or "Day HH:MM-HH:MM"
        m = re.match(
            r"^([A-Za-z]+)(?:-([A-Za-z]+))?\s+(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$",
            seg.strip()
        )
        if m:
            start_day = day_map.get(m.group(1).lower(), m.group(1)[:2])
            end_day = day_map.get(m.group(2).lower(), m.group(2)[:2]) if m.group(2) else None
            time_range = f"{m.group(3)}-{m.group(4)}"
            if end_day:
                result.append(f"{start_day}-{end_day} {time_range}")
            else:
                result.append(f"{start_day} {time_range}")
        else:
            result.append(seg)  # Pass through unparseable segments

    return result


def generate_schema(
    name: str,
    address: str,
    phone: str,
    website: str,
    business_type: str = "LocalBusiness",
    hours: str | None = None,
    description: str | None = None,
) -> dict:
    schema = {
        "@context": "https://schema.org",
        "@type": business_type,
        "name": name,
        "address": parse_address(address),
        "telephone": phone,
        "url": website,
    }

    if hours:
        schema["openingHours"] = parse_hours(hours)

    if description:
        schema["description"] = description

    return schema


def main():
    parser = argparse.ArgumentParser(description="Generate LocalBusiness JSON-LD schema")
    parser.add_argument("--name", required=True, help="Business name")
    parser.add_argument("--address", required=True, help="Full address (e.g. '123 Main St, Toronto, ON M1A 1A1')")
    parser.add_argument("--phone", required=True, help="Phone number")
    parser.add_argument("--website", required=True, help="Website URL")
    parser.add_argument("--type", dest="business_type", default="LocalBusiness",
                        help=f"Schema type. Options: {', '.join(SCHEMA_TYPES)}")
    parser.add_argument("--hours", help="Opening hours (e.g. 'Mon-Fri 09:00-17:00')")
    parser.add_argument("--description", help="Business description")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()

    schema = generate_schema(
        name=args.name,
        address=args.address,
        phone=args.phone,
        website=args.website,
        business_type=args.business_type,
        hours=args.hours,
        description=args.description,
    )

    schema_json = json.dumps(schema, indent=2)
    script_tag = f'<script type="application/ld+json">\n{schema_json}\n</script>'

    if args.output:
        Path(args.output).write_text(script_tag)
        print(f"✅ Schema saved to {args.output}")
    else:
        print("✅ Schema ready — paste this into your site's <head>:\n")
        print(script_tag)


if __name__ == "__main__":
    main()
