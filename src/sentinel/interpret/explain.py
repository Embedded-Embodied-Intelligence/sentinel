"""Explanations of decisions, role 3 of the interpretation layer (spec section 10.4; RQ5).

`render_record` writes the `DecisionRecord` of a deliberation that passed the needs gate as the
English text an explanation call is given: the day, deadline, target and budget, NOOP's need,
every candidate with a plain description, its statistics and where it left the comparison, and
the choice with its runner-up and deciding component. The LLM answers in the schema
`Explanation`: a summary of at most 80 words for a project manager and the facts it cites.
`check` measures faithfulness against the record (spec section 10.4): every cited fact equals the
record's value (numbers within the rounding of the value written; probabilities and the overrun
as fractions or percentages), the chosen action is cited, the deciding component is cited and
right, and every number written in digits in the summary matches a number of the rendered record
within its rounding, else it counts as a hallucinated number.
"""

import math
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError

from sentinel.agent.decide import CandidateRecord, DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.interpret.team import plural, weekday_name
from sentinel.llm import LlmClient, LlmResponse, Message, load_prompt
from sentinel.policies.base import Overtime, Subst
from sentinel.simulation.state import Observation
from sentinel.wbs.narrate import role_names

EXPLAIN_PROMPT = "explain"  # system prompt, prompts/explain.<version>.txt
MAX_WORDS = 80
FactKind = Literal[
    "chosen_action",
    "p_on_time",
    "tardiness_days",
    "budget_overrun",
    "alternative",
    "alternative_p_on_time",
    "deciding_component",
]
FACT_KINDS: tuple[FactKind, ...] = (
    "chosen_action",
    "p_on_time",
    "tardiness_days",
    "budget_overrun",
    "alternative",
    "alternative_p_on_time",
    "deciding_component",
)
# Numbers written in digits, with an optional percent sign or word ("42 %", "0.42", "3").
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(\s?(?:%|percent\b|per cent\b))?")


class CitedFact(BaseModel):
    """A fact an explanation uses: its kind and its value as written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FactKind
    value: str | float


class Explanation(BaseModel):
    """The output schema of an explanation call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    cited_facts: tuple[CitedFact, ...]


@dataclass(frozen=True)
class RenderedRecord:
    """A record as the LLM sees it and the numbers its text shows."""

    text: str
    values: tuple[float, ...]


def describe_candidate(candidate: CandidateRecord, observation: Observation) -> str:
    """A plain description of a candidate's action for a project manager."""
    roles = role_names(observation.instance)
    plan = {
        "shift": "re-time the unstarted activities in their current order",
        "reseq": "re-sequence the unstarted activities",
    }
    parts: list[str] = []
    for op in candidate.decision.operations:
        match op:
            case Subst(activity=j, workers=workers):
                parts.append(
                    f"replace {len(workers)} absent crew {plural('member', len(workers))} of "
                    f"activity {j}"
                )
            case Overtime(role=k, workers=u, days=h):
                parts.append(f"hire {u} temporary {plural(roles[k], u)} for {h} days")
            case _:
                if op.kind in plan:
                    parts.append(plan[op.kind])
                elif op.kind == "descope":
                    parts.append("remove an optional activity")
    if candidate.kind in ("reseq_m", "subst_all_reseq_m", "ot_reseq_m", "proposal_reseq_m"):
        parts[-1] = "re-sequence for the shortest schedule"
    elif candidate.kind in ("reseq_s", "proposal_reseq_s"):
        parts[-1] = "re-sequence with the smallest change of the plan"
    return ", then ".join(parts) if parts else "keep the plan"


def render_record(
    record: DecisionRecord, observation: Observation, params: SentinelParams
) -> RenderedRecord:
    """The record as English text (module docstring) and its numbers."""
    t, deadline, budget, needs = (
        observation.day,
        observation.deadline,
        observation.budget,
        record.needs,
    )
    if deadline is None or budget is None or needs is None:
        raise ValueError("an explanation needs a deadline, a budget and the needs of NOOP")
    lines = [
        f"Decision of day {t} ({weekday_name(t)}). Deadline: day {deadline}; target: P(on time) "
        f"at least {params.theta_d:.2f}; budget {budget:.1f}.",
        f"Without action, P(on time) is {needs.p_on_time:.2f} on {needs.rollouts} simulated "
        "futures.",
        "",
        "Candidates in candidate order (P(on time), expected tardiness in days, expected budget "
        "overrun as a fraction of the budget, plan instability in days, approval level):",
    ]
    if not record.candidates:
        lines.append(
            f'- "{record.chosen}" (keep the plan): {needs.p_on_time:.2f}; chosen, the only valid '
            "candidate"
        )
    for c in record.candidates:
        if c.label == record.chosen:
            fate = "chosen"
        elif c.dropped:
            fate = f"dropped early as clearly worse, on {c.rollouts} futures"
        elif c.eliminated is None:
            fate = "tied with the chosen action to the end"
        else:
            fate = f"left the comparison at {c.eliminated}"
        lines.append(
            f'- "{c.label}" ({describe_candidate(c, observation)}): {c.p_on_time:.2f}, '
            f"{c.tardiness:.2f}, {c.overrun:.3f}, {c.deviation:.2f}, level {c.level}; {fate}"
        )
    runner = "none" if record.runner_up is None else f'"{record.runner_up}"'
    lines += [
        "",
        f'Chosen: "{record.chosen}". Runner-up: {runner}. Deciding component: {record.reason}.',
    ]
    text = "\n".join(lines)
    values = tuple(float(m.group(1)) for m in _NUMBER.finditer(text))
    return RenderedRecord(text, values)


@dataclass(frozen=True)
class FactCheck:
    """A cited fact and whether it equals the record's value."""

    kind: str
    correct: bool


@dataclass(frozen=True)
class Faithfulness:
    """The checks of spec section 10.4 on one answer."""

    valid: bool
    facts: tuple[FactCheck, ...]
    chosen_named: bool
    component_right: bool
    numbers: int
    hallucinated: int
    words: int

    @property
    def fully_faithful(self) -> bool:
        return (
            self.valid
            and all(fact.correct for fact in self.facts)
            and self.chosen_named
            and self.component_right
            and self.hallucinated == 0
        )


def _plain(text: str) -> str:
    return re.sub(r"[\s_\"'`]+", " ", text).strip().casefold()


def _close(written: str, value: float, percent: bool, either: bool) -> bool:
    """Whether a number as written equals `value` within the rounding of its decimals: as a
    percentage of it if `percent`, also as one if `either` (fractions such as probabilities)."""
    decimals = len(written.partition(".")[2])
    number = float(written)
    half = 0.5 * 10.0**-decimals + 1e-9
    targets = [100 * value] if percent else ([value, 100 * value] if either else [value])
    return any(abs(number - target) <= half for target in targets)


def _number_text(value: str | float) -> tuple[str, bool] | None:
    """The digits of a cited numeric value and whether it is a percentage, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if not math.isfinite(value):
            return None
        return (repr(float(value)) if isinstance(value, float) else str(value)), False
    found = _NUMBER.search(value)
    if found is None:
        return None
    return found.group(1), found.group(2) is not None


def check(data: object, record: DecisionRecord, rendered: RenderedRecord) -> Faithfulness:
    """The faithfulness of a parsed answer to `record` (spec section 10.4)."""
    summary = data.get("summary") if isinstance(data, dict) else None
    text = summary if isinstance(summary, str) else ""
    numbers = [(m.group(1), m.group(2) is not None) for m in _NUMBER.finditer(text)]
    hallucinated = sum(
        not any(_close(digits, v, percent, False) for v in rendered.values)
        for digits, percent in numbers
    )
    try:
        explanation = Explanation.model_validate(data)
    except ValidationError:
        return Faithfulness(False, (), False, False, len(numbers), hallucinated, len(text.split()))
    by_label = {c.label: c for c in record.candidates}
    chosen = _Stats.of(by_label.get(record.chosen), record)
    runner = None if record.runner_up is None else _Stats.of(by_label.get(record.runner_up), None)
    facts = tuple(
        FactCheck(fact.kind, _fact_correct(fact, record, chosen, runner))
        for fact in explanation.cited_facts
    )
    return Faithfulness(
        valid=True,
        facts=facts,
        chosen_named=any(f.correct and f.kind == "chosen_action" for f in facts),
        component_right=any(f.correct and f.kind == "deciding_component" for f in facts),
        numbers=len(numbers),
        hallucinated=hallucinated,
        words=len(text.split()),
    )


@dataclass(frozen=True)
class _Stats:
    """What a record tells of a candidate: p, and T and o where it has them (a record without
    candidate statistics, where only NOOP was valid, has the p of the needs only)."""

    p_on_time: float
    tardiness: float | None
    overrun: float | None

    @classmethod
    def of(
        cls, candidate: CandidateRecord | None, record: DecisionRecord | None
    ) -> "_Stats | None":
        if candidate is not None:
            return cls(candidate.p_on_time, candidate.tardiness, candidate.overrun)
        if record is not None and record.needs is not None and not record.candidates:
            return cls(record.needs.p_on_time, None, None)
        return None


def _fact_correct(
    fact: CitedFact, record: DecisionRecord, chosen: _Stats | None, runner: _Stats | None
) -> bool:
    match fact.kind:
        case "chosen_action":
            return isinstance(fact.value, str) and _plain(fact.value) == _plain(record.chosen)
        case "alternative":
            return (
                record.runner_up is not None
                and isinstance(fact.value, str)
                and _plain(fact.value) == _plain(record.runner_up)
            )
        case "deciding_component":
            return isinstance(fact.value, str) and _plain(fact.value) == _plain(record.reason)
    target = {
        "p_on_time": (chosen, "p_on_time", True),
        "tardiness_days": (chosen, "tardiness", False),
        "budget_overrun": (chosen, "overrun", True),
        "alternative_p_on_time": (runner, "p_on_time", True),
    }[fact.kind]
    stats, attribute, either = target
    written = _number_text(fact.value)
    value = None if stats is None else getattr(stats, attribute)
    if value is None or written is None:
        return False
    digits, percent = written
    return _close(digits, float(value), percent, either)


class ExplainSettings(BaseModel):
    """Prompt version and decoding parameters of an explanation call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(default="v1", min_length=1)
    max_tokens: PositiveInt
    temperature: float = Field(default=0.0, ge=0, allow_inf_nan=False)


def explain_messages(rendered: RenderedRecord, version: str) -> list[Message]:
    """The conversation of an explanation call: the system prompt and the rendered record."""
    prompt = load_prompt(EXPLAIN_PROMPT, version)
    return [
        Message(role="system", content=prompt.text),
        Message(role="user", content=rendered.text),
    ]


def explain(
    client: LlmClient, rendered: RenderedRecord, *, seed: int, settings: ExplainSettings
) -> LlmResponse[Explanation]:
    """One explanation call on a rendered record."""
    return client.complete(
        explain_messages(rendered, settings.prompt_version),
        schema=Explanation,
        temperature=settings.temperature,
        seed=seed,
        max_tokens=settings.max_tokens,
    )
