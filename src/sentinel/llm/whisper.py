"""Speech to text with Groq's Whisper (WP14, ADR-0031): one call per recording, no cache, no log.

A recording goes to Groq's OpenAI-compatible transcription endpoint as multipart form data built
with the standard library, with its language and a vocabulary prompt (the names a manager is
likely to say); the text and the length of the audio come back to the caller, which shows the
text to the person who spoke and keeps neither the audio nor the text (CLAUDE.md invariant 7).
Unlike a model call of `sentinel.llm`, a transcription is not cached: a cache would keep what was
said. The key is a `Secret`: it never appears in a message, an exception or a log.
"""

import secrets
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sentinel.llm.core import LlmError
from sentinel.llm.http import Transport, urllib_transport
from sentinel.llm.secrets import Secret

WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3-turbo"
MAX_PROMPT_CHARS = 600  # Whisper reads at most 224 tokens of prompt (Groq documentation)
TIMEOUT_S = 60.0
EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav"}
EXTENSIONS |= {"audio/mpeg": "mp3", "audio/x-wav": "wav", "audio/aac": "m4a"}


class TranscriptionError(LlmError):
    """The provider could not transcribe a recording; `status` is its HTTP status, if any."""


@dataclass(frozen=True)
class Transcript:
    """What was said, the audio's length as the provider measured it, and the model."""

    text: str
    seconds: float | None
    model: str


class Transcriber(Protocol):
    """Speech to text: a recording of `content_type` in `language` with a vocabulary `prompt`."""

    model: str

    def transcribe(
        self, audio: bytes, content_type: str, *, language: str | None, prompt: str = ""
    ) -> Transcript: ...


def multipart(
    fields: Mapping[str, str], file_field: str, filename: str, content_type: str, data: bytes
) -> tuple[bytes, str]:
    """A multipart/form-data body (RFC 7578) with text `fields` and one file, and its
    Content-Type header with the boundary."""
    boundary = f"sentinel-{secrets.token_hex(12)}"
    parts = []
    for name, value in fields.items():
        part = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        parts.append(part.encode())
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
    )
    parts.append(head.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def base_type(content_type: str) -> str:
    """The media type of a Content-Type header without its parameters ("audio/webm")."""
    return content_type.split(";", 1)[0].strip().lower()


class GroqWhisper:
    """Groq's Whisper (`whisper-large-v3-turbo`), called once per recording without retries: a
    person waits, and a failure is said at once (ADR-0028)."""

    def __init__(
        self,
        api_key: Secret,
        *,
        model: str = WHISPER_MODEL,
        url: str = WHISPER_URL,
        timeout_s: float = TIMEOUT_S,
        transport: Transport = urllib_transport,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.url = url
        self.timeout_s = timeout_s
        self.transport = transport

    def transcribe(
        self, audio: bytes, content_type: str, *, language: str | None, prompt: str = ""
    ) -> Transcript:
        media = base_type(content_type)
        fields = {"model": self.model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            fields["language"] = language
        if prompt:
            fields["prompt"] = prompt[:MAX_PROMPT_CHARS]
        body, header = multipart(
            fields, "file", f"recording.{EXTENSIONS.get(media, 'webm')}", media, audio
        )
        headers = {
            "Authorization": f"Bearer {self.api_key.reveal()}",
            "Content-Type": header,
            "Accept": "application/json",
            "User-Agent": "sentinel-research/0.1",  # as the chat clients: Groq refuses urllib's
        }
        reply = self.transport("POST", self.url, body=body, headers=headers, timeout=self.timeout_s)
        if reply.status != 200:
            # The body of an error may quote the request; only the status is kept.
            raise TranscriptionError(f"Groq answered HTTP {reply.status}", status=reply.status)
        data = reply.json()
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str):
            raise TranscriptionError("Groq's answer has no text")
        duration = data.get("duration")
        seconds = float(duration) if isinstance(duration, int | float) else None
        return Transcript(" ".join(text.split()), seconds, self.model)


def silent_wav(seconds: float = 1.0, rate: int = 16_000) -> bytes:
    """A WAV of a quiet tone, for a connection test of transcription."""
    frames = int(seconds * rate)
    samples = b"".join(struct.pack("<h", 200 if (i // 40) % 2 else -200) for i in range(frames))
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(samples),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        rate,
        rate * 2,
        2,
        16,
        b"data",
        len(samples),
    )
    return header + samples
