"""Read-only dependency checks against the installed program's real registrations."""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata
from typing import Any

from zaratustra.journal import Registry

from .models import Dependency, Skill


class Catalog:
    def __init__(
        self,
        commands: tuple[str, ...],
        registry: Registry,
        resource_version: Callable[[str], str] = metadata.version,
    ) -> None:
        self.commands = commands
        self.registry = registry
        self.resource_version = resource_version

    def inventory(self) -> dict[str, Any]:
        return {
            "commands": [{"name": name, "version": "1"} for name in self.commands],
            "types": [
                {"name": row["type"], "version": str(row["schema_version"])}
                for row in self.registry.describe()
            ],
            "resources": [self.installed_resource("zaratustra")],
            "external_access": "not_checked; configuration is not an external operation proof",
        }

    def installed_resource(self, name: str) -> dict[str, Any]:
        try:
            return {"name": name, "version": self.resource_version(name), "status": "available"}
        except metadata.PackageNotFoundError:
            return {"name": name, "status": "not_found"}
        except (OSError, ValueError):
            return {"name": name, "status": "unknown"}

    def check(self, dependency: Dependency) -> dict[str, Any]:
        available: list[str] = []
        detail: str | None = None
        try:
            if dependency.kind == "command":
                available = ["1"] if dependency.name in self.commands else []
            elif dependency.kind == "type":
                available = [
                    str(row["schema_version"])
                    for row in self.registry.describe()
                    if row["type"] == dependency.name
                ]
            else:
                available = [self.resource_version(dependency.name)]
        except metadata.PackageNotFoundError:
            pass
        except (OSError, ValueError):
            detail = "Installed resource metadata could not be checked"
        status = "unknown" if detail else "not_found" if not available else "available"
        if status == "available" and dependency.version and dependency.version not in available:
            status = "incompatible_version"
        return {
            "dependency": dependency.model_dump(mode="json"),
            "status": status,
            "available_versions": available,
            "detail": detail,
        }

    def assess(self, skill: Skill, settings: dict[str, Any], *, selected: bool) -> dict[str, Any]:
        checks = [self.check(dependency) for dependency in skill.dependencies]
        reasons: list[dict[str, Any]] = []
        resolved: dict[str, Any] = {}
        for name in settings:
            if name not in skill.parameters:
                reasons.append({"status": "invalid_setting", "parameter": name})
        for name, parameter in skill.parameters.items():
            value = settings.get(name, parameter.default)
            if value is None:
                if parameter.required:
                    reasons.append({"status": "needs_configuration", "parameter": name})
            elif not parameter.accepts(value):
                reasons.append({"status": "invalid_setting", "parameter": name})
            else:
                resolved[name] = value
        reasons.extend(
            {"status": check["status"], "dependency": check["dependency"]}
            for check in checks
            if check["status"] != "available" and check["dependency"]["required"]
        )
        ready = not reasons
        if not selected:
            reasons.append({"status": "not_connected"})
        return {
            "ready_by_configuration": ready,
            "selected": selected,
            "reasons": reasons,
            "dependencies": checks,
            "settings": resolved,
            "external_access": "not_checked",
        }
