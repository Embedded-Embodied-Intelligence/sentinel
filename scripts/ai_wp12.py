"""The WP12 checks of the AI features with a live model (tasks 12-14 of docs/prompts/WP12.md):
a project described in words (the CEO's text of the WP12 test, rebuilt from its report, and the
two texts of WP11), the CEO's two check-in messages, and an explanation in Polish.

    uv run python scripts/ai_wp12.py openrouter   # gpt-oss-120b pinned to Groq, a few cents
    uv run python scripts/ai_wp12.py ollama       # qwen2.5:7b on this machine, a few minutes

The key comes from `.env` through `sentinel.llm.secrets` and is never printed; the application's
cache keeps no prompts (spec section 10). The results go to docs/qa/ai/wp12-<provider>.json.
"""

import argparse
import importlib.util
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

from sentinel.app import planning
from sentinel.app.config import AppConfig
from sentinel.app.events import RecommendationEntry
from sentinel.app.live import LiveProject, build_model
from sentinel.app.llm import LlmSettingsUpdate, split_clauses
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    Person,
    ProjectDefinition,
    Settings,
    Task,
    TaskReport,
)
from sentinel.app.services import Services, draft_definition
from sentinel.app.terms import internal_terms
from sentinel.app.views import recommendation_view
from sentinel.llm.secrets import load_secret

ROOT = Path(__file__).resolve().parents[1]
MODELS = {"ollama": "qwen2.5:7b", "openrouter": "openai/gpt-oss-120b"}
KEYS = {"openrouter": "OPENROUTER_API_KEY"}

# The CEO's description, rebuilt from the fragments quoted in B8 of docs/qa/raport-ceo-chrome-pl.md.
CEO_TEXT = """Nowa strona internetowa z panelem klienta. W zespole jest analityk, dwóch \
programistów backend, programista frontend i tester.

Najpierw analityk przez około tygodnia zbiera wymagania. Potem dwóch programistów robi logowanie \
i uprawnienia, to zajmie 4 dni. Równolegle jeden programista backend przez 5 dni robi płatności \
online, a drugi przez 3 dni integrację z ERP. Programista frontend przez 2 dni robi powiadomienia \
SMS i przez 2 dni newsletter; możemy z nich zrezygnować, jeśli zabraknie czasu. Na koniec tester \
przez około tygodnia testuje całość, a potem programista backend w jeden dzień uruchamia stronę."""
MESSAGES = (
    "Marek jest na urlopie do środy, a testy potrwają 2 dni dłużej",
    "Filip jest na urlopie od jutra do 26 listopada, a testy integracyjne potrwają 2 dni dłużej",
)
START = date(2026, 11, 9)
CHECKIN = date(2026, 11, 18)  # a Wednesday: Logowanie and both testing tasks are under way


def wp11_texts() -> dict[str, str]:
    """The list and the prose of WP11 (scripts/ai_live.py), without running that driver."""
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("ai_live", ROOT / "scripts" / "ai_live.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {"wp11_list": module.LIST_TEXT, "wp11_prose": module.PROSE_TEXT}


def portal() -> ProjectDefinition:
    """A project like the CEO's run A: two testing tasks, Tomasz, Paulina and Filip."""
    team = (
        Person(key="P1", name="Tomasz Nowak", role="Programista backend"),
        Person(key="P2", name="Paulina Lis", role="Programista backend"),
        Person(key="P3", name="Filip Wójcik", role="Programista frontend"),
        Person(key="P4", name="Ewa Kowalska", role="Tester"),
        Person(key="P5", name="Marta Zając", role="Tester"),
    )
    tasks = (
        Task(key="T1", name="Logowanie", duration=6, crew={"Programista backend": 1}),
        Task(key="T2", name="Migracja treści", duration=5, crew={"Programista frontend": 1}),
        Task(
            key="T3",
            name="Testy integracyjne",
            duration=4,
            crew={"Tester": 1, "Programista backend": 1},
        ),
        Task(key="T4", name="Testy funkcjonalne", duration=4, crew={"Tester": 1}),
        Task(
            key="T5",
            name="Uruchomienie",
            duration=1,
            crew={"Programista backend": 1},
            predecessors=("T1", "T2", "T3", "T4"),
        ),
    )
    return ProjectDefinition(
        name="Portal",
        start=START,
        deadline=date(2026, 11, 27),
        team=team,
        tasks=tasks,
        settings=Settings(language="pl"),
    )


def tracked() -> LiveProject:
    project = LiveProject(portal())
    project.set_baseline(planning.baseline_plan(build_model(project.definition)))
    reports = tuple(
        TaskReport(task=key, status="in_progress", percent=40) for key in ("T1", "T2", "T3", "T4")
    )
    project.apply_checkin(project.resolve_checkin(CheckIn(date=CHECKIN, tasks=reports)))
    return project


def describe(services: Services, name: str, text: str) -> dict[str, Any]:
    began = time.perf_counter()
    session = services.llm.extract(text, 7)
    value = session.final.response.value
    row: dict[str, Any] = {
        "text": name,
        "rounds": len(session.rounds),
        "issues": len(session.final.issues),
    }
    if value is None:
        return {**row, "failed": True, "seconds": round(time.perf_counter() - began, 1)}
    draft = draft_definition(value, START, "pl")
    tasks = [
        {
            "name": t.name,
            "words": len(t.name.split()),
            "days": t.duration,
            "optional": t.optional,
            "after": [next((u.name for u in draft.tasks if u.key == p), p) for p in t.predecessors],
            "description": t.description,
        }
        for t in draft.tasks
    ]
    return {
        **row,
        "seconds": round(time.perf_counter() - began, 1),
        "max_words": max((t["words"] for t in tasks), default=0),
        "tasks": tasks,
    }


def message(services: Services, project: LiveProject, text: str) -> dict[str, Any]:
    began = time.perf_counter()
    draft = services.llm.read_message(project, text, CHECKIN, 11)
    clauses = split_clauses(text, "pl")
    names = {key: node.name for key, node in project.nodes().items()}
    people = {p.key: p.name for p in project.definition.team}
    return {
        "message": text,
        "seconds": round(time.perf_counter() - began, 1),
        "absences": [
            {"person": people.get(a.person, a.person), "back": str(a.return_date)}
            for a in draft.absences
        ],
        "growths": [
            {"task": names.get(i.task, i.task), "factor": i.factor, "days": i.extra_days}
            for i in draft.increases
        ],
        "unparsed": [clauses[n - 1] for n in draft.unparsed if n <= len(clauses)],
        "questions": [
            {
                "kind": q.kind,
                "clause": clauses[q.clause - 1] if q.clause <= len(clauses) else q.clause,
                "candidates": [names.get(c, c) for c in q.candidates],
                "back": None if q.return_date is None else str(q.return_date),
                "days": q.extra_days,
                "factor": q.factor,
            }
            for q in draft.questions
        ],
        "issues": draft.issues,
    }


def explanation(services: Services, project: LiveProject) -> dict[str, Any]:
    """The explanation of the recommendation after Tomasz's week away, in Polish."""
    away = CheckIn(
        date=date(2026, 11, 19),
        absences=(
            AbsenceReport(
                person="P1", first_day=date(2026, 11, 20), return_date=date(2026, 11, 27)
            ),
        ),
    )
    project.apply_checkin(project.resolve_checkin(away))
    recommendation = planning.recommend(project)
    entry = RecommendationEntry(seq=1, recommendation=recommendation, status="open")
    shown = recommendation_view(project, entry, "pl")
    names = {shown.label: shown.title} | {a.label: a.title for a in shown.alternatives}
    began = time.perf_counter()
    result = services.llm.explain(
        recommendation.as_shown,
        project.observation(),
        planning.sentinel_params(project),
        project.require_model().role_names,
        5,
        language="pl",
        names=names,
        reason=shown.reason_text,
    )
    return {
        "chosen": shown.title,
        "seconds": round(time.perf_counter() - began, 1),
        "text": result.text,
        "terms": internal_terms(result.text),
        "valid": result.valid,
        "fully_faithful": result.fully_faithful,
        "error": result.error,
    }


def usage(data: Path) -> dict[str, Any]:
    calls = prompt = completion = 0
    cost = 0.0
    for path in sorted((data / "llm_cache").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            reply = json.loads(line)["reply"]
            calls += 1
            prompt += reply["prompt_tokens"]
            completion += reply["completion_tokens"]
            cost += reply["meta"].get("cost") or 0.0
    return {
        "calls": calls,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cost_usd": round(cost, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(MODELS))
    args = parser.parse_args()
    key = None
    if args.provider in KEYS:
        key = load_secret(KEYS[args.provider])
        if key is None:
            print(f"{KEYS[args.provider]} is not set", file=sys.stderr)
            return 2
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        services = Services(AppConfig(data_dir=data, inline_jobs=True))
        services.llm.update(
            LlmSettingsUpdate(
                provider=args.provider,  # type: ignore[arg-type]
                model=MODELS[args.provider],
                api_key=None if key is None else key.reveal(),
            )
        )
        results: dict[str, Any] = {"provider": args.provider, "model": MODELS[args.provider]}
        texts = {"ceo": CEO_TEXT, **wp11_texts()}
        results["describe"] = [describe(services, name, text) for name, text in texts.items()]
        project = tracked()
        results["messages"] = [message(services, project, text) for text in MESSAGES]
        results["explanation"] = explanation(services, project)
        results["usage"] = usage(data)
    out = ROOT / "docs" / "qa" / "ai" / f"wp12-{args.provider}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results["usage"]), "->", out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
