import os
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

from models import Submission
from prompts import SYSTEM_PROMPT, build_osint_prompt, build_user_message
from storage import load_submission, update_submission

load_dotenv(override=True)

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}

_RISK_BRIEF_TOOL = {
    "name": "submit_risk_brief",
    "description": "Submit the completed KYC risk assessment brief.",
    "input_schema": {
        "type": "object",
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["Low", "Medium", "High", "Critical"],
                "description": "Overall risk classification for this submission.",
            },
            "risk_score": {
                "type": "integer",
                "description": (
                    "Numeric risk score 0–100, consistent with risk_level: "
                    "Low = 0–30, Medium = 31–60, High = 61–85, Critical = 86–100."
                ),
                "minimum": 0,
                "maximum": 100,
            },
            "osint_findings": {
                "type": "array",
                "description": "One entry per OSINT web search performed. Always include all searches, even clean ones.",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "Short label for what was searched, e.g. 'Full name + fraud'.",
                        },
                        "finding": {
                            "type": "string",
                            "description": "What the search returned. Use 'No adverse findings' if nothing concerning was found.",
                        },
                        "relevance": {
                            "type": "string",
                            "enum": ["Low", "Medium", "High"],
                            "description": "How relevant this finding is to the risk assessment.",
                        },
                    },
                    "required": ["source", "finding", "relevance"],
                },
            },
            "flagged_signals": {
                "type": "array",
                "description": "Risk signals identified from both the submission and OSINT findings.",
                "items": {
                    "type": "object",
                    "properties": {
                        "signal": {
                            "type": "string",
                            "description": "Short name for the risk signal.",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["Low", "Medium", "High", "Critical"],
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Concise explanation of why this is a concern.",
                        },
                    },
                    "required": ["signal", "severity", "reasoning"],
                },
            },
            "summary": {
                "type": "string",
                "description": "Plain-English risk summary for the compliance analyst (3–5 sentences), incorporating OSINT findings.",
            },
            "recommendation": {
                "type": "string",
                "enum": ["Approve", "Review", "Reject"],
                "description": "Agent's recommended action.",
            },
        },
        "required": [
            "risk_level", "risk_score", "osint_findings",
            "flagged_signals", "summary", "recommendation",
        ],
    },
}


def _run_osint(submission: Submission) -> str:
    """
    Perform OSINT web searches using the Anthropic web search tool.
    Returns a text summary of all findings for use in the risk brief.
    """
    messages = [{"role": "user", "content": build_osint_prompt(submission)}]

    for _ in range(8):
        response = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=[_WEB_SEARCH_TOOL],
            tool_choice={"type": "auto"},
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            # Model has synthesised all search results into a text response
            return "\n".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        # stop_reason == "tool_use" — searches still in progress
        messages.append({"role": "assistant", "content": response.content})

        # Identify which tool_use blocks already have results (server-side execution)
        resolved_ids = {
            getattr(b, "tool_use_id", None)
            for b in response.content
            if getattr(b, "type", None) in ("tool_result", "server_tool_result")
        }

        # Any tool_use without a result needs a tool_result to continue
        pending = [
            b for b in response.content
            if getattr(b, "type", None) == "tool_use" and b.id not in resolved_ids
        ]

        if pending:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "content": "Search complete."}
                    for b in pending
                ],
            })
        else:
            # Server handled all tool calls — prompt the model to synthesise and respond
            messages.append({
                "role": "user",
                "content": "Please summarise your OSINT findings.",
            })

    return "OSINT searches could not be completed within the iteration limit."


def analyse_submission(submission: Submission) -> dict:
    """
    Phase 1: gather OSINT via web search.
    Phase 2: produce a structured risk brief that incorporates those findings.
    """
    osint_summary = _run_osint(submission)

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[_RISK_BRIEF_TOOL],
        tool_choice={"type": "tool", "name": "submit_risk_brief"},
        messages=[{"role": "user", "content": build_user_message(submission, osint_summary=osint_summary)}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    brief = dict(tool_block.input)
    brief["analysed_at"] = datetime.now(timezone.utc).isoformat()
    return brief


def run_analysis(submission_id: str) -> Submission:
    """Load, analyse, persist, and return the updated submission."""
    submission = load_submission(submission_id)
    submission.risk_brief = analyse_submission(submission)
    submission.status = "analyzed"
    update_submission(submission)
    return submission


_DISPUTE_REVIEW_TOOL = {
    "name": "submit_dispute_review",
    "description": "Submit the outcome of a customer dispute review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["Upheld", "Overturned"],
                "description": (
                    "Upheld = rejection stands. "
                    "Overturned = customer's rebuttal is accepted and rejection is reversed."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "Clear explanation of why the dispute was upheld or overturned. "
                    "Reference specific points from the original risk brief and the customer's rebuttal. "
                    "3–5 sentences."
                ),
            },
            "revised_risk_level": {
                "type": "string",
                "enum": ["Low", "Medium", "High", "Critical"],
                "description": "Revised risk level if the outcome is Overturned. Omit if Upheld.",
            },
        },
        "required": ["outcome", "reasoning"],
    },
}

_DISPUTE_SYSTEM_PROMPT = """You are a senior KYC compliance analyst conducting a second-level review of a disputed rejection decision.

You will receive:
1. The original risk brief that led to the rejection
2. The customer's rebuttal disputing the rejection

Your task is to objectively assess whether the customer's rebuttal provides sufficient new information or credible explanations to overturn the rejection.

Be rigorous. A rebuttal should only succeed if it genuinely addresses the specific concerns raised — not merely reasserts innocence or provides vague reassurances. At the same time, if the rebuttal provides specific, credible, and verifiable information that materially changes the risk picture, you should be willing to overturn the decision.

Use the submit_dispute_review tool to record your outcome."""


def review_dispute(submission_id: str, rebuttal: str) -> Submission:
    """Run a second-level dispute review and persist the result."""
    submission = load_submission(submission_id)
    brief = submission.risk_brief or {}

    signals_text = "\n".join(
        f"- [{s['severity']}] {s['signal']}: {s['reasoning']}"
        for s in brief.get("flagged_signals", [])
    )
    osint_text = "\n".join(
        f"- {o['source']} (Relevance: {o['relevance']}): {o['finding']}"
        for o in brief.get("osint_findings", [])
    )

    user_message = f"""A customer has disputed their KYC rejection. Please review.

**Original risk brief**
- Risk level: {brief.get('risk_level', 'N/A')}
- Risk score: {brief.get('risk_score', 'N/A')} / 100
- Recommendation: {brief.get('recommendation', 'N/A')}
- Summary: {brief.get('summary', 'N/A')}

**Flagged signals:**
{signals_text or 'None recorded.'}

**OSINT findings:**
{osint_text or 'None recorded.'}

**Customer's rebuttal:**
{rebuttal.strip()}

Assess whether the rebuttal materially addresses the concerns and submit your dispute review."""

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_DISPUTE_SYSTEM_PROMPT,
        tools=[_DISPUTE_REVIEW_TOOL],
        tool_choice={"type": "tool", "name": "submit_dispute_review"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    dispute = dict(tool_block.input)
    dispute["rebuttal"] = rebuttal.strip()
    dispute["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    submission.dispute = dispute
    if dispute["outcome"] == "Overturned":
        submission.status = "approved"
        if submission.decision:
            submission.decision["overturned"] = True
    update_submission(submission)
    return submission
