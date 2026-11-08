"""Recordings for a message box (WP14, ADR-0031): a recording becomes text in the box through
Groq's Whisper, with the team's and the tasks' names as its vocabulary; the audio and the text
are stored nowhere, the demo's request log keeps only the recording's length, the daily AI cap
counts it, failures are said plainly, and the microphone shows only with a Groq key."""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from app_cases import small
from fastapi.testclient import TestClient

from sentinel.app.api import create_app
from sentinel.app.config import AppConfig, Limits
from sentinel.app.llm import voice_failure
from sentinel.app.security import CSRF_COOKIE
from sentinel.app.services import Services
from sentinel.llm.http import HttpReply, TransportError
from sentinel.llm.secrets import Secret
from sentinel.llm.whisper import GroqWhisper, Transcript, TranscriptionError, silent_wav

ROOT = Path(__file__).resolve().parents[1]
SAID = "Ada od jutra jest nieobecna i wraca w poniedziałek 16 listopada."
WAV = silent_wav(0.5)
KEY = "test-key-for-recordings"  # pragma: allowlist secret


class Scripted:
    """A transcriber that writes out every recording as `text` and keeps what it was given."""

    model = "scripted"

    def __init__(self, text: str = SAID) -> None:
        self.text = text
        self.calls: list[tuple[int, str, str | None, str]] = []

    def transcribe(
        self, audio: bytes, content_type: str, *, language: str | None, prompt: str = ""
    ) -> Transcript:
        self.calls.append((len(audio), content_type, language, prompt))
        return Transcript(self.text, 15.1, self.model)


def app(
    tmp_path: Path,
    scripted: Scripted,
    *,
    groq_key: str | None = KEY,
    demo: bool = True,
    cap: int | None = None,
    limits: Limits | None = None,
) -> TestClient:
    settings: dict[str, Any] = {"provider": "ollama"}
    if groq_key:
        settings["groq_key"] = groq_key
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "settings.json").write_text(json.dumps({"llm": settings}), encoding="utf-8")
    if limits is None:
        limits = Limits(llm_calls_per_day=cap) if cap is not None else Limits()
    config = AppConfig(
        data_dir=tmp_path,
        demo=demo,
        inline_jobs=True,
        showcase=False,
        request_log=demo,
        llm="capped" if cap is not None else "on",
        limits=limits,
    )
    services = Services(config, transcriber=lambda key: scripted)
    return TestClient(create_app(config, services))


def project(client: TestClient) -> tuple[str, dict[str, str]]:
    client.get("/")
    csrf = {"X-CSRF-Token": client.cookies[CSRF_COOKIE]}
    created = client.post("/api/projects", json=small().model_dump(mode="json"), headers=csrf)
    pid = created.json()["id"]
    assert client.post(f"/api/projects/{pid}/plan", headers=csrf).status_code in (200, 202)
    return pid, csrf


def send(client: TestClient, pid: str, csrf: dict[str, str], body: bytes, **headers: str) -> Any:
    sent = {"content-type": "audio/webm", "x-recording-seconds": "15.0", **csrf, **headers}
    return client.post(f"/projects/{pid}/transcribe", content=body, headers=sent)


def test_the_whisper_request_carries_the_language_the_vocabulary_and_the_recording() -> None:
    sent: dict[str, Any] = {}

    def transport(
        method: str, url: str, *, body: bytes | None, headers: Any, timeout: float
    ) -> Any:
        sent.update(method=method, url=url, body=body, headers=dict(headers))
        answer = {"text": "  Ada od jutra\n jest nieobecna. ", "duration": 3.5, "segments": []}
        return HttpReply(200, json.dumps(answer).encode())

    whisper = GroqWhisper(Secret(KEY), transport=transport)
    found = whisper.transcribe(b"RIFFdata", "audio/webm;codecs=opus", language="pl", prompt="Ada")
    assert found == Transcript("Ada od jutra jest nieobecna.", 3.5, "whisper-large-v3-turbo")
    body = sent["body"].decode("latin-1")
    for field, value in (
        ("model", "whisper-large-v3-turbo"),
        ("language", "pl"),
        ("prompt", "Ada"),
    ):
        assert f'name="{field}"\r\n\r\n{value}\r\n' in body
    assert 'name="response_format"\r\n\r\nverbose_json' in body
    assert 'filename="recording.webm"\r\nContent-Type: audio/webm\r\n\r\nRIFFdata' in body
    assert sent["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert sent["headers"]["User-Agent"] and sent["url"].endswith("/audio/transcriptions")

    def refusing(status: int) -> Any:
        return lambda *args, **kwargs: HttpReply(status, b'{"error": {"message": "x"}}')

    codes = {}
    for status in (401, 400, 429, 503):
        with pytest.raises(TranscriptionError) as caught:
            GroqWhisper(Secret(KEY), transport=refusing(status)).transcribe(
                b"x", "audio/webm", language="pl"
            )
        assert KEY not in str(caught.value)
        codes[status] = voice_failure(caught.value).code
    assert codes == {401: "voice_key", 400: "voice_audio", 429: "voice_quota", 503: "voice_failed"}
    assert voice_failure(TransportError("down")).code == "voice_unreachable"


def test_a_recording_becomes_text_for_the_box_and_nothing_of_it_is_stored(tmp_path: Path) -> None:
    scripted = Scripted()
    with app(tmp_path, scripted) as client:
        pid, csrf = project(client)
        answer = send(client, pid, csrf, WAV + b"unique-audio-bytes")
        assert answer.status_code == 200, answer.text
        assert answer.json() == {"text": SAID, "seconds": 15.1}
        services = client.app.state.services  # type: ignore[attr-defined]
        store = services.store
    [(size, kind, language, vocabulary)] = scripted.calls
    assert (size, kind, language) == (len(WAV) + 18, "audio/webm", "pl")
    assert vocabulary == "Ada, Ben, Cleo, Tom, Build API, Build UI, Test"
    with sqlite3.connect(store.path) as db:
        dump = "\n".join(db.iterdump())
        usage = db.execute("SELECT SUM(count) FROM usage WHERE key = 'llm'").fetchone()[0]
    assert "nieobecna" not in dump and "unique-audio-bytes" not in dump
    assert usage == 1  # the daily AI cap counts the recording
    cached = list((tmp_path / "llm_cache").glob("*")) if (tmp_path / "llm_cache").exists() else []
    assert cached == []
    session = next(iter(sqlite3.connect(store.path).execute("SELECT id FROM sessions")))[0]
    logged = [(r.method, r.path, r.status, r.seconds) for r in store.requests(session)]
    assert ("POST", "/projects/{project_id}/transcribe", 200, 15.1) in logged
    assert all(r[3] is None for r in logged if r[1] != "/projects/{project_id}/transcribe")


def test_recordings_are_refused_plainly(tmp_path: Path) -> None:
    with app(tmp_path / "on", Scripted(), cap=2) as client:
        pid, csrf = project(client)
        kinds = {
            "text": send(client, pid, csrf, b"hello", **{"content-type": "text/plain"}),
            "long": send(client, pid, csrf, WAV, **{"x-recording-seconds": "120"}),
            "empty": send(client, pid, csrf, b""),
        }
        assert {k: r.status_code for k, r in kinds.items()} == {
            "text": 415,
            "long": 413,
            "empty": 422,
        }
        assert "najwyżej 90 sekund" in kinds["long"].json()["error"]
        assert send(client, pid, csrf, WAV).status_code == 200
        assert send(client, pid, csrf, WAV).status_code == 200
        capped = send(client, pid, csrf, WAV)
        assert capped.status_code == 429 and "limit" in capped.json()["error"]
    with app(tmp_path / "off", Scripted(), groq_key=None) as client:
        pid, csrf = project(client)
        refused = send(client, pid, csrf, WAV)
        assert refused.status_code == 503
        assert refused.json()["error"] == "Nagrania wymagają klucza Groq w Ustawieniach."
    with app(tmp_path / "quiet", Scripted(text="")) as client:
        pid, csrf = project(client)
        assert send(client, pid, csrf, WAV).json()["error"].startswith("W nagraniu nic nie")


def test_the_microphone_shows_only_with_a_groq_key(tmp_path: Path) -> None:
    for key, shown in ((KEY, True), (None, False)):
        with app(tmp_path / str(shown), Scripted(), groq_key=key) as client:
            pid, _ = project(client)
            page = client.get(f"/projects/{pid}/checkin").text
            assert ("data-voice " in page) == shown
            assert (f'data-voice-url="/projects/{pid}/transcribe"' in page) == shown
            assert "Przetwórz wiadomość" in page  # typing stays
            describe = client.get(f"/projects/{pid}/setup/tasks", params={"tab": "describe"}).text
            assert ('data-voice-target="text"' in describe) == shown


def test_the_settings_keep_a_groq_key_for_recordings_and_test_them(tmp_path: Path) -> None:
    scripted = Scripted()
    with app(tmp_path, scripted, groq_key=None, demo=False) as client:
        client.get("/")
        csrf = {"X-CSRF-Token": client.cookies[CSRF_COOKIE], "HX-Request": "true"}
        form = {"provider": "ollama", "groq_key": KEY}
        client.post("/settings", data=form, headers=csrf)
        stored = json.loads((tmp_path / "settings.json").read_text("utf-8"))["llm"]
        assert stored["groq_key"] == KEY
        assert client.get("/api/settings/llm").json()["voice"] is True
        page = client.get("/settings").text
        assert KEY not in page and "Klucz Groq do nagrań" in page
        started = client.post("/settings/test-voice", data={"provider": "ollama"}, headers=csrf)
        job = re.search(r'hx-get="(/jobs/[^"]+)"', started.text)
        assert job is not None
        done = client.get(job.group(1).replace("&amp;", "&"), headers=csrf).text
        assert "Nagrania działają" in done and "scripted" in done
        client.post("/settings", data={"provider": "ollama", "forget_groq_key": "on"}, headers=csrf)
        stored = json.loads((tmp_path / "settings.json").read_text("utf-8"))["llm"]
        assert "groq_key" not in stored
