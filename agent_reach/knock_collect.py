# -*- coding: utf-8 -*-
"""Bounded read-only social collection for KnockOS.

Agent Reach remains the access layer. This module invokes only documented read
/search commands, never write actions. It returns source snapshots rather than
pretending every upstream CLI has one stable schema.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import yaml

from agent_reach.config import Config
from agent_reach.channels.twitter import twitter_cli_child_env

MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_QUERY_CHARS = 200
MAX_RESULTS = 25
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class SourceSnapshot:
    schema_version: str
    platform: str
    query: str
    backend: str
    collected_at: str
    status: str
    source_digest_sha256: str
    raw: Any
    error: Optional[str]
    read_only_origin: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_output(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        parsed = yaml.safe_load(raw)
        return parsed if parsed is not None else []
    except yaml.YAMLError:
        return {"text": raw[:100_000]}


def _safe_run(args: list[str], *, env: Optional[dict[str, str]] = None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if len(result.stdout.encode("utf-8", "replace")) > MAX_OUTPUT_BYTES:
        raise RuntimeError("AGENT_REACH_OUTPUT_LIMIT_EXCEEDED")
    if len(result.stderr.encode("utf-8", "replace")) > 64 * 1024:
        raise RuntimeError("AGENT_REACH_STDERR_LIMIT_EXCEEDED")
    return result


def _snapshot(platform: str, query: str, backend: str, status: str, raw: Any, error: Optional[str] = None) -> SourceSnapshot:
    return SourceSnapshot(
        schema_version="knock.agent-reach-source-snapshot.v1",
        platform=platform,
        query=query,
        backend=backend,
        collected_at=_now(),
        status=status,
        source_digest_sha256=_digest(raw),
        raw=raw,
        error=error,
    )


def _bounded(query: str, limit: int) -> tuple[str, int]:
    cleaned = " ".join(query.split()).strip()[:MAX_QUERY_CHARS]
    if not cleaned:
        raise ValueError("SOCIAL_QUERY_REQUIRED")
    return cleaned, max(1, min(MAX_RESULTS, int(limit)))


def collect_twitter(query: str, limit: int = 10, *, config: Optional[Config] = None, runner: Callable[..., subprocess.CompletedProcess[str]] = _safe_run) -> SourceSnapshot:
    query, limit = _bounded(query, limit)
    if not shutil.which("twitter"):
        return _snapshot("twitter", query, "twitter-cli", "UNAVAILABLE", [], "twitter-cli not installed")
    cfg = config or Config(read_only=True)
    child = twitter_cli_child_env(cfg)
    env = os.environ.copy()
    env.update(child)
    if not env.get("TWITTER_AUTH_TOKEN") or not env.get("TWITTER_CT0"):
        return _snapshot("twitter", query, "twitter-cli", "NEEDS_AUTH", [], "explicit Cookie-Editor credentials not configured")
    try:
        result = runner(["twitter", "search", query, "-n", str(limit), "--json"], env=env, timeout=DEFAULT_TIMEOUT_SECONDS)
    except Exception as exc:
        return _snapshot("twitter", query, "twitter-cli", "ERROR", [], type(exc).__name__)
    if result.returncode != 0:
        return _snapshot("twitter", query, "twitter-cli", "ERROR", [], f"command exit {result.returncode}")
    raw = _parse_output(result.stdout)
    return _snapshot("twitter", query, "twitter-cli", "OK", raw)


def _collect_opencli(platform: str, query: str, limit: int, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _safe_run) -> SourceSnapshot:
    query, limit = _bounded(query, limit)
    if not shutil.which("opencli"):
        return _snapshot(platform, query, "OpenCLI", "UNAVAILABLE", [], "OpenCLI not installed")
    if platform == "reddit":
        args = ["opencli", "reddit", "search", query, "-f", "yaml"]
    elif platform == "facebook":
        args = ["opencli", "facebook", "search", query, "-f", "yaml"]
    elif platform == "instagram":
        # Instagram search is user search, not arbitrary post keyword search.
        args = ["opencli", "instagram", "search", query, "-f", "yaml"]
    else:
        raise ValueError(f"OPENCLI_SOCIAL_PLATFORM_UNSUPPORTED:{platform}")
    try:
        result = runner(args, env=os.environ.copy(), timeout=DEFAULT_TIMEOUT_SECONDS)
    except Exception as exc:
        return _snapshot(platform, query, "OpenCLI", "ERROR", [], type(exc).__name__)
    if result.returncode != 0:
        return _snapshot(platform, query, "OpenCLI", "ERROR", [], f"command exit {result.returncode}")
    raw = _parse_output(result.stdout)
    if isinstance(raw, list):
        raw = raw[:limit]
    return _snapshot(platform, query, "OpenCLI", "OK", raw)


def collect_reddit(query: str, limit: int = 10, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _safe_run) -> SourceSnapshot:
    return _collect_opencli("reddit", query, limit, runner=runner)


def collect_facebook(query: str, limit: int = 10, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _safe_run) -> SourceSnapshot:
    return _collect_opencli("facebook", query, limit, runner=runner)


def collect_instagram_users(query: str, limit: int = 10, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _safe_run) -> SourceSnapshot:
    return _collect_opencli("instagram", query, limit, runner=runner)


def collect_youtube(query: str, limit: int = 10, *, runner: Callable[..., subprocess.CompletedProcess[str]] = _safe_run) -> SourceSnapshot:
    query, limit = _bounded(query, limit)
    if not shutil.which("yt-dlp"):
        return _snapshot("youtube", query, "yt-dlp", "UNAVAILABLE", [], "yt-dlp not installed")
    args = ["yt-dlp", "--flat-playlist", "--dump-single-json", f"ytsearch{limit}:{query}"]
    try:
        result = runner(args, env=os.environ.copy(), timeout=DEFAULT_TIMEOUT_SECONDS)
    except Exception as exc:
        return _snapshot("youtube", query, "yt-dlp", "ERROR", [], type(exc).__name__)
    if result.returncode != 0:
        return _snapshot("youtube", query, "yt-dlp", "ERROR", [], f"command exit {result.returncode}")
    return _snapshot("youtube", query, "yt-dlp", "OK", _parse_output(result.stdout))


def collect_brand_mentions(query: str = '"Knock AI"', limit: int = 10) -> dict[str, Any]:
    query, limit = _bounded(query, limit)
    snapshots = [
        collect_twitter(query, limit),
        collect_reddit(query, limit),
        collect_facebook(query, limit),
        collect_youtube(query, limit),
    ]
    # Instagram's search surface is user/account search rather than arbitrary
    # post keyword search, so it is deliberately excluded from mention counts.
    return {
        "schema_version": "knock.agent-reach-collection.v1",
        "query": query,
        "collected_at": _now(),
        "read_only_origin": True,
        "write_actions_executed": False,
        "snapshots": [asdict(item) for item in snapshots],
    }
