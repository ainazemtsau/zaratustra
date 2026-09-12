# Reproduce the shipped generic first-use path

The commands below use only installed product files and user-created generic text.
They do not use development fixtures or contact ChatGPT or another provider.

Create `setup.json`:

```json
{
  "version": 1,
  "process_title": "Generic notes",
  "goal": "Develop the next generic note",
  "expected_result": "One reviewed text update",
  "acceptance": ["The saved source is retained exactly"],
  "boundaries": ["Use generic demonstration data only"],
  "budget": "One bounded local exchange",
  "artifact_title": "Generic working note",
  "created_by": "local setup"
}
```

Create `initial.txt` with real nonblank UTF-8 starting material, then run:

```text
zara entry start catalog.json "Generic Notes" instance setup.json initial.txt
zara entry open catalog.json "Generic Notes" --max-bytes 1048576
zara entry request catalog.json "Generic Notes" request.json --max-bytes 1048576
```

`start` creates the selected directory when absent, explicitly migrates it to schema
7, creates one generic unbound Process/Work/Artifact, and registers it in
`catalog.json`. It displays four exact standard operations. Each must be confirmed by
typing the requested `approve HASH` on the controlling terminal. If confirmation is
not completed, the catalog may truthfully show a draft; `entry open` and `entry
request` will refuse it. Rerun the exact same `start` inputs to use the retained plan;
do not create another workspace to hide an error.

`open` displays and confirms the exact generated `ContextQuery`, then writes the
complete current Core context to stdout. Its artifact-version source contains the
actual accepted `initial.txt` bytes as base64; headings alone are not treated as
saved material. `request` performs the same authorized bounded read and refuses to
overwrite `request.json`. The JSON field `copyable_request` is the text a human may
copy to a chosen external chat. Request creation is not acceptance or completion and
does not launch a provider.

Save only the provider's returned text in `response.txt`; do not edit any technical
field in `request.json`. Then run:

```text
zara entry receive catalog.json "Generic Notes" request.json response.txt \
  --created-by "manual external supplier"
```

The product makes the strict intake envelope and displays the full intended new text,
original revision, exact basis, hashes, publication and acceptance requests. The
returned bytes cannot confirm that preview. Type the requested `approve HASH` only
after reviewing it. The ordinary recoverable publication/acceptance path then saves
new immutable bytes and separate receipts; Work completion remains `not_requested`.
If the instance changed after `request.json` was made, `receive` refuses the stale
target instead of refreshing it.

Repository maintainers can reproduce the isolated installed-wheel demonstration in
a new ignored directory:

```text
uv run --locked python -m tools.probe_entry_t5 --output _scratch/entry-t5-run
```

The probe creates and registers two new generic instances from the wheel in an
unrelated working directory, proves a draft is not openable, opens both by
designation, simulates only a returned generic text file, and checks wrong/stale
targets, shared-alias ambiguity and an unavailable neighbor. Its simulated response
is not a real external-chat trial.

END_OF_FILE: docs/entry-t5/REPRODUCE.md
