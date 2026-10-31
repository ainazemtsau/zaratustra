# Sync notification correction — 0.7.5

Repeated checkpoint requests previously displayed LOCAL_COMMITTED followed by a
GitHub confirmation even when no new commit was created. Automatic chat notices
now show only settled REMOTE_CONFIRMED successes, once per newly confirmed commit.
Intermediate LOCAL_SAVED/LOCAL_COMMITTED notices are suppressed. Explicit tool
status replies and persisted checkpoint states retain their full detail.

A compact notification marker lives under the Git common coordination directory,
protected by the existing checkpoint lease. It survives runtime recreation and is
shared by sessions of the same repository. An existing verified settled status
seeds the upgrade baseline. Declined or throwing host callbacks do not consume a
success. Failures and deferrals remain visible, including live checkpoint contention;
a waiting process does not overwrite the owning process's persisted status.
Presentation bookkeeping cannot change checkpoint durability. A crash or marker
write failure immediately after presentation can still permit a repeated notice.

Five focused native local-repository regressions passed, including repeated and
recreated synchronizers, separate runtime roots, a new commit, pending-to-settled
confirmation, upgrade baselining, declined/throwing callbacks, offline operation,
manual staging and a live checkpoint lease. The old implementation failed all
five before the correction. Five adjacent controls also passed: lost push acknowledgement,
old-epoch completion, offline retry, an older coherent checkpoint with newer pending
work, and confirmed idle polling/clean close. Final targeted total: 10 passed, 0 failed.
No model or paid API conversations were used.

Types, targeted lint/format, dependency boundaries and build passed. A focused
independent source review found no blocking issue. The memory format, schema,
control protocol, dependencies and semantic records are unchanged. Installation
only updates the pinned package; an already loaded Pi session needs /reload to
load the new notification handler.
