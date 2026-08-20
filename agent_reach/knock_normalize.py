# -*- coding: utf-8 -*-
"""Conservative normalization of Agent Reach source snapshots for KnockOS.

Upstream CLIs are allowed to change shape. This adapter therefore recognizes a
small set of common fields and skips items it cannot prove rather than
fabricating IDs/URLs/content.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Mapping, Optional

from agent_reach.knock_collect import SourceSnapshot
from agent_reach.knock_export import SocialSignal, normalize_signal

MAX_NODES = 2000
MAX_DEPTH = 8


def _walk(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> Iterable[Mapping[str, Any]]:
    if budget is None:
        budget = [MAX_NODES]
    if depth > MAX_DEPTH or budget[0] <= 0:
        return
    if isinstance(value, Mapping):
        budget[0] -= 1
        yield value
        for child in value.values():
            yield from _walk(child, depth=depth + 1, budget=budget)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, depth=depth + 1, budget=budget)


def _first(item: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def _string(value: Any, max_chars: int = 10_000) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = str(value).strip().replace("\x00", "")
    return text[:max_chars] or None


def _author(item: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    raw = _first(item, ("author", "user", "creator", "account"))
    if isinstance(raw, Mapping):
        handle = _string(_first(raw, ("username", "handle", "screen_name", "name")), 500)
        display = _string(_first(raw, ("display_name", "name", "title")), 500)
        return handle, display
    handle = _string(_first(item, ("username", "handle", "screen_name", "author_handle")), 500)
    display = _string(_first(item, ("author_name", "display_name", "name")), 500)
    if not handle and isinstance(raw, str):
        handle = _string(raw, 500)
    return handle, display


def _platform_url(platform: str, source_id: str, item: Mapping[str, Any]) -> Optional[str]:
    direct = _string(_first(item, ("url", "link", "permalink", "webpage_url", "post_url", "tweet_url")), 2000)
    if direct:
        if direct.startswith("/") and platform == "reddit":
            return f"https://www.reddit.com{direct}"
        if direct.startswith(("https://", "http://")):
            return direct
    if platform == "twitter" and source_id.isdigit():
        return f"https://x.com/i/web/status/{source_id}"
    if platform == "youtube" and source_id:
        return f"https://www.youtube.com/watch?v={source_id}"
    return None


def _metrics(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = item.get("public_metrics")
    source = raw if isinstance(raw, Mapping) else item
    return {
        "likes": _first(source, ("like_count", "likes", "likeCount")) or 0,
        "replies": _first(source, ("reply_count", "replies", "comment_count", "comments")) or 0,
        "reposts": _first(source, ("retweet_count", "repost_count", "reposts", "retweets")) or 0,
        "shares": _first(source, ("share_count", "shares", "quote_count")) or 0,
        "views": _first(source, ("view_count", "views", "viewCount")) or 0,
    }


def _candidate(platform: str, item: Mapping[str, Any], snapshot: SourceSnapshot) -> Optional[dict[str, Any]]:
    body = _string(_first(item, ("text", "content", "body", "caption", "description", "title")), 100_000)
    source_id = _string(_first(item, ("id", "tweet_id", "post_id", "video_id", "shortcode", "note_id")), 500)
    if not body or not source_id:
        return None
    url = _platform_url(platform, source_id, item)
    if not url:
        return None
    handle, display = _author(item)
    return {
        "platform": platform,
        "source_id": source_id,
        "source_url": url,
        "author_handle": handle,
        "author_display_name": display,
        "text": body,
        "observed_at": snapshot.collected_at,
        "published_at": _string(_first(item, ("created_at", "published_at", "timestamp", "date")), 100),
        "conversation_id": _string(_first(item, ("conversation_id", "thread_id", "root_id")), 500),
        "parent_source_id": _string(_first(item, ("in_reply_to_status_id", "parent_id", "parentId")), 500),
        "metrics": _metrics(item),
        "source_adapter": f"agent-reach:{snapshot.backend}",
    }


def signals_from_snapshot(snapshot: SourceSnapshot) -> list[SocialSignal]:
    if snapshot.status != "OK" or not snapshot.read_only_origin:
        return []
    signals: list[SocialSignal] = []
    seen: set[str] = set()
    for item in _walk(snapshot.raw):
        candidate = _candidate(snapshot.platform, item, snapshot)
        if not candidate:
            continue
        try:
            signal = normalize_signal(candidate)
        except ValueError:
            continue
        if signal.signal_id in seen:
            continue
        seen.add(signal.signal_id)
        signals.append(signal)
        if len(signals) >= 100:
            break
    return signals


def collection_with_signals(collection: Mapping[str, Any]) -> dict[str, Any]:
    raw_snapshots = collection.get("snapshots")
    if not isinstance(raw_snapshots, list):
        raise ValueError("AGENT_REACH_COLLECTION_SNAPSHOTS_REQUIRED")
    signals: list[dict[str, Any]] = []
    for raw in raw_snapshots:
        if not isinstance(raw, Mapping):
            continue
        try:
            snapshot = SourceSnapshot(**raw)
        except TypeError:
            continue
        signals.extend(asdict(item) for item in signals_from_snapshot(snapshot))
    return {**dict(collection), "signals": signals, "normalized_signal_count": len(signals)}
