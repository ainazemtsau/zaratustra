"""Pinned selections and host-independent active-context compilation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid5

from zaratustra.journal import Change, JournalError, Reference, Revision, Store, header, resolve

from .catalog import Catalog
from .models import BINDING_TYPE, SKILL_TYPE, Binding, Configuration, Skill


class Skills:
    def __init__(self, local: Store, stores: list[Store], catalog: Catalog) -> None:
        self.local, self.stores, self.catalog = local, stores, catalog
        self.identity = uuid5(local.scope.id, "skill-bindings-v1")

    def configuration(self, revision: int | None = None) -> tuple[int, Configuration]:
        if revision == 0 or self.identity not in self.local.records:
            return 0, Configuration()
        record = self.local.get(self.identity, revision)
        if record.type_name != BINDING_TYPE:
            raise JournalError("type_conflict", "Configuration identity is occupied")
        return record.revision, Configuration.model_validate(record.payload)

    def read(self, reference: Reference) -> tuple[Revision, Skill]:
        result = resolve(self.stores, reference)
        if result["status"] != "available":
            raise JournalError("scope_unavailable", "Skill is outside the selected scopes")
        if reference.kind != "record" or result["record"]["type_name"] != SKILL_TYPE:
            raise JournalError("invalid_skill", "Select an exact skill record revision")
        record = Revision.model_validate(result["record"])
        return record, Skill.model_validate(record.payload)

    def change(
        self,
        *,
        slot: str,
        reference: Reference | None,
        settings: dict[str, Any],
        expected: int,
        operation_id: UUID,
        reason: str,
        authority_source: str | None,
    ) -> dict[str, Any]:
        current, _ = self.configuration()
        replay = operation_id in self.local.operations
        if not replay and current != expected:
            raise JournalError(
                "revision_conflict", "Read context before changing its configuration"
            )
        _, base = self.configuration(expected)
        bindings = [binding for binding in base.bindings if binding.slot != slot]
        if reference is None:
            if len(bindings) == len(base.bindings):
                raise JournalError("not_connected", "No binding in this slot")
        else:
            if not replay:
                _, skill = self.read(reference)
                family = self.lineage(reference)
                if any(family.intersection(self.lineage(binding.skill)) for binding in bindings):
                    raise JournalError(
                        "ambiguous_replacement", "Replace the original slot explicitly"
                    )
                assessment = self.catalog.assess(skill, settings, selected=True)
                if not assessment["ready_by_configuration"]:
                    raise JournalError(
                        "skill_not_ready", json.dumps(assessment, ensure_ascii=False)
                    )
            bindings.append(Binding(slot=slot, skill=reference, settings=settings))
        configuration = Configuration(bindings=tuple(bindings))
        result = self.local.write(
            Change(
                operation_id=operation_id,
                action="revise" if expected else "create",
                record_id=self.identity,
                expected_revision=expected or None,
                type_name=BINDING_TYPE,
                title="Process skill configuration",
                payload=configuration.model_dump(mode="json"),
                links=(),
                reason=reason,
                authority_source=authority_source,
            )
        )
        record = Revision.model_validate(result["record"])
        result["record"] = header(record)
        result["configuration_revision"] = record.revision
        return result

    def lineage(self, reference: Reference) -> set[tuple[str, UUID, UUID]]:
        result: set[tuple[str, UUID, UUID]] = set()
        current: Reference | None = reference
        while current is not None:
            identity = (current.scope.kind, current.scope.id, current.id)
            if identity in result:
                break
            result.add(identity)
            if len(result) > 32:
                raise JournalError("origin_depth", "Skill ancestry exceeds 32 records")
            if not any(store.scope == current.scope for store in self.stores):
                break
            _, skill = self.read(current)
            current = skill.derived_from
        return result

    def compile(self, process: dict[str, Any], loaded: tuple[str, ...]) -> dict[str, Any]:
        revision, config = self.configuration()
        selected = []
        for binding in config.bindings:
            item: dict[str, Any] = {
                "slot": binding.slot,
                "reference": binding.skill.model_dump(mode="json"),
            }
            try:
                record, skill = self.read(binding.skill)
                assessment = self.catalog.assess(skill, binding.settings, selected=True)
                item.update(
                    name=skill.name,
                    description=skill.description,
                    readiness=assessment,
                    links=[r.model_dump(mode="json") for r in record.links],
                )
                if binding.slot in loaded and assessment["ready_by_configuration"]:
                    markdown = skill.markdown()
                    item.update(
                        path=skill.name + "/SKILL.md",
                        markdown=markdown,
                        sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    )
            except JournalError as error:
                item["readiness"] = {
                    "ready_by_configuration": False,
                    "reasons": [{"status": error.code}],
                }
            selected.append(item)
        # Body loading does not change prepared-action identity. Revisions are immutable.
        signature = {
            "process_id": str(self.local.scope.id),
            "configuration_revision": revision,
            "selected": [
                {k: v for k, v in item.items() if k not in ("markdown", "sha256", "path")}
                for item in selected
            ],
        }
        stamp = hashlib.sha256(
            json.dumps(signature, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return {
            "process": process,
            "configuration_record": str(self.identity),
            "configuration_revision": revision,
            "stamp": stamp,
            "skills": selected,
            "state_revision": self.local.query.expected_revision,
            "capabilities": self.catalog.inventory(),
        }

    def load(self, slot: str) -> dict[str, Any]:
        _, config = self.configuration()
        binding = next((b for b in config.bindings if b.slot == slot), None)
        if binding is None:
            raise JournalError("not_connected", "Skill is not selected in this Process")
        record, skill = self.read(binding.skill)
        assessment = self.catalog.assess(skill, binding.settings, selected=True)
        if not assessment["ready_by_configuration"]:
            raise JournalError("skill_not_ready", json.dumps(assessment, ensure_ascii=False))
        return {
            "slot": slot,
            "reference": record.reference().model_dump(mode="json"),
            "path": skill.name + "/SKILL.md",
            "markdown": skill.markdown(),
            "readiness": assessment,
        }

    def available(self, offset: int, limit: int) -> dict[str, Any]:
        _, config = self.configuration()
        rows = [r for store in self.stores for r in store.current() if r.type_name == SKILL_TYPE]
        skills = []
        for row in rows[offset : offset + limit]:
            skill = Skill.model_validate(row.payload)
            bindings = [
                b for b in config.bindings if b.skill.scope == row.scope and b.skill.id == row.id
            ]
            selected = next((b for b in bindings if b.skill.revision == row.revision), None)
            skills.append(
                {
                    "reference": row.reference().model_dump(mode="json"),
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": {
                        k: v.model_dump(mode="json") for k, v in skill.parameters.items()
                    },
                    "selected_versions": [b.skill.revision for b in bindings],
                    "readiness": self.catalog.assess(
                        skill, selected.settings if selected else {}, selected=selected is not None
                    ),
                }
            )
        return {
            "inventory": self.catalog.inventory(),
            "skills": skills,
            "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
        }
