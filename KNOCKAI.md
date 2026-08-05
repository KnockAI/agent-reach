# KnockAI Fork — Agent Reach

Upstream: https://github.com/Panniantong/Agent-Reach (MIT)

## Security audit — 2026-08-05

Performed by: Claude Sonnet 4.6 / Jacob Wynn

| Check | Result |
|-------|--------|
| eval/exec patterns | PASS — none found |
| subprocess injection | PASS — all list-form args, no shell=True |
| Hardcoded credentials | PASS — none |
| Telemetry / phone-home | PASS — none |
| SSRF protection | PASS — _assert_safe_public_url() in transcribe.py blocks RFC 1918, loopback, metadata.google |
| Pickle/marshal deserialization | PASS — none |
| Browser cookie access | REMOVED — see below |
| Package manager calls in CLI | ACCEPTABLE — apt-get/brew/npm in setup path, list-form |

## Changes from upstream

1. **Pinned all core dependency versions** to the upstream `constraints.txt` tested set.
2. **Removed `browser-cookie3`** from the `[all]` optional extra. The `[cookies]` extra still exists in the source but is intentionally excluded from `[all]` to prevent accidental installation. Reason: `browser_cookie3` / `rookiepy` read the host machine's decrypted browser cookie database — unnecessary for Beowulf and a privacy risk if Beowulf runs on a server.
3. **Updated project URLs** to this fork.

## Install for Beowulf

```bash
pip install "agent-reach[all] @ git+https://github.com/KnockAI/agent-reach.git"
```

Do NOT add `[cookies]` to the install command.

## Platforms available

- Web reader (general URL)
- Twitter/X (read-only, requires manual cookie export)
- Reddit
- YouTube (transcript)
- GitHub
- RSS / Atom feeds
- Exa semantic search
- Instagram, LinkedIn, Facebook (limited, may need cookies)
- Bilibili, XiaoHongShu, V2EX, Xueqiu (Chinese platforms)
