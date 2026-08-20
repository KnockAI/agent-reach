from agent_reach.knock_collect import SourceSnapshot
from agent_reach.knock_normalize import signals_from_snapshot


def snapshot(platform, raw):
    return SourceSnapshot(
        schema_version="knock.agent-reach-source-snapshot.v1",
        platform=platform,
        query="Knock AI",
        backend="fixture",
        collected_at="2026-08-20T05:00:00Z",
        status="OK",
        source_digest_sha256="a" * 64,
        raw=raw,
        error=None,
    )


def test_twitter_common_shape_normalizes_without_inventing_fields():
    signals = signals_from_snapshot(snapshot("twitter", {
        "data": [{
            "id": "12345",
            "text": "What does Knock AI verify?",
            "username": "person",
            "created_at": "2026-08-20T04:50:00Z",
            "public_metrics": {"like_count": 4, "reply_count": 1},
        }]
    }))
    assert len(signals) == 1
    assert signals[0].source_url == "https://x.com/i/web/status/12345"
    assert signals[0].author_handle == "person"
    assert signals[0].metrics["likes"] == 4


def test_items_without_provable_id_or_url_are_skipped():
    signals = signals_from_snapshot(snapshot("facebook", [{"text": "Knock AI mention but no ID"}]))
    assert signals == []


def test_non_ok_snapshot_yields_no_signals():
    item = snapshot("twitter", [{"id": "1", "text": "hello"}])
    item = SourceSnapshot(**{**item.__dict__, "status": "ERROR"})
    assert signals_from_snapshot(item) == []
