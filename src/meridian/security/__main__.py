from __future__ import annotations

import argparse

from meridian.common.config import load_config
from meridian.security.audit_log import verify_audit_log


def main() -> None:
    parser = argparse.ArgumentParser(description="Meridian security utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify-audit", help="Check logs/audit.log's hash chain for tampering.")
    args = parser.parse_args()

    config = load_config()

    if args.command == "verify-audit":
        path = config.log_dir / "audit.log"
        broken = verify_audit_log(path)
        if not path.exists():
            print(f"{path}: no audit log yet.")
        elif not broken:
            entry_count = sum(1 for _ in path.open())
            print(f"{path}: intact ({entry_count} entries).")
        else:
            print(f"{path}: {len(broken)} broken chain link(s) at line(s) {broken}.")


if __name__ == "__main__":
    main()
