"""Explicit schema 14 to 15 upgrade, preserving original revision bytes."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from uuid import uuid4

from .models import SpaceInfo
from .operations import LocalAuthority, _authorize, _local_space
from .storage import (
    STRUCTURES_REBUILD_TABLES,
    STRUCTURES_SCHEMA_NAME,
    STRUCTURES_SCHEMA_SHA256,
    STRUCTURES_SCHEMA_STATEMENTS,
    FoundationError,
    _begin,
    _connect,
    _space_info,
    canonical_json,
    layout,
    read_space,
    utc_now,
)


def upgrade_structures_space(path: Path, authority: LocalAuthority) -> SpaceInfo:
    root, database, _ = layout(path)
    # Disable FK actions only on this migration connection, before its transaction.
    # Copy/drop/rename preserves incoming FK names and does not cascade-delete history.
    with closing(_connect(database, writable=True)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        _begin(connection, writable=True)
        try:
            info = _space_info(connection, root, database)
            _local_space(authority, info)
            if info.schema_version < 14 or info.recovery_state != "active":
                raise FoundationError(
                    "unsupported_schema", "Structures upgrade needs active schema 14"
                )
            _authorize(
                connection,
                actor=authority.actor,
                action="maintenance.backup",
                epoch=info.execution_epoch,
            )
            if info.schema_version == 14:
                for name, definition in STRUCTURES_REBUILD_TABLES.items():
                    columns = [row[1] for row in connection.execute(f"PRAGMA table_info({name})")]
                    indexes = [
                        row[0]
                        for row in connection.execute(
                            "SELECT sql FROM sqlite_schema WHERE type='index' AND tbl_name=? "
                            "AND sql IS NOT NULL",
                            (name,),
                        )
                    ]
                    replacement = name + "_schema15"
                    connection.execute(
                        definition.replace(f"CREATE TABLE {name} ", f"CREATE TABLE {replacement} ")
                    )
                    selected = ",".join(columns)
                    connection.execute(
                        f"INSERT INTO {replacement} ({selected}) SELECT {selected} FROM {name}"
                    )
                    connection.execute(f"DROP TABLE {name}")
                    connection.execute(f"ALTER TABLE {replacement} RENAME TO {name}")
                    for index in indexes:
                        connection.execute(index)
                connection.execute(
                    "CREATE UNIQUE INDEX initial_activity_setup "
                    "ON activity_setups(activity_id) WHERE mode='create'"
                )
                for statement in STRUCTURES_SCHEMA_STATEMENTS:
                    connection.execute(statement)
                connection.execute(
                    "UPDATE memory_index SET material_role=CASE "
                    "WHEN unprocessed=1 THEN 'intake' "
                    "WHEN EXISTS (SELECT 1 FROM knowledge_revisions k WHERE "
                    "k.record_id=memory_index.record_id AND k.revision=memory_index.revision "
                    "AND json_extract(k.payload,'$.channel') IN ('conversation_user',"
                    "'conversation_assistant','tool_result','core_operation')) THEN 'execution' "
                    "ELSE 'working' END"
                )
                now = utc_now().isoformat()
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (15,?,?,?)",
                    (STRUCTURES_SCHEMA_NAME, STRUCTURES_SCHEMA_SHA256, now),
                )
                connection.execute("PRAGMA user_version=15")
                connection.execute("UPDATE spaces SET state_revision=state_revision+1")
                connection.execute(
                    "INSERT INTO maintenance_events VALUES (?,'schema_upgrade',?,?)",
                    (str(uuid4()), now, canonical_json({"from": 14, "to": 15})),
                )
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise FoundationError(
                        "corrupt_space", "Upgrade failed foreign key verification"
                    )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.execute("PRAGMA foreign_keys=ON")
    return read_space(path)


__all__ = ["upgrade_structures_space"]
