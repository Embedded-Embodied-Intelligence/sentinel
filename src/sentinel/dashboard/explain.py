"""Explanations in the cockpit's decision log (WP8; spec section 10.4, ADR-0021).

`template_explanation` writes a deliberation's explanation from its `DecisionRecord` alone, in
English or Polish, in the answer schema of role 3 (`Explanation`): every number in it is a value
of the record as `render_record` shows it (probabilities as whole percentages of their two-decimal
value, tardiness to one decimal of its two-decimal value, the overrun as a percentage of its
three-decimal value), and it cites the facts it uses, so the faithfulness check of spec section
10.4 applies to it as to an LLM answer. With `--explain ollama` or `openrouter` the deliberations
that passed the needs gate are explained by the LLM through the record/replay cache
(`LlmExplainer`), each with its faithfulness check; the others keep the template.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sentinel.agent.decide import CandidateRecord, DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.experiments.explanation_study import ExplanationStudyConfig
from sentinel.experiments.rq5_common import FakeBackend
from sentinel.experiments.runs import derive_seed, load_toml
from sentinel.experiments.wbs_study import make_client
from sentinel.interpret.explain import (
    CitedFact,
    Explanation,
    Faithfulness,
    check,
    explain,
    render_record,
)
from sentinel.llm import DEFAULT_CACHE_DIR, LlmCache, LlmClient
from sentinel.simulation.state import Observation

Language = Literal["en", "pl"]
EXPLAIN_CONFIG = Path("configs/wp6_rq5_explanations.toml")
CACHE_DIR = DEFAULT_CACHE_DIR / "dashboard"
LLM_BACKENDS = ("ollama", "openrouter")

_DESCRIPTIONS: Mapping[Language, Mapping[str, str]] = {
    "en": {
        "noop": "keep the plan",
        "shift": "re-time the unstarted activities in their order",
        "reseq_m": "re-sequence for the shortest schedule",
        "reseq_s": "re-sequence with the smallest plan change",
        "subst": "replace absent crew members",
        "subst_all": "replace every absent crew member",
        "subst_all_reseq_m": "replace absent crew members, then re-sequence",
        "ot_reseq_m": "hire temporary workers, then re-sequence",
        "descope": "remove an optional activity",
        "proposal": "a proposed action",
    },
    "pl": {
        "noop": "zachowaj plan",
        "shift": "przesuń nierozpoczęte zadania z zachowaniem kolejności",
        "reseq_m": "przeplanuj na najkrótszy harmonogram",
        "reseq_s": "przeplanuj z najmniejszą zmianą planu",
        "subst": "zastąp nieobecnych członków zespołu",
        "subst_all": "zastąp wszystkich nieobecnych członków zespołów",
        "subst_all_reseq_m": "zastąp nieobecnych, potem przeplanuj",
        "ot_reseq_m": "zatrudnij pracowników tymczasowych, potem przeplanuj",
        "descope": "usuń zadanie opcjonalne",
        "proposal": "działanie zaproponowane",
    },
}
_DECIDERS: Mapping[Language, Mapping[str, str]] = {
    "en": {
        "on_time": "P(on time) decided",
        "tardiness": "the expected tardiness decided",
        "scope": "the scope loss decided",
        "budget": "the budget overrun decided",
        "stability": "plan stability decided (fewer changed starts)",
        "level": "the approval level decided",
        "order": "they tie on every component, so the candidate order decided",
        "racing": "the others were clearly worse on the first futures and were dropped (racing)",
        "utility": "the scalarised utility decided",
    },
    "pl": {
        "on_time": "rozstrzygnęło P(na czas)",
        "tardiness": "rozstrzygnęło oczekiwane opóźnienie",
        "scope": "rozstrzygnęła utrata zakresu",
        "budget": "rozstrzygnęło przekroczenie budżetu",
        "stability": "rozstrzygnęła stabilność planu (mniej zmienionych terminów)",
        "level": "rozstrzygnął poziom uprawnień",
        "order": "remisują we wszystkich składowych, więc rozstrzygnęła kolejność kandydatów",
        "racing": "pozostałe były wyraźnie gorsze w pierwszych scenariuszach i odpadły (wyścig)",
        "utility": "rozstrzygnęła skalaryzowana użyteczność",
    },
}
_GATES: Mapping[Language, Mapping[str, str]] = {
    "en": {
        "auto": "It is applied at once.",
        "deferred": "It needs approval but is not urgent yet, so it is deferred; NOOP applies "
        "today.",
        "escalated": "It needs approval and goes to the project manager; NOOP applies until then.",
    },
    "pl": {
        "auto": "Działanie jest stosowane od razu.",
        "deferred": "Wymaga zatwierdzenia, ale nie jest jeszcze pilne, więc zostaje odroczone; "
        "dziś obowiązuje NOOP.",
        "escalated": "Wymaga zatwierdzenia i trafia do kierownika projektu; do tego czasu "
        "obowiązuje NOOP.",
    },
}
_TEXTS: Mapping[Language, Mapping[str, str]] = {
    "en": {
        "met": "Day {day}: no need to act. Without action P(on time) is {p} % on {n} simulated "
        "futures, close enough to the target, and the budget holds, so Sentinel keeps the plan.",
        "only": "Day {day}: without action P(on time) is {p} % on {n} simulated futures, "
        "{need}, but no other action is valid, so Sentinel keeps the plan.",
        "chosen": "Day {day}: without action P(on time) is {p0} %, {need}. Sentinel chose "
        "{chosen} ({description}): P(on time) {p} %, expected tardiness {t} days, budget overrun "
        "{o} %.",
        "kept": "Day {day}: without action P(on time) is {p} %, {need}, with expected tardiness "
        "{t} days and budget overrun {o} %. Sentinel keeps the plan (NOOP).",
        "runner": "The runner-up {runner} reaches P(on time) {p} %; {decider}.",
        "alone": "No other candidate was left; {decider}.",
        "below": "below the target",
        "budget": "on target, but the budget is at risk",
        "discarded": "The action approved for today was no longer valid, so Sentinel "
        "deliberated again. ",
        "approved": "Day {day}: the project manager approved {chosen}; it was planned again on "
        "this day and applied.",
    },
    "pl": {
        "met": "Dzień {day}: działanie nie jest potrzebne. Bez działania P(na czas) wynosi {p} % "
        "w {n} symulowanych scenariuszach, blisko celu, a budżet jest dotrzymany, więc Sentinel "
        "zachowuje plan.",
        "only": "Dzień {day}: bez działania P(na czas) wynosi {p} % w {n} symulowanych "
        "scenariuszach, {need}, ale żadne inne działanie nie jest wykonalne, więc Sentinel "
        "zachowuje plan.",
        "chosen": "Dzień {day}: bez działania P(na czas) wynosi {p0} %, {need}. Sentinel wybrał "
        "{chosen} ({description}): P(na czas) {p} %, oczekiwane opóźnienie {t} dnia, "
        "przekroczenie budżetu {o} %.",
        "kept": "Dzień {day}: bez działania P(na czas) wynosi {p} %, {need}, przy oczekiwanym "
        "opóźnieniu {t} dnia i przekroczeniu budżetu {o} %. Sentinel zachowuje plan (NOOP).",
        "runner": "Drugi najlepszy, {runner}, osiąga P(na czas) {p} %; {decider}.",
        "alone": "Nie pozostał inny kandydat; {decider}.",
        "below": "poniżej celu",
        "budget": "zgodnie z celem, ale budżet jest zagrożony",
        "discarded": "Działanie zatwierdzone na dziś nie było już wykonalne, więc Sentinel "
        "rozważył sytuację od nowa. ",
        "approved": "Dzień {day}: kierownik projektu zatwierdził {chosen}; działanie "
        "zaplanowano ponownie tego dnia i zastosowano.",
    },
}


def _percent(p: float) -> str:
    """A probability as a whole percentage of its two-decimal value (as `render_record`)."""
    return str(round(float(f"{p:.2f}") * 100))


def _decimal(text: str, language: Language) -> str:
    return text.replace(".", ",") if language == "pl" else text


def template_explanation(record: DecisionRecord, language: Language = "en") -> Explanation:
    """The explanation of a deliberation or an approval day built from its record only."""
    texts = _TEXTS[language]
    chosen = record.chosen
    if record.reason == "approved":
        summary = texts["approved"].format(day=record.day, chosen=chosen)
        cited = (CitedFact(kind="chosen_action", value=chosen),)
        return Explanation(summary=summary, cited_facts=cited)
    needs = record.needs
    if needs is None:
        raise ValueError("a deliberation record without the needs of NOOP")
    facts = [CitedFact(kind="chosen_action", value=chosen)]
    need = texts["below"] if needs.deadline > 0 else texts["budget"]
    by_label = {c.label: c for c in record.candidates}
    best = by_label.get(chosen)
    if best is None:
        key = "met" if record.reason == "needs_met" else "only"
        p = needs.p_on_time
        summary = texts[key].format(day=record.day, p=_percent(p), n=needs.rollouts, need=need)
        facts.append(CitedFact(kind="p_on_time", value=f"{p:.2f}"))
    else:
        noop = by_label.get("NOOP")
        summary = texts["kept" if chosen == "NOOP" else "chosen"].format(
            day=record.day,
            p0=_percent(needs.p_on_time if noop is None else noop.p_on_time),
            need=need,
            chosen=chosen,
            description=_describe(best, language),
            p=_percent(best.p_on_time),
            t=_decimal(f"{float(f'{best.tardiness:.2f}'):.1f}", language),
            o=_decimal(f"{float(f'{best.overrun:.3f}') * 100:.1f}", language),
        )
        facts += [
            CitedFact(kind="p_on_time", value=f"{best.p_on_time:.2f}"),
            CitedFact(kind="tardiness_days", value=f"{best.tardiness:.2f}"),
            CitedFact(kind="budget_overrun", value=f"{best.overrun:.3f}"),
        ]
        decider = _DECIDERS[language].get(record.reason, record.reason)
        runner = None if record.runner_up is None else by_label.get(record.runner_up)
        if runner is None:
            summary += " " + texts["alone"].format(decider=decider)
        else:
            summary += " " + texts["runner"].format(
                runner=runner.label, p=_percent(runner.p_on_time), decider=decider
            )
            facts += [
                CitedFact(kind="alternative", value=runner.label),
                CitedFact(kind="alternative_p_on_time", value=f"{runner.p_on_time:.2f}"),
            ]
        if record.gate is not None:
            summary += " " + _GATES[language][record.gate]
    facts.append(CitedFact(kind="deciding_component", value=record.reason))
    if record.discarded is not None:
        summary = texts["discarded"] + summary
    return Explanation(summary=summary, cited_facts=tuple(facts))


def _describe(candidate: CandidateRecord, language: Language) -> str:
    kind = "proposal" if candidate.kind.startswith("proposal") else candidate.kind
    return _DESCRIPTIONS[language][kind]


def checkable(summary: str, language: Language) -> str:
    """The summary as the faithfulness check reads numbers: decimal commas as points."""
    return re.sub(r"(\d),(\d)", r"\1.\2", summary) if language == "pl" else summary


@dataclass(frozen=True)
class Shown:
    """The explanation shown in a log row: its text, where it came from, and for an LLM answer
    the model and its faithfulness check (spec section 10.4), or why there is no text."""

    text: str
    source: Literal["template", "llm"]
    model: str | None = None
    faithfulness: Faithfulness | None = None
    error: str | None = None


def shown_template(record: DecisionRecord, language: Language) -> Shown:
    return Shown(template_explanation(record, language).summary, "template")


def explained_by_llm(record: DecisionRecord) -> bool:
    """Whether an LLM explains the record: a deliberation that passed the needs gate (10.4)."""
    return record.deliberated and record.needs is not None and not record.needs.met


class LlmExplainer:
    """LLM explanations through the record/replay cache: the backend and the settings of the
    RQ5 explanation study (`configs/wp6_rq5_explanations.toml`), the working cache
    `data/llm_cache/dashboard/<backend>.jsonl` with full records (the worlds are synthetic) in
    `auto` mode, and one seed per (world, policy, day). `client` replaces the configured one
    (tests)."""

    def __init__(
        self,
        backend: str,
        *,
        config_path: Path = EXPLAIN_CONFIG,
        cache_dir: Path = CACHE_DIR,
        client: LlmClient | None = None,
    ) -> None:
        config = ExplanationStudyConfig.model_validate(load_toml(config_path))
        if backend not in config.backend:
            known = sorted(config.backend)
            raise ValueError(f"unknown backend {backend!r}; the config has {known}")
        self.backend = backend
        self.settings = config.explanation
        self.base_seed = config.base_seed
        self.cache_file = cache_dir / f"{backend}.jsonl"
        if client is None:
            cache = LlmCache(self.cache_file, store_prompts=config.store_prompts)
            settings = config.backend[backend]
            if isinstance(settings, FakeBackend):
                raise ValueError("the fake backend scripts study answers; use a real backend")
            client = make_client(backend, settings, cache, "auto")
        self.client = client
        self.model = getattr(client, "model", config.backend[backend].model)

    def __call__(
        self, record: DecisionRecord, observation: Observation, params: SentinelParams, *keys: str
    ) -> Shown:
        rendered = render_record(record, observation, params)
        seed = derive_seed(self.base_seed, "llm", "dashboard", *keys, str(record.day))
        response = explain(self.client, rendered, seed=seed, settings=self.settings)
        faithfulness = check(response.parsed, record, rendered)
        if response.value is None:
            reason = "no answer" if response.error is None else response.error.kind
            return Shown("", "llm", self.model, faithfulness, f"invalid answer ({reason})")
        return Shown(response.value.summary, "llm", self.model, faithfulness)
