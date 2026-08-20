# -*- coding: utf-8 -*-
"""CLI for bounded read-only KnockOS social collection."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone

from agent_reach.knock_collect import (
    collect_brand_mentions,
    collect_facebook,
    collect_instagram_users,
    collect_reddit,
    collect_twitter,
    collect_youtube,
)
from agent_reach.knock_normalize import collection_with_signals


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-reach-knock-collect")
    parser.add_argument("query", nargs="?", default='"Knock AI"')
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--platform",
        choices=["all", "twitter", "reddit", "facebook", "instagram", "youtube"],
        default="all",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Emit source snapshots without conservative normalized signals",
    )
    args = parser.parse_args()

    if args.platform == "all":
        payload = collect_brand_mentions(args.query, args.limit)
        if not args.raw_only:
            payload = collection_with_signals(payload)
    else:
        fn = {
            "twitter": collect_twitter,
            "reddit": collect_reddit,
            "facebook": collect_facebook,
            "instagram": collect_instagram_users,
            "youtube": collect_youtube,
        }[args.platform]
        snapshot = asdict(fn(args.query, args.limit))
        payload = {
            "schema_version": "knock.agent-reach-collection.v1",
            "query": args.query,
            "collected_at": _now(),
            "read_only_origin": True,
            "write_actions_executed": False,
            "snapshots": [snapshot],
        }
        if not args.raw_only:
            payload = collection_with_signals(payload)

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
