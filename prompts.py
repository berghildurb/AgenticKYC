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


EDD_SYSTEM_PROMPT = """You are a KYC compliance analyst AI conducting a full Enhanced Due Diligence (EDD) assessment. The customer has declared PEP status and has now completed a detailed EDD questionnaire. Your task is to produce a final, comprehensive risk brief that incorporates the original submission, the OSINT findings, and the EDD answers.

Analyse each submission holistically. Look for inconsistencies, implausibilities, and genuine red flags. Be specific — generic observations are not useful to an experienced analyst.

## Risk signals to assess

**Source of funds and source of wealth**
- Vague, implausible, or unverifiable explanations
- Mismatch between stated occupation, source of funds, and claimed total wealth
- Self-employed or consultant with no named business or client base

**Transaction volume vs. customer profile**
- Monthly volumes disproportionate to stated income
- High volumes combined with opaque or inconsistent wealth explanation

**PEP exposure — EDD-calibrated**
- Use the EDD answers to calibrate actual risk. Do NOT apply an automatic minimum risk level.
- A direct PEP (person themselves) with a high-risk jurisdiction, high transaction volume, and vague wealth explanation is Critical.
- A distant associate of a retired local official with a credible, verifiable wealth explanation may be Low or Medium.
- Assess: nature of the connection (self vs. family vs. associate), the role and institution, the jurisdiction, the duration, and whether any investigations are disclosed.
- Undisclosed or evasive EDD answers should increase the risk level significantly.

**Geographic risk**
- FATF blacklisted jurisdictions (North Korea, Iran, Myanmar) — Critical by themselves
- FATF greylisted jurisdictions — significant elevated risk
- Connections to multiple high-risk jurisdictions

**High-risk sectors**
- Cryptocurrency, gambling, arms/defence, real estate (high-value), money service businesses, art/antiquities, jewellery

**Beneficial ownership**
- Acting on behalf of another person without clear and plausible explanation

**Internal consistency**
- EDD answers that contradict the original submission
- Source of wealth inconsistent with stated occupation or income
- Declared awareness of investigations — always flag, assess credibility of explanation

**OSINT / adverse media**
- Any confirmed adverse media, sanctions hits, or fraud associations
- Discrepancies between OSINT and stated information

## Risk levels
- **Low**: Consistent profile, credible EDD answers, clean OSINT, no material concerns.
- **Medium**: Minor concerns — PEP connection is distant or inactive, other profile is clean.
- **High**: Significant concerns — direct PEP, high-risk jurisdiction, vague wealth explanation, or adverse OSINT.
- **Critical**: Absolute disqualifiers — blacklisted jurisdiction, confirmed adverse OSINT, undisclosed investigations found in OSINT, multiple compounding serious flags.

## Recommendation
- **Approve**: Low-risk profile, credible EDD, no material concerns.
- **Review**: Concerns exist but not disqualifying — analyst should investigate further.
- **Reject**: Unacceptable risk or disqualifying factors.

The analyst reading your brief is experienced. Be precise and concise. Call out what matters and explain why."""


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


def build_edd_user_message(submission: Submission, osint_summary: str = "") -> str:
    """Build the user message for the EDD final analysis phase."""
    geo_flags = fatf_flags([
        submission.nationality,
        submission.country_of_birth,
        submission.country_of_residence,
    ])
    sector_flags = high_risk_occupation_flags(submission.occupation, submission.employer)

    context_lines = ["PEP declared: Yes — Enhanced Due Diligence completed (see EDD answers below)"]
    if geo_flags:
        formatted = ", ".join(f"{c} ({t})" for c, t in geo_flags)
        context_lines.append(f"FATF jurisdiction alerts: {formatted}")
    if sector_flags:
        context_lines.append(f"High-risk sector keywords detected: {', '.join(sector_flags)}")

    context_block = "\n**Pre-screening flags (auto-detected):**\n" + "\n".join(f"- {l}" for l in context_lines) + "\n"

    osint_block = ""
    if osint_summary.strip():
        osint_block = f"\n**OSINT findings (from preliminary screening):**\n{osint_summary}\n"

    edd = submission.edd_form or {}
    pep_name_line = ""
    if edd.get("pep_connection_type") != "I am personally a PEP" and edd.get("pep_person_name", "").strip():
        pep_name_line = f"\n- PEP full name: {edd['pep_person_name']}"
    inv_details_line = ""
    if edd.get("investigations_aware") == "Yes" and edd.get("investigations_details", "").strip():
        inv_details_line = f"\n- Investigation details: {edd['investigations_details']}"

    edd_block = f"""
**Enhanced Due Diligence (EDD) answers submitted by customer:**
- Nature of PEP connection: {edd.get('pep_connection_type', 'N/A')}{pep_name_line}
- PEP official role or position: {edd.get('pep_role', 'N/A')}
- Country and institution: {edd.get('pep_country_institution', 'N/A')}
- Duration of connection: {edd.get('connection_duration', 'N/A')}
- Source of wealth (total accumulated assets): {edd.get('source_of_wealth', 'N/A')}
- Aware of any investigations or proceedings: {edd.get('investigations_aware', 'N/A')}{inv_details_line}
"""

    return f"""Please conduct a full KYC/EDD risk assessment for this PEP submission. The customer has completed Enhanced Due Diligence — use the EDD answers alongside the original submission and OSINT findings to determine the final risk level and recommendation.
{context_block}{osint_block}
**Original submission:**
- Full name: {submission.full_name}
- Date of birth: {submission.date_of_birth}
- Nationality: {submission.nationality}
- Country of birth: {submission.country_of_birth}
- Country of residence: {submission.country_of_residence}
- Occupation: {submission.occupation}
- Employer / business: {submission.employer}
- Source of funds: {submission.source_of_funds}
- Expected monthly transaction volume: {submission.expected_transaction_volume}
- PEP status: Yes
- Beneficial ownership declaration: {submission.beneficial_ownership}
{edd_block}
Assess the complete profile — original submission, EDD answers, and OSINT findings — and submit your final risk brief using the provided tool."""
