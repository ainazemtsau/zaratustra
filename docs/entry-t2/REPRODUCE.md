# Reproduce installed entry discovery and basic reading

From the repository, choose a new ignored output directory and run:

```text
uv run --locked python -m tools.probe_entry_t2 --output _scratch/entry-t2-run
```

Concurrent insertion order is unspecified. The probe checks each offered
designation against its exact catalog row independently of that order.

The probe builds the wheel, installs it with only locked runtime dependencies in
an isolated environment, and runs from an unrelated current directory. Through
the installed public product it creates two new generic schema-7 workspaces,
authorizes their initial Works, saves one exact generic acceptance and Result,
and starts two installed child processes that add the instances concurrently to an
explicit catalog as `Morning Notes` and `Review Queue`. The retained summary must
report `concurrent_adds_preserved: true`.

It demonstrates catalog search, an ambiguous shared alias, one missing source
without loss of the neighboring row, and explicit identity-preserving relocation.
Each ambiguity choice is a usable exact designation: an exact designation takes
precedence over a different row's alias of the same case-folded text.
It reads both selected Works through the generic Core reader and verifies the
ready state, terminal state, exact saved basis hash and exact saved next-Work id.
The installed `zara entry find` command is also exercised directly.

For interactive use with an installed package, the corresponding commands are:

```text
zara entry add CATALOG DESIGNATION WORKSPACE --work-id WORK_ID --alias ALIAS
zara entry find CATALOG SEARCH_TEXT
zara entry read CATALOG DESIGNATION --max-bytes 65536
zara entry relocate CATALOG DESIGNATION MOVED_WORKSPACE
```

`entry read` displays and asks the owner to confirm the complete exact
`ProcessQuery`; a catalog row or alias never supplies that authorization. The
read returns no Artifact content. Its saved continuation is historical accepted
metadata, not permission to open or execute the next Work.

The selected output directory retains `summary.json`, `commands.json`, the
catalog, both disposable workspaces, exact read/search outputs and installed CLI
output for local inspection. No demo database or raw transcript is tracked.

Catalog mutations coordinate through a stable sibling advisory-lock file while
retaining atomic JSON replacement. A crash releases the OS lock even though the
harmless lock file remains. This coordinates cooperating local product callers;
manual editors and network-filesystem lock/rename behavior are outside the guarantee.

END_OF_FILE: docs/entry-t2/REPRODUCE.md
