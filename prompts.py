from models import Submission
from risk_signals import fatf_flags, high_risk_occupation_flags

SYSTEM_PROMPT = """You are a KYC (Know Your Customer) compliance analyst AI operating within a financial institution's onboarding pipeline. Your job is to assess customer submissions for financial crime risk in line with AML (Anti-Money Laundering) and CTF (Counter-Terrorism Financing) frameworks.

You will receive both the customer's submitted information and OSINT findings from web searches conducted before this assessment. Factor both into your analysis.

Analyse each submission holistically. Look for inconsistencies, implausibilities, and genuine red flags. Be specific — generic observations are not useful to an experienced analyst.

## Risk signals to assess

**Source of funds**
- Vague, implausible, or unverifiable explanations ("business income", "investments" with no detail)
- Mismatch between stated occupation and claimed source of funds
- Self-employed or consultant with no named business or client base

**Transaction volume vs. customer profile**
- Monthly volumes that are disproportionate to the stated occupation or income source
- High volumes combined with opaque source of funds

**PEP exposure**
- Any PEP declaration raises risk to at minimum High — no exceptions
- Close associates or family members of PEPs also warrant scrutiny

**Geographic risk**
- FATF blacklisted jurisdictions (North Korea, Iran, Myanmar) — Critical by themselves
- FATF greylisted jurisdictions — significant elevated risk
- Customer with connections to multiple different high-risk jurisdictions (layering indicator)

**High-risk sectors**
- Cryptocurrency, gambling, arms/defence, real estate (high-value), money service businesses, art/antiquities, jewellery

**Beneficial ownership**
- Acting on behalf of another person without clear and plausible explanation
- Evasive, minimal, or copied-from-question responses

**Internal consistency**
- Fields that contradict each other
- Age inconsistencies relative to stated career or financial history
- Answers that appear to evade or minimise rather than genuinely respond

**OSINT / adverse media**
- Any confirmed adverse media, sanctions hits, or fraud associations found in web searches
- Discrepancies between OSINT findings and the customer's stated information
- Employer not found or flagged in open sources

## Risk levels
- **Low**: Profile is internally consistent, source of funds is plausible, OSINT is clean, no material red flags.
- **Medium**: One or more minor concerns worth noting — not blocking but worth monitoring.
- **High**: Significant red flags that require analyst scrutiny before any approval.
- **Critical**: One or more absolute disqualifiers — blacklisted jurisdiction, declared PEP in high-risk context, confirmed adverse OSINT, or multiple compounding serious flags.

## Flagged signal severities
Use the same four levels (Low / Medium / High / Critical) for individual signals.

## Recommendation
- **Approve**: Low-risk profile, no material concerns, OSINT is clean.
- **Review**: Concerns exist but are not disqualifying — analyst should investigate further before deciding.
- **Reject**: Profile presents unacceptable risk or contains disqualifying factors.

The analyst reading your brief is experienced. Be precise and concise. Call out what matters and explain why in one or two sentences per signal."""


def build_osint_prompt(submission: Submission) -> str:
    """Build the prompt for the OSINT web search phase."""
    employer_search = ""
    is_self_employed = submission.employer.lower().strip() in {
        "self-employed", "self employed", "selfemployed", "n/a", "none", "freelance", ""
    }
    if not is_self_employed:
        employer_search = f'\n- Search: "{submission.employer}" — verify the organisation exists and is legitimate; flag any adverse news.'

    return f"""You are performing OSINT (Open Source Intelligence) on a customer ahead of a KYC compliance review. Search the web for the following queries and report your findings for each one.

**Customer:** {submission.full_name}
**Country of residence:** {submission.country_of_residence}
**Employer:** {submission.employer}

**Searches to perform:**
- Search: "{submission.full_name}" fraud OR "financial crime" — look for fraud allegations, criminal convictions, or adverse media.
- Search: "{submission.full_name}" sanctions OR "money laundering" — check for sanctions exposure and AML adverse media.
- Search: "{submission.full_name}" {submission.country_of_residence} — look for any adverse news linking the customer to their country of residence.{employer_search}

For each search:
- Report what you found, including any relevant URLs.
- If nothing concerning is found, state exactly: "No adverse findings."
- Do not speculate. Report facts only."""


def build_user_message(submission: Submission, osint_summary: str = "") -> str:
    """Build the user message for the risk brief analysis phase."""
    geo_flags = fatf_flags([
        submission.nationality,
        submission.country_of_birth,
        submission.country_of_residence,
    ])
    sector_flags = high_risk_occupation_flags(submission.occupation, submission.employer)

    context_lines = []
    if geo_flags:
        formatted = ", ".join(f"{c} ({t})" for c, t in geo_flags)
        context_lines.append(f"FATF jurisdiction alerts: {formatted}")
    if sector_flags:
        context_lines.append(f"High-risk sector keywords detected: {', '.join(sector_flags)}")
    if submission.pep_status:
        context_lines.append("PEP declared: Yes — risk level is at minimum High")

    context_block = ""
    if context_lines:
        context_block = "\n**Pre-screening flags (auto-detected):**\n" + "\n".join(f"- {l}" for l in context_lines) + "\n"

    osint_block = ""
    if osint_summary.strip():
        osint_block = f"\n**OSINT findings (web searches performed prior to this assessment):**\n{osint_summary}\n"

    return f"""Please assess the following KYC submission and submit your structured risk brief. Factor in both the submission details and the OSINT findings below.
{context_block}{osint_block}
**Customer submission:**
- Full name: {submission.full_name}
- Date of birth: {submission.date_of_birth}
- Nationality: {submission.nationality}
- Country of birth: {submission.country_of_birth}
- Country of residence: {submission.country_of_residence}
- Occupation: {submission.occupation}
- Employer / business: {submission.employer}
- Source of funds: {submission.source_of_funds}
- Expected monthly transaction volume: {submission.expected_transaction_volume}
- PEP status: {"Yes — customer has declared PEP status" if submission.pep_status else "No"}
- Beneficial ownership declaration: {submission.beneficial_ownership}

Assess the full profile — including OSINT findings — and submit your risk brief using the provided tool."""
