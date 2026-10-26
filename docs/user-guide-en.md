# Sentinel — a guide for project managers

Sentinel watches the deadline and the budget of your project. After every check-in it works
out whether the deadline is at risk and, if so, proposes a concrete change: a substitute, a
temporary person, moved dates or a new order of tasks. Before it proposes anything, it tries
every option on hundreds of simulated futures of the project. Changes that affect people,
money or scope always wait for your decision.

This guide is for the person who runs the project. Installation for IT is at the
[end](#9-installation-for-it). Polish version: [user-guide-pl.md](user-guide-pl.md).

**Contents:**
[1. What Sentinel is](#1-what-sentinel-is) ·
[2. Your first project](#2-your-first-project) ·
[3. Reading the overview](#3-reading-the-overview) ·
[4. Check-ins](#4-check-ins) ·
[5. Recommendations and autonomy](#5-recommendations-and-autonomy) ·
[6. The simulator](#6-the-simulator) ·
[7. Privacy](#7-privacy) ·
[8. Frequently asked questions](#8-frequently-asked-questions) ·
[9. Installation for IT](#9-installation-for-it)

## 1. What Sentinel is

Projects rarely go to plan: someone falls ill, a task turns out bigger, new work appears.
Sentinel takes your plan and what you report at check-ins and plays out **200 possible futures
of the project**, with absences and surprises at the pace you choose when you set the project
up. From these futures come:

- the **chance of meeting the deadline** (e.g. "39 %": the project ends on time in 78 of the
  200 futures),
- the **most likely finish** and the **bad case** (one in ten finishes even later),
- **what threatens the deadline**: the tasks it depends on most often,
- a **recommendation**: the best change, tried on the same futures as the forecast.

Sentinel does not guess: every number on the screen comes from the same simulations, so "no
change" on a recommendation is exactly the chance on the overview. Artificial intelligence (AI)
is optional: it can read a description of the project or a message from the team and explain a
decision in its own words, but it never decides.

![The start page with the list of projects](ui/en_start.png)

*The start page: your projects with their chance of meeting the deadline and the decisions
waiting for you.*

## 2. Your first project

Click **New project**. The wizard has three steps; everything is saved as you go, so you can
stop and come back with **Continue the setup** on the start page.

### Step 1: Basics

![Wizard step 1: name, dates, budget, how sure the estimates are](ui/en_wizard_basics.png)

- **Project name**, **Start date** and **Deadline**, the last day by which all work should be
  done. Without a deadline Sentinel shows the forecast dates, but no chance and no
  recommendations.
- **Budget (optional)** in cost units: by default one cost unit is one person-day (one person
  working for a day). Leave it empty and Sentinel estimates it from the tasks (with a 10 %
  reserve).
- **How sure are the time estimates?** *Quite sure*, *Usual* or *Rough*: the less sure, the more
  the task durations vary in the futures.
- **How turbulent is the team?** *Calm*, *Usual* or *Turbulent*: how often absences and
  surprises happen.

### Step 2: Team

Enter people with their roles (e.g. "Backend developer", "Tester"), or click **Paste a list of
people** and paste, e.g. from a spreadsheet, one person per line: `Ada Turner, Backend
developer`. Roles are free text; case, spacing and a final plural *s* do not matter ("Tester"
and "testers" are the same role). The order matters: when work is assigned, Sentinel picks the
people higher up the list first.

### Step 3: Tasks

You can enter the tasks in three ways (tabs at the top):

![Wizard step 3: the task table](ui/en_wizard_tasks.png)

1. **Describe the project**: write in your own words what has to be done, by whom and for how
   long; the AI reads the tasks and the team, and you check them before using them (needs an
   AI to be set up).
2. **Import a spreadsheet**: download the **tasks template (CSV)**, fill it in with Excel,
   LibreOffice or Google Sheets and upload it. One row is one task:

   | id | name | duration_days | predecessors | optional | crew:Backend developer | crew:Tester |
   | --- | --- | --- | --- | --- | --- | --- |
   | T1 | Design the payment API | 3 | | no | 1 | 0 |
   | T2 | Build the payment API | 5 | T1 | no | 2 | 0 |
   | T3 | Test the payment API | 2 | T2 | no | 0 | 1 |

   `duration_days` are working days, `predecessors` the ids of the tasks that must finish first
   (several separated by spaces or commas), `optional` = `yes` for a task that may be dropped,
   and the `crew:` columns say how many people of a role are needed (role names as in step 2).
   Problems are listed with their row numbers; save the file as CSV (UTF-8).
3. **Add manually**: a table of name, working days, people per role, after which tasks, and
   whether it is optional. Problems (a loop of dependencies, too few people in a role, a
   deadline before the shortest possible duration) are listed at once, in plain words.

Click **Create the plan**. Sentinel lays out a plan that finishes early for your team and opens
the project's overview.

## 3. Reading the overview

![The project overview: chance, dates and costs](ui/en_overview.png)

- **Chance of meeting the deadline** with a rating: *On track* (80 % or more), *At risk*
  (50–79 %), *Unlikely* (below 50 %). The arrow below shows the change since the previous
  check-in.
- **Deadline**, **Most likely finish** (half of the futures end earlier, half later) and **Bad
  case (1 in 10 later)**.
- **Spent so far**, e.g. "27 of 84 cost units (person-days)", and the **Expected total cost**
  with the chance of staying within the budget. A cost unit is a person-day by default; if you
  enter daily rates in the project settings (e.g. in euros), costs are in your unit.
- **Waiting for your decision**: recommendations that need your approval (section 5).

Further down:

![What threatens the deadline, and plan and progress](ui/en_overview_threats.png)

- **What threatens the deadline**: the tasks that most often decide the deadline in the futures
  where the project is late, e.g. "The task “Product catalogue API” decides the deadline in 7
  of 10 late scenarios". Tasks the whole plan depends on (such as the first and the last task)
  and tasks already done are not listed. If no task stands out, Sentinel says that the risk is
  spread across the plan. Below the list: who is away and which tasks have not started as
  planned.
- **Plan and progress**: the original plan (grey), work done (green), in progress (blue, with
  an outline of the work left), planned (light blue) and absences (stripes), with today and the
  deadline. The same chart is also available as a table.

**Ask Sentinel** starts a new analysis at any time (e.g. after you changed the deadline in the
settings).

## 4. Check-ins

A check-in tells Sentinel what happened. Once a week is enough (e.g. on Friday), and at once
when something important changes. Click **Check-in**.

![The check-in](ui/en_checkin.png)

1. **Status at the end of**: the day the check-in describes (usually today).
2. **Tasks in progress and next**: for each, *Not started*, *In progress* with the share done
   (a slider, in per cent) or *Done* with its finish date. Optionally, when the task started and
   who works on it (by default Sentinel assumes the plan and free people). Tasks you say nothing
   about stay as they are.
3. **Someone is away**: the person, from when and (if known) until when. **Only when, never
   why**: there is no place for the reason of an absence.
4. **A task grows**: how many more working days a task in progress needs.
5. **New task**: its name, working days, what it comes after and what it must be done before.
6. Or **write a message** in plain words ("Ada is ill until Wednesday, the API needs 3 more
   days") and click **Read the message**: the AI lists what it found and you untick what is
   wrong. Only the ticked items are saved.

Click **Save the check-in**. After a few seconds the overview shows the new chance and, if a
change is needed, a recommendation.

> **Tip:** when a substitute takes over a task, part of their time goes into getting up to
> speed. Sentinel counts that time cautiously while the task runs, so the estimate of the work
> left improves when you mark the task as *Done*.

## 5. Recommendations and autonomy

After every check-in Sentinel tries the possible changes and picks the best: first the chance of
meeting the deadline, then the expected delay, the budget and how little the plan changes. A
recommendation shows:

![A recommendation: the action, its effect and the reasons](ui/en_recommendation.png)

- the **action** in plain words, e.g. "Substitute: Cyrus Hill takes over Ben Carter's part in
  “Product catalogue API”",
- its **effect** compared with no change: the chance ("39 % → 55 %"), the expected finish, the
  cost ("+2 units, +2 % of the budget") and how many tasks have their dates moved,
- **why** it needs your approval (*affects people*, *costs money*, *changes scope* or *changes
  the plan more than your setting allows*) and **why** this change was chosen,
- the **options compared**, each tried on the same 200 futures as the forecast on the overview,
  so "No change (keep the plan)" has exactly the overview's chance:

![The options compared](ui/en_recommendation_options.png)

You decide with **Approve**, **Decide later** or **Reject**. An approved change goes into the
plan at once (e.g. the substitute joins the task, a temporary person is hired for the stated
number of days). **Can wait** means there are still a few days before the risk becomes real.
"No change — the plan is still the best" is good news: no change helps more than the current
plan.

**Autonomy.** In the project's **Settings** you choose what Sentinel may do without asking:

![Project settings: autonomy](ui/en_settings.png)

| Setting | Automatic | Waits for you |
| --- | --- | --- |
| Only advise me | nothing | every change |
| May shift dates | moving dates without changing the order | the rest |
| May re-plan the order (recommended) | also a new order of tasks | substitutes, temporary people, dropping a task |
| May also add people and substitutes | also substitutes and temporary people | dropping a task |

A change applied automatically is shown on the overview; new dates or a new order have an
**Undo** button while nothing has happened after them. The **History** lists every check-in,
recommendation and decision.

## 6. The simulator

The simulator shows Sentinel at work without a real project: choose an example project (small:
30 tasks, medium: 60 tasks), how turbulent the team is and who manages the project,
**Sentinel** or **Nobody reacts**. Click **Start the simulation**, then simulate 1, 5 or 10 days
at a time, or **To the end**.

![The simulator](ui/en_simulator.png)

At the end, **How it ended** compares the same project with the same events (absences, growing
tasks, new tasks) run by Sentinel and with nobody reacting: the finish date, the delay, the
cost, plan changes, temporary people and substitutions. The timeline below shows what happened
and what Sentinel did.

![The comparison in the simulator](ui/en_simulator_comparison.png)

The simulator uses the application's settings (e.g. at least one temporary person per role can
always be added), not the setup of the research studies, so its results can differ from
theirs. One run is one possible fate of the project; chance plays a part, so try a few.

## 7. Privacy

- Sentinel stores only people's **availability** (from when until when someone is away), **never
  the reason** for an absence: there is no field for it (GDPR, Art. 9).
- The project's data stay on the server where Sentinel runs (your computer or the company's
  server). Without AI, nothing leaves it.
- AI is optional. A **local model (Ollama)** runs on your own hardware and sends nothing out;
  cloud models (Groq, OpenRouter) receive only the text they read. AI answers on real projects
  are remembered without the messages.
- The public demo: every visitor gets an own sandbox that nobody else sees; it is deleted with
  its projects after 24 hours.

## 8. Frequently asked questions

**How does Sentinel know how long tasks take?** From your estimates and how sure they are
(step 1). In each future a task takes a little less or more, as in real life.

**Why did the chance change although I reported nothing?** It does not change without a
check-in or a change of the settings: the same data always give the same numbers. If time has
passed and tasks have not started, report that in a check-in.

**Do I have to approve recommendations?** No. You can reject them or leave them for later.
Sentinel changes nothing about people, money or scope without your approval.

**What is a person-day?** One person working for one day. It is the default cost unit; a
temporary person costs one and a half person-days a day. Set your own rates in the project
settings (**Daily cost of one person**).

**Can I change the team or the tasks after the first check-in?** Names, the deadline, the budget
and the settings, always. After the first check-in the plan's structure changes through
check-ins (new tasks, longer tasks, absences) and approved recommendations.

**How do I get my data out?** In the project settings: the plan as CSV, the whole project as
JSON and a detailed report with charts.

**Can the AI change anything by itself?** No. The AI only reads text (which you check anyway)
and explains a decision; the explanation is marked with whether it agrees with the data.

## 9. Installation for IT

Details, backups and the public demo: [deploy.md](deploy.md).

**Important:** the application has no user accounts: everybody who can open its address sees
every project. Serve it only inside the company network (VPN) or behind a proxy that signs
people in.

**Company server (Docker):**

```bash
git clone https://github.com/Embedded-Embodied-Intelligence/sentinel.git && cd sentinel
docker compose up -d --build          # the app on the server's http://127.0.0.1:8000
docker compose ps                     # after about 30 s: (healthy)
```

The data (projects, settings, the AI key) are in the `sentinel-data` volume; to upgrade:
`git pull && docker compose up -d --build`. The simulator's example projects (once):
`docker compose run --rm sentinel python /app/scripts/fetch_psplib.py --sets j30 j60 --root /data/psplib`.

**Laptop (without Docker):** install [uv](https://docs.astral.sh/uv/), then `uv sync` and
`uv run sentinel ui` → http://127.0.0.1:8000.

**AI: options and costs** (chosen on the app's **Settings** page; the key stays on the server
and is never shown again):

| Option | Cost | Do data leave the company? |
| --- | --- | --- |
| No AI | free | no; everything but reading text and AI explanations works |
| Local model (Ollama) | free; a graphics card with 6 GB or more (or slower on the processor) | no; `docker compose --profile ollama up -d` and `docker compose --profile ollama exec ollama ollama pull qwen2.5:7b` |
| Groq (cloud) | a free plan with daily limits | yes, to Groq (US); a key from console.groq.com |
| OpenRouter (cloud) | pay per use (prices on openrouter.ai) | yes, to OpenRouter and the model's host |
