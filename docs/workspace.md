# Personal workspace and connected projects

Zaratustra 0.21.0 separates the installed product, personal Core and source projects.
Core stays on schema 14; existing setup and separate Work acceptance are unchanged.

## Installation

Install the wheel with Python 3.13.7 and ordinary Pi from PATH (tested: Pi 1.0.4,
Node 22.19.0). Run `zaratustra setup`. Choose a personal folder, an existing Core
folder or a new space, and optionally a private GitHub repository. Setup displays
these choices before preparing them. The default uses a Codex subscription and
never automatically switches to a paid API.

Installed package and runtime stay outside the personal folder. Downloading source
does not make that checkout your personal workspace. Typical layout:

```text
personal/
  README.md           instructions for this workspace
  space/.zara-core/   authoritative data (excluded from Git)
  activities/        generated readable snapshots
  documents/         personal documents
  projects/          explicitly colocated small projects
runtime/             config and technical delivery receipts
product-source/      separate product checkout
```

Ordinary `zaratustra` opens the selected personal folder. No PowerShell launcher
or product-source copy inside the personal repository is required.

## Existing configuration

Version 1 is still readable. Explicit version 2 migration keeps the same Core path
and identity; it creates no Activities and does not repeat their setup:

```text
zaratustra workspace migrate --config <old-config> --personal-root <personal> --runtime-root <runtime> --output <new-config>
zaratustra bind --config <new-config>
zaratustra projects register product <product-source>
```

Preserve dirty work and move an old Git worktree with `git worktree move`. Revise
resources through Core; no rewriting historical Attempts or their exact versions.
A closed Work retains its historical resource.

## Projects

`zaratustra workspace info` and `zaratustra projects list` show registered roots.
In Pi use `/zara-workspace`, `/zara-project` and `zara_workspace`. A selected Work's
project is its versioned Core resource. Upstream native file and command tools use
that root. Assigned Work does too. Resume checks Core and registered roots rather
than trusting an old cwd recorded in the transcript.

A project under personal/projects is allowed after explicit registration and needs
no nested Git. Linking an Activity does not move all its documents. Personal memory
and plans stay in Core; code goes to the selected project. Results retain the
resource actually used. An interactive change after a completed response interrupts
the prior Attempt before revising its resource. An unresolved send or another
session's Attempt prevents switching; assigned Attempts cannot switch roots.

## Saving and GitHub

Core saving is immediate. Publication and Work acceptance are separate actions.
After a meaningful saved piece, the assistant offers a prepared snapshot with its
destination and composition. Pi asks once before publishing that packet. Declining
or leaving it unanswered does not discard local work.

```text
zaratustra git prepare
zaratustra git status
zaratustra git publish <preparation-id>
zaratustra git defer <preparation-id>
zaratustra git check
```

Eligible files are README, Git configuration for exact delivery, generated Activity
views, documents and explicitly colocated projects. SQLite/WAL, runtime, credentials,
caches, old installations and source archives are excluded. The configured personal
remote must be private and use main. Before push, rights, exact basis versions,
local hashes and committed bytes are checked again. Unrelated staged changes prevent
publication. A lost push response stays unknown until checked against remote refs;
it is never blindly resent.

Snapshots contain retained record versions, Work results, Methods, setup history,
originals and execution accounting. Large UTF-8 text is split at character boundaries
with an index. Concatenating original parts yields exact text. Binary originals stay
addressed in Core; Markdown is neither a binary backup nor a complete Core restore.

Deleted or restricted bases invalidate the old prepared packet. Preparing again
replaces the generated local view and stages obsolete derived files for removal.
Already published Git history is a delivery copy; ordinary Core deletion does not
rewrite remote history. Full recovery uses the separate native Core backup.

ChatGPT Web reads published files and cannot write Core or GitHub. Before preparing
external context, the agent reports pending publication. Export is a versioned
snapshot and does not automatically update a foreign chat.

## Verification

`tools.probe_workspace_pi` uses ordinary Pi, its native factories, fictional spaces
and a localhost synthetic provider. It checks project roots, retained deliverables,
declined publication, ContextManifest, compact and resume. It uses no real model.
Native tests cover migration, Unicode originals, changed/revoked/deleted bases,
wrong destinations and uncertain sends.
