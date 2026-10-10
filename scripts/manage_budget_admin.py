"""Explicitly grant or revoke a doctor's budget capability on an existing DB."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from martin.auth.capabilities import set_budget_admin
from martin.db.app_db import get_app_db_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor-id", required=True)
    parser.add_argument("--operator-label", required=True)
    parser.add_argument("--db", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--grant", action="store_true")
    action.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    path = args.db or get_app_db_path()
    if not path.is_file():
        parser.error("An existing initialized business database is required")
    try:
        result = set_budget_admin(
            args.doctor_id, args.grant, operator_label=args.operator_label, db_path=path
        )
    except Exception as exc:
        print("Capability change failed: " + type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
