## What changed

<!-- one or two sentences -->

## Why

<!-- the failure this fixes, or the gap it fills -->

## Verified how

<!--
Which client, which model, what you actually ran and saw.
"No changes to protocol code" is a valid answer for docs-only PRs.
-->

## Checks

- [ ] `python -m py_compile` passes on every touched module
- [ ] no real keys, relay URLs, or absolute personal paths added
- [ ] `relay-models.json`, `instances.json`, `dumps-*/`, `*.log` not committed
- [ ] if protocol-related: tested against a real WorkBuddy desktop session
- [ ] read [`SECURITY.md`](../SECURITY.md) "what this project won't do"
