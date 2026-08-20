from dataclasses import asdict

import pytest

from agent_reach.knock_export import SOCIAL_CHANNELS, capability_snapshot, normalize_signal


class StubConfig:
    def get(self, _key, default=None):
        return default


def test_capability_snapshot_is_read_only_and_never_advertises_publish():
    snapshot = capability_snapshot(config=StubConfig(), channel_names=("web",))
    assert snapshot["integration_mode"] == "READ_ONLY_SOCIAL_INTELLIGENCE"
    assert snapshot["publishing_supported"] is False
    assert snapshot["credential_exported"] is False
    assert len(snapshot["channels"]) == 1
    row = snapshot["channels"][0]
    assert row["read_only"] is True
    assert row["publishing_supported"] is False


def test_normalize_signal_is_deterministic_and_read_only():
    payload = {
        "platform": "twitter",
        "source_id": "12345",
        "source_url": "https://x.com/knock/status/12345",
        "author_handle": "someone",
        "text": "What does Knock AI verify?",
        "published_at": "2026-08-20T05:00:00Z",
        "observed_at": "2026-08-20T05:01:00Z",
        "conversation_id": "thread-1",
        "metrics": {"likes": 4, "replies": 2, "views": 100},
    }
    first = normalize_signal(payload)
    second = normalize_signal(payload)
    assert first.signal_id == second.signal_id
    assert first.source_digest_sha256 == second.source_digest_sha256
    assert first.read_only_origin is True
    assert first.data_classification == "PUBLIC"
    assert first.metrics["likes"] == 4
    assert first.metrics["replies"] == 2
    assert asdict(first)["platform"] == "twitter"


def test_normalize_signal_rejects_missing_source_and_unknown_platform():
    with pytest.raises(ValueError, match="UNSUPPORTED_SOCIAL_PLATFORM"):
        normalize_signal({
            "platform": "made-up-network",
            "source_id": "1",
            "source_url": "https://example.com/1",
            "text": "hello",
        })

    with pytest.raises(ValueError, match="SOCIAL_SIGNAL_SOURCE_ID_REQUIRED"):
        normalize_signal({
            "platform": SOCIAL_CHANNELS[0],
            "source_url": "https://example.com/1",
            "text": "hello",
        })


def test_normalize_signal_never_trusts_negative_metrics():
    signal = normalize_signal({
        "platform": "reddit",
        "source_id": "abc",
        "source_url": "https://www.reddit.com/r/example/comments/abc",
        "text": "example",
        "metrics": {"likes": -20, "replies": "3"},
    })
    assert signal.metrics["likes"] == 0
    assert signal.metrics["replies"] == 3
