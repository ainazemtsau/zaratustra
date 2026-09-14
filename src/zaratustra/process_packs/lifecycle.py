"""Local trusted registrations select exact code; they never write or grant rights."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from zaratustra.core import MutationRequest, NextWork, PackReference, Work

from .capability_models import CapabilityReader


class PackError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class PackRule(Protocol):
    def next_work(
        self,
        work: Work,
        accepted_result: bytes,
        work_id: UUID,
        artifact_id: UUID,
    ) -> NextWork | None: ...


@dataclass(frozen=True)
class PackRegistration:
    reference: PackReference
    rule: PackRule
    reader: CapabilityReader | None = None

    def __post_init__(self) -> None:
        reference = PackReference.model_validate(self.reference.model_dump())
        object.__setattr__(self, "reference", reference)
        if not callable(getattr(self.rule, "next_work", None)):
            raise PackError("invalid_pack", "Registration needs a callable rule adapter")
        if self.reader is not None and not callable(getattr(self.reader, "describe", None)):
            raise PackError("invalid_pack", "Read adapter needs describe")


@dataclass(frozen=True)
class PackRegistry:
    registrations: tuple[PackRegistration, ...] = ()

    def __post_init__(self) -> None:
        # Copy the container; callers cannot mutate a registered set through a list.
        object.__setattr__(self, "registrations", tuple(self.registrations))
        coordinates = [self._coordinate(row.reference) for row in self.registrations]
        if len(coordinates) != len(set(coordinates)):
            raise PackError("registration_collision", "A pack/version has more than one adapter")

    @staticmethod
    def _coordinate(reference: PackReference) -> tuple[str, str]:
        return reference.pack_id, reference.pack_version

    def register(self, registration: PackRegistration) -> PackRegistry:
        for current in self.registrations:
            if self._coordinate(current.reference) == self._coordinate(registration.reference):
                if (
                    current.reference == registration.reference
                    and current.rule is registration.rule
                    and current.reader is registration.reader
                ):
                    return self
                raise PackError("registration_collision", "An existing pack/version cannot change")
        return PackRegistry((*self.registrations, registration))

    def resolve(self, reference: PackReference) -> PackRegistration:
        reference = PackReference.model_validate(reference.model_dump())
        for registration in self.registrations:
            if self._coordinate(registration.reference) != self._coordinate(reference):
                continue
            if registration.reference != reference or (
                reference.contract_version,
                reference.state_version,
            ) != (1, 1):
                raise PackError("incompatible_pack", "Exact type, contract1 and state1 required")
            return registration
        raise PackError("missing_pack", "The exact saved pack/version is not registered")


def binding_request(
    registry: PackRegistry,
    reference: PackReference,
    *,
    operation_id: UUID,
    workspace_id: UUID,
    work_id: UUID,
    expected_revision: int,
    provenance: str,
) -> MutationRequest:
    """Validate installation and propose a bind; Core still requires exact authorization."""
    registered = registry.resolve(reference)
    return MutationRequest(
        version=5,
        operation="bind_pack",
        operation_id=operation_id,
        workspace_id=workspace_id,
        work_id=work_id,
        expected_revision=expected_revision,
        provenance=provenance,
        pack_binding=registered.reference,
    )
