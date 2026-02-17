"""CLI for temporary media TTL cleanup."""

from __future__ import annotations

import argparse

from .media_retention import cleanup_temp_media, load_media_retention_config_from_env


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up temporary media files by TTL policy.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print config and current policy; do not delete files.",
    )
    args = parser.parse_args()

    config = load_media_retention_config_from_env()
    print(f"Media temp dir: {config.temp_dir}")
    print(f"TTL hours: {config.ttl_hours}")

    if args.dry_run:
        print("Dry-run mode: no files were deleted.")
        return

    report = cleanup_temp_media(config)
    print(
        "Cleanup report: "
        f"scanned={report.scanned_files}, "
        f"deleted={report.deleted_files}, "
        f"kept={report.kept_files}, "
        f"bytes_deleted={report.bytes_deleted}"
    )


if __name__ == "__main__":
    main()
