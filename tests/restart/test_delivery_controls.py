"""Reached D failures; each targets a specific externally observed invariant."""

from pathlib import Path

import pytest

from .test_negative_controls import API, M
from .test_negative_controls import test_seeded_defect_is_killed as run_seed

STORAGE = "core/src/zaratustra_core/storage.py"
MAINTENANCE = "core/src/zaratustra_core/maintenance.py"
SEEDS: list[tuple[str, str, list[tuple[str, str]], str]] = [
    (
        "D-cancelled-ID-reused",
        "app/src/zaratustra_app/conversation.py",
        [
            (
                '                work_id = base_id + ":after-cancel:" + str(successor)',
                "                " + M + chr(10) + "                break",
            )
        ],
        "test_conversation.py::test_cancelled_entry_requires_new_input_then_new_work",
    ),
    (
        "D-cancelled-blind-restart",
        "app/src/zaratustra_app/conversation.py",
        [
            (
                'if not any(m["seq"] > watermark for m in messages):',
                "if (" + M + " or False):",
            )
        ],
        "test_conversation.py::test_cancelled_entry_requires_new_input_then_new_work",
    ),
    (
        "D-outbox-published-partial",
        "app/src/zaratustra_app/conversation.py",
        [
            (
                '        staging = pending.with_suffix(".staging")',
                "        " + M + chr(10) + "        staging = pending",
            )
        ],
        "test_conversation.py::test_entry_outbox_physical_crash[partial_write]",
    ),
    (
        "D-database-hash-ignored",
        MAINTENANCE,
        [
            (
                'or hashlib.sha256(database).hexdigest() != manifest["database_sha256"]',
                "or (" + M + " or False)",
            )
        ],
        "test_maintenance.py::test_corrupt_partial_backups_refused[valid_database_change]",
    ),
    (
        "D-logical-integrity-skipped",
        MAINTENANCE,
        [
            (
                "def integrity(path: Path) -> None:",
                "def integrity(path: Path) -> None:"
                + chr(10)
                + "    "
                + M
                + chr(10)
                + "    return",
            )
        ],
        "test_maintenance.py::test_rehashed_incoherent_backup_refused[orphan_head]",
    ),
    (
        "D-ref-before-durable",
        API,
        [
            (
                '                durable(self.root / "artifacts" / sha256, raw)',
                "                "
                + M
                + chr(10)
                + '                db.execute("INSERT INTO artifacts VALUES(?,?,?)", '
                '(sha256, len(raw), p["content_type"]))'
                + chr(10)
                + "                db.commit()"
                + chr(10)
                + '                durable(self.root / "artifacts" / sha256, raw)',
            )
        ],
        "test_maintenance.py::test_staging_physical_crash[stage_sync]",
    ),
    (
        "D-ignore-artifact-integrity",
        STORAGE,
        [
            (
                "if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha256:",
                "if (" + M + " or False):",
            )
        ],
        "test_maintenance.py::test_corrupt_partial_backups_refused[bytes]",
    ),
    (
        "D-incomplete-inventory",
        MAINTENANCE,
        [
            (
                'if rows != manifest["artifacts"] or original != manifest["source"]:',
                "if (" + M + " or False):",
            )
        ],
        "test_maintenance.py::test_corrupt_partial_backups_refused[manifest]",
    ),
    (
        "D-retain-old-credentials",
        MAINTENANCE,
        [
            (
                '            db.execute("DELETE FROM credentials")',
                "            " + M,
            )
        ],
        "test_maintenance.py::test_backup_complete_new_epoch_quarantine",
    ),
    (
        "D-retain-old-epoch",
        MAINTENANCE,
        [
            (
                '"UPDATE meta SET instance=?,space=?,epoch=epoch+1"',
                '"UPDATE meta SET instance=?,space=?,epoch=epoch+0"',
            ),
            (
                "        token = secrets.token_urlsafe(32)",
                "        " + M + chr(10) + "        token = secrets.token_urlsafe(32)",
            ),
        ],
        "test_maintenance.py::test_backup_complete_new_epoch_quarantine",
    ),
    (
        "D-allow-quarantine-writes",
        API,
        [
            (
                '                fail("denied", "quarantined")',
                "                " + M,
            )
        ],
        "test_maintenance.py::test_backup_complete_new_epoch_quarantine",
    ),
    (
        "D-maintenance-fence-only-late",
        MAINTENANCE,
        [
            ("from contextlib import closing", "from contextlib import closing, nullcontext"),
            ("with exclusion(core.root):", "with (" + M + " or nullcontext()):"),
        ],
        "test_maintenance.py::test_backup_crash_and_maintenance_excludes_writer[backup_hold_inventory]",
    ),
    (
        "D-diagnostics-body-leak",
        API,
        [
            (
                '                "excluded": ["conversation_text", "record_bodies", '
                '"credentials", "paths"],',
                '                "leak": ('
                + M
                + ' or db.execute("SELECT body FROM records LIMIT 1").fetchone()[0]),'
                + chr(10)
                + '                "excluded": ["conversation_text", "record_bodies", '
                '"credentials", "paths"],',
            )
        ],
        "test_maintenance.py::test_artifact_bytes_refs_and_diagnostics",
    ),
]


@pytest.mark.parametrize("seed", SEEDS, ids=[s[0] for s in SEEDS])
def test_delivery_defect_is_killed(
    tmp_path: Path, seed: tuple[str, str, list[tuple[str, str]], str]
) -> None:
    run_seed(tmp_path, seed)
    assert (tmp_path / "mutant" / seed[1]).is_file()
