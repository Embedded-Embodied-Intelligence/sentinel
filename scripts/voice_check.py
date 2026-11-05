"""The WP14 check of the owner's check-in message spoken and written, with the live models.

The recording of the owner's message (`tests/fixtures/owner_message_pl.wav`: 15 s, 16 kHz mono,
made by Windows' Polish voice "Microsoft Paulina Desktop" through System.Speech from the text of
`docs/qa/ai/messages-pl.jsonl`, m01) is written out by Groq's Whisper (whisper-large-v3-turbo)
and read by gpt-oss-120b (OpenRouter, pinned to Groq): first through the services, then in the
browser as a remote tester does task 3 of the usability test in demo mode, by message and by
voice, with Chromium's fake microphone playing the recording. It records the timings (recording
length to the text in the box, the reading) and the items of each review, and saves the reports.

    uv run python scripts/voice_check.py      # about 2 min, well under 0.01 USD

The keys come from `.env` through `sentinel.llm.secrets` and are never printed; the application
keeps no prompt, no audio and no transcript. The results go to docs/qa/ai/voice-check.json.
"""

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import time
from datetime import UTC, date
from pathlib import Path
from typing import Any

from sentinel.app.config import DEMO_CONFIG, AppConfig, load_config
from sentinel.app.llm import LlmSettingsUpdate
from sentinel.app.services import Services
from sentinel.experiments.runs import derive_seed
from sentinel.llm.secrets import load_secret

ROOT = Path(__file__).resolve().parents[1]
RECORDING = ROOT / "tests" / "fixtures" / "owner_message_pl.wav"
OUT = ROOT / "docs" / "qa" / "ai" / "voice-check.json"
REPORT_DATE = date(2026, 11, 4)
MODEL = "openai/gpt-oss-120b"
WAIT = 90_000  # ms for an answer of the AI


def module(name: str, path: Path) -> Any:
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


evaluation = module("messages_eval", ROOT / "scripts" / "messages_eval.py")
logs = module("usability_logs", ROOT / "scripts" / "usability_logs.py")
e2e = module("e2e_env", ROOT / "tests" / "e2e_env.py")


def configure(services: Services, openrouter: str, groq: str) -> None:
    services.llm.update(
        LlmSettingsUpdate(provider="openrouter", model=MODEL, api_key=openrouter, groq_key=groq)
    )


def usage(*folders: Path) -> dict[str, Any]:
    found = [evaluation.usage(folder) for folder in folders]
    return {key: round(sum(f[key] for f in found), 6) for key in found[0]}


def services_part(data: Path, owner: dict[str, Any], keys: tuple[str, str]) -> dict[str, Any]:
    """The recording written out and read through the services, as the pages call them."""
    services = Services(AppConfig(data_dir=data, inline_jobs=True))
    configure(services, *keys)
    project = evaluation.usability_project()
    names = [p.name for p in project.definition.team] + [t.name for t in project.definition.tasks]
    began = time.perf_counter()
    said = services.llm.transcribe(
        RECORDING.read_bytes(), "audio/wav", language="pl", vocabulary=", ".join(names)
    )
    written = time.perf_counter()
    seed = derive_seed(project.definition.settings.seed, "llm", "message", said.text)
    draft = services.llm.read_message(project, said.text, REPORT_DATE, seed)
    read = time.perf_counter()
    services.close()
    found = evaluation.review_items(project, draft)
    scored = evaluation.score(evaluation.expected_items(owner), found)
    return {
        "recording_s": said.seconds,
        "transcription_s": round(written - began, 2),
        "transcript": said.text,
        "reading_s": round(read - written, 2),
        "items": [f.show() for f in found],
        "exact": scored["exact"],
        "expected": scored["expected"],
        "wrong_dates": scored["wrong_dates"],
    }


def browser_part(data: Path, owner: dict[str, Any], settings: Path) -> dict[str, Any]:
    """Task 3 of the usability test in demo mode, by message and by voice."""
    from playwright.sync_api import expect, sync_playwright

    shutil.copy(settings, data / "settings.json")
    config = load_config(ROOT / DEMO_CONFIG, data_dir=data, secure_cookies=False)
    runs: dict[str, Any] = {}
    server = e2e.serve(config)
    site = next(server)
    try:
        with sync_playwright() as playwright:
            fake = f"--use-file-for-fake-audio-capture={RECORDING}%noloop"
            args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", fake]
            browser = playwright.chromium.launch(env=e2e.chromium_env(), args=args)
            context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="pl-PL")
            context.set_default_timeout(30_000)
            page = context.new_page()
            for code, way in (("P1", "message"), ("P2", "voice")):
                page.goto(site.base + "/")
                create_project(page, f"{code} Aplikacja rezerwacji wizyt")
                page.get_by_role("link", name="Raport statusu").first.click()
                page.get_by_label("Stan na koniec dnia").fill(REPORT_DATE.isoformat())
                box = page.locator("#message")
                run: dict[str, Any] = {}
                if way == "message":
                    box.fill(owner["text"])
                else:
                    page.get_by_role("button", name="Nagraj głosem").click()
                    began = time.perf_counter()
                    expect(page.locator("[data-voice-live]")).to_be_visible()
                    page.wait_for_timeout(16_000)  # the recording lasts 15 s
                    page.get_by_role("button", name="Zatrzymaj").click()
                    stopped = time.perf_counter()
                    expect(box).not_to_have_value("", timeout=WAIT)
                    shown = time.perf_counter()
                    run |= {
                        "recorded_s": round(stopped - began, 1),
                        "stop_to_text_s": round(shown - stopped, 2),
                        "transcript": box.input_value(),
                        "status": page.locator("[data-voice-status]").inner_text(),
                    }
                began = time.perf_counter()
                page.get_by_role("button", name="Przetwórz wiadomość").click()
                items = page.locator("#message-result .confirm-list li")
                expect(items.first).to_be_visible(timeout=WAIT)
                run["reading_s"] = round(time.perf_counter() - began, 2)
                run["review"] = [items.nth(i).inner_text() for i in range(items.count())]
                workshop = page.locator("fieldset.task-row", has_text="Warsztat z klientem")
                api = page.locator("fieldset.task-row", has_text="Baza danych i API")
                run["rows"] = {
                    "workshop_done": workshop.get_by_label("Gotowe", exact=True).is_checked(),
                    "workshop_finish": workshop.get_by_label("Zakończone dnia").input_value(),
                    "api_in_progress": api.get_by_label("W toku").is_checked(),
                    "api_percent": api.get_by_label("Wykonana część").input_value(),
                }
                page.get_by_role("button", name="Zapisz raport").click()
                page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=WAIT)
                run["saved"] = True
                runs[way] = run
            browser.close()
        text = logs.export(config.database, "P1", UTC) or ""
        runs["log"] = [
            line.strip()
            for line in text.splitlines()
            if "Recorded a message" in line or "Status report" in line or "status report" in line
        ]
    finally:
        next(server, None)
    return runs


def create_project(page: Any, name: str) -> None:
    """Task 1 of the protocol, as in tests/test_ui_usability.py."""
    folder = ROOT / "docs" / "usability"
    team = (folder / "zespol-testowy.txt").read_text("utf-8").strip()
    page.get_by_role("link", name="Nowy projekt").first.click()
    page.get_by_label("Nazwa projektu").fill(name)
    page.get_by_label("Data rozpoczęcia").fill("2026-11-02")
    page.get_by_label("Termin", exact=True).fill("2026-12-04")
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url(re.compile(r"/setup/team$"))
    page.get_by_text("Wklej listę osób").click()
    page.get_by_label("Jedna osoba w wierszu: imię, rola").fill(team)
    page.get_by_role("button", name="Dodaj te osoby").click()
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url(re.compile(r"/setup/tasks$"))
    page.get_by_role("link", name="Zaimportuj arkusz").click()
    page.get_by_label("Plik arkusza (CSV)").set_input_files(str(folder / "projekt-testowy.csv"))
    page.get_by_role("button", name="Importuj zadania").click()
    page.wait_for_url(re.compile(r"tab=manual"))
    page.get_by_role("button", name="Utwórz plan").click()
    page.wait_for_url(re.compile(r"flash=plan_ready"), timeout=120_000)


def main() -> int:
    openrouter = load_secret("OPENROUTER_API_KEY")
    groq = load_secret("GROQ_API_KEY")
    if openrouter is None or groq is None:
        print("OPENROUTER_API_KEY and GROQ_API_KEY must be set", file=sys.stderr)
        return 2
    owner = evaluation.read_cases(None, ["m01"])[0]
    keys = (openrouter.reveal(), groq.reveal())
    with tempfile.TemporaryDirectory() as tmp:
        first, second = Path(tmp) / "services", Path(tmp) / "demo"
        first.mkdir()
        second.mkdir()
        results: dict[str, Any] = {"model": MODEL, "transcription": "whisper-large-v3-turbo"}
        results["services"] = services_part(first, owner, keys)
        results["browser"] = browser_part(second, owner, first / "settings.json")
        results["usage"] = usage(first, second)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results["services"], ensure_ascii=False))
    print(json.dumps(results["usage"]), "->", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
