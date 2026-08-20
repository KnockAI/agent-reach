# KnockOS Social Command boundary

This fork exposes Agent Reach to KnockOS as a **read-only social intelligence capability layer**.

## Responsibility split

- **Agent Reach**: discover, read, search, and health-check supported social/network sources.
- **KnockOS Social Command**: durable conversation state, brand policy, claim provenance, risk classification, approvals, outbound connector permissions, audit, scheduling, analytics, and lead routing.
- **OMEGA/model gateway**: optional drafting/reasoning. It is not the authority to publish.

## Machine interface

```bash
agent-reach-knock status
agent-reach-knock normalize social-item.json
```

`status` emits only non-secret channel capability/health metadata. Credentials and diagnostic details are not serialized.

`normalize` converts an item already retrieved by an Agent Reach upstream tool into `knock.social-signal.v1` with a stable digest and `read_only_origin=true`.

## Hard boundary

This integration does not expose post, reply, like, follow, delete, DM-send, account-management, or publishing actions. Social publishing credentials belong to dedicated KnockOS outbound connectors with separate approval scopes.

A browser cookie or session used by Agent Reach for reading must never be treated as permission to speak for the Knock brand.
