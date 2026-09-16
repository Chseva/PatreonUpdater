"""Command-line entry point."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .mega import read_listing
from .app_paths import data_root
from .mappings import load_mappings
from .patreon import PatreonApiError, PatreonClient
from .report import build_report, render_markdown


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Audit MEGA folder links in published Patreon posts.")
    result.add_argument("--mega-listing", type=Path, required=True, help="Path to MEGA folder links.txt")
    result.add_argument("--campaign-id", help="Optional campaign ID override; discovered from your token by default")
    result.add_argument("--output", type=Path, default=Path("patreon_mega_report.md"), help="Markdown report destination")
    result.add_argument("--json-output", type=Path, help="Optional JSON report destination")
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.mega_listing.is_file():
        parser().error(f"MEGA listing does not exist: {args.mega_listing}")
    token = getpass.getpass("Patreon API token (input hidden): ").strip()
    if not token:
        parser().error("A Patreon API token is required.")
    local_folders = read_listing(args.mega_listing)
    try:
        # A null published_at indicates a draft/unpublished post. The audit scope is
        # intentionally limited to material patrons can currently see.
        client = PatreonClient(token)
        campaign_id = args.campaign_id or client.discover_campaign_id()
        posts = [post for post in client.iter_campaign_posts(campaign_id) if post.published_at]
    except PatreonApiError as error:
        print(f"Audit failed: {error}")
        return 2
    report = build_report(posts, local_folders, load_mappings(data_root() / "manual_mappings.json"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(report), encoding="utf-8")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    print(f"Fetched {len(posts)} posts; wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
