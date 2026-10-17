# Reproducible working checkpoint

**NOT_READY.** This is saved source and technical evidence, not a release or an
accepted permanent-use version. The current archived codec checkpoint is
[`zaratustra-pi-0.2.0-32b096a.zip`](zaratustra-pi-0.2.0-32b096a.zip), from source
`32b096a474f36fb55a6296110261e6a67d6981a4`. Its SHA256 is
`011eb1314d90e052aaf1fc83dfe676be195aeca70efadf67a508368fa9f2a566`.
[Source metadata](zaratustra-pi-0.2.0-32b096a.source.json) pins all nine members;
[evidence](../evidence/permanent-use/README.md) separates checked behavior from
remaining work. Expanded local test folders and older failed packages are not
canonical deliveries.

The owner approved successor continuation for Sleep. That implementation and its
data-format upgrade are in progress after this codec freeze. Do not use this
checkpoint as evidence that meaningful Sleep adaptation or the complete required
gate has passed.

To inspect this package in a disposable installation, extract the ZIP into a
permanent directory, keep the extracted directory, then register that directory:

```text
pi install "/absolute/path/zaratustra-pi-0.2.0-32b096a"
```

Prerequisites are Pi1.3.0, Node22 and `uv` on PATH. First entry provisions
Python3.13.7 and pinned dependencies; downloads need network access. Pi owns its
authentication. No personal configuration or Activity is included in the ZIP.
After installation, open ordinary `pi` in the intended project and enter
`/zaratustra`. Subsequent work uses ordinary prose and builtin coding tools.
There is no daily PowerShell script, manual JSON setup or production call cap.

A local package is identified by its absolute path. Installing another directory
does not replace the old registration. Inside Pi, a supported path replacement is:

```text
!pi remove "/absolute/old/package/path"
!pi install "/absolute/new/package/path"
/reload
/zaratustra
```

Use `-l` on both shell commands if the original registration was project-local.
Pi and a shell must be available on PATH. `remove` unregisters the local path; it
does not delete that directory or the separate Core data root. There are no Pi
`/install` or `/remove` slash commands. The new package verifies compatibility
before selecting its runtime; it reconnects to the existing Core rather than
initializing another Activity. The forthcoming protocol upgrade must also refuse
old writers before mutation.

The archive contains portable Python and TypeScript. Native Windows entry was
tested; this checkpoint does not claim native macOS/Linux execution proof.
Backup setup, disaster recovery, cross-device synchronization and private Activity
uploads are outside the current minimal flow.

END_OF_FILE: delivery/README.md
