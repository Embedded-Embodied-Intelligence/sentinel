"""The evaluation set of the application's check-in messages (WP14, task 3): the 30 Polish
reports of `docs/qa/ai/messages-pl.jsonl` on the usability project (as planned, and after the
owner's report of 4 November) and on the showcase project, each with the items its review should
show. Every report is read by the application's own path (`LlmService.read_message`, the seed of
`Services.read_message`) and its review is scored item by item: an item is exact when its type,
its task or person and its dates or values all match; an item the review shows that no expected
item has counts against the score; a date shown ticked, without a question, that is not the
expected one is a wrong date shown without a question.

    uv run python scripts/messages_eval.py openrouter              # gpt-oss-120b, all 30
    uv run python scripts/messages_eval.py ollama --limit 10       # qwen2.5:7b, the first 10
    uv run python scripts/messages_eval.py openrouter --label before

The key comes from `.env` through `sentinel.llm.secrets` and is never printed; the cache keeps no
prompts (spec section 10). The results go to docs/qa/ai/messages-eval-<label>-<provider>.json.
"""

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any

from sentinel.app import planning, showcase
from sentinel.app.config import AppConfig
from sentinel.app.events import replay
from sentinel.app.io import definition_from_csv
from sentinel.app.live import LiveProject, build_model
from sentinel.app.llm import LlmSettingsUpdate
from sentinel.app.message_reader import split_clauses, work_left
from sentinel.app.models import AbsenceReport, CheckIn, Person, Settings, TaskReport
from sentinel.app.services import Services
from sentinel.app.store import EventRow
from sentinel.experiments.runs import derive_seed
from sentinel.llm.secrets import load_secret

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "docs" / "qa" / "ai" / "messages-pl.jsonl"
OUT = ROOT / "docs" / "qa" / "ai"
MODELS = {
    "ollama": "qwen2.5:7b",
    "openrouter": "openai/gpt-oss-120b",
    "groq": "openai/gpt-oss-120b",
}
KEYS = {"openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY"}
USABILITY = ROOT / "docs" / "usability"
TOLERANCE_DAYS = 0.1  # a growth in days of work: one decimal, as the review shows it


def usability_project() -> LiveProject:
    """The usability test's project as a tester makes it (task 1 of the protocol): the CSV, the
    team list, Mon 2 Nov to Fri 4 Dec 2026, in Polish, planned."""
    team = [
        Person(key=f"P{i}", name=name.strip(), role=role.strip())
        for i, (name, role) in enumerate(
            (
                line.split(",", 1)
                for line in (USABILITY / "zespol-testowy.txt").read_text("utf-8").splitlines()
                if line.strip()
            ),
            start=1,
        )
    ]
    definition = definition_from_csv(
        (USABILITY / "projekt-testowy.csv").read_bytes(),
        None,
        name="P0 Aplikacja rezerwacji wizyt",
        start=date(2026, 11, 2),
        deadline=date(2026, 12, 4),
        settings=Settings(language="pl"),
    ).model_copy(update={"team": tuple(team)})
    project = LiveProject(definition)
    project.set_baseline(planning.baseline_plan(build_model(definition)))
    return project


def owner_report(project: LiveProject) -> LiveProject:
    """The owner's report of Wed 4 Nov (task 3): the workshop done on 3 Nov, the API at 15 %,
    Bartosz away from 5 Nov, back on 16 Nov."""
    keys = {task.name: task.key for task in project.definition.tasks}
    people = {person.name: person.key for person in project.definition.team}
    checkin = CheckIn(
        date=date(2026, 11, 4),
        tasks=(
            TaskReport(task=keys["Warsztat z klientem"], status="done", finish=date(2026, 11, 3)),
            TaskReport(task=keys["Baza danych i API"], status="in_progress", percent=15),
        ),
        absences=(
            AbsenceReport(
                person=people["Bartosz Kowalski"],
                first_day=date(2026, 11, 5),
                return_date=date(2026, 11, 16),
            ),
        ),
    )
    project.apply_checkin(project.resolve_checkin(checkin))
    return project


def showcase_project() -> LiveProject:
    """The showcase as a new demo sandbox holds it: its log replayed (two check-ins)."""
    stamp = datetime(2026, 11, 13, tzinfo=UTC)
    rows = [
        EventRow("showcase", seq, kind, payload, stamp)
        for seq, (kind, payload) in enumerate(showcase.events("pl"), start=1)
    ]
    return replay(rows).project


@cache
def state(name: str) -> LiveProject:
    if name == "usability":
        return usability_project()
    if name == "usability_4nov":
        return owner_report(usability_project())
    if name == "showcase":
        return showcase_project()
    raise ValueError(f"unknown state {name}")


@dataclass
class Item:
    """An item of a review or of the expected review: its subject (what it is about), its form
    ("item": ticked to confirm, "doubtful": unticked with a note, "question": a choice to make)
    and its values (dates as ISO strings, numbers)."""

    subject: tuple[str, ...]
    form: str
    values: dict[str, Any] = field(default_factory=dict)

    @property
    def dated(self) -> bool:
        return any(k in self.values for k in ("from", "back", "finish", "start"))

    def show(self) -> dict[str, Any]:
        return {"subject": list(self.subject), "form": self.form, **self.values}


def _day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def expected_items(case: Mapping[str, Any]) -> list[Item]:
    items = []
    for raw in case["expected"]:
        kind = raw["type"]
        if kind == "nothing":
            items.append(Item(("nothing",), "item"))
        elif kind == "absence":
            items.append(
                Item(("absence", raw["person"]), "item", {"from": raw["from"], "back": raw["back"]})
            )
        elif kind == "done":
            items.append(
                Item(("task", raw["task"]), "item", {"status": "done", "finish": raw["finish"]})
            )
        elif kind == "progress":
            values: dict[str, Any] = {"status": "in_progress", "percent": raw.get("percent")}
            if raw.get("start"):
                values["start"] = raw["start"]
            items.append(Item(("task", raw["task"]), "item", values))
        elif kind == "increase":
            values = {k: raw[k] for k in ("extra_days", "factor") if k in raw}
            items.append(Item(("increase", raw["task"]), "item", values))
        elif kind == "new_task":
            values = {k: raw.get(k) for k in ("duration", "after", "before")}
            items.append(Item(("new_task", raw["name"].casefold()), "item", values))
        elif raw["kind"] == "unknown_person":
            items.append(
                Item(("unknown_person",), "question", {"from": raw["from"], "back": raw["back"]})
            )
        elif raw["kind"] == "ambiguous_task":
            items.append(Item(("ambiguous", *sorted(raw["candidates"])), "question"))
        else:  # a question about a date
            about = "absence" if raw["about"] == "absence" else "task"
            items.append(Item((about, raw.get("person") or raw["task"]), "question"))
    return items


def review_items(project: LiveProject, draft: Any) -> list[Item]:
    """The items of a review (`MessageDraft`) as the page shows them."""
    names = {key: node.name for key, node in project.nodes().items()}
    people = {p.key: p.name for p in project.definition.team}
    left = work_left(project)
    doubtful = set(getattr(draft, "doubtful", ())) | set(getattr(draft, "unchecked_absences", ()))
    unchecked = set(getattr(draft, "unchecked_tasks", ()))
    items = []
    for i, a in enumerate(draft.absences):
        items.append(
            Item(
                ("absence", people.get(a.person, a.person)),
                "doubtful" if i in doubtful else "item",
                {"from": _day(a.first_day), "back": _day(a.return_date)},
            )
        )
    for i, report in enumerate(getattr(draft, "tasks", ())):
        values: dict[str, Any] = {"status": report.status}
        if report.status == "done":
            values["finish"] = _day(report.finish)
        else:  # a start without a share is saved at 0 %, the share "not given"
            values["percent"] = round(report.percent) if report.percent else None
        if report.start is not None:
            values["start"] = _day(report.start)
        form = "doubtful" if i in unchecked else "item"
        items.append(Item(("task", names.get(report.task, report.task)), form, values))
    for g in draft.increases:
        values = {}
        if g.extra_days is not None:
            values["extra_days"] = g.extra_days
        elif g.factor is not None and g.task in left:  # as the review shows it, in days of work
            values["extra_days"] = round(left[g.task] * (g.factor - 1), 1)
            values["factor"] = g.factor
        elif g.factor is not None:
            values["factor"] = g.factor
        items.append(Item(("increase", names.get(g.task, g.task)), "item", values))
    for n in draft.new_tasks:
        values = {
            "duration": n.duration,
            "after": None if n.after is None else names.get(n.after, n.after),
            "before": None if n.before is None else names.get(n.before, n.before),
        }
        items.append(Item(("new_task", n.name.casefold()), "item", values))
    for q in draft.questions:
        if q.kind == "unknown_person":  # its dates, or the choices of them it offers
            firsts = sorted({_day(a.first_day) for a in q.absences}) or [_day(q.first_day)]
            backs = sorted({str(_day(a.return_date)) for a in q.absences}) or [_day(q.return_date)]
            values = {
                "from": firsts[0] if len(firsts) == 1 else firsts,
                "back": None
                if backs in (["None"], [None])
                else backs[0]
                if len(backs) == 1
                else backs,
            }
            items.append(Item(("unknown_person",), "question", values))
        elif q.kind == "ambiguous_task":
            items.append(
                Item(("ambiguous", *sorted(names.get(c, c) for c in q.candidates)), "question")
            )
        elif q.person is not None:  # a question about a date (WP14)
            items.append(Item(("absence", people.get(q.person, q.person)), "question"))
        else:
            items.append(Item(("task", names.get(q.task, q.task)), "question"))
    return items


def same(expected: Item, found: Item) -> bool:
    """Whether a found item is the expected one: its type, subject and values; an item shown
    unticked with a note ("doubtful") is one, a question is not."""
    if (expected.form == "question") != (found.form == "question"):
        return False
    for key, value in expected.values.items():
        got = found.values.get(key)
        if key == "extra_days" and value is not None and got is not None:
            if abs(value - got) > TOLERANCE_DAYS:
                return False
        elif key == "factor" and value is not None and got is not None:
            if abs(value - got) > 0.01:
                return False
        elif got != value:
            return False
    return not (found.values.get("start") and "start" not in expected.values)


def score(expected: list[Item], found: list[Item]) -> dict[str, Any]:
    """Exact items, items the review got wrong, items it added, and the dates it shows ticked
    without a question that are not the expected ones."""
    if [e.subject for e in expected] == [("nothing",)]:
        ok = not found
        return {
            "expected": 1,
            "exact": int(ok),
            "wrong": [],
            "missing": [],
            "added": [f.show() for f in found],
            "wrong_dates": sum(1 for f in found if f.form == "item" and f.dated),
        }
    left = list(found)
    exact, wrong, missing = 0, [], []
    wrong_dates = 0
    for e in expected:
        match = next((f for f in left if f.subject == e.subject), None)
        if match is None:
            missing.append(e.show())
            continue
        left.remove(match)
        if same(e, match):
            exact += 1
            continue
        wrong.append({"expected": e.show(), "found": match.show()})
        dates = ("from", "back", "finish", "start")
        moved = e.form == "question" or any(match.values.get(k) != e.values.get(k) for k in dates)
        if match.form == "item" and match.dated and moved:
            wrong_dates += 1
    wrong_dates += sum(1 for f in left if f.form == "item" and f.dated)
    return {
        "expected": len(expected),
        "exact": exact,
        "wrong": wrong,
        "missing": missing,
        "added": [f.show() for f in left],
        "wrong_dates": wrong_dates,
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


def read_cases(limit: int | None, only: Iterable[str] = ()) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in CASES.read_text("utf-8").splitlines() if line.strip()]
    wanted = set(only)
    if wanted:
        cases = [c for c in cases if c["id"] in wanted]
    return cases[:limit] if limit else cases


def run(services: Services, case: Mapping[str, Any]) -> dict[str, Any]:
    project = state(case["state"])
    when = date.fromisoformat(case["date"])
    seed = derive_seed(project.definition.settings.seed, "llm", "message", case["text"])
    began = time.perf_counter()
    try:
        draft = services.llm.read_message(project, case["text"], when, seed)
    except Exception as exc:  # a failed reading scores nothing; the run goes on
        result = score(expected_items(case), [])
        return {"id": case["id"], "error": type(exc).__name__, **result}
    seconds = round(time.perf_counter() - began, 1)
    found = review_items(project, draft)
    clauses = split_clauses(case["text"], "pl")
    return {
        "id": case["id"],
        "seconds": seconds,
        "items": [f.show() for f in found],
        "unparsed": [clauses[n - 1] for n in draft.unparsed if n <= len(clauses)],
        **score(expected_items(case), found),
    }


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sum(r["expected"] for r in rows)
    exact = sum(r["exact"] for r in rows)
    added = sum(len(r["added"]) for r in rows)
    return {
        "cases": len(rows),
        "expected_items": expected,
        "exact_items": exact,
        "added_items": added,
        "exact_share": round(exact / (expected + added), 3) if expected + added else None,
        "wrong_dates_without_question": sum(r["wrong_dates"] for r in rows),
        "doubtful_items": sum(
            1 for r in rows for item in r.get("items", ()) if item["form"] == "doubtful"
        ),
        "failed_readings": sum(1 for r in rows if "error" in r),
    }


def rescore(path: Path) -> int:
    """Score the items a stored run found against the current expected items, without a call:
    the "before" runs are compared with the "after" runs on one set of expectations."""
    results = json.loads(path.read_text("utf-8"))
    cases = {c["id"]: c for c in read_cases(None)}
    rows = []
    for row in results["cases"]:
        found = [
            Item(
                tuple(i["subject"]),
                i["form"],
                {k: v for k, v in i.items() if k not in ("subject", "form")},
            )
            for i in row.get("items", ())
        ]
        rows.append({**row, **score(expected_items(cases[row["id"]]), found)})
    results["cases"] = rows
    results["summary"] = summary(rows)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results["summary"]), "->", path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(MODELS))
    parser.add_argument("--limit", type=int, default=None, help="the first N reports only")
    parser.add_argument("--only", nargs="*", default=(), help="report ids, e.g. m01 m05")
    parser.add_argument("--label", default="after", help="before or after (the file name)")
    parser.add_argument(
        "--rescore", type=Path, default=None, help="score a stored results file again (no calls)"
    )
    args = parser.parse_args()
    if args.rescore is not None:
        return rescore(args.rescore)
    key = None
    if args.provider in KEYS:
        key = load_secret(KEYS[args.provider])
        if key is None:
            print(f"{KEYS[args.provider]} is not set", file=sys.stderr)
            return 2
    cases = read_cases(args.limit, args.only)
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
        rows = []
        for case in cases:
            row = run(services, case)
            rows.append(row)
            print(
                f"{row['id']}: {row['exact']}/{row['expected']} exact, "
                f"{len(row['added'])} added, {row['wrong_dates']} wrong dates",
                flush=True,
            )
        results = {
            "provider": args.provider,
            "model": MODELS[args.provider],
            "label": args.label,
            "summary": summary(rows),
            "usage": usage(data),
            "cases": rows,
        }
        services.close()
    suffix = f"-first{args.limit}" if args.limit else ""
    out = OUT / f"messages-eval-{args.label}-{args.provider}{suffix}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results["summary"]), json.dumps(results["usage"]), "->", out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
