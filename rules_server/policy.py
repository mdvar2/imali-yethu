"""Spending policy held by the rules server, outside the agent's reach.

Changed only through PUT /policy with the CFO admin key. Every change is
appended to an audit log with the old and new values.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POLICY_PATH = DATA_DIR / "policy.json"
AUDIT_PATH = DATA_DIR / "policy_audit.jsonl"

DEFAULT_POLICY = {
    "max_payment_zar": "50000.00",
    "weekly_cap_zar": "200000.00",
    "approved_suppliers": ["SUP-001", "SUP-002"],
    "paused": False,
}


def load_policy() -> dict:
    """Current policy as JSON-ready strings. Falls back to the defaults."""
    try:
        stored = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_POLICY)
    return {**DEFAULT_POLICY, **stored}


def max_payment() -> Decimal:
    return Decimal(load_policy()["max_payment_zar"])


def weekly_cap() -> Decimal:
    return Decimal(load_policy()["weekly_cap_zar"])


def approved_suppliers() -> set[str]:
    return set(load_policy()["approved_suppliers"])


def save_policy(new_policy: dict, actor: str = "CFO dashboard") -> dict:
    old = load_policy()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Write atomically so a crash never leaves a half-written policy behind.
    fd, tmp = tempfile.mkstemp(dir=POLICY_PATH.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(new_policy, f, indent=2)
    os.replace(tmp, POLICY_PATH)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor,
        "old": old,
        "new": new_policy,
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return new_policy
