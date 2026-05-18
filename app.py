import time

import streamlit as st
from datetime import date, datetime, timezone

from agent import run_analysis, review_dispute
from models import Submission
from storage import load_all_submissions, load_submission, save_submission, update_submission
from synthetic_profiles import SYNTHETIC_PROFILES

st.set_page_config(page_title="KYC Intelligence Platform", layout="wide")

# ── Global styles ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
.stApp { background: #f8fafc; }
.block-container { padding: 3rem 3rem 4rem !important; }
hr { border: none !important; border-top: 1px solid #e2e8f0 !important; margin: 2rem 0 !important; }
.stButton > button { border-radius: 8px !important; font-weight: 600 !important; font-size: 0.875rem !important; }
.stButton > button[kind="primary"] { background: #0f172a !important; color: white !important; border: none !important; }
.stButton > button[kind="primary"]:hover { background: #1e293b !important; }
.stButton > button[kind="secondary"] { background: white !important; border: 1.5px solid #e2e8f0 !important; color: #374151 !important; }
.stButton > button[kind="secondary"]:hover { border-color: #94a3b8 !important; }
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div { border: 1.5px solid #e2e8f0 !important; border-radius: 8px !important; }
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus { border-color: #0f172a !important; box-shadow: 0 0 0 3px rgba(15,23,42,0.07) !important; }
section[data-testid="stSidebar"] { background: #0f172a !important; }
section[data-testid="stSidebar"] label { color: #cbd5e1 !important; font-weight: 500 !important; }
section[data-testid="stSidebar"] p { color: #94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

# ── Shared helpers ────────────────────────────────────────────────────────────

_RISK_COLORS = {
    "Low":      "#28a745",
    "Medium":   "#fd7e14",
    "High":     "#dc3545",
    "Critical": "#6f42c1",
}
_STATUS_COLORS = {
    "pending":  "#6c757d",
    "analyzed": "#0d6efd",
    "approved": "#28a745",
    "rejected": "#dc3545",
}


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:4px;font-size:0.82em;font-weight:600">{text}</span>'
    )


def risk_badge(level: str) -> str:
    return _badge(level, _RISK_COLORS.get(level, "#6c757d"))


def status_badge(status: str) -> str:
    return _badge(status.capitalize(), _STATUS_COLORS.get(status, "#6c757d"))


def fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        return iso


# ── Session state ─────────────────────────────────────────────────────────────

if "selected_id" not in st.session_state:
    st.session_state.selected_id = None
if "customer_view" not in st.session_state:
    st.session_state.customer_view = "home"  # home | new_application | check_status


# ── Navigation ────────────────────────────────────────────────────────────────

page = st.sidebar.radio("Navigation", ["Customer Onboarding", "Analyst Dashboard"])

if page == "Analyst Dashboard" and st.session_state.customer_view != "home":
    st.session_state.customer_view = "home"
    st.session_state.pop("_looked_up_id", None)

st.sidebar.divider()
if st.sidebar.button("⚡ Generate Test Submissions", use_container_width=True):
    st.session_state["_do_generate"] = True

# ── Product header ────────────────────────────────────────────────────────────

_header_title = "KYC Intelligence Platform" if page == "Customer Onboarding" else "Compliance Review System"
st.markdown(f"""
<div style="display:flex;align-items:center;gap:12px;padding-bottom:24px;
            margin-bottom:8px;border-bottom:1px solid #e2e8f0;background:#f8fafc">
    <div style="width:32px;height:32px;background:#2563eb;border-radius:8px;
                display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="2"   y="2"   width="5.5" height="5.5" rx="1.5" fill="white"/>
            <rect x="8.5" y="2"   width="5.5" height="5.5" rx="1.5" fill="white" opacity="0.7"/>
            <rect x="2"   y="8.5" width="5.5" height="5.5" rx="1.5" fill="white" opacity="0.7"/>
            <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1.5" fill="white" opacity="0.4"/>
        </svg>
    </div>
    <div style="font-size:15px;font-weight:700;color:#0f172a;letter-spacing:-0.3px">{_header_title}</div>
</div>
""", unsafe_allow_html=True)

# ── Synthetic stress test ─────────────────────────────────────────────────────

if st.session_state.pop("_do_generate", False):
    st.subheader("Generating test submissions…")
    progress_bar = st.progress(0)
    status       = st.empty()

    for i, profile_data in enumerate(SYNTHETIC_PROFILES):
        name = profile_data["full_name"]
        status.info(f"Analysing {i + 1} of 5 — **{name}**")
        progress_bar.progress(i / 5)

        sub = Submission(**profile_data)
        save_submission(sub)
        try:
            run_analysis(sub.id)
        except Exception as e:
            st.warning(f"Analysis failed for {name}: {e}")

        progress_bar.progress((i + 1) / 5)

    status.success("All 5 submissions generated and analysed. Loading dashboard…")
    time.sleep(1.5)
    st.session_state.selected_id = None          # land on the list view
    st.session_state["_goto_dashboard"] = True   # switch page after rerun
    st.rerun()

if st.session_state.pop("_goto_dashboard", False):
    # Force navigation to the analyst dashboard after generation
    page = "Analyst Dashboard"

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER ONBOARDING
# ─────────────────────────────────────────────────────────────────────────────

if page == "Customer Onboarding":

    # Reset customer_view when navigating away and back
    cv = st.session_state.customer_view

    # ── Home: choose a path ───────────────────────────────────────────────────

    if cv == "home":
        st.title("Welcome")
        st.write("What would you like to do?")
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        col_a, col_b = st.columns(2, gap="large")
        with col_a:
            st.markdown("""
            <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;
                        padding:28px 24px;box-shadow:0 1px 3px rgba(0,0,0,0.05);min-height:140px">
                <div style="font-size:1.1rem;font-weight:700;color:#0f172a;margin-bottom:8px">New Application</div>
                <div style="color:#64748b;font-size:0.9rem;line-height:1.5">
                    Complete the KYC onboarding form to open an account.
                    You will receive a reference ID when you submit.
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            if st.button("Start Application", type="primary", use_container_width=True):
                st.session_state.customer_view = "new_application"
                st.rerun()

        with col_b:
            st.markdown("""
            <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;
                        padding:28px 24px;box-shadow:0 1px 3px rgba(0,0,0,0.05);min-height:140px">
                <div style="font-size:1.1rem;font-weight:700;color:#0f172a;margin-bottom:8px">Check My Application</div>
                <div style="color:#64748b;font-size:0.9rem;line-height:1.5">
                    View the status of an existing application or file a dispute
                    if your application was rejected.
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            if st.button("Check Status", use_container_width=True):
                st.session_state.customer_view = "check_status"
                st.rerun()

    # ── New application form ──────────────────────────────────────────────────

    elif cv == "new_application":
        if st.button("← Back"):
            st.session_state.customer_view = "home"
            st.rerun()

        st.title("New Application")
        st.write(
            "Please complete all fields accurately. "
            "Incomplete or false information may result in your application being declined."
        )

        with st.form("kyc_form", clear_on_submit=True):
            st.subheader("Personal Information")
            full_name            = st.text_input("Full Legal Name")
            date_of_birth        = st.date_input(
                "Date of Birth",
                value=date(1990, 1, 1),
                min_value=date(1900, 1, 1),
                max_value=date.today(),
            )
            nationality          = st.text_input("Nationality")
            country_of_birth     = st.text_input("Country of Birth")
            country_of_residence = st.text_input("Country of Residence")

            st.subheader("Employment & Finances")
            occupation                  = st.text_input("Occupation / Job Title")
            employer                    = st.text_input("Employer or Business Name")
            source_of_funds             = st.text_area(
                "Source of Funds",
                placeholder=(
                    "Describe how you obtained the funds you intend to use — "
                    "e.g. salary, business income, inheritance, sale of property."
                ),
                height=100,
            )
            expected_transaction_volume = st.selectbox(
                "Expected Monthly Transaction Volume",
                ["Under €1,000", "€1,000 – €10,000", "€10,000 – €50,000",
                 "€50,000 – €100,000", "Over €100,000"],
            )

            st.subheader("Compliance Declarations")
            pep_raw = st.radio(
                "Are you, or have you ever been, a Politically Exposed Person (PEP)?",
                ["No", "Yes"],
                help=(
                    "A PEP is someone who holds or has held a prominent public position, "
                    "or is a close associate of such a person."
                ),
            )
            beneficial_ownership = st.text_area(
                "Beneficial Ownership",
                placeholder=(
                    "Are you acting on behalf of another person or entity? "
                    "If yes, provide their full name, relationship, and reason."
                ),
                height=100,
            )

            submitted = st.form_submit_button("Submit Application", type="primary")

        if submitted:
            missing = [
                label for label, val in [
                    ("Full Legal Name",      full_name),
                    ("Nationality",          nationality),
                    ("Country of Birth",     country_of_birth),
                    ("Country of Residence", country_of_residence),
                    ("Occupation",           occupation),
                    ("Employer",             employer),
                    ("Source of Funds",      source_of_funds),
                    ("Beneficial Ownership", beneficial_ownership),
                ]
                if not val.strip()
            ]
            if missing:
                st.error(f"Please fill in: {', '.join(missing)}")
            else:
                submission = Submission(
                    full_name=full_name.strip(),
                    date_of_birth=str(date_of_birth),
                    nationality=nationality.strip(),
                    country_of_birth=country_of_birth.strip(),
                    country_of_residence=country_of_residence.strip(),
                    occupation=occupation.strip(),
                    employer=employer.strip(),
                    source_of_funds=source_of_funds.strip(),
                    expected_transaction_volume=expected_transaction_volume,
                    pep_status=(pep_raw == "Yes"),
                    beneficial_ownership=beneficial_ownership.strip(),
                )
                save_submission(submission)

                with st.spinner("Analysing your submission..."):
                    try:
                        run_analysis(submission.id)
                    except Exception as e:
                        st.warning(f"Analysis could not complete automatically: {e}")

                st.success(
                    f"Application submitted. Your reference ID is **{submission.id}**. "
                    "A compliance analyst will review your application."
                )

    # ── Check status / dispute ────────────────────────────────────────────────

    elif cv == "check_status":
        if st.button("← Back"):
            st.session_state.customer_view = "home"
            st.session_state.pop("_looked_up_id", None)
            st.rerun()

        st.title("Check Application Status")
        st.write("Enter your reference ID to view your application status or file a dispute.")

        lookup_id = st.text_input(
            "Reference ID",
            placeholder="e.g. A1B2C3D4",
            key="lookup_id",
        ).strip().upper()

        if st.button("Check Status", type="primary", key="do_lookup"):
            if not lookup_id:
                st.error("Please enter your reference ID.")
            else:
                try:
                    load_submission(lookup_id)
                    st.session_state["_looked_up_id"] = lookup_id
                except FileNotFoundError:
                    st.error("No application found with that reference ID.")
                    st.session_state.pop("_looked_up_id", None)

        if "_looked_up_id" in st.session_state:
            try:
                looked_up = load_submission(st.session_state["_looked_up_id"])
            except FileNotFoundError:
                st.session_state.pop("_looked_up_id", None)
                looked_up = None

            if looked_up:
                st.divider()
                st.markdown(f"**Name:** {looked_up.full_name}")

                if looked_up.status == "pending":
                    st.info("Your application is being processed. Please check back shortly.")

                elif looked_up.status == "analyzed":
                    st.info("Your application is under review by a compliance analyst.")

                elif looked_up.status == "approved":
                    st.success("Your application has been approved.")
                    if looked_up.dispute and looked_up.dispute.get("outcome") == "Overturned":
                        st.caption("Note: approved following a successful dispute review.")

                elif looked_up.status == "rejected":
                    if looked_up.dispute:
                        dispute      = looked_up.dispute
                        disp_outcome = dispute.get("outcome", "")
                        if disp_outcome == "Overturned":
                            st.success("Your dispute was successful. The rejection has been overturned.")
                        else:
                            st.error("Your application was rejected. Your dispute was reviewed and the decision was upheld.")
                            st.markdown(f"**Reviewer's reasoning:** {dispute['reasoning']}")
                    else:
                        st.error("Your application has been rejected.")
                        st.write(
                            "For legal and regulatory reasons, we are unable to disclose the specific grounds "
                            "for this decision. If you believe this decision is incorrect, you may submit a "
                            "dispute below and provide any information you believe is relevant."
                        )
                        rebuttal_text = st.text_area(
                            "Your rebuttal",
                            placeholder=(
                                "Explain why you believe the rejection is incorrect. "
                                "Be specific — provide verifiable details that address the reasons for rejection."
                            ),
                            height=150,
                            key="rebuttal_input",
                        )
                        if st.button("Submit Dispute", type="primary", key="submit_dispute"):
                            if not rebuttal_text.strip():
                                st.error("Please enter a rebuttal before submitting.")
                            else:
                                with st.spinner("Submitting your dispute for review…"):
                                    try:
                                        review_dispute(looked_up.id, rebuttal_text)
                                        st.session_state.pop("_looked_up_id", None)
                                        st.success(
                                            "Your dispute has been submitted and reviewed. "
                                            "Enter your reference ID again to see the outcome."
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Dispute submission failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# ANALYST DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

elif page == "Analyst Dashboard":

    # ── Detail view ───────────────────────────────────────────────────────────

    if st.session_state.selected_id:
        submission = load_submission(st.session_state.selected_id)

        if st.button("← Back to submissions"):
            st.session_state.selected_id = None
            st.rerun()

        st.divider()

        # Header
        col_name, col_status = st.columns([3, 1])
        with col_name:
            st.title(submission.full_name)
            st.caption(f"ID: {submission.id}  ·  Submitted: {fmt_ts(submission.timestamp)}")
        with col_status:
            st.markdown(
                f"<div style='text-align:right;margin-top:1rem'>{status_badge(submission.status)}</div>",
                unsafe_allow_html=True,
            )

        # ── Risk brief ────────────────────────────────────────────────────────

        if submission.risk_brief:
            brief = submission.risk_brief

            st.subheader("Risk Assessment")
            col_level, col_rec = st.columns(2)
            with col_level:
                st.markdown("**Overall Risk Level**")
                st.markdown(risk_badge(brief["risk_level"]), unsafe_allow_html=True)
                if "risk_score" in brief:
                    score     = brief["risk_score"]
                    bar_color = _RISK_COLORS.get(brief["risk_level"], "#6c757d")
                    st.markdown(
                        f"""
                        <div style="margin-top:0.75rem">
                            <div style="display:flex;align-items:center;gap:0.75rem">
                                <div style="flex:1;background:#e9ecef;border-radius:6px;height:14px;overflow:hidden">
                                    <div style="width:{score}%;background:{bar_color};height:100%;border-radius:6px"></div>
                                </div>
                                <span style="font-weight:700;font-size:1.05em;color:{bar_color};white-space:nowrap">{score} / 100</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            with col_rec:
                st.markdown("**Recommendation**")
                rec_color = {
                    "Approve": "#28a745",
                    "Review":  "#fd7e14",
                    "Reject":  "#dc3545",
                }.get(brief["recommendation"], "#6c757d")
                st.markdown(_badge(brief["recommendation"], rec_color), unsafe_allow_html=True)

            st.markdown(f"*Analysed: {fmt_ts(brief.get('analysed_at', ''))}*")

            st.divider()

            # Flagged signals
            st.subheader("Flagged Signals")
            signals = brief.get("flagged_signals", [])
            if signals:
                for signal in signals:
                    sev          = signal["severity"]
                    border_color = _RISK_COLORS.get(sev, "#6c757d")
                    st.markdown(
                        f"""
                        <div style="border-left:4px solid {border_color};
                                    padding:0.6rem 1rem;
                                    margin-bottom:0.8rem;
                                    background:#f8f9fa;
                                    border-radius:0 4px 4px 0">
                            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.3rem">
                                <strong>{signal['signal']}</strong>
                                {risk_badge(sev)}
                            </div>
                            <div style="color:#444;font-size:0.93em">{signal['reasoning']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No signals flagged.")

            st.divider()

            # External Intelligence (OSINT)
            osint = brief.get("osint_findings", [])
            if osint:
                st.subheader("External Intelligence")
                _RELEVANCE_COLORS = {
                    "Low":    "#6c757d",
                    "Medium": "#fd7e14",
                    "High":   "#dc3545",
                }
                for item in osint:
                    rel          = item.get("relevance", "Low")
                    border_color = _RELEVANCE_COLORS.get(rel, "#6c757d")
                    st.markdown(
                        f"""
                        <div style="border-left:4px solid {border_color};
                                    padding:0.6rem 1rem;
                                    margin-bottom:0.8rem;
                                    background:#f8f9fa;
                                    border-radius:0 4px 4px 0">
                            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.3rem">
                                <strong>{item['source']}</strong>
                                {_badge(f"Relevance: {rel}", border_color)}
                            </div>
                            <div style="color:#444;font-size:0.93em">{item['finding']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.divider()

            # Summary
            st.subheader("Summary")
            st.write(brief["summary"])

            st.divider()

        else:
            st.warning("No risk brief available. Analysis may still be running or failed.")

        # ── Submission details (collapsed) ────────────────────────────────────

        with st.expander("View raw submission details"):
            fields = {
                "Date of Birth":               submission.date_of_birth,
                "Nationality":                 submission.nationality,
                "Country of Birth":            submission.country_of_birth,
                "Country of Residence":        submission.country_of_residence,
                "Occupation":                  submission.occupation,
                "Employer":                    submission.employer,
                "Source of Funds":             submission.source_of_funds,
                "Expected Transaction Volume": submission.expected_transaction_volume,
                "PEP Status":                  "Yes" if submission.pep_status else "No",
                "Beneficial Ownership":        submission.beneficial_ownership,
            }
            for label, val in fields.items():
                st.markdown(f"**{label}:** {val}")

        st.divider()

        # ── Decision section ──────────────────────────────────────────────────

        if submission.status == "analyzed":
            st.subheader("Decision")
            notes = st.text_area(
                "Analyst notes (optional)",
                placeholder="Add any notes to accompany your decision.",
                key="decision_notes",
            )
            col_approve, col_reject, _ = st.columns([1, 1, 4])

            with col_approve:
                if st.button("Approve", type="primary", use_container_width=True):
                    submission.status   = "approved"
                    submission.decision = {
                        "outcome":    "approved",
                        "notes":      notes.strip(),
                        "decided_at": datetime.now(timezone.utc).isoformat(),
                    }
                    update_submission(submission)
                    st.rerun()

            with col_reject:
                if st.button("Reject", type="secondary", use_container_width=True):
                    submission.status   = "rejected"
                    submission.decision = {
                        "outcome":    "rejected",
                        "notes":      notes.strip(),
                        "decided_at": datetime.now(timezone.utc).isoformat(),
                    }
                    update_submission(submission)
                    st.rerun()

        elif submission.status in ("approved", "rejected"):
            decision      = submission.decision or {}
            outcome_color = "#28a745" if submission.status == "approved" else "#dc3545"
            st.subheader("Decision")
            st.markdown(_badge(submission.status.capitalize(), outcome_color), unsafe_allow_html=True)
            st.caption(f"Decided: {fmt_ts(decision.get('decided_at', ''))}")
            if decision.get("notes"):
                st.markdown(f"**Analyst notes:** {decision['notes']}")

            # ── Dispute outcome (read-only on analyst side) ───────────────────

            if submission.dispute:
                dispute      = submission.dispute
                disp_outcome = dispute.get("outcome", "")
                disp_color   = "#28a745" if disp_outcome == "Overturned" else "#dc3545"
                st.divider()
                st.subheader("Dispute Review")
                st.markdown(_badge(disp_outcome, disp_color), unsafe_allow_html=True)
                st.caption(f"Reviewed: {fmt_ts(dispute.get('reviewed_at', ''))}")
                st.markdown(f"**Reviewer reasoning:** {dispute['reasoning']}")
                if dispute.get("revised_risk_level"):
                    st.markdown(f"**Revised risk level:** {dispute['revised_risk_level']}")
                with st.expander("View customer rebuttal"):
                    st.write(dispute.get("rebuttal", ""))

        elif submission.status == "pending":
            st.info("Analysis is still pending for this submission.")

    # ── List view ─────────────────────────────────────────────────────────────

    else:
        st.title("Analyst Dashboard")

        submissions = load_all_submissions()
        if not submissions:
            st.info("No submissions yet.")
        else:
            counts = {"pending": 0, "analyzed": 0, "approved": 0, "rejected": 0}
            for s in submissions:
                counts[s.status] = counts.get(s.status, 0) + 1

            c1, c2, c3, c4 = st.columns(4)
            for _col, _label, _value, _color in [
                (c1, "Total Submissions",  len(submissions),                       "#0f172a"),
                (c2, "Awaiting Review",    counts["pending"] + counts["analyzed"], "#2563eb"),
                (c3, "Approved",           counts["approved"],                     "#16a34a"),
                (c4, "Rejected",           counts["rejected"],                     "#dc2626"),
            ]:
                with _col:
                    st.markdown(f"""
                    <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;
                                padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,0.05)">
                        <div style="font-size:11px;font-weight:600;color:#94a3b8;
                                    text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px">{_label}</div>
                        <div style="font-size:36px;font-weight:800;color:{_color};
                                    line-height:1;font-variant-numeric:tabular-nums">{_value}</div>
                    </div>""", unsafe_allow_html=True)

            st.divider()

            h1, h2, h3, h4, h5 = st.columns([3, 1.8, 1.5, 1.5, 1])
            for _hcol, _hlabel in [(h1, "Name"), (h2, "Submitted"), (h3, "Risk Level"), (h4, "Status")]:
                _hcol.markdown(
                    f'<div style="font-size:11px;font-weight:600;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:0.08em">{_hlabel}</div>',
                    unsafe_allow_html=True,
                )

            st.divider()

            for s in submissions:
                col1, col2, col3, col4, col5 = st.columns([3, 1.8, 1.5, 1.5, 1])
                col1.markdown(
                    f'<div style="line-height:1.4;padding:2px 0">'
                    f'<div style="font-size:14.5px;font-weight:600;color:#0f172a">{s.full_name}</div>'
                    f'<div style="font-size:11.5px;color:#94a3b8;font-family:monospace;margin-top:2px">{s.id}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                col2.markdown(
                    f'<div style="font-size:13px;color:#64748b;padding-top:4px">{fmt_ts(s.timestamp)}</div>',
                    unsafe_allow_html=True,
                )

                if s.risk_brief:
                    col3.markdown(risk_badge(s.risk_brief["risk_level"]), unsafe_allow_html=True)
                else:
                    col3.markdown("—")

                col4.markdown(status_badge(s.status), unsafe_allow_html=True)

                if col5.button("View", key=f"view_{s.id}"):
                    st.session_state.selected_id = s.id
                    st.rerun()

                st.markdown(
                    '<div style="border-top:1px solid #f1f5f9;margin:8px 0 4px"></div>',
                    unsafe_allow_html=True,
                )
