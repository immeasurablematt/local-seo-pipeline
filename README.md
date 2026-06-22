# Local SEO Automation Pipeline

Reusable Local SEO pipeline triggered from Discord. Drop a domain + business info, get a full audit, Google Sheets tracker populated, schema markup generated, competitor review analysis, and AI-generated copy ready to paste into a landing page.

## What It Does

| Script | What it does | Output |
|--------|-------------|--------|
| `hot_lead_eval.py` | Score a GBP listing as a prospect | HOT / WARM / COLD with breakdown |
| `audit.py` | DataForSEO Local Pack competitors + on-page checks | Populates Sheets Tabs 1 + 3, saves `.competitors.json` |
| `market_intel.py` | Pull competitor reviews → Claude sorts into 10 insight buckets | `.market_intel.json` |
| `copy_gen.py` | Interactive strength quiz → Claude builds copy skeleton | `.copy_skeleton.md` |
| `schema_gen.py` | Generate LocalBusiness JSON-LD | Paste-ready schema for `<head>` |
| `citations_check.py` | NAP check across 20 directories | Populates Sheets Tab 4 |
| `setup_sheets.py` | Create the 5-tab Google Sheets template | Run once per client |
| `discord_trigger.py` | Parse Discord commands and run the pipeline | Discord reply |

---

## Full Pipeline (in order)

```
1. hot_lead_eval.py   →  Is this worth pursuing?
2. audit.py           →  Audit the domain, map the competitive landscape
3. market_intel.py    →  What do customers love/hate in this market?
4. copy_gen.py        →  What can WE own? → generates copy skeleton
5. /landing-page      →  Build the site from the copy skeleton
6. schema_gen.py      →  Generate LocalBusiness JSON-LD for <head>
7. citations_check.py →  Fix NAP consistency across directories
```

---

## Setup

```bash
pip install -r requirements.txt
```

DataForSEO creds come from the macOS Keychain under `service=openclaw`:
```bash
export DATAFORSEO_LOGIN="$(security find-generic-password -s openclaw -a dataforseo-login -w)"
export DATAFORSEO_PASSWORD="$(security find-generic-password -s openclaw -a dataforseo-password -w)"
```

Claude API key (needed for `market_intel.py` and `copy_gen.py`):
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or use the credential loader:
```bash
bash /Users/bob/.openclaw/workspace/load-all-credentials.sh python scripts/audit.py ...
```

---

## Step 0: Create the Google Sheets Template

```bash
python scripts/setup_sheets.py
# Creates a 5-tab tracker and saves the ID to .sheets_id

# Custom title:
python scripts/setup_sheets.py --title "Joe's Plumbing SEO Tracker"
```

---

## Script Reference

### 1. hot_lead_eval.py

Score a prospect from their Google Maps listing before committing to a full audit.

```bash
python scripts/hot_lead_eval.py \
  --name "Joe's Plumbing" \
  --city "Toronto" \
  --rating 3.8 \
  --reviews 12 \
  --website "https://joesplumbing.com" \
  --keyword "plumber toronto"

# No website on the GBP listing:
python scripts/hot_lead_eval.py \
  --name "Joe's Plumbing" --city "Toronto" \
  --rating 3.8 --reviews 12

# Mock mode (skip live website fetch):
python scripts/hot_lead_eval.py --name "Test Biz" --city "Toronto" \
  --rating 4.1 --reviews 30 --website "https://example.com" --mock
```

**Scoring breakdown:**

| Signal | Max pts |
|--------|---------|
| Review count (≤ 10) | 35 |
| Rating (< 3.5★) | 20 |
| No website on GBP | 20 |
| No LocalBusiness schema | 10 |
| Keyword missing from `<title>` | 6 |
| Phone not on homepage | 5 |
| Keyword missing from `<h1>` | 4 |
| No viewport meta | 3 |

- **60+** → HOT — pitch the package
- **35–59** → WARM — worth a call
- **< 35** → COLD — move on

Discord shortcut: `!hot-lead name='Business' city='Toronto' rating=3.8 reviews=12`

---

### 2. audit.py

Full audit of a client domain. Fetches top-5 Local Pack competitors via DataForSEO and runs on-page checks.

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

**What it writes:**
- Sheets Tab 1 (Sites Dashboard) — one row per audit
- Sheets Tab 3 (Competitor Audit) — one row per competitor
- `.competitors.json` — competitor list consumed by `market_intel.py`

---

### 3. market_intel.py

Fetch Google reviews for each competitor and use Claude to sort them into 10 customer-value buckets. This answers: *"What does this market reward and punish?"*

**Runs automatically from `.competitors.json` written by audit.py.**

```bash
# After running audit.py (reads .competitors.json automatically):
python scripts/market_intel.py --keyword "plumber toronto"

# Specify competitors manually (skip audit.py):
python scripts/market_intel.py \
  --keyword "plumber toronto" \
  --competitor "Acme Plumbing" \
  --competitor "Fast Flow Plumbing" \
  --competitor "Toronto Plumbing Pro"

# Control how many reviews to pull per competitor (default: 50):
python scripts/market_intel.py --keyword "plumber toronto" --reviews-per-biz 100

# Mock mode:
python scripts/market_intel.py --keyword "plumber toronto" --mock
```

**The 10 buckets:**

| Bucket | What it captures |
|--------|-----------------|
| Reliability | Shows up on time, follows through on promises |
| Communication | Responsive, keeps clients informed at every stage |
| Price Transparency | Clear quotes, no surprise charges |
| Quality of Work | Craftsmanship, attention to detail, professional results |
| Speed | Fast turnaround, completes on schedule |
| Facility / Space | Clean work area, tidy, professional environment |
| Staff Attitude | Friendly, polite, professional, puts clients at ease |
| Process / Ease | Easy to book, smooth workflow, no friction |
| Results / Outcome | Problem actually solved, measurable improvement |
| Value for Money | Clients feel they got more than they paid for |

**Output:** `.market_intel.json` — bucket-level analysis with frequency, sentiment, top praise, top complaints, and market gap for each bucket.

---

### 4. copy_gen.py

Interactive: walks you through each bucket and asks if it's a genuine strength of the client. Claude then writes the full copy skeleton based on what competitors are failing at vs. what the client can credibly own.

```bash
python scripts/copy_gen.py \
  --keyword "plumber toronto" \
  --name "Joe's Plumbing" \
  --city "Toronto" \
  --phone "416-555-1234" \
  --website "https://joesplumbing.com"

# Mock mode (skips interactive prompts, uses pre-set answers):
python scripts/copy_gen.py --keyword "plumber toronto" --mock
```

**Interactive flow:**

For each of the 10 buckets, the script shows:
- What the market gap is (what competitors are failing at)
- What customers praise / complain about

Then asks:
```
Is this a strength for your business? (yes/no/skip) [no]:
What's your proof point or unique claim?
```

**Copy skeleton output (`.copy_skeleton.md`) includes:**

| Section | What you get |
|---------|-------------|
| Homepage Headline | 3 variations (strongest marked ⭐) |
| Subheadline | 1-2 sentences with keyword |
| Feature Bullets | 3-5 scannable bullets tied to owned strengths |
| Social Proof Prompt | What testimonial to collect and what it should say |
| Google Ads Hook | 2 variations (headline + description) |
| Email Subject Lines | 3 variations for cold outreach |
| FAQ | 4 questions customers actually ask |
| CTA Copy | Primary + secondary button text |

---

### 5. /landing-page (Claude Code skill)

Once you have `.copy_skeleton.md`, use the `/landing-page` skill to build the full HTML page.

In Claude Code, type:
```
/landing-page
```

Then provide:
- Business name + value proposition from the copy skeleton
- CTA from the copy skeleton
- Brand colours (if known)
- Phone / email

The skill generates a single `index.html` with Tailwind CSS, dark mode, mobile-first design, and LocalBusiness JSON-LD schema built in.

---

### 6. schema_gen.py

Generate LocalBusiness JSON-LD for the `<head>` of any page.

```bash
python scripts/schema_gen.py \
  --name "Joe's Plumbing" \
  --address "123 Main St, Toronto, ON M1A 1A1" \
  --phone "416-555-1234" \
  --website "https://joesplumbing.com" \
  --type "Plumber" \
  --hours "Mon-Fri 08:00-18:00, Sat 09:00-14:00" \
  --description "Licensed plumber serving Toronto and the GTA."

# Save to file:
python scripts/schema_gen.py ... --output schema.json
```

---

### 7. citations_check.py

Check NAP (Name, Address, Phone) consistency across 20 local directories.

```bash
python scripts/citations_check.py \
  --name "Joe's Plumbing" \
  --address "123 Main St, Toronto, ON" \
  --phone "416-555-1234"

# Mock mode:
python scripts/citations_check.py --name "Test Biz" --address "1 Test St" --phone "555-0000" --mock
```

---

## Discord Commands

Drop these in `#code` or `#localseo`. Hackerman picks them up and posts results back.

### !seo-audit
Full domain audit + competitor map:
```
!seo-audit domain=example.com name='Business Name' address='123 Main St, Toronto, ON' phone='416-555-1234' keyword='plumber toronto'
```

### !hot-lead
Score a GBP listing as a prospect:
```
!hot-lead name='Joe Plumbing' city='Toronto' rating=3.8 reviews=12
!hot-lead name='Joe Plumbing' city='Toronto' rating=3.8 reviews=12 website='https://example.com' keyword='plumber toronto'
```

### !market-intel
Pull competitor reviews + Claude bucket analysis:
```
!market-intel keyword='plumber toronto' city='Toronto'
```

All commands accept `--mock` to skip live API calls during testing.

---

## Google Sheets Tabs

| Tab | Purpose |
|-----|---------|
| Sites Dashboard | One row per client domain |
| SEO Checklist | 52-point task list per site |
| Competitor Audit | Top-5 Local Pack competitors |
| Citations Tracker | 20-directory NAP check |
| Monthly Reports | Rank tracking over time |

---

## Location Default

Canada (`location_code: 2124`). For US, pass `location_code=2840` to DataForSEO.

---

## ⚠️ Important

**DO NOT run on any real site until Matthew approves.**
First test site: Jetta Grove Consulting — but test on a dummy domain first.
Frank Baggetta (frankbaggetta.ca) — schema already generated in `docs/frankbaggetta-schema.json`.

---

## Full Example Run (end to end)

```bash
# Load creds
export DATAFORSEO_LOGIN="$(security find-generic-password -s openclaw -a dataforseo-login -w)"
export DATAFORSEO_PASSWORD="$(security find-generic-password -s openclaw -a dataforseo-password -w)"
export ANTHROPIC_API_KEY="sk-ant-..."

# 1. Is this worth pursuing?
python scripts/hot_lead_eval.py \
  --name "Joe's Plumbing" --city "Toronto" \
  --rating 3.8 --reviews 12 --website "https://joesplumbing.com" \
  --keyword "plumber toronto"
# → HOT LEAD — score 71/100

# 2. Audit the domain, map competitors
python scripts/audit.py \
  --domain joesplumbing.com --name "Joe's Plumbing" \
  --address "123 Main St, Toronto, ON M1A 1A1" --phone "416-555-1234" \
  --keyword "plumber toronto" --city "Toronto"
# → .competitors.json written with top 5 Local Pack rivals

# 3. What does this market punish and reward?
python scripts/market_intel.py --keyword "plumber toronto"
# → .market_intel.json written with 10-bucket analysis

# 4. What can we own? (interactive)
python scripts/copy_gen.py \
  --keyword "plumber toronto" --name "Joe's Plumbing" \
  --city "Toronto" --phone "416-555-1234"
# → .copy_skeleton.md written with headlines, ads, FAQ, CTAs

# 5. Build the landing page
# In Claude Code:  /landing-page
# Paste key sections from .copy_skeleton.md when prompted

# 6. Add schema to the page
python scripts/schema_gen.py \
  --name "Joe's Plumbing" \
  --address "123 Main St, Toronto, ON M1A 1A1" \
  --phone "416-555-1234" \
  --website "https://joesplumbing.com" \
  --type "Plumber" \
  --hours "Mon-Fri 08:00-18:00" \
  --description "Licensed plumber serving Toronto and the GTA." \
  --output schema.json
```
