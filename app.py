import time
from pathlib import Path

import streamlit as st
from datetime import date, datetime, timezone

from agent import run_analysis, review_dispute, finalise_edd_analysis
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
    "pending":      "#6c757d",
    "awaiting_edd": "#f59e0b",
    "analyzed":     "#0d6efd",
    "approved":     "#28a745",
    "rejected":     "#dc3545",
}


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:3px 10px;'
        f'border-radius:4px;font-size:0.82em;font-weight:600">{text}</span>'
    )


def risk_badge(level: str) -> str:
    return _badge(level, _RISK_COLORS.get(level, "#6c757d"))


def status_badge(status: str) -> str:
    _labels = {"awaiting_edd": "Awaiting EDD"}
    label = _labels.get(status, status.capitalize())
    return _badge(label, _STATUS_COLORS.get(status, "#6c757d"))


def fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M UTC")
    except Exception:
        return iso


def _append_email(submission, subject: str, body: str, action: str = "") -> None:
    """Append a simulated email notification to the submission. Caller must save."""
    submission.emails.append({
        "subject": subject,
        "body":    body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read":    False,
        "action":  action,
    })


# ── Session state ─────────────────────────────────────────────────────────────

if "selected_id" not in st.session_state:
    st.session_state.selected_id = None
if "customer_view" not in st.session_state:
    st.session_state.customer_view = "home"  # home | new_application | check_status | inbox


# ── Navigation ────────────────────────────────────────────────────────────────

page = st.sidebar.radio("Navigation", ["Customer Onboarding", "Analyst Dashboard"])

if page == "Analyst Dashboard" and st.session_state.customer_view != "home":
    st.session_state.customer_view = "home"
    st.session_state.pop("_looked_up_id", None)
    st.session_state.pop("_inbox_open_idx", None)

_inbox_unread = 0
if "_looked_up_id" in st.session_state:
    try:
        _inbox_unread = sum(
            1 for e in load_submission(st.session_state["_looked_up_id"]).emails
            if not e.get("read")
        )
    except Exception:
        pass
_inbox_label = f"📬 My Inbox  ({_inbox_unread})" if _inbox_unread > 0 else "📬 My Inbox"
if st.sidebar.button(_inbox_label, use_container_width=True, key="nav_inbox"):
    st.session_state.customer_view = "inbox"
    st.session_state.pop("_inbox_open_idx", None)
    st.rerun()

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

        # Clear form fields before any widgets render (cannot do this mid-run)
        if st.session_state.pop("_form_clear", False):
            for _k in ["fv_first_name", "fv_middle_name", "fv_last_name",
                       "fv_nationality", "fv_country_of_birth",
                       "fv_country_of_residence", "fv_occupation", "fv_employer",
                       "fv_source_of_funds", "fv_beneficial_ownership"]:
                st.session_state[_k] = ""

        st.title("New Application")
        st.write(
            "Please complete all fields accurately. "
            "Incomplete or false information may result in your application being declined."
        )

        # Initialise persistent field values so they survive a failed validation rerun
        for _k, _default in [
            ("fv_first_name", ""), ("fv_middle_name", ""), ("fv_last_name", ""),
            ("fv_nationality", ""), ("fv_country_of_birth", ""),
            ("fv_country_of_residence", ""), ("fv_occupation", ""), ("fv_employer", ""),
            ("fv_source_of_funds", ""), ("fv_beneficial_ownership", ""),
        ]:
            if _k not in st.session_state:
                st.session_state[_k] = _default

        # Show submission success message (set after a successful submit + rerun)
        _sid = st.session_state.pop("_form_success_id", None)
        if _sid:
            st.session_state["_last_success_id"] = _sid
        _last_sid = st.session_state.get("_last_success_id")
        if _last_sid:
            st.success(
                f"Application submitted. Your reference ID is **{_last_sid}**. "
                "A compliance analyst will review your application."
            )

        # Show analysis error if analysis failed on previous run
        _analysis_err = st.session_state.pop("_analysis_error", None)
        if _analysis_err:
            st.error(
                f"Your application was submitted but the automated analysis could not complete. "
                f"A compliance analyst has been notified and will review it manually.\n\n"
                f"*Technical detail: {_analysis_err}*"
            )

        # Validation error banner rendered above the form
        _error_slot = st.empty()

        def _label(text: str, required: bool = True) -> None:
            if required:
                st.markdown(
                    f'{text} <span style="color:#ef4444;font-weight:600">*</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'{text} <span style="color:#94a3b8;font-size:0.85em">(optional)</span>',
                    unsafe_allow_html=True,
                )

        st.caption("Fields marked * are required.")

        with st.form("kyc_form"):
            st.subheader("Personal Information")

            _label("First Name")
            first_name = st.text_input("First Name", key="fv_first_name", label_visibility="collapsed")

            _label("Middle Name", required=False)
            middle_name = st.text_input("Middle Name", key="fv_middle_name", label_visibility="collapsed")

            _label("Last Name")
            last_name = st.text_input("Last Name", key="fv_last_name", label_visibility="collapsed")

            _label("Date of Birth")
            date_of_birth = st.date_input(
                "Date of Birth",
                value=date(1990, 1, 1),
                min_value=date(1900, 1, 1),
                max_value=date.today(),
                label_visibility="collapsed",
            )

            _label("Nationality")
            nationality = st.text_input("Nationality", key="fv_nationality", label_visibility="collapsed")

            _label("Country of Birth")
            country_of_birth = st.text_input("Country of Birth", key="fv_country_of_birth", label_visibility="collapsed")

            _label("Country of Residence")
            country_of_residence = st.text_input("Country of Residence", key="fv_country_of_residence", label_visibility="collapsed")

            st.subheader("Employment & Finances")

            _label("Occupation / Job Title")
            occupation = st.text_input("Occupation / Job Title", key="fv_occupation", label_visibility="collapsed")

            _label("Employer or Business Name")
            employer = st.text_input("Employer or Business Name", key="fv_employer", label_visibility="collapsed")

            _label("Source of Funds")
            source_of_funds = st.text_area(
                "Source of Funds",
                placeholder=(
                    "Describe how you obtained the funds you intend to use — "
                    "e.g. salary, business income, inheritance, sale of property."
                ),
                height=100,
                key="fv_source_of_funds",
                label_visibility="collapsed",
            )

            _label("Expected Monthly Transaction Volume")
            expected_transaction_volume = st.selectbox(
                "Expected Monthly Transaction Volume",
                ["Under €1,000", "€1,000 – €5,000", "€5,000 – €10,000",
                 "€10,000 – €15,000", "€15,000 – €20,000", "€20,000 – €30,000",
                 "€30,000 – €40,000", "€40,000 – €50,000", "€50,000 – €100,000",
                 "Over €100,000"],
                label_visibility="collapsed",
            )

            st.subheader("Compliance Declarations")

            _label("Are you, or have you ever been, a Politically Exposed Person (PEP)?")
            st.caption("A PEP is someone who holds or has held a prominent public position, or is a close associate of such a person.")
            pep_raw = st.radio(
                "PEP status",
                ["No", "Yes"],
                label_visibility="collapsed",
            )

            _label("Beneficial Ownership", required=False)
            beneficial_ownership = st.text_area(
                "Beneficial Ownership",
                placeholder=(
                    "Are you acting on behalf of another person or entity? "
                    "If yes, provide their full name, relationship, and reason."
                ),
                height=100,
                key="fv_beneficial_ownership",
                label_visibility="collapsed",
            )

            submitted = st.form_submit_button("Submit Application", type="primary")

        if submitted:
            missing = [
                label for label, val in [
                    ("First Name",           first_name),
                    ("Last Name",            last_name),
                    ("Nationality",          nationality),
                    ("Country of Birth",     country_of_birth),
                    ("Country of Residence", country_of_residence),
                    ("Occupation",           occupation),
                    ("Employer",             employer),
                    ("Source of Funds",      source_of_funds),
                ]
                if not val.strip()
            ]
            if missing:
                fields_list = ", ".join(missing)
                _error_slot.error(
                    f"Please complete the following required fields: **{fields_list}**."
                )
            else:
                _parts = [first_name.strip(), middle_name.strip(), last_name.strip()]
                _full_name = " ".join(p for p in _parts if p)
                _pep = (pep_raw == "Yes")
                submission = Submission(
                    full_name=_full_name,
                    date_of_birth=str(date_of_birth),
                    nationality=nationality.strip(),
                    country_of_birth=country_of_birth.strip(),
                    country_of_residence=country_of_residence.strip(),
                    occupation=occupation.strip(),
                    employer=employer.strip(),
                    source_of_funds=source_of_funds.strip(),
                    expected_transaction_volume=expected_transaction_volume,
                    pep_status=_pep,
                    beneficial_ownership=beneficial_ownership.strip(),
                    edd_required=_pep,
                )
                save_submission(submission)

                _analysis_error = None
                with st.spinner("Analysing your submission..."):
                    try:
                        run_analysis(submission.id)
                    except Exception as e:
                        _analysis_error = str(e)

                if _analysis_error:
                    st.session_state["_analysis_error"] = _analysis_error

                # Add emails (reload so we don't overwrite the risk brief)
                _post = load_submission(submission.id)
                _append_email(
                    _post,
                    f"Application Received — Reference ID: {_post.id}",
                    f"We have received your KYC application (Reference ID: {_post.id}) and it is "
                    "now under review. A compliance analyst will be in touch once a decision has "
                    "been made. Please keep your reference ID safe — you will need it to check "
                    "the status of your application.",
                )
                if _post.edd_required:
                    _append_email(
                        _post,
                        "Action Required — Enhanced Due Diligence",
                        f"Because you have declared a political affiliation, we are required to "
                        f"collect additional information before your application (Reference ID: {_post.id}) "
                        "can proceed. Please complete the Enhanced Due Diligence form by selecting "
                        "'Check My Application' and entering your reference ID.",
                        action="edd",
                    )
                update_submission(_post)
                st.session_state["_looked_up_id"] = _post.id  # pre-fill so inbox works immediately

                # Flag for clearing on next run — cannot modify widget keys mid-run
                st.session_state["_form_clear"] = True
                st.session_state["_form_success_id"] = submission.id
                st.session_state.pop("_last_success_id", None)  # clear so top banner rerenders
                st.rerun()

        if _last_sid:
            st.success(
                f"Application submitted. Your reference ID is **{_last_sid}**. "
                "A compliance analyst will review your application."
            )

    # ── Inbox ─────────────────────────────────────────────────────────────────

    elif cv == "inbox":
        if st.button("← Back"):
            st.session_state.customer_view = "home"
            st.session_state.pop("_inbox_open_idx", None)
            st.rerun()

        st.title("My Inbox")

        if "_looked_up_id" not in st.session_state:
            st.write("Enter your reference ID to view your messages.")
            _inbox_id_input = st.text_input(
                "Reference ID", placeholder="e.g. A1B2C3D4", key="inbox_id_input"
            ).strip().upper()
            if st.button("View Messages", type="primary", key="inbox_lookup_btn"):
                if not _inbox_id_input:
                    st.error("Please enter your reference ID.")
                else:
                    try:
                        load_submission(_inbox_id_input)
                        st.session_state["_looked_up_id"] = _inbox_id_input
                        st.rerun()
                    except FileNotFoundError:
                        st.error("No application found with that reference ID.")
        else:
            try:
                _inbox_sub = load_submission(st.session_state["_looked_up_id"])
            except FileNotFoundError:
                st.session_state.pop("_looked_up_id", None)
                st.error("Application not found. Please re-enter your reference ID.")
                st.rerun()
                _inbox_sub = None

            if _inbox_sub:
                _emails_rev = list(reversed(_inbox_sub.emails))
                _n = len(_emails_rev)
                _open_idx = st.session_state.get("_inbox_open_idx")

                if _open_idx is not None and _open_idx < _n:
                    # ── Open email view ───────────────────────────────────────
                    _email = _emails_rev[_open_idx]

                    if st.button("← Back to inbox"):
                        st.session_state.pop("_inbox_open_idx", None)
                        st.rerun()

                    st.markdown(f"### {_email['subject']}")
                    st.caption(fmt_ts(_email["timestamp"]))
                    st.divider()
                    st.write(_email["body"])

                    if _email.get("action") == "dispute":
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("Go to Dispute →", type="primary", key="inbox_go_dispute"):
                            st.session_state.customer_view = "check_status"
                            st.session_state.pop("_inbox_open_idx", None)
                            st.rerun()
                    elif _email.get("action") == "edd":
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("Complete EDD Form →", type="primary", key="inbox_go_edd"):
                            st.session_state.customer_view = "check_status"
                            st.session_state.pop("_inbox_open_idx", None)
                            st.rerun()

                else:
                    # ── Email list view ───────────────────────────────────────
                    _unread_total = sum(1 for e in _inbox_sub.emails if not e.get("read"))
                    st.caption(
                        f"Application {_inbox_sub.id}  ·  {_n} message(s)"
                        + (f"  ·  {_unread_total} unread" if _unread_total else "")
                    )

                    if _n == 0:
                        st.info("No messages yet.")
                    else:
                        for _i, _email in enumerate(_emails_rev):
                            _is_unread = not _email.get("read", False)
                            _col_dot, _col_content, _col_btn = st.columns([0.4, 6.2, 1.2])

                            with _col_dot:
                                if _is_unread:
                                    st.markdown(
                                        '<div style="width:8px;height:8px;background:#2563eb;'
                                        'border-radius:50%;margin-top:14px"></div>',
                                        unsafe_allow_html=True,
                                    )

                            with _col_content:
                                _w = "700" if _is_unread else "400"
                                _c = "#0f172a" if _is_unread else "#64748b"
                                st.markdown(
                                    f'<div style="font-weight:{_w};color:{_c};font-size:0.95em;'
                                    f'padding-top:4px">{_email["subject"]}</div>'
                                    f'<div style="font-size:0.8em;color:#94a3b8;margin-top:2px">'
                                    f'{fmt_ts(_email["timestamp"])}</div>',
                                    unsafe_allow_html=True,
                                )

                            with _col_btn:
                                if st.button("Open", key=f"open_email_{_i}", use_container_width=True):
                                    # Mark as read on open
                                    _orig = _n - 1 - _i
                                    if not _inbox_sub.emails[_orig].get("read"):
                                        _inbox_sub.emails[_orig]["read"] = True
                                        update_submission(_inbox_sub)
                                    st.session_state["_inbox_open_idx"] = _i
                                    st.rerun()

                            st.markdown(
                                '<div style="border-top:1px solid #f1f5f9;margin:4px 0 2px"></div>',
                                unsafe_allow_html=True,
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

                elif looked_up.status == "awaiting_edd":
                    st.markdown(
                        '<div style="background:#fef3c7;border-left:4px solid #f59e0b;'
                        'padding:14px 18px;border-radius:0 8px 8px 0;margin-bottom:1.5rem">'
                        '<strong>Action Required</strong><br>'
                        'Your application requires additional information before it can proceed. '
                        'Please complete the Enhanced Due Diligence form below.'
                        '</div>',
                        unsafe_allow_html=True,
                    )

                    _edd_error = st.empty()

                    with st.form("edd_form"):
                        st.subheader("Enhanced Due Diligence")
                        st.write(
                            "Because you have declared a political affiliation, we are required "
                            "to collect the following information. All fields are required unless "
                            "marked optional."
                        )

                        st.markdown("**Nature of PEP connection**")
                        edd_connection = st.radio(
                            "Nature of PEP connection",
                            ["I am personally a PEP",
                             "I am a family member of a PEP",
                             "I am a close associate of a PEP"],
                            label_visibility="collapsed",
                        )

                        st.markdown(
                            'Full name of the politically exposed person '
                            '<span style="color:#94a3b8;font-size:0.85em">(if not yourself)</span>',
                            unsafe_allow_html=True,
                        )
                        edd_pep_name = st.text_input(
                            "PEP full name",
                            placeholder="Leave blank if you are the PEP",
                            label_visibility="collapsed",
                        )

                        st.markdown('Their official role or position <span style="color:#ef4444;font-weight:600">*</span>', unsafe_allow_html=True)
                        edd_pep_role = st.text_input(
                            "PEP role",
                            placeholder="e.g. Minister of Finance, Senator, Deputy Director",
                            label_visibility="collapsed",
                        )

                        st.markdown('Country and institution they are or were associated with <span style="color:#ef4444;font-weight:600">*</span>', unsafe_allow_html=True)
                        edd_pep_country_inst = st.text_input(
                            "Country and institution",
                            placeholder="e.g. Ministry of Finance, Government of South Sudan",
                            label_visibility="collapsed",
                        )

                        st.markdown("**How long has this connection been active?**")
                        edd_duration = st.selectbox(
                            "Connection duration",
                            ["Less than 1 year", "1–5 years", "More than 5 years", "No longer active"],
                            label_visibility="collapsed",
                        )

                        st.markdown('Source of wealth — origin of your total accumulated wealth and assets <span style="color:#ef4444;font-weight:600">*</span>', unsafe_allow_html=True)
                        edd_wealth = st.text_area(
                            "Source of wealth",
                            placeholder=(
                                "Describe the origin of your total wealth and assets — "
                                "e.g. career earnings, inheritance, business ownership, property sales."
                            ),
                            height=120,
                            label_visibility="collapsed",
                        )

                        st.markdown("**Are you aware of any investigations or proceedings involving the PEP?**")
                        edd_investigations = st.radio(
                            "Investigations",
                            ["No", "Yes"],
                            label_visibility="collapsed",
                        )
                        st.markdown(
                            'If Yes — provide details '
                            '<span style="color:#94a3b8;font-size:0.85em">(optional if No)</span>',
                            unsafe_allow_html=True,
                        )
                        edd_inv_details = st.text_area(
                            "Investigation details",
                            placeholder="Describe any known investigations or proceedings",
                            height=80,
                            label_visibility="collapsed",
                        )

                        edd_submitted = st.form_submit_button(
                            "Submit Enhanced Due Diligence Information",
                            type="primary",
                        )

                    if edd_submitted:
                        edd_missing = []
                        if not edd_pep_role.strip():
                            edd_missing.append("PEP official role or position")
                        if not edd_pep_country_inst.strip():
                            edd_missing.append("Country and institution")
                        if not edd_wealth.strip():
                            edd_missing.append("Source of wealth")
                        if edd_connection != "I am personally a PEP" and not edd_pep_name.strip():
                            edd_missing.append("Full name of the politically exposed person")
                        if edd_investigations == "Yes" and not edd_inv_details.strip():
                            edd_missing.append("Investigation details (required when Yes is selected)")

                        if edd_missing:
                            _edd_error.error(
                                f"Please complete the following required fields: **{', '.join(edd_missing)}**."
                            )
                        else:
                            from datetime import timezone as _tz
                            _edd_data = {
                                "pep_connection_type":    edd_connection,
                                "pep_person_name":        edd_pep_name.strip(),
                                "pep_role":               edd_pep_role.strip(),
                                "pep_country_institution": edd_pep_country_inst.strip(),
                                "connection_duration":    edd_duration,
                                "source_of_wealth":       edd_wealth.strip(),
                                "investigations_aware":   edd_investigations,
                                "investigations_details": edd_inv_details.strip(),
                                "submitted_at":           datetime.now(timezone.utc).isoformat(),
                            }
                            # Save EDD answers before running analysis
                            _edd_sub = load_submission(looked_up.id)
                            _edd_sub.edd_form = _edd_data
                            update_submission(_edd_sub)

                            with st.spinner("Submitting your information and running full analysis…"):
                                try:
                                    finalise_edd_analysis(looked_up.id)
                                    _edd_fresh = load_submission(looked_up.id)
                                    _append_email(
                                        _edd_fresh,
                                        "Enhanced Due Diligence Received",
                                        f"Thank you for completing your Enhanced Due Diligence "
                                        f"(Reference ID: {_edd_fresh.id}). Your application is now "
                                        "under full review by a compliance analyst. We will be in touch "
                                        "once a decision has been made.",
                                    )
                                    update_submission(_edd_fresh)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Submission failed: {e}")

                elif looked_up.status == "analyzed":
                    st.info("Your application is under review by a compliance analyst.")

                elif looked_up.status == "approved":
                    st.success("Your application has been approved.")
                    if any(d.get("analyst_decision") == "Accepted" for d in (looked_up.disputes or [])):
                        st.caption("Note: approved following a successful dispute review.")

                elif looked_up.status == "rejected":
                    cust_disputes   = looked_up.disputes or []
                    dispute_count   = looked_up.dispute_count
                    has_pending     = any(not d.get("analyst_decision") for d in cust_disputes)

                    if has_pending:
                        st.warning(
                            "Your dispute has been received and is under review. "
                            "We will contact you once a decision has been made."
                        )
                    elif dispute_count >= 2:
                        st.error("Your application has been rejected.")
                        st.warning(
                            "You have reached the maximum number of disputes. "
                            "Please contact us at compliance@kycplatform.com"
                        )
                    else:
                        # Customer can file a dispute (0 filed, or 1 filed and upheld)
                        st.error("Your application has been rejected.")
                        st.write(
                            "For legal and regulatory reasons, we are unable to disclose the specific "
                            "grounds for this decision. If you believe this decision is incorrect, you "
                            "may submit a dispute below and provide any information you believe is relevant."
                        )

                        dispute_num = dispute_count + 1
                        st.caption(f"Dispute {dispute_num} of 2")

                        rebuttal_text = st.text_area(
                            "Explain why you believe this decision is incorrect",
                            placeholder=(
                                "Be specific — provide verifiable details that address "
                                "the reasons for your rejection."
                            ),
                            height=150,
                            key="rebuttal_input",
                        )
                        tin_input = st.text_input(
                            "Tax Identification Number (optional)",
                            placeholder="Provide this to help verify your income source",
                            key="tin_input",
                        )
                        uploaded_files = st.file_uploader(
                            "Supporting documents — payslip, bank statement, ID (optional)",
                            type=["pdf", "png", "jpg", "jpeg"],
                            accept_multiple_files=True,
                            key="dispute_docs",
                        )

                        if st.button("Submit Dispute", type="primary", key="submit_dispute"):
                            if not rebuttal_text.strip():
                                st.error("Please explain why you believe the rejection is incorrect.")
                            else:
                                files_to_save = (uploaded_files or [])[:2]
                                filenames = []
                                if files_to_save:
                                    dispute_dir = Path(f"data/disputes/{looked_up.id}")
                                    dispute_dir.mkdir(parents=True, exist_ok=True)
                                    for uf in files_to_save:
                                        fname = f"d{dispute_num}_{uf.name}"
                                        with open(dispute_dir / fname, "wb") as out:
                                            out.write(uf.getbuffer())
                                        filenames.append(fname)

                                with st.spinner("Submitting your dispute…"):
                                    try:
                                        review_dispute(
                                            looked_up.id,
                                            rebuttal_text,
                                            tin=tin_input,
                                            document_filenames=filenames,
                                        )
                                        _fresh = load_submission(looked_up.id)
                                        _append_email(
                                            _fresh,
                                            "Dispute Received",
                                            f"We have received your dispute "
                                            f"(Reference ID: {_fresh.id}) and it is under review. "
                                            "We will contact you once a decision has been made.",
                                        )
                                        update_submission(_fresh)
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
                if brief.get("edd_pending") or brief.get("risk_level") is None:
                    st.markdown(_badge("EDD Pending", "#f59e0b"), unsafe_allow_html=True)
                    st.caption("Risk level will be set once the customer completes the EDD form.")
                else:
                    st.markdown(risk_badge(brief["risk_level"]), unsafe_allow_html=True)
                    score = brief.get("risk_score")
                    if score is not None:
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
                }.get(brief.get("recommendation", ""), "#6c757d")
                st.markdown(_badge(brief.get("recommendation", "Pending EDD"), rec_color), unsafe_allow_html=True)

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
                    _append_email(
                        submission,
                        "Application Approved",
                        f"We are pleased to inform you that your application "
                        f"(Reference ID: {submission.id}) has been approved. Welcome aboard.",
                    )
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
                    _append_email(
                        submission,
                        "Application Update",
                        f"We regret to inform you that we were unable to approve your application "
                        f"(Reference ID: {submission.id}) at this time. For legal and regulatory "
                        "reasons we are unable to share the specific grounds for this decision. "
                        "If you believe this decision is incorrect, you may submit a dispute using "
                        "your reference ID.",
                        action="dispute",
                    )
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

        elif submission.status == "awaiting_edd":
            st.markdown(
                '<div style="background:#fef3c7;border-left:4px solid #f59e0b;'
                'padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:1rem">'
                '<strong>Enhanced Due Diligence in progress</strong><br>'
                'This customer has declared PEP status. The EDD form has been sent to them and '
                'must be completed before a decision can be made. No action is required from you at this stage.'
                '</div>',
                unsafe_allow_html=True,
            )

        elif submission.status == "pending":
            st.info("Analysis has not completed for this submission.")
            if st.button("Run Analysis Now", type="primary", key="retry_analysis"):
                with st.spinner("Running analysis…"):
                    try:
                        run_analysis(submission.id)
                        st.success("Analysis complete.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

        # ── Disputes section (shown for any status once disputes exist) ────────

        if submission.disputes:
            has_pending_dispute = any(not d.get("analyst_decision") for d in submission.disputes)

            st.divider()

            if has_pending_dispute:
                st.markdown(
                    '<div style="background:#fef3c7;border-left:4px solid #f59e0b;'
                    'padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:1.5rem">'
                    '<strong>This customer has filed a dispute — your review is required</strong>'
                    '</div>',
                    unsafe_allow_html=True,
                )

            for i, disp in enumerate(submission.disputes, 1):
                st.subheader(f"Dispute {i} of {submission.dispute_count}")
                st.caption(f"Filed: {fmt_ts(disp.get('timestamp', ''))}")

                st.markdown("**Customer rebuttal**")
                st.write(disp.get("rebuttal", ""))

                if disp.get("tin"):
                    st.markdown(f"**Tax Identification Number:** `{disp['tin']}`")

                docs = disp.get("documents_uploaded", [])
                if docs:
                    st.markdown(f"**Supporting documents:** {', '.join(docs)}")

                # AI recommendation card
                ai_rec   = disp.get("ai_recommendation", "")
                ai_color = "#16a34a" if ai_rec == "Overturn Rejection" else "#dc2626"
                rl_line  = (
                    f'<div style="margin-top:6px;font-size:0.85em;color:#64748b">'
                    f'Suggested revised risk level: <strong>{disp["revised_risk_level"]}</strong></div>'
                    if disp.get("revised_risk_level") else ""
                )
                st.markdown(
                    f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
                    f'padding:16px;margin:0.75rem 0 1rem">'
                    f'<div style="font-size:11px;font-weight:600;color:#94a3b8;text-transform:uppercase;'
                    f'letter-spacing:0.08em;margin-bottom:8px">AI Advisory Recommendation</div>'
                    f'<div style="margin-bottom:8px">{_badge(ai_rec, ai_color)}</div>'
                    f'<div style="color:#374151;font-size:0.92em;line-height:1.5">'
                    f'{disp.get("ai_reasoning", "")}</div>'
                    f'{rl_line}</div>',
                    unsafe_allow_html=True,
                )

                analyst_decision = disp.get("analyst_decision")

                if analyst_decision:
                    # Read-only outcome
                    dec_color = "#16a34a" if analyst_decision == "Accepted" else "#dc2626"
                    st.markdown(
                        f"**Your decision:** {_badge(analyst_decision, dec_color)}",
                        unsafe_allow_html=True,
                    )
                    if disp.get("analyst_notes"):
                        st.markdown(f"**Notes:** {disp['analyst_notes']}")
                    if analyst_decision == "Upheld" and submission.dispute_count < 2:
                        st.info("Customer may file a second dispute.")
                else:
                    # Action buttons for analyst
                    analyst_notes = st.text_area(
                        "Analyst notes (optional)",
                        placeholder="Add notes to accompany your decision.",
                        key=f"dispute_notes_{i}",
                    )
                    col_accept, col_uphold, _ = st.columns([1.3, 1.3, 3.4])
                    with col_accept:
                        if st.button("Accept Customer", type="primary", key=f"accept_d{i}", use_container_width=True):
                            fresh = load_submission(submission.id)
                            fresh.disputes[i - 1]["analyst_decision"] = "Accepted"
                            fresh.disputes[i - 1]["analyst_notes"]    = analyst_notes.strip()
                            fresh.status = "approved"
                            _append_email(
                                fresh,
                                "Decision Updated",
                                f"Following your dispute, we have reviewed your application "
                                f"(Reference ID: {fresh.id}) and are pleased to inform you that "
                                "it has been approved. Welcome aboard.",
                            )
                            update_submission(fresh)
                            st.rerun()
                    with col_uphold:
                        if st.button("Uphold Rejection", type="secondary", key=f"uphold_d{i}", use_container_width=True):
                            fresh = load_submission(submission.id)
                            fresh.disputes[i - 1]["analyst_decision"] = "Upheld"
                            fresh.disputes[i - 1]["analyst_notes"]    = analyst_notes.strip()
                            _disputes_remaining = max(0, 2 - fresh.dispute_count)
                            if _disputes_remaining > 0:
                                _append_email(
                                    fresh,
                                    "Dispute Outcome",
                                    f"We have reviewed your dispute (Reference ID: {fresh.id}) "
                                    "and unfortunately must uphold our original decision. If you "
                                    "have additional information, you may submit a further dispute. "
                                    f"You have {_disputes_remaining} dispute(s) remaining.",
                                    action="dispute",
                                )
                            else:
                                _append_email(
                                    fresh,
                                    "Dispute Outcome",
                                    f"We have reviewed your dispute (Reference ID: {fresh.id}) "
                                    "and unfortunately must uphold our original decision. You have "
                                    "reached the maximum number of disputes for this application. "
                                    "Please contact us at compliance@kycplatform.com if you have "
                                    "further questions.",
                                )
                            update_submission(fresh)
                            st.rerun()

                if i < len(submission.disputes):
                    st.markdown('<div style="border-top:1px solid #e2e8f0;margin:1rem 0"></div>', unsafe_allow_html=True)

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
