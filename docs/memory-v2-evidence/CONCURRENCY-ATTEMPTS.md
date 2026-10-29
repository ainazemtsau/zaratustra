# Bounded concurrency attempts

All fixtures were synthetic temporary workspaces. No ZT/Health data, model calls or paid APIs were used; no run exceeded ten concurrent child processes.

- Initial harness type validation found heterogeneous-array inference; corrected before execution.
- Initial seed validation lacked required Entity aliases/disambiguation; corrected before child execution.
- The first actual child profiles preserved independent Work and replay checks, but the guarded-update fixture omitted required Entity data. Those profiles were not qualified as passing.
- A correction initially missed the fixture because the default formatter ignores fixtures. That redundant run was stopped using only its verified controller process; absence of remaining owned workers was checked.
- With the corrected fixture, the two-process profile passed, then the ten-process profile passed. Public results are `concurrency-2.json` and `concurrency-10.json`; raw prior fixtures were preserved locally.

The passing measurements were exported without rerunning tests. Host PIDs and temporary paths are omitted; timing/RSS limitations are explicit in each JSON file.
