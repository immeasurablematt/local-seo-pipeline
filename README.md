# Local SEO Automation Pipeline

Reusable Local SEO pipeline triggered from Discord. Drop a domain + business info, get a full audit, Google Sheets tracker populated, and schema markup generated.

## What It Does

- **audit.py** — DataForSEO Local Pack competitors + on-page checks → populates Sheets Tab 1 + Tab 3
- **citations_check.py** — NAP check across 20 directories → populates Sheets Tab 4
- **schema_gen.py** — Generates LocalBusiness JSON-LD ready to paste into `<head>`
- **setup_sheets.py** — Creates the 5-tab Google Sheets template (run once)
- **discord_trigger.py** — Parses `!seo-audit` Discord commands and runs the pipeline

## Setup

```bash
pip install -r requirements.txt
```

DataForSEO creds are in the macOS Keychain under `service=openclaw`:
```bash
export DATAFORSEO_LOGIN="$(security find-generic-password -s openclaw -a dataforseo-login -w)"
export DATAFORSEO_PASSWORD="$(security find-generic-password -s openclaw -a dataforseo-password -w)"
```

Or use the credential loader:
```bash
bash /Users/bob/.openclaw/workspace/load-all-credentials.sh python scripts/audit.py ...
```

## Step 1: Create the Google Sheets Template

```bash
python scripts/setup_sheets.py
# Creates a 5-tab tracker and saves the ID to .sheets_id
```

Custom title:
```bash
python scripts/setup_sheets.py --title "Jetta Grove SEO Tracker"
```

## Script Reference

### audit.py

```bash
python scripts/audit.py \
  --domain example.com \
  --name "Business Name" \
  --address "123 Main St, Toronto, ON M1A 1A1" \
  --phone "416-555-1234" \
  --keyword "plumber toronto" \
  --city "Toronto"

# Test without API calls:
python scripts/audit.py --domain example.com --name "Test Biz" \
  --address "1 Test St, Toronto, ON" --phone "555-0000" \
  --keyword "plumber toronto" --city "Toronto" --mock
```

### citations_check.py

```bash
python scripts/citations_check.py \
  --name "Business Name" \
  --address "123 Main St, Toronto, ON" \
  --phone "416-555-1234"

# Mock mode:
python scripts/citations_check.py --name "Test Biz" --address "1 Test St" --phone "555-0000" --mock
```

### schema_gen.py

```bash
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
```

## Discord Trigger

Drop this in `#code` or `#localseo`:

```
!seo-audit domain=example.com name='Business Name' address='123 Main St, Toronto, ON' phone='416-555-1234' keyword='plumber toronto'
```

Hackerman picks it up, runs the audit, and posts results + Sheets link back.

## ⚠️ Important

**DO NOT run on any real site until Matthew approves.**
First test site: Jetta Grove Consulting — but test on a dummy domain first.

## Google Sheets Tabs

| Tab | Purpose |
|-----|---------|
| Sites Dashboard | One row per client domain |
| SEO Checklist | 52-point task list per site |
| Competitor Audit | Top-5 Local Pack competitors |
| Citations Tracker | 20-directory NAP check |
| Monthly Reports | Rank tracking over time |

## Location Default

Canada (`location_code: 2124`). For US, pass `location_code=2840` to DataForSEO.
