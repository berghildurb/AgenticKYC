# KYC Intelligence Platform

An agentic Know Your Customer (KYC) compliance tool built with Claude and Streamlit. It automates the initial risk screening of customer onboarding submissions, performs real-time OSINT web searches, and produces structured risk briefs for human compliance analysts to review.

---

## Overview

The platform models the full KYC lifecycle:

1. A customer completes an onboarding form
2. An AI agent runs OSINT web searches and produces a structured risk brief
3. A compliance analyst reviews the brief and makes a decision
4. Rejected customers can file up to two disputes; the AI advises but the analyst decides
5. Politically Exposed Persons (PEPs) go through an enhanced due diligence (EDD) flow before a risk score is produced

The system is intentionally split into two separate views — a **Customer Onboarding** portal and an **Analyst Dashboard** — to reflect real-world separation of concerns.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Streamlit UI (app.py)                   │
│                                                                 │
│   Customer Onboarding            Analyst Dashboard              │
│   ─────────────────────          ───────────────────            │
│   Home                           Submission list                │
│   New Application form           Risk brief detail              │
│   Check Application Status       Approve / Reject               │
│   EDD form (PEP only)            Dispute review                 │
│   Inbox                                                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │   agent.py     │
                    │                │
                    │  _run_osint()  │  ← Claude web_search tool
                    │                │
                    │  analyse_      │  ← submit_risk_brief tool
                    │  submission()  │
                    │                │
                    │  finalise_edd_ │  ← submit_risk_brief tool
                    │  analysis()    │    (EDD-informed prompt)
                    │                │
                    │  review_       │  ← submit_dispute_
                    │  dispute()     │    recommendation tool
                    └───────┬────────┘
                            │
          ┌─────────────────┼──────────────────────┐
          │                 │                      │
   ┌──────▼──────┐  ┌───────▼───────┐  ┌──────────▼──────┐
   │  models.py  │  │  prompts.py   │  │  storage.py     │
   │             │  │               │  │                 │
   │  Submission │  │  SYSTEM_PROMPT│  │  JSON files     │
   │  dataclass  │  │  EDD_SYSTEM_  │  │  data/          │
   │             │  │  PROMPT       │  │  submissions/   │
   └─────────────┘  │  build_*()    │  └─────────────────┘
                    └───────────────┘
```

### Key design decisions

- **Human-in-the-loop**: The AI never makes final approve/reject decisions. It produces recommendations; analysts and customers retain control.
- **Two-phase OSINT + brief**: OSINT runs first in a loop (up to 8 iterations, up to 5 web searches) to gather intelligence, then a forced tool call produces a structured risk brief from that intelligence.
- **EDD gating**: PEP submissions cannot be scored until the customer completes an Enhanced Due Diligence questionnaire. The preliminary pass identifies signals but leaves risk_level and risk_score as None.
- **Simulated inbox**: Emails are stored as a list on each Submission object. This simulates a real notification system without requiring external infrastructure.
- **JSON file storage**: Submissions are persisted as individual JSON files under `data/submissions/`. No database is required.

---

## Submission Status Flow

### Non-PEP customers
```
pending  →  analyzed  →  approved
                      →  rejected  →  (dispute filed)  →  approved
                                                        →  rejected (upheld)
```

### PEP customers
```
pending  →  awaiting_edd  →  analyzed  →  approved
                                       →  rejected  →  (dispute filed)  →  ...
```

---

## File Reference

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI — all pages, routing, forms, and state management |
| `agent.py` | Claude API calls — OSINT, risk brief, EDD analysis, dispute advisory |
| `models.py` | `Submission` dataclass — the central data model |
| `prompts.py` | All system prompts and user message builders |
| `storage.py` | JSON read/write with schema migration |
| `risk_signals.py` | FATF jurisdiction lists and high-risk sector keywords |
| `synthetic_profiles.py` | Five test profiles for the stress-test button |

---

## Setup

### Requirements

- Python 3.11+
- An Anthropic API key with access to `claude-sonnet-4-6` and the `web_search_20250305` tool

### Installation

```bash
# Clone or copy the project folder
cd "Agentic KYC Solution"

# Install dependencies
pip install -r requirements.txt

# Create a .env file with your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

### Running

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Usage Guide

### Customer Onboarding

**New Application**

1. Click **Start Application** from the home screen
2. Fill in all required fields — personal details, employment, source of funds, PEP declaration
3. Click **Submit Application**
4. The agent runs in the background (OSINT + risk brief). A reference ID is shown when complete — save it.

**Checking Status**

1. Click **Check Status** from the home screen
2. Enter your reference ID
3. The current status is shown:
   - *Pending* — analysis is running
   - *Under review* — awaiting analyst decision
   - *Approved* — application accepted
   - *Rejected* — see dispute options below
   - *Action Required* — EDD form needed (PEP customers only)

**PEP Enhanced Due Diligence**

If you declared PEP status, an email is sent to your inbox after submission asking you to complete an EDD form. You can also navigate directly via Check My Application. The EDD form asks about:
- Your relationship to the PEP
- The PEP's role and institution
- How long the connection has been active
- Your overall source of wealth
- Any known investigations or proceedings

The full risk assessment only runs after this form is submitted.

**Disputes**

Rejected customers can file up to two disputes:
1. Go to **Check My Application** and enter your reference ID
2. Write a rebuttal explaining why you believe the rejection is incorrect
3. Optionally provide a Tax Identification Number and up to two supporting documents
4. A compliance analyst reviews the dispute with an AI advisory recommendation and makes the final call

**Inbox**

The inbox shows all system messages for your application. Access it via the **My Inbox** sidebar button. Unread messages are shown with a blue dot. Action emails (rejection, dispute outcome, EDD request) have a button that takes you directly to the relevant form.

---

### Analyst Dashboard

**Submission List**

Shows all submissions with name, submission time, risk level badge, and status badge. Click **View** to open the detail view.

Summary cards at the top show counts for: total, awaiting review, approved, rejected.

**Risk Brief Detail**

For each analysed submission the detail view shows:

- **Risk level and score** — colour-coded badge and progress bar
- **Recommendation** — Approve / Review / Reject
- **Flagged Signals** — each signal has a severity (Low / Medium / High / Critical) and a reasoning note
- **External Intelligence** — OSINT findings from web searches, each tagged with a relevance level
- **Summary** — a plain-English paragraph synthesising the findings
- **Raw submission details** — collapsible expander

**Approve / Reject**

Available for submissions in the `analyzed` state. An optional notes field is shown alongside the buttons. Both actions trigger an email to the customer.

**EDD Submissions**

Submissions in `awaiting_edd` state show an amber banner. No decision buttons are available until the customer completes the EDD form and the full analysis runs.

**Dispute Review**

When a customer files a dispute, an amber banner appears on the submission. The analyst sees:
- The customer's rebuttal
- Any Tax Identification Number provided
- A list of uploaded supporting documents
- An **AI Advisory Recommendation** card (Uphold Rejection or Overturn Rejection) with reasoning

Two buttons are then available:
- **Accept Customer** — approves the submission, sends a success email
- **Uphold Rejection** — maintains the rejection; if the customer has a second dispute remaining, sends an email prompting them to use it

Up to two disputes per submission are supported.

**Stress Test**

The **Generate Test Submissions** sidebar button creates five synthetic submissions covering a range of risk profiles and runs the full AI analysis on each:

| Profile | Expected Risk |
|---------|--------------|
| Adaeze Obi — Nigerian nurse, salary income, low volume | Low |
| Thomas Weber — German freelancer, vague self-employed income | Medium |
| Markus van der Berg — Dutch broker, UAE, opaque structured finance | High |
| Claudette Martin — Belgian PEP, South Sudan, over €100k | Critical (enters EDD flow) |
| Viktor Bout — Real sanctioned individual, verified by OSINT | Critical |

Profiles are behaviour-driven. Risk levels are determined by occupation, transaction volume, source of funds, jurisdiction, and OSINT findings — not by nationality or ethnicity.

---

## AI Agent Details

### Phase 1 — OSINT

The agent runs up to 5 web searches using the `web_search_20250305` tool:
- Name + "fraud" / "financial crime"
- Name + "sanctions" / "money laundering"
- Name + country of residence
- Employer name verification (if not self-employed)

Results are synthesised into a free-text summary passed to Phase 2.

### Phase 2 — Risk Brief

A forced `submit_risk_brief` tool call produces:

| Field | Description |
|-------|-------------|
| `risk_level` | Low / Medium / High / Critical |
| `risk_score` | 0–100 (Low: 0–30, Medium: 31–60, High: 61–85, Critical: 86–100) |
| `flagged_signals` | Array of `{signal, severity, reasoning}` |
| `osint_findings` | Array of `{source, finding, relevance}` |
| `summary` | 3–5 sentence plain-English summary |
| `recommendation` | Approve / Review / Reject |

### EDD Analysis (PEP only)

A separate `EDD_SYSTEM_PROMPT` instructs the agent not to apply an automatic risk floor for PEPs. Risk is calibrated using the EDD answers — a distant, inactive associate of a retired local official can score Low; a direct PEP with a high-risk jurisdiction and vague wealth explanation can score Critical.

OSINT findings from the preliminary pass are reused (not re-run) in the EDD analysis.

### Dispute Advisory

A separate agent reviews disputes with a `submit_dispute_recommendation` tool. It receives the original risk brief, the customer rebuttal, any TIN provided, and filenames of uploaded documents. It returns either `Uphold Rejection` or `Overturn Rejection` with reasoning. The analyst makes the final call.

---

## Data Storage

Submissions are stored as JSON files in `data/submissions/<ID>.json`. The `_deserialise()` function in `storage.py` handles schema migration transparently — old submissions missing new fields (e.g. `edd_required`, `edd_form`) will default those fields to their zero values and load without error.

Uploaded dispute documents are saved to `data/disputes/<submission_id>/`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | API key for Claude. Must have access to `claude-sonnet-4-6` and the built-in web search tool. |

---

## Notes on Regulatory Design

- **Tipping-off protection**: Rejection emails and the Check My Application page do not disclose the specific grounds for rejection, in line with AML tipping-off regulations (e.g. POCA 2002 s.333A in the UK).
- **Human decision authority**: The AI produces recommendations and advisory opinions only. Approve, Reject, Accept Customer, and Uphold Rejection actions are all executed by a human analyst.
- **EDD for PEPs**: The EDD flow is modelled on FATF Recommendation 12, which requires enhanced due diligence for politically exposed persons before establishing a business relationship.
- **Dispute limits**: A maximum of two disputes per submission is enforced, reflecting typical internal complaints procedures.
