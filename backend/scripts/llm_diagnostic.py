"""
llm_diagnostic.py — Comprehensive Diagnostic Tool for EduSense Multi-Provider, Multi-Key LLM Layer.

Usage:
    python backend/scripts/llm_diagnostic.py              # Show status, keys (masked), and routing chains
    python backend/scripts/llm_diagnostic.py --test-all   # Run live probe on every key & test connectivity
    python backend/scripts/llm_diagnostic.py --json       # Output JSON format
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.services import llm


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    """Render a clean text table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    hdr = "| " + " | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)) + " |"
    body_lines = []
    for row in rows:
        line = "| " + " | ".join(f"{str(v):<{widths[i]}}" for i, v in enumerate(row)) + " |"
        body_lines.append(line)

    return "\n".join([sep, hdr, sep] + body_lines + [sep])


def run_diagnostic(test_all: bool = False, json_output: bool = False):
    print("=" * 80)
    print(" EduSense LLM Layer — Diagnostic & Key Validation Tool")
    print("=" * 80)

    if test_all:
        print("[*] Probing every configured key across all providers (live test)...")
        results = llm.router.validate_all_keys(probe=True)
    else:
        results = llm.router.validate_all_keys(probe=False)

    status_data = llm.router.status()

    if json_output:
        print(json.dumps({
            "keys": results,
            "providers": status_data["providers"],
            "chains": status_data["chains"],
            "usage_today": status_data.get("usage_today", {}),
        }, indent=2))
        return

    # 1. Key Registry Table
    print("\n--- Key Registry (All Keys Masked to Last 4 Chars) ---")
    headers = ["PROVIDER", "LABEL", "KEY (MASKED)", "QUOTA GROUP", "DEDICATED FEATURES", "STATUS", "REQ/DAY", "FAILURES"]
    rows = []
    for k in results:
        status_str = k["status"].upper()
        if k["disabled"]:
            status_str += " [DISABLED]"
        feats = ", ".join(k["dedicated_features"]) if k["dedicated_features"] else "(general pool)"
        rows.append([
            k["provider"],
            k["label"],
            k["key_masked_last4"],
            k["quota_group"],
            feats,
            status_str,
            str(k.get("requests_today", 0)),
            k.get("last_error", "")[:35] or "None"
        ])

    if rows:
        print(format_table(rows, headers))
    else:
        print("  No keys configured. Set keys in backend/.env using <PROVIDER>_API_KEYS or <PROVIDER>_KEY_<LABEL>.")

    # 2. Redundancy & Quota Sharing Analysis
    print("\n--- Quota Group & Redundancy Analysis ---")
    groups_by_provider: dict[str, dict[str, list[str]]] = {}
    for k in results:
        p = k["provider"]
        g = k["quota_group"]
        groups_by_provider.setdefault(p, {}).setdefault(g, []).append(k["key_masked_last4"])

    for p, gmap in groups_by_provider.items():
        print(f"Provider: {p.upper()}")
        for grp, key_list in gmap.items():
            if len(key_list) > 1:
                print(f"  [!] Quota Group '{grp}' shares quota across {len(key_list)} keys: {', '.join(key_list)}")
                print(f"      NOTE: These keys share rate limits and will cool down together on 429/quota.")
            else:
                print(f"  [OK] Quota Group '{grp}': 1 independent key ({key_list[0]})")

    # 3. Model Pair Availability Matrix
    print("\n--- Provider & Model Availability Summary ---")
    p_headers = ["PROVIDER", "HEALTHY KEYS", "MODELS COUNT", "READY / ACTIVE", "COOLING DOWN"]
    p_rows = []
    for p in status_data["providers"]:
        models = p.get("models", [])
        total_pairs = len(models)
        cooling = sum(1 for m in models if m.get("cooling_down"))
        ready = sum(1 for m in models if not m.get("disabled") and not m.get("cooling_down"))
        p_rows.append([
            p["provider"],
            f"{p['keys_healthy']} / {p['keys_total']}",
            str(len(set(m['model'] for m in models))),
            str(ready),
            str(cooling),
        ])
    print(format_table(p_rows, p_headers))

    # 4. Computed Feature Best-Fit Routing Chains
    print("\n--- Feature Best-Fit Candidate Routing Chains ---")
    for feat, chain in status_data["chains"].items():
        chain_display = " -> ".join(chain[:5]) + (f" (+{len(chain)-5} more)" if len(chain) > 5 else "")
        print(f"  * {feat:<20} : {chain_display or '(no healthy providers)'}")

    # 5. Usage Today
    usage = status_data.get("usage_today", {})
    if usage.get("providers"):
        print("\n--- Daily Usage & Quota Consumption ---")
        for p, stat in usage["providers"].items():
            print(f"  {p:<12}: {stat.get('requests', 0)} requests, ~{stat.get('tokens', 0)} tokens")

    print("\n" + "=" * 80)
    print(" Diagnostic Complete.")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="EduSense Multi-Provider LLM Diagnostic Tool")
    parser.add_argument("--test-all", action="store_true", help="Probe all configured keys live")
    parser.add_argument("--probe", action="store_true", help="Alias for --test-all")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    run_diagnostic(test_all=args.test_all or args.probe, json_output=args.json)


if __name__ == "__main__":
    main()
