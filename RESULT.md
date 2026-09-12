# Installed entry discovery and basic reading

## outcome

Scope achieved for the bounded discovery/read increment.

An exact designation resolves to its uniquely named
row before aliases are considered. Shared aliases remain permitted and remain
ambiguous when no exact designation matches; every designation offered for that
ambiguity is therefore actionable by the same read and relocate resolver.

1. Two explicitly created Process instances are found by the human-readable
   designations `Morning Notes` and `Review Queue`. The selected ready Work reports
   `selected_work_ready`; the selected terminal Work reports `saved_result`, its
   exact accepted Artifact version/hash and its exact saved next-Work value.
2. A shared alias returns both designations as explicit choices. When one source is
   unavailable, the other row remains available. Identity substitution is reported
   as mismatched and relocation requires an explicit exact-identity check. Catalog
   membership supplies no Core authorization; the basic reader accepts only one
   selected/visible Work under an exactly authorized current `ProcessQuery`.
3. Concurrent successful catalog mutations no longer lose a prior success. Forced
   spawned-process overlap preserves both distinct adds; a same-designation overlap
   produces one success and one explicit `designation_exists`; add/relocate preserves
   both the relocation and the independently added row.
4. The installed-wheel probe reproduces concurrent discovery and basic reading on
   two newly created generic schema-7 workspaces without a development Pack or owner
   data.

Core identity, authority, immutable Pack binding, acceptance and mutation semantics
are unchanged. The new reader is metadata-only and performs no workspace writes.

## evidence

Commands successfully executed on the finished candidate:

- `uv run --locked python -m tools.check --deliver`
- `uv run --locked python -m pytest tests/zaratustra/entry/test_catalog.py -q`
- `uv run --locked python -m tools.probe_entry_t2 --output _scratch/<new-entry-t2-run>`

The focused catalog suite passed seven tests using a task-local cache. The
installed-wheel summary records `exact_designation_precedes_alias: true`,
`ambiguity_choices_actionable: true`, and preserved concurrent adds, alongside
the read/relocation observations below. The probe checks each ambiguity choice
against its exact row without assuming a concurrent insertion order.

The final complete native delivery gate exited successfully after formatting,
lint, strict types, 12 import contracts, 264 passing tests, wheel/source build and
report structure validation. A task-local pytest cache was used. The complete
native transcript and installed outputs are retained locally; no partial or
interrupted run is counted as delivery evidence.

The final installed probe ran from an unrelated directory against an isolated
Python 3.13.7 environment. Two synchronized installed child processes both added
their independent row and `concurrent_adds_preserved` was true. The probe also
observed two available designations; an ambiguity with two choices; `Morning Notes`
unavailable while `Review Queue` remained available after moving one source;
both sources available after explicit relocation; one ready Work; and one done
Work with one accepted basis, a saved Result and an exact next-Work identity. It
also directly exercised installed `zara entry find`. Reproduction and output
inventory are documented in `docs/entry-t2/REPRODUCE.md`; technical choices are in
`docs/entry-t2/PLAN.md`.

## assumptions

The caller explicitly chooses the catalog and every added workspace. The current
trusted local-console/local-chat boundary remains the source of Core authorization;
catalog files and aliases are untrusted discovery inputs. Catalog operations target
schema-7 workspaces containing the existing one-Process graph. A saved continuation
is historical accepted metadata, not evidence that its Work is currently openable.

## cuts

No Process constructor, content opening through this reader, Pack execution or
binding, transfer coordinator/import preview, startup flow, model choice, memory,
GUI, real subject Process, or external chat transfer is included. The catalog does
not scan directories or silently follow moved paths. Advisory locking coordinates
cooperating local product callers only; arbitrary manual edits and distributed or
network filesystems without equivalent lock/rename guarantees remain outside scope.

## cost

One small installed catalog adapter, one bounded generic Core projection, four CLI
subcommands, one dependency-boundary contract, focused catalog regression coverage,
one installed probe and two compact product documents. Catalog/search/path/locking
policy is isolated in the adapter; future subject reading can replace the CLI
bootstrap choice without changing Core identity or Pack binding.

## manual-acceptance

No personal-use test or owner acceptance is claimed. Automated checks establish
the stated technical behavior only; the parent performs separate fresh verification.

## next

solmax

The next engineering risk is the later constructor/first-use flow: it must choose
initial binding and authority deliberately without turning catalog discovery into
creation authority or implying that a saved continuation is ready to execute.

END_OF_FILE: RESULT.md
