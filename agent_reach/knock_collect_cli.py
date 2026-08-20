# -*- coding: utf-8 -*-
"""CLI for bounded read-only KnockOS social collection."""

import argparse
import json
from dataclasses import asdict

from agent_reach.knock_collect import (
    collect_brand_mentions,
    collect_facebook,
    collect_instagram_users,
    collect_reddit,
    collect_twitter,
    collect_youtube,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-reach-knock-collect")
    parser.add_argument("query", nargs="?", default='"Knock AI"')
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--platform",
        choices=["all", "twitter", "reddit", "facebook", "instagram", "youtube"],
        default="all",
    )
    args = parser.parse_args()

    if args.platform == "all":
        payload = collect_brand_mentions(args.query, args.limit)
    else:
        fn = {
            "twitter": collect_twitter,
            "reddit": collect_reddit,
            "facebook": collect_facebook,
            "instagram": collect_instagram_users,
            "youtube": collect_youtube,
        }[args.platform]
        payload = asdict(fn(args.query, args.limit))

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
