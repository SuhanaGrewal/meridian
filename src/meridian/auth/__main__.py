from __future__ import annotations

import argparse

from meridian.auth.credentials import get_credentials
from meridian.common.config import ensure_dirs, load_config
from meridian.common.logging import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authenticate Meridian with Google (Gmail/Calendar/Docs/Drive, readonly)."
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force a token refresh using the stored refresh token, instead of reusing a valid access token as-is.",
    )
    args = parser.parse_args()

    config = load_config()
    ensure_dirs(config)
    logger = get_logger("meridian.auth.cli", log_dir=config.log_dir)

    creds = get_credentials(config=config, force_refresh=args.force_refresh)

    logger.info(
        "cli authentication complete",
        extra={"operation": "auth.cli", "status": "success", "duration_ms": 0},
    )
    print(f"Authenticated. Token valid: {creds.valid}.")


if __name__ == "__main__":
    main()
