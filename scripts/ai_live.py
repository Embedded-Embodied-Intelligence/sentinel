"""The AI features of the application through the browser with a real model (WP11; docs/qa/ai/).

Starts `sentinel ui` on a fresh data directory, tests the provider on the settings page (a wrong
model, key or address first, then the right ones), then drives the flows in Polish as a manager
would, with a screenshot at every step: the wizard's "describe the project" with a structured list
and with free prose (checked against what the text states), a check-in message with two facts, and
AI explanations with their faithfulness badge. At the end it sweeps the data directory, the caches,
the server's log and the served pages for the reason of the absence the message gives (invariant 7)
and sums the tokens and the cost from the cache.

    uv run python scripts/ai_live.py ollama [--out docs/qa/ai] [--flows list,prose,message]
    uv run python scripts/ai_live.py openrouter [--out docs/qa/ai]
    uv run python scripts/ai_live.py groq --flows settings   # the connection test only
    uv run python scripts/ai_live.py errors [--out docs/qa/ai]

`errors` needs no model: a local stand-in for Ollama answers with invalid JSON, an HTTP error or a
page that is no JSON, does not answer in time or is down, and each form must say so in plain words
and keep working on the same page, until the stand-in recovers and the same request is answered.

A key comes from OPENROUTER_API_KEY or GROQ_API_KEY (environment or `.env`): it is typed into the
settings page's password field and removed through the same page at the end. It is never printed
or logged.
"""

import argparse
import json
import re
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from qa_run import (
    Driver,
    Task,
    add_absence,
    add_workdays,
    books,
    move_team,
    new_project,
    planned_project,
    report_tasks,
    server,
    write_log,
)
from ui_screenshots import language_env

from sentinel.llm.secrets import Secret, load_secret

ROOT = Path(__file__).resolve().parents[1]
WAIT = 1_500_000  # ms: a repair session of a local model on a busy machine (--wait)
BUDGET_USD = 0.20  # of the whole work package (WP11)
START = date(2026, 10, 5)
DEADLINE = date(2026, 11, 20)
FIRST_CHECKIN = date(2026, 10, 19)  # every task on plan, so that "Logowanie" is running
MESSAGE_DAY = date(2026, 10, 21)  # a Wednesday: "do piątku" is away through Friday 23 October
RETURN_DAY = date(2026, 10, 26)  # so back on Monday (spec section 11.3, v2.1.5)
LONG_ABSENCE_DAY = date(2026, 10, 22)  # a second absence, which a substitution can answer
MESSAGE = "Ania jest chora do piątku, a logowanie zajmie jeszcze 3 dni dłużej"
REASON = re.compile(rb"\bchor|\bsick|\bill\b|illness|\bflu\b|gryp|\bL4\b", re.IGNORECASE)
TEAM = """Ania Nowak, Programista
Bartek Zieliński, Programista
Cezary Wójcik, Programista
Filip Lis, Programista
Dorota Mazur, Tester
Ewa Sikora, Analityk"""
PROVIDERS = {
    "ollama": ("Model lokalny (Ollama)", "qwen2.5:7b"),
    "openrouter": ("OpenRouter (chmura)", "openai/gpt-oss-120b"),
    "groq": ("Groq (chmura)", "openai/gpt-oss-120b"),
}
KEY_VARIABLES = {"openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY"}
WRONG_KEY = "not-a-key"  # refused by the provider, at no cost
WRONG_MODEL = "no-such-vendor/no-such-model"
CLOSED_ADDRESS = "http://127.0.0.1:9"  # nothing answers here


@dataclass(frozen=True)
class Expected:
    """A task as the description states it; `word` finds it among the tasks the model names."""

    word: str
    days: int
    crew: dict[str, int]
    after: tuple[str, ...] = ()


LIST_TEXT = """Portal klienta. Zespół: 4 programistów, 1 tester, 1 analityk.

Zadania:
1. Warsztat z klientem: 3 dni, 1 analityk, bez poprzedników.
2. Specyfikacja wymagań: 4 dni, 1 analityk, po zadaniu "Warsztat z klientem".
3. Model danych: 3 dni, 1 programista, po zadaniu "Specyfikacja wymagań".
4. Logowanie: 6 dni, 1 programista, po zadaniu "Model danych".
5. Profil klienta: 5 dni, 1 programista, po zadaniu "Model danych".
6. Lista faktur: 5 dni, 1 programista, po zadaniu "Model danych".
7. Płatności online: 7 dni, 2 programistów, po zadaniach "Logowanie" i "Lista faktur".
8. Powiadomienia e-mail: 3 dni, 1 programista, po zadaniu "Profil klienta".
9. Testy integracyjne: 5 dni, 1 programista i 1 tester, po zadaniach "Płatności online" i \
"Powiadomienia e-mail".
10. Dokumentacja użytkownika: 3 dni, 1 analityk, po zadaniu "Płatności online".
11. Szkolenie klienta: 2 dni, 1 analityk, po zadaniu "Dokumentacja użytkownika".
12. Wdrożenie produkcyjne: 2 dni, 1 programista i 1 tester, po zadaniach "Testy integracyjne" i \
"Szkolenie klienta".
"""
LIST_TRUTH = (
    Expected("warsztat", 3, {"analityk": 1}),
    Expected("specyfikacja", 4, {"analityk": 1}, ("warsztat",)),
    Expected("model danych", 3, {"programista": 1}, ("specyfikacja",)),
    Expected("logowanie", 6, {"programista": 1}, ("model danych",)),
    Expected("profil", 5, {"programista": 1}, ("model danych",)),
    Expected("faktur", 5, {"programista": 1}, ("model danych",)),
    Expected("płatności", 7, {"programista": 2}, ("logowanie", "faktur")),
    Expected("powiadomienia", 3, {"programista": 1}, ("profil",)),
    Expected("testy", 5, {"programista": 1, "tester": 1}, ("płatności", "powiadomienia")),
    Expected("dokumentacja", 3, {"analityk": 1}, ("płatności",)),
    Expected("szkolenie", 2, {"analityk": 1}, ("dokumentacja",)),
    Expected("wdrożenie", 2, {"programista": 1, "tester": 1}, ("testy", "szkolenie")),
)
PROSE_TEXT = """Budujemy aplikację mobilną dla serwisantów. W zespole są cztery osoby \
programujące, jedna testerka i jedna analityczka.

Zaczynamy od tego, że analityczka przez dwa dni prowadzi wywiady z serwisantami. Potem, też sama, \
przez trzy dni spisuje wymagania. Kiedy wymagania są gotowe, jeden programista przez cztery dni \
przygotowuje API zleceń. Równolegle z API, też dopiero po wymaganiach, drugi programista przez \
pięć dni robi logowanie. Gdy API zleceń będzie gotowe, jedna osoba programująca przez pięć dni \
tworzy ekran listy zleceń, a inna przez cztery dni tryb offline. Ekran szczegółów zlecenia zajmuje \
trzy dni jednemu programiście i może się zacząć dopiero po ekranie listy zleceń i po logowaniu. \
Skanowanie kodów kreskowych to dwa dni pracy jednego programisty po ekranie szczegółów. Jak tryb \
offline i skanowanie będą gotowe, dwóch programistów przez trzy dni integruje całość z systemem \
ERP. Po integracji testerka przez sześć dni prowadzi testy w terenie, a analityczka w tym samym \
czasie, trzy dni, pisze instrukcję dla serwisantów. Na samym końcu, po testach w terenie i po \
instrukcji, jeden programista razem z testerką przez dwa dni publikuje aplikację w sklepie.
"""
PROSE_TRUTH = (
    Expected("wywiad", 2, {"analityk": 1}),
    Expected("wymaga", 3, {"analityk": 1}, ("wywiad",)),
    Expected("api", 4, {"programista": 1}, ("wymaga",)),
    Expected("logowan", 5, {"programista": 1}, ("wymaga",)),
    Expected("list", 5, {"programista": 1}, ("api",)),
    Expected("offline", 4, {"programista": 1}, ("api",)),
    Expected("szczeg", 3, {"programista": 1}, ("list", "logowan")),
    Expected("skan", 2, {"programista": 1}, ("szczeg",)),
    Expected("erp", 3, {"programista": 2}, ("offline", "skan")),
    Expected("teren", 6, {"tester": 1}, ("erp",)),
    Expected("instrukcj", 3, {"analityk": 1}, ("erp",)),
    Expected("sklep", 2, {"programista": 1, "tester": 1}, ("teren", "instrukcj")),
)


def text_of(locator: Any) -> str:
    return " ".join(locator.inner_text().split())


def test_connection(d: Driver, label: str) -> None:
    """Press the connection test on the settings page and log what it says."""
    page = d.page
    page.evaluate("document.querySelector('#test-result').innerHTML = ''")
    began = time.perf_counter()
    page.get_by_role("button", name="Sprawdź połączenie").click()
    page.locator("#test-result .callout").wait_for(timeout=WAIT)
    d.shot(f"settings_{label}", full=True)
    d.note(
        kind="settings_test",
        attempt=label,
        text=text_of(page.locator("#test-result")),
        seconds=round(time.perf_counter() - began, 1),
    )


def choose_provider(d: Driver, provider: str, key: Secret | None) -> None:
    """Test the provider on the settings page, wrong settings first, and save the right ones."""
    page = d.page
    label, model = PROVIDERS[provider]
    page.goto(d.base + "/settings")
    page.wait_for_load_state("networkidle")
    d.shot("settings_start", full=True)
    page.get_by_label(label).check()
    page.get_by_label("Model", exact=True).fill(WRONG_MODEL)
    if key is None:
        test_connection(d, "wrong_model")
        page.locator("#host").fill(CLOSED_ADDRESS)
        test_connection(d, "wrong_address")
        page.locator("#host").fill("")
    else:
        page.get_by_role("button", name="Sprawdź połączenie").click()
        page.locator("#alerts .callout").wait_for(timeout=WAIT)
        d.shot("settings_no_key", full=True)
        d.note(kind="settings_test", attempt="no_key", text=text_of(page.locator("#alerts")))
        page.locator("#api_key").fill(WRONG_KEY)
        test_connection(d, "wrong_key")
        page.locator("#api_key").fill(key.reveal())  # a password field: dots on the screenshot
        test_connection(d, "wrong_model")
    page.get_by_label("Model", exact=True).fill(model)
    d.shot("settings_filled", full=True)
    test_connection(d, "right")
    page.get_by_role("button", name="Zapisz ustawienia").click()
    page.wait_for_url(re.compile(r"flash=settings_saved"))
    d.shot("settings_saved", full=True)


def score(rows: list[dict[str, Any]], truth: tuple[Expected, ...]) -> dict[str, Any]:
    """The model's task rows against what the description states: tasks found and, of those,
    the durations, crews (roles by the start of their name) and predecessors that agree."""

    def find(word: str, names: list[str]) -> str | None:
        return next((n for n in names if word in n.lower()), None)

    names = [str(row["name"]) for row in rows]
    by_name = {str(row["name"]): row for row in rows}
    found = days = crew = after = 0
    wrong: list[str] = []
    for item in truth:
        name = find(item.word, names)
        if name is None:
            wrong.append(f"missing: {item.word}")
            continue
        found += 1
        row = by_name[name]
        if row["days"] == item.days:
            days += 1
        else:
            wrong.append(f"{name}: {row['days']} days, stated {item.days}")
        shown = {str(role).lower(): count for role, count in row["crew"].items()}
        if shown == item.crew:
            crew += 1
        else:
            wrong.append(f"{name}: crew {row['crew']}, stated {item.crew}")
        wanted = {find(word, names) for word in item.after}
        if wanted == set(row["after"]):
            after += 1
        else:
            wrong.append(f"{name}: after {row['after']}, stated {sorted(map(str, wanted))}")
    extra = [n for n in names if not any(item.word in n.lower() for item in truth)]
    return {
        "stated": len(truth),
        "tasks_returned": len(rows),
        "found": found,
        "durations_right": days,
        "crews_right": crew,
        "predecessors_right": after,
        "extra_tasks": extra,
        "differences": wrong,
    }


def describe(
    d: Driver, label: str, name: str, text: str, truth: tuple[Expected, ...], deadline: date
) -> str | None:
    """The wizard with the team pasted and the tasks described in words; the project's id, or
    None if the plan could not be created (the log says why)."""
    page = d.page
    page.goto(d.base + "/new")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Nazwa projektu").fill(name)
    page.get_by_label("Data rozpoczęcia").fill(START.isoformat())
    page.get_by_label("Termin", exact=True).fill(deadline.isoformat())
    d.shot(f"{label}_basics")
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/team")
    page.get_by_text("Wklej listę osób").click()
    page.get_by_label("Jedna osoba w wierszu").fill(TEAM)
    page.get_by_role("button", name="Dodaj te osoby").click()
    page.get_by_label("Imię i nazwisko osoby 6").wait_for(state="attached")
    d.shot(f"{label}_team", full=True)
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/tasks")
    project = page.url.split("/projects/")[1].split("/")[0]
    page.get_by_role("link", name="Opisz słowami").click()
    page.wait_for_url("**tab=describe")
    page.locator("#text").fill(text)
    d.shot(f"{label}_text", full=True)
    began = time.perf_counter()
    page.get_by_role("button", name="Odczytaj opis").click()
    page.wait_for_load_state("networkidle")
    d.shot(f"{label}_reading")
    page.locator("#describe-result .callout").wait_for(timeout=WAIT)
    seconds = round(time.perf_counter() - began, 1)
    d.shot(f"{label}_review", full=True)
    rows = review_rows(page, project, d)
    d.note(
        kind="extraction",
        label=label,
        seconds=seconds,
        callout=text_of(page.locator("#describe-result .callout").first),
        rows=rows,
        score=score(rows, truth) if rows else None,
    )
    if not rows:
        return None
    page.get_by_role("button", name="Użyj tych zadań").click()
    page.wait_for_url("**tab=manual**")
    page.wait_for_load_state("networkidle")
    d.shot(f"{label}_tasks", full=True)
    page.get_by_role("button", name="Utwórz plan").click()
    try:
        page.wait_for_url(re.compile(r"flash=plan_ready"), timeout=120_000)
    except Exception:
        d.shot(f"{label}_refused", full=True)
        d.note(
            kind="plan_refused",
            label=label,
            errors=[text_of(c) for c in page.locator(".callout").all()],
        )
        return None
    d.settle()
    d.moment(f"{label} plan")
    d.shot(f"{label}_overview", full=True)
    return project


def review_rows(page: Any, project: str, d: Driver) -> list[dict[str, Any]]:
    """The tasks of the review table, from the draft it would save."""
    draft = page.locator('#describe-result input[name="draft"]')
    if not draft.count():
        return []
    definition = json.loads(draft.get_attribute("value"))
    names = {t["key"]: t["name"] for t in definition["tasks"]}
    return [
        {
            "name": t["name"],
            "days": t["duration"],
            "crew": t["crew"],
            "after": [names.get(p, p) for p in t["predecessors"]],
        }
        for t in definition["tasks"]
    ]


def checkin_on_plan(d: Driver, project: str, when: date) -> None:
    """A check-in by hand: every task as the plan has it on `when`."""
    page = d.page
    page.goto(f"{d.base}/projects/{project}/checkin")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Stan na koniec dnia").fill(when.isoformat())
    view = books(d, project)
    team = {t["key"]: Task(t["key"], t["name"]) for t in view["tasks"]}
    move_team(view, team, add_workdays(START, -1), when, {})
    reported = report_tasks(d, view, team)
    d.note(kind="first_checkin", reported=reported)
    page.locator("button.btn-primary").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=120_000)
    d.settle()
    d.moment("first check-in")


def message_flow(d: Driver, project: str) -> None:
    """A second check-in from a message: read, confirm, save."""
    page = d.page
    page.goto(f"{d.base}/projects/{project}/checkin")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Stan na koniec dnia").fill(MESSAGE_DAY.isoformat())
    page.locator("#message").fill(MESSAGE)
    d.shot("message_written", full=True)
    began = time.perf_counter()
    page.get_by_role("button", name="Przetwórz wiadomość").click()
    page.locator(
        "#message-result .review-block, #message-result .row-list-empty, #message-result .callout"
    ).first.wait_for(timeout=WAIT)
    seconds = round(time.perf_counter() - began, 1)
    # In a full-page shot the sticky bar of the form would cover the review.
    page.locator("#message").evaluate("e => e.scrollIntoView({block: 'start'})")
    d.shot("message_read")
    items = [text_of(i) for i in page.locator("#message-result .confirm-list li").all()]
    values = {
        name: [
            json.loads(str(i.get_attribute("value")))
            for i in page.locator(f'#message-result input[name="{name}"]').all()
        ]
        for name in ("msg_absence", "msg_increase", "msg_new")
    }
    view = books(d, project)
    running = [
        {"name": t["name"], "percent": t["percent"], "duration": t["duration"]}
        for t in view["tasks"]
        if t["state"] in ("in_progress", "paused")
    ]
    d.note(
        kind="message",
        seconds=seconds,
        items=items,
        values=values,
        running=running,
        result=text_of(page.locator("#message-result")),
        expected_return=RETURN_DAY,
    )
    page.locator("button.btn-primary").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=120_000)
    d.settle()
    d.moment("message check-in")
    d.shot("message_saved", full=True)


def explain_shown(d: Driver, label: str) -> None:
    """On a recommendation's page: ask for the AI explanation and log it with its badge."""
    page = d.page
    page.wait_for_load_state("networkidle")
    d.shot(f"{label}_recommendation", full=True)
    title = text_of(page.locator("#rec-title"))
    why = [text_of(r) for r in page.locator("ul.bullets li").all()]
    began = time.perf_counter()
    page.get_by_role("button", name="Wyjaśnij innymi słowami (AI)").click()
    page.locator(".review-block, #explain-area .callout").first.wait_for(timeout=WAIT)
    seconds = round(time.perf_counter() - began, 1)
    page.wait_for_load_state("networkidle")
    d.shot(f"{label}_answer", full=True)
    block = page.locator(".review-block")
    d.note(
        kind="explanation",
        label=label,
        seconds=seconds,
        recommendation=title,
        why=why,
        block=text_of(block) if block.count() else text_of(page.locator("#explain-area")),
        badge=text_of(block.locator(".badge")) if block.locator(".badge").count() else "",
    )


def explanation_flow(d: Driver, project: str) -> None:
    """The AI explanation of a recommendation that keeps the plan and of one that acts: a second
    absence, without a return, which a free person of the role can answer."""
    page = d.page
    page.goto(f"{d.base}/projects/{project}")
    d.settle()
    review = page.get_by_role("link", name="Przejrzyj i zdecyduj")
    if review.count():
        review.first.click()
    else:
        page.get_by_role("button", name="Zapytaj Sentinela").first.click()
    page.wait_for_url("**/recommendations/**", timeout=WAIT)
    explain_shown(d, "explain_first")
    page.goto(f"{d.base}/projects/{project}/checkin")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Stan na koniec dnia").fill(LONG_ABSENCE_DAY.isoformat())
    add_absence(page, "Bartek Zieliński (Programista)", LONG_ABSENCE_DAY, None)
    page.locator("button.btn-primary").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=120_000)
    d.settle()
    d.moment("second absence")
    d.shot("explain_second_overview", full=True)
    review = page.get_by_role("link", name="Przejrzyj i zdecyduj")
    if not review.count():
        page.get_by_role("button", name="Zapytaj Sentinela").first.click()
        page.wait_for_url("**/recommendations/**", timeout=WAIT)
    else:
        review.first.click()
        page.wait_for_url("**/recommendations/**", timeout=WAIT)
    explain_shown(d, "explain_second")


def forget_key(d: Driver) -> None:
    """Remove the key through the settings page, so that no copy of it is left."""
    page = d.page
    page.goto(d.base + "/settings")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Bez AI").check()
    page.get_by_role("button", name="Zapisz ustawienia").click()
    page.wait_for_url(re.compile(r"flash=settings_saved"))


def pages_of(d: Driver, projects: list[str]) -> dict[str, bytes]:
    """The pages and exports the server serves for the projects, as bytes."""
    paths = ["/", "/settings"]
    for project in projects:
        paths += [
            f"/projects/{project}{tail}"
            for tail in ("", "/checkin", "/history", "/settings", "/report.html")
        ]
        paths += [f"/api/projects/{project}", f"/api/projects/{project}/export.json"]
        view = books(d, project)
        paths += [
            f"/projects/{project}/recommendations/{r['seq']}" for r in view["recommendations"]
        ]
    return {path: d.page.request.get(d.base + path).body() for path in paths}


def sweep(data: Path, server_log: Path, pages: dict[str, bytes]) -> dict[str, Any]:
    """Every file of the data directory, the server's log and the served pages against the
    reason of the absence; and every cache record for what a cache without prompts may hold."""
    found: list[dict[str, str]] = []

    def look(where: str, content: bytes) -> None:
        for match in REASON.finditer(content):
            near = content[max(0, match.start() - 40) : match.end() + 40]
            found.append({"where": where, "near": near.decode("utf-8", "replace")})

    files = [p for p in data.rglob("*") if p.is_file()]
    for path in files:
        look(str(path.relative_to(data)), path.read_bytes())
    look("server log", server_log.read_bytes())
    for path, content in pages.items():
        look(re.sub(r"/projects/[\w-]{16}", "/projects/<id>", path), content)
    records = [
        json.loads(line)
        for path in sorted((data / "llm_cache").glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return {
        "files_swept": len(files),
        "pages_swept": len(pages),
        "matches": found,
        "cache_records": len(records),
        "records_without_prompts": sum(
            r["request"].get("store_prompts") is False and "messages" not in r["request"]
            for r in records
        ),
    }


def usage(data: Path) -> dict[str, Any]:
    """Tokens, time and cost per kind of call, from the cache's records."""
    per: dict[str, dict[str, Any]] = {}
    for path in sorted((data / "llm_cache").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            row = per.setdefault(
                record["request"]["schema_name"],
                {"calls": 0, "prompt": 0, "completion": 0, "seconds": 0.0, "cost": 0.0},
            )
            reply = record["reply"]
            row["calls"] += 1
            row["prompt"] += reply["prompt_tokens"]
            row["completion"] += reply["completion_tokens"]
            row["seconds"] = round(row["seconds"] + reply["latency_s"], 1)
            row["cost"] += reply["meta"].get("cost") or 0.0
            row.setdefault("providers", set()).add(str(reply["meta"].get("provider")))
            if reply["meta"].get("withheld"):
                row["withheld"] = row.get("withheld", 0) + 1
    for row in per.values():
        row["providers"] = sorted(row["providers"])
        row["cost"] = round(row["cost"], 6)
    return per


def run(args: argparse.Namespace, browser: Any) -> int:
    global WAIT
    WAIT = args.wait * 1000
    provider = args.provider
    key = None
    if provider in KEY_VARIABLES:
        key = load_secret(KEY_VARIABLES[provider])
        if key is None:
            print(f"{KEY_VARIABLES[provider]} is not set")
            return 2
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    flows = set(args.flows.split(","))
    data = Path(tempfile.mkdtemp(prefix=f"sentinel-ai-{provider}-"))
    server_log = out / f"{provider}-server.log"
    with server(data, server_log) as base:
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="pl-PL", reduced_motion="reduce"
        )
        context.set_default_timeout(60_000)
        context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
        d = Driver(context.new_page(), base, out, provider)
        projects: list[str] = []
        spent: dict[str, Any] = {}
        pages: dict[str, bytes] = {}
        try:
            choose_provider(d, provider, key)
            first = None
            if "list" in flows:
                first = describe(d, "list", "Portal klienta", LIST_TEXT, LIST_TRUTH, DEADLINE)
                projects += [first] if first else []
            if "prose" in flows:
                second = describe(
                    d, "prose", "Aplikacja serwisu", PROSE_TEXT, PROSE_TRUTH, DEADLINE
                )
                projects += [second] if second else []
                first = first or second
            if "message" in flows and first:
                checkin_on_plan(d, first, FIRST_CHECKIN)
                message_flow(d, first)
                explanation_flow(d, first)
        except Exception as exc:  # the log and the sweep still matter when a flow fails
            d.shot("failure", full=True)
            d.note(kind="failure", url=d.page.url, error=str(exc)[:600])
        finally:
            spent = usage(data)
            d.note(kind="usage", per_schema=spent)
            pages = pages_of(d, projects)
            write_log(out / f"{provider}-log.json", d.log)
        if key is not None:
            forget_key(d)
            assert key.reveal() not in (data / "settings.json").read_text(encoding="utf-8")
        context.close()
    result = sweep(data, server_log, pages)
    d.note(kind="sweep", **result)
    write_log(out / f"{provider}-log.json", d.log)
    total = sum(row["cost"] for row in spent.values())
    print(f"cost {total:.5f} USD of the budget {BUDGET_USD}; data directory {data}")
    return 0


class Stub:
    """A local stand-in for Ollama that answers as `mode` says: `ok`, `invalid` (an answer that
    is no JSON), `http500`, `html` (a page instead of JSON), `hang`; `stop()` takes it down."""

    def __init__(self) -> None:
        self.mode = "ok"
        self.calls = 0
        self.server: ThreadingHTTPServer | None = None
        self.port = 0

    def start(self) -> None:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def send(self, status: int, body: bytes, kind: str = "application/json") -> None:
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/show":
                    digest = "0" * 64
                    self.send(200, json.dumps({"modelfile": f"FROM /m/sha256-{digest}\n"}).encode())
                    return
                stub.calls += 1
                if stub.mode == "hang":
                    time.sleep(30)
                    return
                if stub.mode == "http500":
                    self.send(500, b'{"error": "the model crashed"}')
                    return
                if stub.mode == "html":
                    self.send(200, b"<html>a proxy's error page</html>", "text/html")
                    return
                content = "to nie jest JSON" if stub.mode == "invalid" else good_answer(payload)
                answer = {
                    "model": "stub",
                    "message": {"role": "assistant", "content": content},
                    "done_reason": "stop",
                    "prompt_eval_count": 10,
                    "eval_count": 10,
                }
                self.send(200, json.dumps(answer).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def good_answer(payload: dict[str, Any]) -> str:
    """A valid answer of the stand-in, by the system prompt it was asked with."""
    system, user = payload["messages"][0]["content"], payload["messages"][1]["content"]
    if user == "Connection test.":
        return '{"ok": true}'
    if system.startswith("You extract"):
        activity = {"duration_days": 2, "crew": {"Programista": 1}}
        return json.dumps(
            {
                "team": [{"role": "Programista", "count": 2}],
                "activities": [
                    {"name": "Analiza", "predecessors": [], **activity},
                    {"name": "Budowa", "predecessors": ["Analiza"], **activity},
                ],
            }
        )
    if system.startswith("You turn"):
        worker = re.search(r"(\d+) Ala", user)
        return json.dumps(
            {"events": [{"type": "absence", "worker": int(worker[1]), "return_day": None}]}
            if worker
            else {"events": []}
        )
    label = re.search(r"chosen[^:]*: *(\S+)", user, re.IGNORECASE)
    return json.dumps(
        {
            "summary": "The plan stays as it is.",
            "cited_facts": [
                {"kind": "chosen_action", "value": label[1] if label else "NOOP"},
                {"kind": "deciding_component", "value": "stability"},
            ],
        }
    )


ERROR_MODES = ("down", "invalid", "http500", "html", "hang", "ok")


def error_scenarios(args: argparse.Namespace, browser: Any) -> int:
    """Every form against every failure of the stand-in, on one page without reloading it, and
    the same request answered once the stand-in has recovered."""
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="sentinel-ai-errors-"))
    config = data.parent / f"{data.name}.toml"
    config.write_text("llm_timeout_s = 4.0\n", encoding="utf-8")
    stub = Stub()
    stub.start()
    server_log = out / "errors-server.log"
    with server(data, server_log, "--config", str(config)) as base:
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="pl-PL", reduced_motion="reduce"
        )
        context.set_default_timeout(60_000)
        context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
        d = Driver(context.new_page(), base, out, "errors")
        page = d.page

        def set_mode(mode: str) -> None:
            if mode == "down":
                stub.stop()
                return
            if stub.server is None:
                stub.start()
            stub.mode = mode

        def attempt(form: str, mode: str, click: Any, result: Any) -> None:
            set_mode(mode)
            before = stub.calls
            page.evaluate(f"document.querySelector('{result}').innerHTML = ''")
            began = time.perf_counter()
            click()
            page.wait_for_function(
                f"!document.querySelector('{result} .job') && "
                f"document.querySelector('{result}').children.length > 0",
                timeout=WAIT,
            )
            d.shot(f"{form}_{mode}", full=True)
            d.note(
                kind="error_scenario",
                form=form,
                mode=mode,
                shown=text_of(page.locator(result)),
                alert=page.locator(f"{result} .callout-bad").count() > 0,
                model_calls=stub.calls - before,
                seconds=round(time.perf_counter() - began, 1),
            )

        page.goto(d.base + "/settings")
        page.wait_for_load_state("networkidle")
        page.get_by_label(PROVIDERS["ollama"][0]).check()
        page.locator("#host").fill(f"http://127.0.0.1:{stub.port}")
        for mode in ERROR_MODES:
            attempt(
                "settings",
                mode,
                page.get_by_role("button", name="Sprawdź połączenie").click,
                "#test-result",
            )
        page.get_by_role("button", name="Zapisz ustawienia").click()
        page.wait_for_url(re.compile(r"flash=settings_saved"))
        set_mode("ok")

        project = planned_project(page, d.base, "Awarie AI")
        draft = new_project(
            page, d.base, "Opis z awariami", "Ala, Programista\nBartek, Programista"
        )
        page.goto(f"{d.base}/projects/{draft}/setup/tasks?tab=describe")
        page.wait_for_load_state("networkidle")
        page.locator("#text").fill(
            "Najpierw analiza, 2 dni, potem budowa, 2 dni; jeden programista."
        )
        for mode in ERROR_MODES:
            attempt(
                "describe",
                mode,
                page.get_by_role("button", name="Odczytaj opis").click,
                "#describe-result",
            )
        d.note(
            kind="form_after", form="describe", text_kept=bool(page.locator("#text").input_value())
        )

        page.goto(f"{d.base}/projects/{project}/checkin")
        page.wait_for_load_state("networkidle")
        page.get_by_label("Stan na koniec dnia").fill("2026-11-03")
        page.locator("#message").fill(MESSAGE)
        for mode in ERROR_MODES:
            attempt(
                "message",
                mode,
                page.get_by_role("button", name="Przetwórz wiadomość").click,
                "#message-result",
            )
        d.note(
            kind="form_after",
            form="message",
            text_kept=bool(page.locator("#message").input_value()),
            items=[text_of(i) for i in page.locator("#message-result .confirm-list li").all()],
        )
        page.locator("button.btn-primary").click()
        page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=120_000)
        d.settle()
        d.shot("message_saved", full=True)

        page.get_by_role("button", name="Zapytaj Sentinela").first.click()
        page.wait_for_url("**/recommendations/**", timeout=WAIT)
        page.wait_for_load_state("networkidle")
        recommendation = page.url
        for mode in ERROR_MODES:
            set_mode(mode)
            began = time.perf_counter()
            before = stub.calls
            page.goto(recommendation)
            page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="Wyjaśnij innymi słowami (AI)").click()
            page.locator("#explain-area .job").wait_for(state="attached", timeout=WAIT)
            page.wait_for_function("!document.querySelector('#explain-area .job')", timeout=WAIT)
            page.wait_for_load_state("networkidle")
            d.shot(f"explain_{mode}", full=True)
            area = page.locator("#explain-area .callout")
            shown = area.first if area.count() else page.locator(".review-block").first
            d.note(
                kind="error_scenario",
                form="explain",
                mode=mode,
                shown=text_of(shown),
                model_calls=stub.calls - before,
                seconds=round(time.perf_counter() - began, 1),
            )
        pages = pages_of(d, [project])
        write_log(out / "errors-log.json", d.log)
        context.close()
    stub.stop()
    result = sweep(data, server_log, pages)
    d.note(kind="sweep", **result)
    write_log(out / "errors-log.json", d.log)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("provider", choices=(*PROVIDERS, "errors"))
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "qa" / "ai")
    parser.add_argument("--flows", default="list,prose,message")
    parser.add_argument("--wait", type=int, default=WAIT // 1000, help="seconds for one AI answer")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(env=language_env("pl"))
        code = error_scenarios(args, browser) if args.provider == "errors" else run(args, browser)
        browser.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
