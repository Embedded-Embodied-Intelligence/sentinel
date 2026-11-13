"""Finanse (v3 spec section 8; spec section 11.9): the portfolio's figures, computed by code from
each live project's budget, cost so far and forecast, and the budget requests that only a
person approves.

A request moves `amount` cost units from one live project's budget to another's. It is pending
until a person approves or rejects it; an approved request is applied if both projects still
exist as live projects with a plan and the source keeps at least what it has spent, as two
definition changes that carry the request (the log shows them); otherwise it is recorded as not
applied, with its reason. The model takes no part in it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_REASON = 300
RequestStatus = Literal["pending", "approved", "rejected", "not_applied"]
NotApplied = Literal["missing", "no_plan", "simulator", "below_spent"]


class BudgetMove(BaseModel):
    """The request a budget change applies (kept in the definition change, WP20)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: str
    source: str  # project names as they were
    target: str
    amount: float = Field(gt=0, allow_inf_nan=False)
    reason: str = Field(default="", max_length=MAX_REASON)


@dataclass(frozen=True)
class Line:
    """A project's row of the portfolio, in cost units; `chance` is the share of the forecast's
    worlds within the budget (None for a finished project, whose cost is final)."""

    id: str
    name: str
    budget: float
    spent: float
    forecast: float
    chance: float | None
    person_days: bool

    @property
    def deviation(self) -> float:
        return self.forecast - self.budget

    @property
    def share(self) -> float:
        return self.deviation / self.budget if self.budget else 0.0


class Request(BaseModel):
    """A budget request and its fate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    source: str  # project ids
    target: str
    source_name: str
    target_name: str
    amount: float = Field(gt=0, allow_inf_nan=False)
    reason: str = Field(default="", max_length=MAX_REASON)
    status: RequestStatus = "pending"
    filed: datetime
    decided: datetime | None = None
    why: NotApplied | None = None
    spent: float | None = None  # the source's cost so far, for "below_spent"


def new_request(request_id: str, source: Line, target: Line, amount: float, reason: str) -> Request:
    """A pending request, or ValueError with the code of the page's message."""
    if source.id == target.id:
        raise ValueError("budget_same")
    if not amount > 0:
        raise ValueError("budget_amount")
    return Request(
        id=request_id,
        source=source.id,
        target=target.id,
        source_name=source.name,
        target_name=target.name,
        amount=amount,
        reason=" ".join(reason.split())[:MAX_REASON],
        filed=datetime.now(UTC),
    )


def applicable(
    request: Request, lines: Mapping[str, Line], kinds: Mapping[str, str]
) -> NotApplied | None:
    """Why an approved request cannot be applied now, or None when it can."""
    for project in (request.source, request.target):
        if project not in kinds:
            return "missing"
        if kinds[project] != "live":
            return "simulator"
        if project not in lines:
            return "no_plan"
    if lines[request.source].budget - request.amount < lines[request.source].spent:
        return "below_spent"
    return None


def decided(
    request: Request,
    status: RequestStatus,
    why: NotApplied | None = None,
    spent: float | None = None,
) -> Request:
    return request.model_copy(
        update={"status": status, "decided": datetime.now(UTC), "why": why, "spent": spent}
    )


def as_payload(request: Request) -> dict[str, Any]:
    return request.model_dump(mode="json")
