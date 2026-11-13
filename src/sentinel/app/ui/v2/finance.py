"""Finanse of the group "Praca" (docs/design/v3-spec.md, section 8; spec section 11.9; WP20):
the portfolio in work-days computed by code with a bar per project; "Streszczenie dla zarządu
(AI)" written by the model from a fact sheet that code built, shown with the fact guard; and
"Przesuń budżet", a request that only a person approves, with a confirmation step."""

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import finance
from sentinel.app.errors import AppError
from sentinel.app.messages import render
from sentinel.app.planning import half_up
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form
from sentinel.app.ui.v2.numbers import per_hundred, state_of
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.interpret.facts import Names, check

BASE = PREFIX + "/finance"
STATES = {"good": "within", "warn": "at_risk", "bad": "over"}
TONES = {"within": "good", "at_risk": "warn", "over": "bad", "overrun": "bad"}


@dataclass(frozen=True)
class Row:
    """A project's row as the page shows it: whole units, the deviation with its sign and share,
    the chance in 100 within the budget, the state and the bar's widths (% of the row's
    scale)."""

    id: str
    name: str
    budget: int
    spent: int
    forecast: int
    deviation: str
    share: str
    chance: int | None
    state: str
    tone: str
    spent_w: float
    forecast_w: float
    budget_x: float


def whole(value: float) -> int:
    return int(half_up(value))


def signed(value: int) -> str:
    return f"+{value}" if value > 0 else (f"\u2212{-value}" if value < 0 else "0")


def row_of(line: finance.Line) -> Row:
    n = None if line.chance is None else per_hundred(line.chance)
    if line.spent > line.budget:
        state = "overrun"
    elif n is None:
        state = "within"
    else:
        state = STATES[state_of(n)]
    scale = max(line.budget, line.forecast, line.spent) or 1.0
    return Row(
        id=line.id,
        name=line.name,
        budget=whole(line.budget),
        spent=whole(line.spent),
        forecast=whole(line.forecast),
        deviation=signed(whole(line.deviation)),
        share=signed(whole(100 * line.share)),
        chance=n,
        state=state,
        tone=TONES[state],
        spent_w=round(100 * line.spent / scale, 1),
        forecast_w=round(100 * line.forecast / scale, 1),
        budget_x=round(100 * line.budget / scale, 1),
    )


def sheet(t: TextsV2, rows: list[Row]) -> str:
    """The fact sheet of the portfolio, written by code in the page's language: one line per
    project and the totals (the summary's only source)."""
    lines = [
        t(
            "v2.fin.sheet_line",
            project=r.name,
            budget=r.budget,
            spent=r.spent,
            forecast=r.forecast,
            deviation=r.deviation,
            share=r.share,
            chance="–" if r.chance is None else r.chance,
        )
        for r in rows
    ]
    budget, spent, forecast = (
        sum(getattr(r, k) for r in rows) for k in ("budget", "spent", "forecast")
    )
    lines.append(
        t(
            "v2.fin.sheet_total",
            budget=budget,
            spent=spent,
            forecast=forecast,
            deviation=signed(forecast - budget),
        )
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class RequestRow:
    request: finance.Request
    line: str
    filed: str
    decided: str | None
    why: str | None


def request_rows(t: TextsV2, requests: list[finance.Request]) -> list[RequestRow]:
    rows = []
    for r in requests:
        why = None
        if r.why is not None:
            spent = "" if r.spent is None else str(whole(r.spent))
            why = t(f"v2.fin.why.{r.why}", source=r.source_name, spent=spent)
        rows.append(
            RequestRow(
                request=r,
                line=t(
                    "v2.fin.line",
                    amount=_amount(r.amount),
                    source=r.source_name,
                    target=r.target_name,
                ),
                filed=t("v2.fin.filed", when=r.filed.astimezone().strftime("%Y-%m-%d %H:%M")),
                decided=None
                if r.decided is None
                else t("v2.fin.decided", when=r.decided.astimezone().strftime("%Y-%m-%d %H:%M")),
                why=why,
            )
        )
    return rows


def _amount(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def values(request: Request, error: str | None = None) -> dict[str, Any]:
        t = texts(request)
        session = ui.session(request)
        lines = services.portfolio(session, ui.language(request))
        rows = [row_of(line) for line in lines]
        return {
            "title": t("v2.fin.title"),
            "nav": "finance",
            "rows": rows,
            "person_days": all(line.person_days for line in lines),
            "total": {
                "budget": sum(r.budget for r in rows),
                "spent": sum(r.spent for r in rows),
                "forecast": sum(r.forecast for r in rows),
                "deviation": signed(sum(r.forecast - r.budget for r in rows)),
            },
            "sheet": sheet(t, rows) if rows else "",
            "requests": request_rows(t, services.budget_requests(session)),
            "available": services.llm.available,
            "error": error,
        }

    @routes.get(BASE)
    def finance_page(request: Request) -> Response:
        return page(ui, request, "finance.html", **values(request))

    @routes.post(BASE + "/summary")
    def summary(request: Request) -> Response:
        data = values(request)
        try:
            job = services.board_summary(ui.session(request), data["sheet"], ui.language(request))
        except AppError as error:
            message = render(error.code, ui.language(request), error.params)
            return page(ui, request, "_fin_summary.html", job=None, failed=message, result=None)
        return page(ui, request, "_fin_summary.html", job=job.id, failed=None, result=None)

    @routes.get(BASE + "/summary")
    def summary_poll(request: Request) -> Response:
        t = texts(request)
        job = services.job(
            ui.session(request), request.query_params.get("job", ""), ui.language(request)
        )
        if job.status in ("queued", "running"):
            return page(ui, request, "_fin_summary.html", job=job.id, failed=None, result=None)
        found = None if job.result is None else services.summary_of(str(job.result.get("summary")))
        if job.status == "failed" or found is None:
            reason = "" if job.error is None else job.error.message
            failed = t("v2.fin.summary_failed", reason=reason)
            return page(ui, request, "_fin_summary.html", job=None, failed=failed, result=None)
        text, model = found
        data = values(request)
        names = Names(projects=tuple(r.name for r in data["rows"]))
        guard = check(data["sheet"], text, language=ui.language(request), names=names)
        result = {"text": text, "model": model, "guard": guard}
        return page(ui, request, "_fin_summary.html", job=None, failed=None, result=result)

    @routes.post(BASE + "/requests")
    async def file(request: Request) -> Response:
        form = await Form.read(request)
        try:
            amount = float(form.get("amount").replace(",", "."))
        except ValueError:
            amount = 0.0
        try:
            services.file_request(
                ui.session(request),
                form.get("source"),
                form.get("target"),
                amount,
                form.get("reason"),
                ui.language(request),
            )
        except AppError as error:
            message = render(error.code, ui.language(request), error.params)
            return page(ui, request, "finance.html", **values(request, message))
        return ui.redirect(request, BASE)

    @routes.get(BASE + "/requests/{request_id}/confirm")
    def confirm(request: Request, request_id: str) -> Response:
        """The confirmation step before an approval (spec section 8)."""
        t = texts(request)
        found = next(
            (r for r in services.budget_requests(ui.session(request)) if r.id == request_id), None
        )
        if found is None:
            raise AppError("request_not_found", "not_found")
        question = t(
            "v2.fin.confirm",
            amount=_amount(found.amount),
            source=found.source_name,
            target=found.target_name,
        )
        return page(ui, request, "_fin_confirm.html", request_id=request_id, question=question)

    @routes.post(BASE + "/requests/{request_id}/{decision}")
    def decide(request: Request, request_id: str, decision: str) -> Response:
        if decision not in ("approve", "reject"):
            raise AppError("request_not_found", "not_found")
        services.decide_request(
            ui.session(request), request_id, decision == "approve", ui.language(request)
        )
        return ui.redirect(request, BASE)

    return routes
