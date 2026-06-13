#!/usr/bin/env python3
"""
discord_trigger.py — Handler for Discord SEO commands.

OpenClaw calls this script when it detects a command in #code or #localseo.

Commands:
    !seo-audit   — full audit of a domain
    !hot-lead    — score a GBP listing as a potential client (Hot/Warm/Cold)

!seo-audit format:
    !seo-audit domain=example.com name='Business Name' address='123 Main St, Toronto, ON' phone='416-555-1234' keyword='plumber toronto'

!hot-lead format:
    !hot-lead name='Joe Plumbing' city='Toronto' rating=3.8 reviews=12 website='https://example.com' keyword='plumber toronto'
    !hot-lead name='Joe Plumbing' city='Toronto' rating=3.8 reviews=12   (no website listed)

Direct usage:
    python discord_trigger.py "!seo-audit ..."
    python discord_trigger.py "!hot-lead name='Joe Plumbing' city='Toronto' rating=3.8 reviews=12"
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit.py"
HOT_LEAD_SCRIPT = REPO_ROOT / "scripts" / "hot_lead_eval.py"

# Load DataForSEO creds from keychain at runtime
CREDENTIAL_LOADER = Path("/Users/bob/.openclaw/workspace/load-all-credentials.sh")

REQUIRED_PARAMS = ["domain", "name", "address", "phone", "keyword"]


def parse_command(command_str: str) -> dict | None:
    """
    Parse !seo-audit key=value pairs from a command string.
    Supports both quoted ('value') and unquoted values.
    Also detects --mock flag.
    """
    # Strip the command prefix
    cmd = re.sub(r"^!seo-audit\s*", "", command_str.strip())

    params: dict = {}

    # Extract quoted values first: key='value' or key="value"
    for match in re.finditer(r'(\w+)=["\']([^"\']*)["\']', cmd):
        params[match.group(1)] = match.group(2)
        cmd = cmd.replace(match.group(0), "")

    # Extract unquoted values: key=value (no spaces)
    for match in re.finditer(r'(\w+)=(\S+)', cmd):
        if match.group(1) not in params:
            params[match.group(1)] = match.group(2)

    # Detect --mock flag
    params["mock"] = "--mock" in command_str

    return params


def validate_params(params: dict) -> list[str]:
    """Return list of missing required parameters."""
    return [p for p in REQUIRED_PARAMS if not params.get(p)]


def run_audit(params: dict) -> tuple[str, str | None]:
    """
    Run audit.py with parsed params.
    Returns (stdout_output, error_message_or_None).
    """
    cmd = [
        sys.executable, str(AUDIT_SCRIPT),
        "--domain", params["domain"],
        "--name", params["name"],
        "--address", params["address"],
        "--phone", params["phone"],
        "--keyword", params["keyword"],
        "--city", params.get("city", params["keyword"].split()[-1] if params.get("keyword") else ""),
    ]

    if params.get("mock"):
        cmd.append("--mock")

    if params.get("sheets_id"):
        cmd.extend(["--sheets-id", params["sheets_id"]])

    # Export DataForSEO creds from keychain before running
    env_setup = (
        'export DATAFORSEO_LOGIN="$(security find-generic-password -s openclaw -a dataforseo-login -w 2>/dev/null)"; '
        'export DATAFORSEO_PASSWORD="$(security find-generic-password -s openclaw -a dataforseo-password -w 2>/dev/null)"; '
    )

    try:
        result = subprocess.run(
            f"{env_setup} {' '.join(repr(c) for c in cmd)}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout, None
        else:
            return result.stdout, result.stderr or "Audit script returned non-zero exit code."
    except subprocess.TimeoutExpired:
        return "", "Audit timed out after 120 seconds."
    except Exception as e:
        return "", str(e)


def format_discord_response(params: dict, audit_output: str, error: str | None) -> str:
    """Format output for Discord (max 1900 chars)."""
    domain = params.get("domain", "unknown")

    if error:
        return f"❌ `!seo-audit` failed for `{domain}`:\n```\n{error[:500]}\n```"

    # Extract key lines from audit output
    lines = audit_output.strip().splitlines()
    summary_lines = []
    sheets_url = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("✅") or stripped.startswith("❌") or stripped.startswith("⚠️"):
            summary_lines.append(stripped)
        if "docs.google.com/spreadsheets" in stripped:
            sheets_url = stripped.replace("✅ Sheets updated: ", "").strip()

    # Build response
    response = f"**Local SEO Audit — `{domain}`**\n"

    if summary_lines:
        # Group on-page checks
        onpage = [l for l in summary_lines if any(
            kw in l for kw in ["Title", "H1", "schema", "Phone", "Address", "Mobile", "viewport"]
        )]
        competitors = [l for l in summary_lines if "competitor" in l.lower() or "Local Pack" in l]
        other = [l for l in summary_lines if l not in onpage and l not in competitors]

        if onpage:
            response += "\n**On-Page:**\n" + "\n".join(onpage[:8])
        if competitors:
            response += "\n\n**Competitors:**\n" + "\n".join(competitors[:5])
        if other:
            response += "\n\n" + "\n".join(other[:5])
    else:
        # Fallback: first 1400 chars of output
        response += f"\n```\n{audit_output[:1400]}\n```"

    if sheets_url:
        response += f"\n\n📊 **Sheets:** {sheets_url}"

    # Trim to Discord limit
    if len(response) > 1900:
        response = response[:1897] + "..."

    return response


def run_hot_lead(params: dict) -> tuple[str, str | None]:
    """Run hot_lead_eval.py with parsed params."""
    cmd = [
        sys.executable, str(HOT_LEAD_SCRIPT),
        "--name", params["name"],
        "--city", params.get("city", ""),
    ]
    if params.get("rating"):
        cmd.extend(["--rating", str(params["rating"])])
    if params.get("reviews"):
        cmd.extend(["--reviews", str(params["reviews"])])
    if params.get("website"):
        cmd.extend(["--website", params["website"]])
    if params.get("keyword"):
        cmd.extend(["--keyword", params["keyword"]])
    if params.get("mock"):
        cmd.append("--mock")
    if params.get("sheets_id"):
        cmd.extend(["--sheets-id", params["sheets_id"]])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return result.stdout, None
        return result.stdout, result.stderr or "hot_lead_eval returned non-zero."
    except subprocess.TimeoutExpired:
        return "", "hot_lead_eval timed out."
    except Exception as e:
        return "", str(e)


def format_hot_lead_response(params: dict, output: str, error: str | None) -> str:
    """Format !hot-lead output for Discord."""
    name = params.get("name", "unknown")
    if error:
        return f"❌ `!hot-lead` failed for `{name}`:\n```\n{error[:500]}\n```"

    lines = output.strip().splitlines()
    verdict_line = next((l for l in lines if any(v in l for v in ("HOT LEAD", "WARM LEAD", "COLD LEAD"))), "")
    score_line = next((l for l in lines if "score" in l.lower()), "")

    block = "\n".join(l for l in lines if l.strip())
    response = f"**Lead Eval — {name}**\n```\n{block[:1500]}\n```"
    if len(response) > 1900:
        response = response[:1897] + "..."
    return response


def print_usage():
    print("""Usage:
  python discord_trigger.py "!seo-audit domain=example.com name='Business Name' address='123 Main St, Toronto, ON' phone='416-555-1234' keyword='plumber toronto'"
  python discord_trigger.py "!hot-lead name='Joe Plumbing' city='Toronto' rating=3.8 reviews=12 website='https://example.com' keyword='plumber toronto'"

Optional for both:
  --mock        Skip live requests (for testing)
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command_str = " ".join(sys.argv[1:])

    if "!hot-lead" in command_str:
        cmd = re.sub(r"^!hot-lead\s*", "", command_str.strip())
        params = parse_command("!seo-audit " + cmd)  # reuse parser
        params["mock"] = "--mock" in command_str

        if not params.get("name") or not params.get("city"):
            print("❌ !hot-lead requires at least name= and city=")
            print_usage()
            sys.exit(1)

        output, error = run_hot_lead(params)
        print(format_hot_lead_response(params, output, error))
        return

    if "!seo-audit" not in command_str:
        command_str = "!seo-audit " + command_str

    params = parse_command(command_str)

    missing = validate_params(params)
    if missing:
        print(f"❌ Missing required parameters: {', '.join(missing)}")
        print_usage()
        sys.exit(1)

    print(f"🚀 Running audit for {params['domain']}...")

    output, error = run_audit(params)
    response = format_discord_response(params, output, error)
    print(response)


if __name__ == "__main__":
    main()
