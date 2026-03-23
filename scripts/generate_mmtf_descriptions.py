#!/usr/bin/env python3
"""
generate_mmtf_descriptions.py
==============================
Meridant Matrix — Generate capability_description for all MMTF capabilities.

Calls Claude once per capability to produce a 2-3 sentence plain-English
description of what the capability covers, grounded in the capability name,
domain, subdomain, and L1-L5 maturity descriptors already in the DB.

Checkpointed — safe to interrupt and resume. Progress is saved to:
    /tmp/mmtf_desc_progress.json

Run from project root inside Docker:
    docker compose exec app python scripts/generate_mmtf_descriptions.py

Options:
    --dry-run       Print prompts without making API calls or DB writes
    --limit N       Only process the first N capabilities (for testing)
    --overwrite     Regenerate descriptions for capabilities that already have one
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FRAMEWORKS_DB    = os.getenv("MERIDANT_FRAMEWORKS_DB_PATH", "/app/data/meridant_frameworks.db")
CHECKPOINT_FILE  = "/tmp/mmtf_desc_progress.json"
ANTHROPIC_MODEL  = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
FRAMEWORK_ID     = 1   # MMTF
MAX_RETRIES      = 5
RETRY_BASE_DELAY = 2.0


# ---------------------------------------------------------------------------
# Anthropic helpers
# ---------------------------------------------------------------------------

def _get_client():
    from anthropic import Anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")
    return Anthropic(api_key=api_key)


def _call_with_retry(client, prompt: str) -> str:
    from anthropic import APIStatusError
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except APIStatusError as e:
            if e.status_code == 529 and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"    [overloaded] retry {attempt}/{MAX_RETRIES} in {delay:.1f}s...")
                time.sleep(delay)
            else:
                raise


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint() -> set:
    """Return set of capability_ids already completed."""
    p = Path(CHECKPOINT_FILE)
    if p.exists():
        try:
            return set(json.loads(p.read_text()).get("done", []))
        except Exception:
            pass
    return set()


def _save_checkpoint(done: set) -> None:
    Path(CHECKPOINT_FILE).write_text(json.dumps({"done": sorted(done)}))


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(cap: dict, domain_name: str, subdomain_name: str, levels: list[dict]) -> str:
    level_block = ""
    for lv in levels:
        state = (lv.get("capability_state") or "").strip()
        if state:
            level_block += f"  L{lv['level']} ({lv.get('level_name','')}) — {state}\n"

    return f"""You are a technology transformation consultant writing concise capability descriptions for an IT maturity assessment framework called MMTF (Meridant Matrix Transformation Framework).

Write a 2-3 sentence plain-English description of the following capability. The description should explain:
1. What this capability covers and why it matters
2. The typical activities or outcomes it encompasses

Do NOT reference maturity levels, scores, or assessment. Do NOT use bullet points. Return only the description paragraph — no preamble, no heading, no quotes.

Capability: {cap['capability_name']}
Domain: {domain_name}
Subdomain: {subdomain_name}

Maturity level context (for grounding only):
{level_block or '  (no level data available)'}
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate MMTF capability descriptions via Claude.")
    parser.add_argument("--dry-run",   action="store_true", help="Print prompts, no API calls or DB writes")
    parser.add_argument("--limit",     type=int, default=0, help="Only process first N capabilities")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing descriptions")
    args = parser.parse_args()

    if not Path(FRAMEWORKS_DB).exists():
        sys.exit(f"ERROR: DB not found at {FRAMEWORKS_DB}")

    conn = sqlite3.connect(FRAMEWORKS_DB)
    conn.row_factory = sqlite3.Row

    # Load capabilities
    caps = conn.execute(
        """
        SELECT c.id, c.capability_name, c.capability_description,
               d.domain_name, sd.subdomain_name
        FROM Next_Capability c
        JOIN Next_Domain    d  ON d.id  = c.domain_id
        JOIN Next_SubDomain sd ON sd.id = c.subdomain_id
        WHERE c.framework_id = ?
        ORDER BY c.domain_id, c.subdomain_id, c.id
        """,
        (FRAMEWORK_ID,),
    ).fetchall()

    # Load level descriptors
    levels_raw = conn.execute(
        """
        SELECT capability_id, level, level_name, capability_state
        FROM Next_CapabilityLevel
        WHERE framework_id = ? AND level_name IS NOT NULL
        ORDER BY capability_id, level
        """,
        (FRAMEWORK_ID,),
    ).fetchall()
    level_map: dict[int, list] = {}
    for lv in levels_raw:
        level_map.setdefault(lv["capability_id"], []).append(dict(lv))

    # Filter
    todo = [
        c for c in caps
        if args.overwrite or not c["capability_description"]
    ]
    if args.limit:
        todo = todo[:args.limit]

    done = _load_checkpoint()
    remaining = [c for c in todo if c["id"] not in done]

    total     = len(todo)
    already   = len(todo) - len(remaining)
    print(f"MMTF capabilities: {len(caps)} total, {total} to process, {already} already done.")
    if not remaining:
        print("Nothing to do.")
        conn.close()
        return

    if args.dry_run:
        print("\n[dry-run] Sample prompt for first capability:\n")
        c = remaining[0]
        print(_build_prompt(dict(c), c["domain_name"], c["subdomain_name"], level_map.get(c["id"], [])))
        conn.close()
        return

    client = _get_client()

    for i, cap in enumerate(remaining, 1):
        cap_dict = dict(cap)
        prompt   = _build_prompt(cap_dict, cap["domain_name"], cap["subdomain_name"], level_map.get(cap["id"], []))

        print(f"[{i}/{len(remaining)}] {cap['capability_name']} ({cap['domain_name']})...", end=" ", flush=True)
        try:
            description = _call_with_retry(client, prompt)
            conn.execute(
                "UPDATE Next_Capability SET capability_description = ? WHERE id = ?",
                (description, cap["id"]),
            )
            conn.commit()
            done.add(cap["id"])
            _save_checkpoint(done)
            print("✓")
        except Exception as e:
            print(f"✗ ERROR: {e}")
            # Continue with next capability — don't abort the run

    conn.close()
    print(f"\nDone. {len(done)} descriptions written.")
    if Path(CHECKPOINT_FILE).exists():
        Path(CHECKPOINT_FILE).unlink()
        print("Checkpoint file removed.")


if __name__ == "__main__":
    main()
