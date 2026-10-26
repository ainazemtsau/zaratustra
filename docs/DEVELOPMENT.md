# Development and maintenance

Incremental fixes follow [RELEASING.md](RELEASING.md). Current approval-UI maintenance
preserves immutable proposals and the actual native confirmation boundary; see
[release notes](../CHANGELOG.md). The earlier concurrency delivery below remains its
historical qualification scope, not a requirement to repeat heavy runs for every fix.

## Concurrent workspace delivery

Read ../AGENTS.md and CONCURRENCY.md. Owner approved local multi-session coordination
on 26 October 2026. The later owner amendment stops 100-process qualification: accepted
verification is at most ten processes; retain prior failed attempts honestly. No further
100-process or heavy growth runs. No full historical check/deliver matrix or model/API
conversations. Use targeted mechanical tests, types/lint/build and focused review.

Pi 1.4.0, isolated Node 24.22.1 / SQLite 3.53.4. Keep global Node/Pi and real private ZT/
Health unchanged. Domain identities/history stay; schema 9/control 2 introduce concurrency
and derived indexes. No server/daemon, per-Activity SQL tables or automatic Git actions.
Historical original specs and sealed evidence remain unchanged.

END_OF_FILE: docs/DEVELOPMENT.md
