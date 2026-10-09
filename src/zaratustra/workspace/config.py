"""Explicit local installation configuration; paths are never domain data."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(pattern="^[A-Za-z0-9_-]{1,80}$")
    path: Path


class GitDestination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repository: str = Field(pattern="^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    branch: Literal["main"] = "main"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repository}.git"


class LaunchConfig(BaseModel):
    """V1 is read without reinterpretation; V2 names the personal root explicitly."""

    model_config = ConfigDict(extra="allow")
    version: Literal[1, 2]
    actor: str
    space_id: UUID
    space: Path
    workspace: Path
    sqlite_dll: Path
    pi_runtime: Path
    pi_source: Literal["system", "managed"] = "managed"
    node: str = "node"
    provider_profile: Literal["codex-sse", "local-completions"]
    provider_base_url: str
    provider_id: str
    model_id: str
    reserve_units: int = Field(ge=1)
    limit_units: int | None = Field(default=None, ge=1)
    free_conversation_limit_units: int | None = Field(default=None, ge=1)
    context_max_bytes: int | None = Field(default=None, ge=1)
    context_window: int | None = None
    max_tokens: int | None = None
    personal_root: Path | None = None
    runtime_root: Path | None = None
    projects: tuple[Project, ...] = ()
    git: GitDestination | None = None

    @model_validator(mode="after")
    def explicit_roots(self) -> LaunchConfig:
        if self.version == 2:
            if self.personal_root is None or self.runtime_root is None:
                raise ValueError("V2 requires personal_root and runtime_root")
            personal, runtime = self.personal_root.resolve(), self.runtime_root.resolve()
            if runtime.is_relative_to(personal) or personal.is_relative_to(runtime):
                raise ValueError("Runtime and personal workspace must be separate")
            if self.workspace.resolve() != personal:
                raise ValueError("Default workspace must be personal_root")
        names = [project.name.casefold() for project in self.projects]
        if "personal" in names:
            raise ValueError("personal is reserved for the personal workspace")
        roots = [str(project.path.resolve()).casefold() for project in self.projects]
        if len(names) != len(set(names)) or len(roots) != len(set(roots)):
            raise ValueError("Project names and roots must be unique")
        return self

    def project_root(self, name: str | None = None) -> Path:
        if name is None or name == "personal":
            return self.workspace.resolve()
        for project in self.projects:
            if project.name == name:
                return project.path.resolve()
        raise ValueError(f"Project is not registered: {name}")

    def project_name(self, root: Path) -> str:
        resolved = root.resolve()
        if resolved == self.workspace.resolve():
            return "personal"
        for project in self.projects:
            if project.path.resolve() == resolved:
                return project.name
        raise ValueError(f"Resource root is not registered: {resolved}")


def read_config(path: Path) -> LaunchConfig:
    return LaunchConfig.model_validate_json(path.read_bytes())


def write_config(path: Path, config: LaunchConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def migrate_config(
    source: Path,
    destination: Path,
    *,
    personal_root: Path,
    runtime_root: Path,
    projects: tuple[Project, ...] = (),
    git: GitDestination | None = None,
) -> LaunchConfig:
    """Explicit, repeatable config-only migration; never initializes or moves Core."""
    old = read_config(source)
    result = LaunchConfig.model_validate(
        {
            **old.model_dump(),
            "version": 2,
            "personal_root": personal_root.resolve(),
            "workspace": personal_root.resolve(),
            "runtime_root": runtime_root.resolve(),
            "projects": projects,
            "git": git,
        }
    )
    if (personal_root / "src" / "zaratustra" / "release.py").exists():
        raise ValueError("Product source checkout cannot be the personal workspace")
    if destination.exists() and destination.resolve() != source.resolve():
        if read_config(destination) != result:
            raise ValueError("Migration destination contains another configuration")
        return result
    if not personal_root.is_dir() or not runtime_root.is_dir():
        raise ValueError("Choose existing personal and runtime directories")
    write_config(destination, result)
    return result


def register_project(path: Path, project: Project) -> LaunchConfig:
    config = read_config(path)
    if config.version != 2:
        raise ValueError("Explicitly migrate launch configuration to V2 first")
    root = project.path.resolve()
    if not root.is_dir():
        raise ValueError("Choose an existing project directory")
    if root.is_relative_to(config.workspace.resolve()) and root != config.workspace.resolve():
        if (root / ".git").exists():
            raise ValueError("Projects inside the personal workspace cannot contain nested Git")
    if config.runtime_root and root.is_relative_to(config.runtime_root.resolve()):
        raise ValueError("Runtime is not a project")
    prior = next((item for item in config.projects if item.name == project.name), None)
    if prior is not None:
        if prior.path.resolve() != root:
            raise ValueError("Registered name already selects another project")
        return config
    result = LaunchConfig.model_validate(
        {
            **config.model_dump(),
            "projects": (*config.projects, project.model_copy(update={"path": root})),
        }
    )
    write_config(path, result)
    return result


def workspace_info(config: LaunchConfig) -> dict[str, object]:
    return {
        "version": config.version,
        "personal_root": str(config.workspace.resolve()),
        "core": str(config.space.resolve()),
        "runtime": str(config.runtime_root or "legacy"),
        "projects": [item.model_dump(mode="json") for item in config.projects],
        "git": config.git.model_dump(mode="json") if config.git else None,
    }
