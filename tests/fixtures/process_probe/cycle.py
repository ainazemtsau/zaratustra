"""Fictional alternating cycle: only the current persisted phase's mark is needed."""

from uuid import UUID

from zaratustra.core import NextWork, Work

from .runner import Observation, RuleBlocked


class CycleRule:
    def next_work(
        self, work: Work, observation: Observation, work_id: UUID, artifact_id: UUID
    ) -> NextWork:
        if work.executor_requirements == ("probe.cycle/v1:observe",):
            if not observation.observed:
                raise RuleBlocked("Observe phase needs its observation mark")
            next_phase = "record"
        elif work.executor_requirements == ("probe.cycle/v1:record",):
            if not observation.recorded:
                raise RuleBlocked("Record phase needs its recording mark")
            next_phase = "observe"
        else:
            raise RuleBlocked("Work is not bound to a cycle probe v1 phase")
        return NextWork(
            work_id=work_id,
            artifact_id=artifact_id,
            goal=f"Perform the fictional {next_phase} phase",
            expected_result=f"The {next_phase} mark",
            acceptance=(f"The current {next_phase} phase has its own mark",),
            boundaries=work.boundaries,
            budget=work.budget,
            executor_requirements=(f"probe.cycle/v1:{next_phase}",),
            artifact_title=f"Fictional {next_phase} observation",
            authority_scope="work_metadata",
        )
