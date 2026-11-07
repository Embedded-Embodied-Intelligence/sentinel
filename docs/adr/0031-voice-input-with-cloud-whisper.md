# ADR-0031: Voice input with Groq's Whisper, nothing of a recording kept

- Status: accepted
- Date: 2026-11-05
- WP: WP14

## Context

The owner's rehearsal of the usability test asked for speaking a status report instead of typing
it. The pages already send a typed message to the configured AI (spec section 11.3); a spoken one
needs speech to text first. The machines the app targets have 4 CPU cores and no usable GPU
(`docs/infra/environment.md`), the project may not add runtime dependencies, the demo has a daily
AI cap, and nothing a manager writes about absences may be stored (invariant 7).

## Decision

A microphone button beside the message box of the check-in and of "describe the project" records
in the browser (MediaRecorder, at most 90 s, no new script), sends the audio as the body of one
request, and the server has Groq's `whisper-large-v3-turbo` write it out (language of the page,
the team's and the tasks' names as the vocabulary prompt). The text goes back into the box for
the person to read and correct; nothing is processed until they press "Process the message". The
audio is held in memory only, never cached, logged or written to disk; the text is not stored
either (a saved report keeps only the items confirmed). The demo's request log keeps that a
recording was written out and its length; the daily AI cap counts it. The button shows only with
a Groq key (the provider's own, or one for recordings on Settings) in a secure page.

## Alternatives considered

| Option | Why not now |
| --- | --- |
| Local Whisper (whisper.cpp, faster-whisper) | A new runtime dependency and a model download; on the 4-core server `large-v3-turbo` runs at about real time or slower, so a 30 s report waits 30–60 s, against 0.5 s on Groq; a future option for a company that must keep audio inside |
| The browser's Web Speech API | Chrome sends the audio to Google without a choice of provider, Firefox has none; no vocabulary prompt |
| Record/replay cache as for model calls (invariant 3) | A cache would keep what was said; a transcription makes no decision and its text is checked by the person before anything uses it |
| Multipart upload | Starlette spools a large upload to a temporary file on disk; the raw body is read in memory with a limit |
| A job, as for model calls | A job's result is stored in the database; the answer takes about a second |

## Consequences

The audio goes to Groq in the USA, as a typed message goes to a cloud model; the guides and the
deploy guide say so, and Settings offers to test recordings. Groq's free tier limits apply; a
failure says plainly what to do (no microphone permission, no key, provider down, too long). The
app now has a second cloud call outside the record/replay cache, kept in `sentinel.llm.whisper`
and used only by the pages, never by a study.

## Update (WP15): live preview and five minutes in the v2 interface

The v2 voice component (`docs/design/v2-spec.md`, section 9) records up to a technical cap of
5 minutes (a warning at 4:30) and shows a live preview: about every 3 s the audio recorded so far
(the MediaRecorder's chunks from the start, a valid file) goes to `POST /v2/transcribe?preview=1`,
one request in flight at a time and a tick skipped while one runs; the text appears grey at the
cursor in a mirror of the box. On ✓ (or Enter) the whole recording is written out once more and
replaces the preview as ordinary text; on ✕ (or Esc) the recording and the dictated span go, the
text around it stays. A preview does not count against the demo's daily AI cap and is not logged
with a length; the final transcription is counted and logged as in WP14. A refused preview (429
from Groq's free tier, 20 requests a minute and 7,200 audio seconds an hour) keeps the recording
going with "Podgląd chwilowo niedostępny". Sending the growing recording rather than only its
new part keeps every request a valid audio file at the price of more audio seconds: a 2-minute
recording sends about 40 minutes of audio in previews, so long dictations may meet the hourly
limit, after which only the final transcription runs. Nothing more is stored.
