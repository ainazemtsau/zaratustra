"""Fictional batch gate: every independent mark is required before continuation."""

from uuid import UUID

from zaratustra.core import NextWork, Work

from .runner import Observation, RuleBlocked


class BatchRule:
    def next_work(
        self, work: Work, observation: Observation, work_id: UUID, artifact_id: UUID
    ) -> NextWork:
        if work.executor_requirements != ("probe.batch/v1",):
            raise RuleBlocked("Work is not bound to batch probe v1")
        if not (observation.observed and observation.recorded):
            raise RuleBlocked("Batch requires both observed and recorded")
        return NextWork(
            work_id=work_id,
            artifact_id=artifact_id,
            goal="Inspect the next fictional batch",
            expected_result="Both independent marks",
            acceptance=("Observation and recording marks are both present",),
            boundaries=work.boundaries,
            budget=work.budget,
            executor_requirements=("probe.batch/v1",),
            artifact_title="Next fictional batch observation",
            authority_scope="work_metadata",
        )
