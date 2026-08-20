import subprocess

from agent_reach import knock_collect


class StubConfig:
    def get(self, key, default=None):
        values = {
            "twitter_auth_token": "token",
            "twitter_ct0": "csrf",
        }
        return values.get(key, default)


def completed(stdout: str, code: int = 0):
    return subprocess.CompletedProcess(args=["stub"], returncode=code, stdout=stdout, stderr="")


def test_twitter_collection_is_bounded_read_only_and_does_not_log_credentials(monkeypatch):
    monkeypatch.setattr(knock_collect.shutil, "which", lambda name: "/usr/bin/twitter" if name == "twitter" else None)
    captured = {}

    def runner(args, *, env=None, timeout=30):
        captured["args"] = args
        captured["env"] = env
        return completed('[{"id":"1","text":"Knock AI"}]')

    result = knock_collect.collect_twitter("Knock AI", 999, config=StubConfig(), runner=runner)
    assert result.status == "OK"
    assert result.read_only_origin is True
    assert captured["args"][:3] == ["twitter", "search", "Knock AI"]
    assert captured["args"][4] == str(knock_collect.MAX_RESULTS)
    assert "token" not in str(captured["args"])
    assert "csrf" not in str(captured["args"])


def test_opencli_collector_uses_search_only(monkeypatch):
    monkeypatch.setattr(knock_collect.shutil, "which", lambda name: "/usr/bin/opencli" if name == "opencli" else None)
    seen = []

    def runner(args, *, env=None, timeout=30):
        seen.append(args)
        return completed("- id: abc\n  title: Example\n")

    result = knock_collect.collect_facebook("Knock AI", 5, runner=runner)
    assert result.status == "OK"
    assert seen == [["opencli", "facebook", "search", "Knock AI", "-f", "yaml"]]
    assert all(word not in seen[0] for word in ["post", "comment", "like", "delete"])


def test_missing_tools_fail_closed(monkeypatch):
    monkeypatch.setattr(knock_collect.shutil, "which", lambda _name: None)
    result = knock_collect.collect_reddit("Knock AI")
    assert result.status == "UNAVAILABLE"
    assert result.raw == []
    assert result.read_only_origin is True
