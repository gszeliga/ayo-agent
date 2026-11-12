"""The phase machine: which transitions exist and the exit criteria code checks.

The model can only propose a transition (`propose_transition`); `missing_for` decides. Each
rejection names what is missing, so the model can act on it: the facts by their model
names (`where`, not `where_`), or one of the codes in `MISSING_DETAILS`.
"""

from dataclasses import dataclass

from ayo_copilot.conversation.case import FIELDS, CaseSnapshot, Phase


@dataclass(frozen=True)
class Target:
    """An allowed transition target and its condition, as told to the model (Spanish)."""

    phase: Phase
    condition: str


TRANSITIONS: dict[Phase, tuple[Target, ...]] = {
    "understand": (
        Target(
            "challenge",
            "cuando los cuatro datos (what, where, since, standard) están registrados.",
        ),
    ),
    "challenge": (Target("analyse", "cuando hay al menos una evidencia (evidence) registrada."),),
    "analyse": (Target("action", "cuando hay una causa validada (validated_cause) registrada."),),
    "action": (
        Target(
            "followup",
            "cuando hay al menos una acción registrada, cada una con responsable y fecha.",
        ),
    ),
    "followup": (
        Target("action", "para reabrir el plan y añadir o cambiar acciones; sin condiciones."),
        Target(
            "closed",
            "cuando hay al menos una acción y ninguna está pendiente; el caso queda cerrado.",
        ),
    ),
    "closed": (),
}

# Short reasons for the model, per missing-item code (English, like the error codes).
MISSING_DETAILS: dict[str, str] = {
    "evidence": "no evidence recorded yet",
    "validated_cause": "no validated cause recorded yet",
    "action": "no action recorded yet",
    "incomplete_actions": "some actions have no owner or due date",
    "pending_actions": "some actions are still pending",
}


def targets(phase: Phase) -> tuple[Phase, ...]:
    """The phases reachable from `phase`, in table order (none from `closed`)."""
    return tuple(target.phase for target in TRANSITIONS[phase])


def describe_targets(phase: Phase) -> str:
    """One line per target, `- <phase>: <condition>`, for the model (the
    `propose_transition` description and the phase prompts' `$exit_conditions`)."""
    return "\n".join(f"- {target.phase}: {target.condition}" for target in TRANSITIONS[phase])


def is_allowed(source: Phase, target: Phase) -> bool:
    return target in targets(source)


def missing_for(snapshot: CaseSnapshot, target: Phase) -> list[str]:
    """What the case still lacks to move from its current phase to `target`; empty when
    the transition can be accepted. The transition itself must be allowed."""
    source = snapshot.case.state
    if not is_allowed(source, target):
        raise ValueError(f"transition {source} -> {target} is not allowed")
    if source == "understand":
        return list(snapshot.case.missing_fields())
    if source == "challenge":
        return [] if snapshot.has_event("evidence") else ["evidence"]
    if source == "analyse":
        return [] if snapshot.has_event("validated_cause") else ["validated_cause"]
    if source == "action":
        if not snapshot.actions:
            return ["action"]
        complete = all(a.owner.strip() and a.due_date is not None for a in snapshot.actions)
        return [] if complete else ["incomplete_actions"]
    # followup
    if target == "action":
        return []
    if not snapshot.actions:
        return ["action"]
    return ["pending_actions"] if any(a.status == "pending" for a in snapshot.actions) else []


def describe_missing(missing: list[str]) -> str:
    """One short sentence for the model."""
    facts = [item for item in missing if item in FIELDS]
    parts = [f"missing facts: {', '.join(facts)}"] if facts else []
    parts += [MISSING_DETAILS[item] for item in missing if item not in FIELDS]
    return "; ".join(parts)
