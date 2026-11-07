"""The v2 voice endpoint (docs/design/v2-spec.md, section 9; ADR-0031): a recording, or the part of
a recording still running for the live preview, written out by Groq's Whisper. The audio is read
in memory up to its limit and dropped; the text goes back as JSON and is stored nowhere. A
preview does not count against the demo's daily AI cap and is not logged with a length."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from sentinel.app.errors import AppError
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import parse_number
from sentinel.app.ui.v2.shell import PREFIX, texts
from sentinel.llm.whisper import base_type

VOICE_CAP_S = 300  # the technical cap of a recording (section 9), warned at 4:30 by the page
VOICE_SLACK_S = 5
MAX_AUDIO_BYTES = 12 * 1024 * 1024  # five minutes in a browser's codecs, with room
VOICE_STATUS = {"invalid": 422, "limit": 429, "unavailable": 503, "not_found": 404}


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    @routes.post(PREFIX + "/transcribe")
    async def transcribe(request: Request) -> Response:
        t = texts(request)
        preview = request.query_params.get("preview") == "1"
        project = request.query_params.get("project") or None

        def refused(code: str, status: int, **params: object) -> Response:
            return JSONResponse({"error": t.msg(code, **params)}, status_code=status)

        kind = base_type(request.headers.get("content-type", ""))
        if not kind.startswith("audio/"):
            return refused("voice_type", 415)
        claimed = parse_number(request.headers.get("x-recording-seconds", ""))
        limit = VOICE_CAP_S + VOICE_SLACK_S
        if claimed is not None and claimed > limit:
            return refused("voice_too_long", 413, seconds=VOICE_CAP_S)
        if int(request.headers.get("content-length") or 0) > MAX_AUDIO_BYTES:
            return refused("voice_too_long", 413, seconds=VOICE_CAP_S)
        audio = bytearray()
        async for chunk in request.stream():
            audio += chunk
            if len(audio) > MAX_AUDIO_BYTES:
                return refused("voice_too_long", 413, seconds=VOICE_CAP_S)
        if not audio:
            return refused("voice_empty", 422)
        try:
            found = await run_in_threadpool(
                lambda: services.transcribe(
                    ui.session(request),
                    project,
                    bytes(audio),
                    kind,
                    ui.language(request),
                    preview=preview,
                )
            )
        except AppError as exc:
            return JSONResponse(
                {"error": t.error(exc)}, status_code=VOICE_STATUS.get(exc.kind, 503)
            )
        finally:
            audio.clear()
        seconds = found.seconds if found.seconds is not None else claimed
        if seconds is not None and not preview:
            request.state.log_seconds = round(seconds, 1)
        if seconds is not None and seconds > limit:
            return refused("voice_too_long", 413, seconds=VOICE_CAP_S)
        return JSONResponse({"text": found.text, "seconds": seconds})

    return routes
