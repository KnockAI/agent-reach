# -*- coding: utf-8 -*-
"""KnockOS integration boundary for the open-source Agent Reach capability layer.

This module intentionally stays READ ONLY. Agent Reach discovers/reads/searches
social sources; it does not receive KnockOS publishing credentials and cannot
post, reply, like, follow, delete, or mutate social accounts through this
integration.

Two outputs are provided:

1. a machine-readable capability/health snapshot for KnockOS Social Command;
2. a normalized SocialSignal envelope for content already retrieved by an
   Agent Reach upstream tool.

Keeping normalization here means KnockOS does not need to understand every
upstream CLI's ad-hoc response shape. Keeping publishing out means a browser
cookie or read session can never silently become an outbound brand action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

from agent_reach.channels import get_all_channels
from agent_reach.config import Config

SCHEMA_VERSION = "knock.social-signal.v1"
CAPABILITY_SCHEMA_VERSION = "knock.social-capability.v1"

# Only channels relevant to Knock social listening are exported. Other Agent
# Reach channels remain usable by the generic agent but are not silently wired
# into Social Command.
SOCIAL_CHANNELS = (
    "twitter",
    "facebook",
    "instagram",
    "linkedin",
    "reddit",
    "youtube",
)

# Capabilities are deliberately conservative and reflect what Agent Reach is
# used for in this integration: discovery/read/search. Outbound actions are a
# separate KnockOS connector boundary.
CHANNEL_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "twitter": ("READ", "SEARCH"),
    "facebook": ("READ", "SEARCH"),
    "instagram": ("READ", "SEARCH"),
    "linkedin": ("READ", "SEARCH"),
    "reddit": ("READ", "SEARCH"),
    "youtube": ("READ", "SEARCH"),
}


@dataclass(frozen=True)
class ChannelHealth:
    platform: str
    status: str
    active_backend: Optional[str]
    tier: int
    capabilities: tuple[str, ...]
    read_only: bool = True
    publishing_supported: bool = False


@dataclass(frozen=True)
class SocialSignal:
    schema_version: str
    signal_id: str
    platform: str
    source_id: str
    source_url: str
    author_handle: Optional[str]
    author_display_name: Optional[str]
    text: str
    observed_at: str
    published_at: Optional[str]
    conversation_id: Optional[str]
    parent_source_id: Optional[str]
    metrics: dict[str, int]
    source_adapter: str
    source_digest_sha256: str
    data_classification: str
    read_only_origin: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, *, max_chars: int = 100_000) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "").strip()
    return text[:max_chars]


def _clean_optional(value: Any, *, max_chars: int = 500) -> Optional[str]:
    text = _clean_text(value, max_chars=max_chars)
    return text or None


def _positive_metric(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def capability_snapshot(
    *,
    config: Optional[Config] = None,
    channel_names: Iterable[str] = SOCIAL_CHANNELS,
) -> dict[str, Any]:
    """Return a non-secret read-only channel capability snapshot.

    ``Channel.check`` is allowed to probe local upstream tooling. The returned
    message is intentionally discarded because third-party diagnostics may
    contain local paths or other implementation detail that KnockOS does not
    need. Credentials are never serialized.
    """

    cfg = config or Config(read_only=True)
    requested = set(channel_names)
    rows: list[ChannelHealth] = []

    for channel in get_all_channels():
        if channel.name not in requested:
            continue
        try:
            status, _message = channel.check(cfg)
        except Exception:
            status = "error"
            channel.active_backend = None

        rows.append(
            ChannelHealth(
                platform=channel.name,
                status=status,
                active_backend=channel.active_backend,
                tier=channel.tier,
                capabilities=CHANNEL_CAPABILITIES.get(channel.name, ("READ",)),
            )
        )

    rows.sort(key=lambda row: row.platform)
    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "integration_mode": "READ_ONLY_SOCIAL_INTELLIGENCE",
        "publishing_supported": False,
        "credential_exported": False,
        "channels": [asdict(row) for row in rows],
    }


def normalize_signal(payload: Mapping[str, Any]) -> SocialSignal:
    """Normalize an upstream-retrieved social item into a KnockOS envelope.

    Required fields are deliberately small: platform, source id/URL, and text.
    This function performs no network access and no account mutation.
    """

    platform = _clean_text(payload.get("platform"), max_chars=32).lower()
    if platform not in SOCIAL_CHANNELS:
        raise ValueError(f"UNSUPPORTED_SOCIAL_PLATFORM:{platform or 'missing'}")

    source_id = _clean_text(payload.get("source_id"), max_chars=500)
    source_url = _clean_text(payload.get("source_url"), max_chars=2_000)
    text = _clean_text(payload.get("text"))
    if not source_id:
        raise ValueError("SOCIAL_SIGNAL_SOURCE_ID_REQUIRED")
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("SOCIAL_SIGNAL_SOURCE_URL_REQUIRED")
    if not text:
        raise ValueError("SOCIAL_SIGNAL_TEXT_REQUIRED")

    observed_at = _clean_optional(payload.get("observed_at")) or _utc_now()
    published_at = _clean_optional(payload.get("published_at"))
    raw_metrics = payload.get("metrics")
    metric_map = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    metrics = {
        key: _positive_metric(metric_map.get(key))
        for key in ("likes", "replies", "reposts", "shares", "views")
    }

    digest_source = {
        "platform": platform,
        "source_id": source_id,
        "source_url": source_url,
        "text": text,
        "published_at": published_at,
    }
    digest = _canonical_digest(digest_source)
    signal_id = f"{platform}:{digest[:24]}"

    return SocialSignal(
        schema_version=SCHEMA_VERSION,
        signal_id=signal_id,
        platform=platform,
        source_id=source_id,
        source_url=source_url,
        author_handle=_clean_optional(payload.get("author_handle")),
        author_display_name=_clean_optional(payload.get("author_display_name")),
        text=text,
        observed_at=observed_at,
        published_at=published_at,
        conversation_id=_clean_optional(payload.get("conversation_id")),
        parent_source_id=_clean_optional(payload.get("parent_source_id")),
        metrics=metrics,
        source_adapter=_clean_optional(payload.get("source_adapter")) or "agent-reach",
        source_digest_sha256=digest,
        data_classification="PUBLIC",
        read_only_origin=True,
    )


def _load_json(path: str) -> Mapping[str, Any]:
    if path == "-":
        raw = input()
    else:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise ValueError("SOCIAL_SIGNAL_INPUT_MUST_BE_OBJECT")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-reach-knock",
        description="Read-only Agent Reach → KnockOS Social Command integration",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Emit social channel health/capabilities as JSON")
    normalize = sub.add_parser("normalize", help="Normalize one retrieved social item as JSON")
    normalize.add_argument("input", help="JSON file path, or '-' for one JSON line from stdin")
    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(capability_snapshot(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "normalize":
        result = normalize_signal(_load_json(args.input))
        print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
        return

    raise SystemExit(2)


if __name__ == "__main__":
    main()
