"""Words, numbers and colours of the cockpit (WP8): every label in English and Polish (the
presentation is Polish; LLM texts stay English, CLAUDE.md invariant 3), numbers with a decimal
point or comma, and the palette of the WP4/WP5 figures (`paper_figures`)."""

from collections.abc import Mapping, Sequence
from typing import Literal

from sentinel.dashboard.assemble import DayEvents, Row, Segment
from sentinel.dashboard.world import Forecast
from sentinel.simulation.engine import Substitution

Language = Literal["en", "pl"]
LANGUAGES: tuple[Language, ...] = ("en", "pl")

# Palette and ink of the WP3-WP5 figures; the policies take their slots of those figures.
COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
INK, INK_2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
DEADLINE = COLORS[7]
_SLOTS = {
    "no_reaction": 0,
    "always_substitute": 1,
    "full_resolve": 2,
    "full_resolve_subst": 3,
    "stable_resolve": 4,
    "stable_resolve_subst": 4,
}
_SENTINEL_SLOT = 6
_FALLBACK = COLORS[5]  # the second of two policies with the same slot


def policy_colors(first: str, second: str) -> tuple[str, str]:
    """The colours of the two policies: their figure slots, the second one changed if equal."""
    a, b = (COLORS[_SLOTS.get(name, _SENTINEL_SLOT)] for name in (first, second))
    return a, (_FALLBACK if b == a else b)


# Display names of the policies, those of the WP4/WP5 summaries (`policy_summary.POLICY_LABELS`,
# kept equal by a test; that module loads matplotlib).
POLICY_NAMES: Mapping[str, str] = {
    "no_reaction": "NoReaction",
    "always_substitute": "AlwaysSubstitute",
    "full_resolve": "FullResolve",
    "full_resolve_subst": "FullResolve(subst)",
    "stable_resolve": "StableResolve",
    "stable_resolve_subst": "StableResolve(subst)",
    "sentinel_full": "Sentinel",
    "sentinel_no_ot": "Sentinel no OT",
    "sentinel_gate": "Sentinel Λ=2",
    "sentinel_scalarised": "Sentinel scalarised",
    "sentinel_lambda0": "Sentinel Λ=0",
    "sentinel_lambda1": "Sentinel Λ=1",
    "sentinel_descope": "Sentinel DESCOPE",
    "sentinel_delta03": "Sentinel δ=0.3",
}

ROLES: Mapping[Language, tuple[str, ...]] = {
    "en": ("backend developer", "frontend developer", "tester", "DevOps engineer"),
    "pl": ("programista backendu", "programista frontendu", "tester", "inżynier DevOps"),
}

WORDS: Mapping[Language, Mapping[str, str]] = {
    "en": {
        "title": "Sentinel cockpit",
        "subtitle": "{instance}, replication {replication}, λ_A = {lambda_a}: {first} and "
        "{second} on the same simulated world (common random numbers)",
        "deadline_line": "Deadline D = day {deadline} (δ_D = {delta}, C* = {c_star}, {reference});"
        " budget B = {budget}",
        "ref_opt": "optimum",
        "ref_hrs": "best known",
        "nav_kpis": "Key figures",
        "nav_gantt": "Plan and execution",
        "nav_risk": "Risk",
        "nav_log": "Decision log",
        "nav_howto": "How to read this",
        "nav_provenance": "Provenance",
        "measure": "Measure",
        "kpi_deadline": "Deadline D",
        "kpi_makespan": "Realised makespan C",
        "kpi_on_time": "On time (C ≤ D)",
        "kpi_cost": "Cost / budget B",
        "kpi_changes": "Plan changes (planned starts moved)",
        "kpi_overtime": "Overtime: temporary workers (cost)",
        "kpi_subst": "Substituted crew members",
        "kpi_escalations": "Escalations (approved, deferred)",
        "kpi_deliberations": "Deliberations",
        "kpi_descoped": "Removed activities (DESCOPE)",
        "day_n": "day {day}",
        "days_n": "{days} days",
        "yes": "✓ yes",
        "no_late": "✗ no, {days} days late",
        "no_late_1": "✗ no, 1 day late",
        "truncated": "✗ no, stopped at the day limit",
        "none": "—",
        "gantt_title": "Plan and execution: {policy}",
        "gantt_compare": "Plan and execution: {policy} (open)",
        "gantt_note": "Thin grey bar: baseline plan. Thick bar: realised execution.",
        "legend_plan": "baseline plan",
        "legend_full": "work, full crew",
        "legend_partial": "work, part of the crew absent",
        "legend_paused": "paused, no crew member present",
        "legend_subst": "substitution (SUBST)",
        "legend_temp": "temporary worker in the crew (OVERTIME)",
        "legend_shock": "work increase (D2)",
        "legend_new": "new activity (D3); its row is marked +",
        "legend_absence": "absence of a crew member",
        "legend_idle": "absences of idle workers only",
        "legend_descoped": "removed (DESCOPE)",
        "lane_absences": "absences",
        "lane_work": "work increases",
        "lane_new": "new activities",
        "day": "day",
        "plan_line": "plan: {makespan}",
        "deadline_label": "D = {deadline}",
        "realised_line": "{policy}: {makespan}",
        "risk_title": "Risk over time: {policy}",
        "risk_note_agent": "The agent's own forecast at each of its {n} deliberations.",
        "risk_note_policy": "{policy} makes no forecast; the cockpit computes the same estimate "
        "every {period} days ({n} points).",
        "risk_panel_p": "P(C ≤ D): probability of finishing by the deadline",
        "risk_panel_c": "Makespan forecast: P10–P90 band and median",
        "series_noop": "without action",
        "legend_noop": "forecast without action (NOOP)",
        "legend_chosen_auto": "chosen action, applied at once",
        "legend_chosen_wait": "chosen action, deferred or escalated",
        "legend_target": "target θ_D",
        "legend_band": "P10–P90 of the simulated makespans",
        "legend_median": "median makespan",
        "legend_deadline": "deadline D",
        "target_label": "target {target}",
        "makespan_axis": "makespan [days]",
        "log_title": "Decision log: {policy}",
        "log_none": "{policy} does not deliberate; the decision log shows Sentinel's decisions "
        "only.",
        "filter_text": "Filter",
        "filter_placeholder": "action, event or day",
        "filter_gate": "Gate",
        "filter_all": "all",
        "filter_actions": "only actions other than NOOP",
        "rows_shown": "rows shown",
        "col_day": "Day",
        "col_events": "Events",
        "col_needs": "Needs n_D / n_B",
        "col_chosen": "Chosen (level)",
        "col_p": "p̂ / T̂",
        "col_runner": "Runner-up",
        "col_component": "Deciding component",
        "col_gate": "Gate",
        "col_explanation": "Explanation",
        "gate_auto": "auto",
        "gate_deferred": "deferred",
        "gate_escalated": "escalated",
        "gate_approved": "approved",
        "gate_none": "no action",
        "escalated_to": "escalated → day {day}",
        "discarded": "approval discarded: {label}",
        "ev_absence": "absent: worker {worker} → act. {activity}",
        "ev_return": "back: worker {worker} → act. {activity}",
        "ev_idle": "idle absent: +{count}",
        "ev_work": "work ×{factor}: act. {activity}",
        "ev_new": "new act. {activity}",
        "ev_review": "review",
        "ev_approval": "approval day",
        "badge_template": "template",
        "badge_faithful": "LLM {model}: faithful ✓",
        "badge_unfaithful": "LLM {model}: not faithful ✗ ({details})",
        "badge_invalid": "LLM {model}: {error}",
        "faith_details": "facts {right}/{facts}, chosen action {chosen}, component {component}, "
        "numbers not in the record {numbers}",
        "c_on_time": "P(on time)",
        "c_tardiness": "tardiness",
        "c_scope": "scope",
        "c_budget": "budget",
        "c_stability": "stability",
        "c_level": "level",
        "c_order": "order (tie)",
        "c_racing": "racing",
        "c_utility": "utility",
        "c_needs_met": "needs gate",
        "c_only_candidate": "only candidate",
        "c_approved": "approval",
        "howto_title": "How to read this",
        "provenance_title": "Provenance",
        "p_command": "Command",
        "p_code": "Code",
        "p_clean": "commit {commit}, clean",
        "p_dirty": "commit {commit}, with uncommitted changes",
        "p_nogit": "no git checkout",
        "p_seeds": "Seeds",
        "p_seeds_text": "world seed {seed} = derive_seed({base}, {set}, {instance}, {replication}) "
        "(WP2b), shared by both policies; the agent's rollouts on day t use "
        "derive_seed({seed}, sentinel, t), rollout i derive_seed(that, rollout, i)",
        "p_world": "World",
        "p_world_text": "{instance}: {activities} real activities, {workers} workers; scenario "
        "λ_A = {lambda_a}, E[L] = {mean_absence}, λ_S = {lambda_s}, λ_N = {lambda_n}; durations "
        "PERT({a}, {m}, {b}), λ = {lam}; review period T_r = {period}",
        "p_plan": "Baseline plan",
        "p_plan_text": "{method}, makespan {makespan} ({status})",
        "p_goals": "Deadline and budget",
        "p_goals_text": "D = ⌈(1 + δ_D) C*⌉ = {deadline} with δ_D = {delta} and C* = {c_star} "
        "({reference}); B = {budget} with reserve β = {beta} (spec §1.2)",
        "p_policy": "Policy {policy}",
        "p_sentinel": "Sentinel, rule {rule}, variant {variant}: N₁ = {n1}, N = {n}, "
        "θ_D = {theta}, ε_D = {eps_d}, ε_T = {eps_t}, ε_B = {eps_b}, ε_Δ = {eps_delta}, "
        "Λ = {autonomy}, τ_def = {tau}, δ_h = {delay}, DESCOPE {descope}, T_cp = {tcp}, "
        "CP-SAT seed {cp_seed}",
        "p_baseline": "registry policy {policy}, T_cp = {tcp}, CP-SAT seed {cp_seed}; day limit of "
        "δ_D = {delta} as in the studies",
        "p_explain": "Explanations",
        "p_explain_template": "template, built from each decision record only",
        "p_explain_llm": "{backend} ({model}) through the record/replay cache {cache}; template "
        "for deliberations that did not pass the needs gate",
        "p_software": "Software",
        "p_note": "The page is generated by sentinel dashboard; it holds no timestamps, so the "
        "same command at the same commit writes the same file.",
        "on": "on",
        "off": "off",
        "desc_gantt": "Gantt chart of {rows} activities: baseline plan and realised execution, "
        "with {absences} days with absences, {work} work increases and {new} new activities.",
        "desc_risk": "Forecasts at {n} days; P(C ≤ D) without action from {first} to {last}; "
        "deadline D = {deadline}.",
        "desc_risk_empty": "No forecasts.",
        "tip_absences": "day {day}: {items}",
        "tip_absent_crew": "worker {worker} absent (crew of activity {activity})",
        "tip_absent_idle": "idle workers absent: {count}",
        "tip_work": "day {day}: {items}",
        "tip_work_item": "activity {activity}, remaining work ×{factor}",
        "tip_new": "day {day}: {items}",
        "tip_new_item": "new activity {activity}, p = {duration}",
        "tip_activity": "activity {activity}: p = {duration}, crew {crew}",
        "tip_planned": "activity {activity} planned on days {first}–{last}",
        "tip_segment": "activity {activity}, days {first}–{last}: {present} of {crew} crew members "
        "present",
        "tip_segment_temp": " (with temporary workers)",
        "tip_paused": "days {first}–{last}: paused, no crew member present",
        "tip_temp": "activity {activity}: temporary workers in the crew from day {day}",
        "tip_subst": "day {day}: {replaced} absent crew members of activity {activity} replaced; "
        "+{handover} days of handover",
        "tip_shock": "day {day}: remaining work of activity {activity} ×{factor}",
        "tip_inserted": "day {day}: activity {activity} inserted (D3)",
        "tip_descoped": "day {day}: activity {activity} removed (DESCOPE)",
        "tip_forecast": "day {day}: P(C ≤ D) = {p} without action on {n} rollouts; makespan "
        "P10–P90 {p10}–{p90}, median {p50}",
        "tip_chosen": "day {day}: chosen {label}, P(C ≤ D) = {p} ({gate})",
    },
    "pl": {
        "title": "Kokpit Sentinel",
        "subtitle": "{instance}, replikacja {replication}, λ_A = {lambda_a}: {first} i {second} "
        "w tym samym symulowanym świecie (wspólne liczby losowe)",
        "deadline_line": "Termin D = dzień {deadline} (δ_D = {delta}, C* = {c_star}, "
        "{reference}); budżet B = {budget}",
        "ref_opt": "optimum",
        "ref_hrs": "najlepsze znane",
        "nav_kpis": "Wskaźniki",
        "nav_gantt": "Plan i wykonanie",
        "nav_risk": "Ryzyko",
        "nav_log": "Dziennik decyzji",
        "nav_howto": "Jak to czytać",
        "nav_provenance": "Pochodzenie",
        "measure": "Miara",
        "kpi_deadline": "Termin D",
        "kpi_makespan": "Zrealizowany czas trwania C",
        "kpi_on_time": "Na czas (C ≤ D)",
        "kpi_cost": "Koszt / budżet B",
        "kpi_changes": "Zmiany planu (przesunięte terminy)",
        "kpi_overtime": "Nadgodziny: pracownicy tymczasowi (koszt)",
        "kpi_subst": "Zastąpieni członkowie zespołów",
        "kpi_escalations": "Eskalacje (zatwierdzone, odroczone)",
        "kpi_deliberations": "Deliberacje",
        "kpi_descoped": "Usunięte zadania (DESCOPE)",
        "day_n": "dzień {day}",
        "days_n": "{days} dni",
        "yes": "✓ tak",
        "no_late": "✗ nie, spóźnienie: {days} dni",
        "no_late_1": "✗ nie, spóźnienie: 1 dzień",
        "truncated": "✗ nie, przerwano na limicie dni",
        "none": "—",
        "gantt_title": "Plan i wykonanie: {policy}",
        "gantt_compare": "Plan i wykonanie: {policy} (rozwiń)",
        "gantt_note": "Cienki szary pasek: plan bazowy. Gruby pasek: rzeczywiste wykonanie.",
        "legend_plan": "plan bazowy",
        "legend_full": "praca, pełny zespół",
        "legend_partial": "praca, część zespołu nieobecna",
        "legend_paused": "wstrzymane, brak obecnych członków zespołu",
        "legend_subst": "zastępstwo (SUBST)",
        "legend_temp": "pracownik tymczasowy w zespole (OVERTIME)",
        "legend_shock": "wzrost pracy (D2)",
        "legend_new": "nowe zadanie (D3); jego wiersz oznaczono +",
        "legend_absence": "nieobecność członka zespołu",
        "legend_idle": "nieobecności tylko wolnych pracowników",
        "legend_descoped": "usunięte (DESCOPE)",
        "lane_absences": "nieobecności",
        "lane_work": "wzrosty pracy",
        "lane_new": "nowe zadania",
        "day": "dzień",
        "plan_line": "plan: {makespan}",
        "deadline_label": "D = {deadline}",
        "realised_line": "{policy}: {makespan}",
        "risk_title": "Ryzyko w czasie: {policy}",
        "risk_note_agent": "Własna prognoza agenta przy każdej z {n} deliberacji.",
        "risk_note_policy": "{policy} nie prognozuje; kokpit liczy tę samą ocenę co {period} dni "
        "({n} punktów).",
        "risk_panel_p": "P(C ≤ D): prawdopodobieństwo zakończenia w terminie",
        "risk_panel_c": "Prognoza czasu trwania: przedział P10–P90 i mediana",
        "series_noop": "bez działania",
        "legend_noop": "prognoza bez działania (NOOP)",
        "legend_chosen_auto": "wybrane działanie, zastosowane od razu",
        "legend_chosen_wait": "wybrane działanie, odroczone lub eskalowane",
        "legend_target": "cel θ_D",
        "legend_band": "P10–P90 symulowanych czasów trwania",
        "legend_median": "mediana czasu trwania",
        "legend_deadline": "termin D",
        "target_label": "cel {target}",
        "makespan_axis": "czas trwania [dni]",
        "log_title": "Dziennik decyzji: {policy}",
        "log_none": "{policy} nie prowadzi deliberacji; dziennik pokazuje tylko decyzje Sentinela.",
        "filter_text": "Filtr",
        "filter_placeholder": "działanie, zdarzenie lub dzień",
        "filter_gate": "Bramka",
        "filter_all": "wszystkie",
        "filter_actions": "tylko działania inne niż NOOP",
        "rows_shown": "pokazane wiersze",
        "col_day": "Dzień",
        "col_events": "Zdarzenia",
        "col_needs": "Potrzeby n_D / n_B",
        "col_chosen": "Wybór (poziom)",
        "col_p": "p̂ / T̂",
        "col_runner": "Drugi najlepszy",
        "col_component": "Składowa decydująca",
        "col_gate": "Bramka",
        "col_explanation": "Wyjaśnienie",
        "gate_auto": "automatycznie",
        "gate_deferred": "odroczone",
        "gate_escalated": "eskalowane",
        "gate_approved": "zatwierdzone",
        "gate_none": "bez działania",
        "escalated_to": "eskalowane → dzień {day}",
        "discarded": "zatwierdzenie odrzucone: {label}",
        "ev_absence": "nieobecny: pracownik {worker} → zad. {activity}",
        "ev_return": "powrót: pracownik {worker} → zad. {activity}",
        "ev_idle": "wolni nieobecni: +{count}",
        "ev_work": "praca ×{factor}: zad. {activity}",
        "ev_new": "nowe zad. {activity}",
        "ev_review": "przegląd",
        "ev_approval": "dzień zatwierdzenia",
        "badge_template": "szablon",
        "badge_faithful": "LLM {model}: wierne ✓",
        "badge_unfaithful": "LLM {model}: niewierne ✗ ({details})",
        "badge_invalid": "LLM {model}: {error}",
        "faith_details": "fakty {right}/{facts}, wybrane działanie {chosen}, składowa "
        "{component}, liczby spoza rekordu {numbers}",
        "c_on_time": "P(na czas)",
        "c_tardiness": "opóźnienie",
        "c_scope": "zakres",
        "c_budget": "budżet",
        "c_stability": "stabilność",
        "c_level": "poziom",
        "c_order": "kolejność (remis)",
        "c_racing": "wyścig",
        "c_utility": "użyteczność",
        "c_needs_met": "bramka potrzeb",
        "c_only_candidate": "jedyny kandydat",
        "c_approved": "zatwierdzenie",
        "howto_title": "Jak to czytać",
        "provenance_title": "Pochodzenie",
        "p_command": "Polecenie",
        "p_code": "Kod",
        "p_clean": "commit {commit}, bez zmian",
        "p_dirty": "commit {commit}, z niezatwierdzonymi zmianami",
        "p_nogit": "brak repozytorium git",
        "p_seeds": "Ziarna",
        "p_seeds_text": "ziarno świata {seed} = derive_seed({base}, {set}, {instance}, "
        "{replication}) (WP2b), wspólne dla obu polityk; symulacje agenta w dniu t używają "
        "derive_seed({seed}, sentinel, t), przebieg i derive_seed(tego, rollout, i)",
        "p_world": "Świat",
        "p_world_text": "{instance}: {activities} zadań rzeczywistych, {workers} pracowników; "
        "scenariusz λ_A = {lambda_a}, E[L] = {mean_absence}, λ_S = {lambda_s}, λ_N = {lambda_n}; "
        "czasy trwania PERT({a}, {m}, {b}), λ = {lam}; okres przeglądu T_r = {period}",
        "p_plan": "Plan bazowy",
        "p_plan_text": "{method}, czas trwania {makespan} ({status})",
        "p_goals": "Termin i budżet",
        "p_goals_text": "D = ⌈(1 + δ_D) C*⌉ = {deadline} dla δ_D = {delta} i C* = {c_star} "
        "({reference}); B = {budget} z rezerwą β = {beta} (spec. §1.2)",
        "p_policy": "Polityka {policy}",
        "p_sentinel": "Sentinel, reguła {rule}, wariant {variant}: N₁ = {n1}, N = {n}, "
        "θ_D = {theta}, ε_D = {eps_d}, ε_T = {eps_t}, ε_B = {eps_b}, ε_Δ = {eps_delta}, "
        "Λ = {autonomy}, τ_def = {tau}, δ_h = {delay}, DESCOPE {descope}, T_cp = {tcp}, "
        "ziarno CP-SAT {cp_seed}",
        "p_baseline": "polityka z rejestru {policy}, T_cp = {tcp}, ziarno CP-SAT {cp_seed}; limit "
        "dni dla δ_D = {delta} jak w badaniach",
        "p_explain": "Wyjaśnienia",
        "p_explain_template": "szablon, zbudowany wyłącznie z rekordu decyzji",
        "p_explain_llm": "{backend} ({model}) przez pamięć podręczną nagraj/odtwórz {cache}; "
        "szablon dla deliberacji, które nie przeszły bramki potrzeb",
        "p_software": "Oprogramowanie",
        "p_note": "Stronę generuje polecenie sentinel dashboard; nie zawiera znaczników czasu, "
        "więc to samo polecenie w tym samym commicie zapisuje ten sam plik.",
        "on": "wł.",
        "off": "wył.",
        "desc_gantt": "Wykres Gantta {rows} zadań: plan bazowy i rzeczywiste wykonanie; dni z "
        "nieobecnościami: {absences}, wzrosty pracy: {work}, nowe zadania: {new}.",
        "desc_risk": "Prognozy w {n} dniach; P(C ≤ D) bez działania od {first} do {last}; termin "
        "D = {deadline}.",
        "desc_risk_empty": "Brak prognoz.",
        "tip_absences": "dzień {day}: {items}",
        "tip_absent_crew": "nieobecny pracownik {worker} (zespół zadania {activity})",
        "tip_absent_idle": "nieobecni wolni pracownicy: {count}",
        "tip_work": "dzień {day}: {items}",
        "tip_work_item": "zadanie {activity}, pozostała praca ×{factor}",
        "tip_new": "dzień {day}: {items}",
        "tip_new_item": "nowe zadanie {activity}, p = {duration}",
        "tip_activity": "zadanie {activity}: p = {duration}, zespół {crew}",
        "tip_planned": "zadanie {activity} zaplanowane na dni {first}–{last}",
        "tip_segment": "zadanie {activity}, dni {first}–{last}: obecnych {present} z {crew} "
        "członków zespołu",
        "tip_segment_temp": " (z pracownikami tymczasowymi)",
        "tip_paused": "dni {first}–{last}: wstrzymane, brak obecnych członków zespołu",
        "tip_temp": "zadanie {activity}: pracownicy tymczasowi w zespole od dnia {day}",
        "tip_subst": "dzień {day}: zastąpieni nieobecni członkowie zespołu zadania {activity}: "
        "{replaced}; przekazanie +{handover} dnia",
        "tip_shock": "dzień {day}: pozostała praca zadania {activity} ×{factor}",
        "tip_inserted": "dzień {day}: dodano zadanie {activity} (D3)",
        "tip_descoped": "dzień {day}: usunięto zadanie {activity} (DESCOPE)",
        "tip_forecast": "dzień {day}: P(C ≤ D) = {p} bez działania na {n} przebiegach; czas "
        "trwania P10–P90 {p10}–{p90}, mediana {p50}",
        "tip_chosen": "dzień {day}: wybrano {label}, P(C ≤ D) = {p} ({gate})",
    },
}

HOWTO: Mapping[Language, tuple[str, ...]] = {
    "en": (
        "Both policies run on the same simulated world: the same durations, absences and other "
        "disruptions drawn from one seed (common random numbers), so the differences in the key "
        "figures come from the decisions.",
        "Plan and execution: per activity the baseline plan (thin grey bar) and what happened "
        "(thick bar): solid while the full crew worked, striped while part of it was absent, an "
        "outline while the activity was paused. Activities never start before their planned day "
        "(railway rule), so delays carry forward. The lanes on top show each day's disruptions.",
        "Risk: the agent's own forecast at each deliberation, the probability of finishing by "
        "the deadline if nothing is done (NOOP), and the band in which 80 % of the simulated "
        "makespans fall (P10–P90), next to the deadline and the realised makespans. Triangles "
        "mark the forecast of the action the agent chose.",
        "Each deliberation simulates candidate actions on the same futures and chooses "
        "lexicographically: the probability of being on time up to the target θ_D, then the "
        "expected tardiness, the budget, plan stability and the approval level; differences "
        "within statistical and practical margins are ties. The deciding component is the one "
        "that separated the choice from the runner-up.",
        "Permission gate: an action at or above the autonomy level Λ needs approval. While the "
        "slack exceeds τ_def days it is deferred; otherwise it is escalated to the project "
        "manager, who approves it after δ_h days, and it is planned again on that day.",
        "Explanations: the template text uses only values of the decision record. An LLM "
        "explanation, when asked for, is checked against the record (spec §10.4), and its badge "
        "shows the result.",
        "Hover over bars and markers for details; the filter narrows the decision log. The page "
        "needs no network and prints on A4.",
    ),
    "pl": (
        "Obie polityki działają w tym samym symulowanym świecie: te same czasy trwania, "
        "nieobecności i inne zakłócenia z jednego ziarna (wspólne liczby losowe), więc różnice "
        "we wskaźnikach wynikają z decyzji.",
        "Plan i wykonanie: dla każdego zadania plan bazowy (cienki szary pasek) i to, co się "
        "wydarzyło (gruby pasek): pełny, gdy pracował cały zespół, kreskowany, gdy część zespołu "
        "była nieobecna, sam obrys, gdy zadanie było wstrzymane. Zadania nie zaczynają się przed "
        "planowanym dniem (zasada kolejowa), więc opóźnienia się przenoszą. Pasy u góry pokazują "
        "zakłócenia każdego dnia.",
        "Ryzyko: własna prognoza agenta przy każdej deliberacji, czyli prawdopodobieństwo "
        "zakończenia w terminie bez działania (NOOP), oraz przedział, w którym mieści się 80 % "
        "symulowanych czasów trwania (P10–P90), na tle terminu i zrealizowanych czasów trwania. "
        "Trójkąty oznaczają prognozę działania wybranego przez agenta.",
        "Przy każdej deliberacji agent symuluje działania kandydackie na tych samych scenariuszach "
        "i wybiera leksykograficznie: prawdopodobieństwo terminowości do celu θ_D, potem "
        "oczekiwane opóźnienie, budżet, stabilność planu i poziom uprawnień; różnice w granicach "
        "marginesów statystycznych i praktycznych są remisami. Składowa decydująca to ta, która "
        "oddzieliła wybór od drugiego kandydata.",
        "Bramka uprawnień: działanie na poziomie Λ lub wyższym wymaga zatwierdzenia. Dopóki zapas "
        "przekracza τ_def dni, jest odraczane; w przeciwnym razie trafia do kierownika projektu, "
        "który zatwierdza je po δ_h dniach, a w tym dniu jest planowane ponownie.",
        "Wyjaśnienia: tekst z szablonu używa wyłącznie wartości z rekordu decyzji. Wyjaśnienie "
        "LLM, jeśli o nie poproszono, jest sprawdzane z rekordem (spec. §10.4), a odznaka "
        "pokazuje wynik.",
        "Najedź na paski i znaczniki, aby zobaczyć szczegóły; filtr zawęża dziennik decyzji. "
        "Strona nie potrzebuje sieci i drukuje się na A4.",
    ),
}


def _days(first: int, end: int) -> tuple[int, int]:
    """The first and last day of days `first .. end - 1`."""
    return first, max(first, end - 1)


class Text:
    """The words and number format of one language."""

    def __init__(self, language: Language) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"unknown language {language!r}; known: {LANGUAGES}")
        self.language = language
        self.words = WORDS[language]

    def __getitem__(self, key: str) -> str:
        return self.words[key]

    def format(self, key: str, **values: object) -> str:
        return self.words[key].format(**values)

    def num(self, value: float, decimals: int) -> str:
        text = f"{value:.{decimals}f}"
        return text.replace(".", ",") if self.language == "pl" else text

    def role(self, k: int) -> str:
        return ROLES[self.language][k]

    def crew(self, demands: Sequence[int]) -> str:
        """People per role, e.g. "backend developer ×2, tester ×1" ("—" without demands)."""
        parts = [f"{self.role(k)} ×{n}" for k, n in enumerate(demands) if n > 0]
        return ", ".join(parts) or self["none"]

    def gantt_desc(self, rows: int, events: Sequence[DayEvents]) -> str:
        return self.format(
            "desc_gantt",
            rows=rows,
            absences=sum(bool(d.crew_absences or d.idle_absences) for d in events),
            work=sum(len(d.work_increases) for d in events),
            new=sum(len(d.new_activities) for d in events),
        )

    def absences_tip(self, day: DayEvents) -> str:
        items = [self.format("tip_absent_crew", worker=w, activity=j) for w, j in day.crew_absences]
        if day.idle_absences:
            items.append(self.format("tip_absent_idle", count=len(day.idle_absences)))
        return self.format("tip_absences", day=day.day, items="; ".join(items))

    def work_tip(self, day: DayEvents) -> str:
        items = [
            self.format("tip_work_item", activity=j, factor=self.num(f, 2))
            for j, f in day.work_increases
        ]
        return self.format("tip_work", day=day.day, items="; ".join(items))

    def new_tip(self, day: DayEvents) -> str:
        items = [self.format("tip_new_item", activity=j, duration=p) for j, p in day.new_activities]
        return self.format("tip_new", day=day.day, items="; ".join(items))

    def activity_tip(self, row: Row) -> str:
        crew = self.crew(row.demands)
        return self.format("tip_activity", activity=row.activity, duration=row.duration, crew=crew)

    def planned_tip(self, row: Row) -> str:
        assert row.planned is not None
        first, last = _days(row.planned, row.planned + row.duration)
        return self.format("tip_planned", activity=row.activity, first=first, last=last)

    def segment_tip(self, row: Row, segment: Segment) -> str:
        first, last = _days(segment.start, segment.end)
        text = self.format(
            "tip_segment",
            activity=row.activity,
            first=first,
            last=last,
            present=segment.present,
            crew=row.crew,
        )
        return text + (self["tip_segment_temp"] if segment.temporary else "")

    def paused_tip(self, first: int, end: int) -> str:
        a, b = _days(first, end)
        return self.format("tip_paused", first=a, last=b)

    def temporary_tip(self, row: Row, day: int) -> str:
        return self.format("tip_temp", activity=row.activity, day=day)

    def substitution_tip(self, substitution: Substitution) -> str:
        return self.format(
            "tip_subst",
            day=substitution.day,
            replaced=len(substitution.replaced),
            activity=substitution.activity,
            handover=self.num(substitution.handover, 1),
        )

    def shock_tip(self, row: Row, day: int, factor: float) -> str:
        return self.format("tip_shock", day=day, activity=row.activity, factor=self.num(factor, 2))

    def inserted_tip(self, row: Row) -> str:
        return self.format("tip_inserted", day=row.inserted_day, activity=row.activity)

    def descoped_tip(self, row: Row) -> str:
        return self.format("tip_descoped", day=row.descoped_day, activity=row.activity)

    def risk_desc(self, forecasts: Sequence[Forecast], deadline: int) -> str:
        if not forecasts:
            return self["desc_risk_empty"]
        return self.format(
            "desc_risk",
            n=len(forecasts),
            first=self.num(forecasts[0].p_on_time, 2),
            last=self.num(forecasts[-1].p_on_time, 2),
            deadline=deadline,
        )

    def target_label(self, target: float) -> str:
        return self.format("target_label", target=self.num(target, 2))

    def deadline_label(self, deadline: int) -> str:
        return self.format("deadline_label", deadline=deadline)

    def forecast_tip(self, forecast: Forecast) -> str:
        return self.format(
            "tip_forecast",
            day=forecast.day,
            p=self.num(forecast.p_on_time, 2),
            n=forecast.rollouts,
            p10=self.num(forecast.p10, 1),
            p90=self.num(forecast.p90, 1),
            p50=self.num(forecast.p50, 1),
        )

    def chosen_tip(self, forecast: Forecast) -> str:
        assert forecast.p_chosen is not None
        gate = self[f"gate_{forecast.gate or 'none'}"]
        return self.format(
            "tip_chosen",
            day=forecast.day,
            label=forecast.chosen,
            p=self.num(forecast.p_chosen, 2),
            gate=gate,
        )
