import streamlit as st
import google.generativeai as genai
import streamlit_authenticator as stauth
from datetime import date, datetime
import json

# ══════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="PhysioClinic AI",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ══════════════════════════════════════════════════════════
# CUSTOM CSS
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }

    [data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    [data-testid="stMetricLabel"] { font-size: 13px !important; color: #64748b !important; }
    [data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700 !important; }

    .vas-low    { background:#dcfce7; color:#166534; padding:3px 10px; border-radius:20px; font-weight:600; font-size:13px; }
    .vas-medium { background:#fef9c3; color:#854d0e; padding:3px 10px; border-radius:20px; font-weight:600; font-size:13px; }
    .vas-high   { background:#fee2e2; color:#991b1b; padding:3px 10px; border-radius:20px; font-weight:600; font-size:13px; }

    .status-confirmed { background:#dbeafe; color:#1e40af; padding:3px 10px; border-radius:20px; font-size:13px; font-weight:500; }
    .status-completed { background:#d1fae5; color:#065f46; padding:3px 10px; border-radius:20px; font-size:13px; font-weight:500; }
    .status-cancelled { background:#fee2e2; color:#991b1b; padding:3px 10px; border-radius:20px; font-size:13px; font-weight:500; }
    .status-walkin    { background:#f3e8ff; color:#6b21a8; padding:3px 10px; border-radius:20px; font-size:13px; font-weight:500; }

    .section-header {
        font-size: 11px; font-weight: 600; letter-spacing: 1.5px;
        color: #94a3b8; text-transform: uppercase; margin: 20px 0 8px;
    }
    .analysis-box {
        background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
        border-left: 4px solid #0284c7;
        border-radius: 0 12px 12px 0;
        padding: 20px; margin-top: 16px;
    }
    .priority-urgent {
        background: #fff1f2; border: 1px solid #fda4af;
        border-radius: 10px; padding: 14px 18px; margin: 10px 0;
    }
    .priority-routine {
        background: #f0fdf4; border: 1px solid #86efac;
        border-radius: 10px; padding: 14px 18px; margin: 10px 0;
    }

    #MainMenu, footer { visibility: hidden; }
    .stDeployButton { display: none; }

    .stFormSubmitButton > button {
        background: linear-gradient(135deg, #0284c7, #0369a1) !important;
        color: white !important; border: none !important;
        border-radius: 10px !important; font-weight: 600 !important;
        padding: 12px 24px !important; font-size: 15px !important;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════
for k, v in {
    "authentication_status": None,
    "db": [],
    "analysis_target": None,
    "analysis_cache": {},
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════
# SECRETS
# ══════════════════════════════════════════════════════════
try:
    credentials = st.secrets["credentials"].to_dict()
    cookie = st.secrets["cookie"].to_dict()
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception as e:
    st.error(f"❌ Configuration Error: {e}")
    st.info("Ensure your Streamlit Cloud Secrets has: [credentials], [cookie], and GEMINI_API_KEY")
    st.stop()

# ══════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════
authenticator = stauth.Authenticate(
    credentials, cookie['name'], cookie['key'], cookie['expiry_days']
)
try:
    authenticator.login()
except Exception as e:
    st.error(f"Login Widget Error: {e}")


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════
def vas_badge(level):
    try:
        v = int(level)
    except:
        return f'<span class="vas-medium">{level}</span>'
    if v <= 3:
        return f'<span class="vas-low">VAS {v} – Mild</span>'
    elif v <= 6:
        return f'<span class="vas-medium">VAS {v} – Moderate</span>'
    else:
        return f'<span class="vas-high">VAS {v} – Severe</span>'

def status_badge(status):
    s = str(status).lower()
    if "confirm" in s:  return f'<span class="status-confirmed">{status}</span>'
    elif "complete" in s: return f'<span class="status-completed">{status}</span>'
    elif "cancel" in s:  return f'<span class="status-cancelled">{status}</span>'
    else: return f'<span class="status-walkin">{status}</span>'

def calc_age(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return "N/A"

def patient_id(p):
    return f"{p.get('name','')}_{p.get('date','')}_{p.get('time','')}"

def build_analysis_prompt(patient: dict) -> str:
    age = calc_age(patient.get("dob", ""))
    age_str = f"{age} years old" if age != "N/A" else "Age unknown"
    return "\n".join([
        "You are a senior physiotherapist and clinical assessor. Using ALL the information below, produce a structured clinical report.",
        "Format your response using these exact headings:",
        "",
        "## 🔬 Anatomical & Biomechanical Analysis",
        "## 🩺 Differential Diagnoses",
        "## 🚨 Red Flags & Urgent Referral Criteria",
        "## 💊 Recommended Treatment Plan",
        "## 📈 Prognosis & Recovery Timeline",
        "## 🏠 Home Management & Self-Care Advice",
        "## 📋 Pre-Appointment Notes for Therapist",
        "",
        "Be specific, clinically accurate, and tailor every section to this exact patient.",
        "",
        "═══════════ PATIENT PROFILE ═══════════",
        f"Full Name:            {patient.get('name', 'Unknown')}",
        f"Age:                  {age_str}",
        f"Date of Birth:        {patient.get('dob', 'Not provided')}",
        f"Gender:               {patient.get('gender', 'Not specified')}",
        f"Occupation:           {patient.get('occupation', 'Not provided')}",
        f"Activity Level:       {patient.get('activity_level', 'Not provided')}",
        f"Current Medications:  {patient.get('medications', 'None reported')}",
        f"Previous Injury/Op:   {patient.get('prev_injury', 'Not specified')}",
        "",
        "═══════════ CLINICAL PRESENTATION ═════",
        f"Pain Location/Area:   {patient.get('location', 'Not specified')}",
        f"Pain Severity (VAS):  {patient.get('level', 'Not specified')} / 10",
        f"Pain Characteristics: {patient.get('pain_type', 'Not specified')}",
        f"Pain Worst Timing:    {patient.get('pain_timing', 'Not specified')}",
        f"Condition Duration:   {patient.get('duration', 'Not specified')}",
        f"Referral Source:      {patient.get('referral', 'Not specified')}",
        f"Patient Notes:        {patient.get('notes', 'None provided')}",
        "",
        "═══════════ APPOINTMENT DETAILS ════════",
        f"Appointment Date:     {patient.get('date', 'Not specified')}",
        f"Appointment Time:     {patient.get('time', 'Not specified')}",
        f"Session Type:         {patient.get('session', 'Not specified')}",
        f"Assigned Therapist:   {patient.get('therapist', 'Not specified')}",
        f"Booking Status:       {patient.get('status', 'Not specified')}",
    ])


# ══════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════
if st.session_state["authentication_status"]:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("## 🏥 PhysioClinic AI")
        st.markdown("---")
        authenticator.logout('Logout', 'sidebar')
        st.markdown(f"👋 **{st.session_state.get('name', 'User')}**")
        st.markdown("---")
        page = st.radio(
            "Navigate",
            ["📊 Dashboard", "📅 Book Appointment", "📆 Schedule", "🩺 AI Analysis", "💡 Clinic Insights"],
            label_visibility="collapsed"
        )
        st.markdown("---")
        db = st.session_state.db
        total = len(db)
        confirmed = sum(1 for p in db if "confirm" in str(p.get("status","")).lower())
        urgent = sum(1 for p in db if int(p.get("level", 0)) >= 7)
        st.metric("Total Patients", total)
        st.metric("Confirmed", confirmed)
        st.metric("High Pain (VAS≥7)", urgent)

    # ══════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════
    if page == "📊 Dashboard":
        st.title("📊 Clinic Dashboard")
        st.caption(f"Today — {date.today().strftime('%A, %d %B %Y')}")

        db = st.session_state.db
        total = len(db)
        today_appts = sum(1 for p in db if p.get("date") == str(date.today()))
        avg_vas = round(sum(int(p.get("level", 5)) for p in db) / total, 1) if total else 0
        urgent_count = sum(1 for p in db if int(p.get("level", 0)) >= 7)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 Total Bookings", total)
        c2.metric("📅 Today's Appointments", today_appts)
        c3.metric("📊 Avg Pain Score", avg_vas)
        c4.metric("🚨 High Severity (VAS≥7)", urgent_count)

        st.markdown("---")
        col_l, col_r = st.columns([3, 2])

        with col_l:
            st.subheader("📅 Upcoming Appointments")
            upcoming = sorted(
                [p for p in db if p.get("date","") >= str(date.today())],
                key=lambda x: (x.get("date",""), x.get("time",""))
            )[:10]
            if upcoming:
                for p in upcoming:
                    cols = st.columns([3, 2, 2, 2])
                    cols[0].markdown(f"**{p.get('name','N/A')}**  \n<small>{p.get('location','')}</small>", unsafe_allow_html=True)
                    cols[1].markdown(f"📅 {p.get('date','')}")
                    cols[2].markdown(f"🕐 {p.get('time','')}")
                    cols[3].markdown(vas_badge(p.get("level","?")), unsafe_allow_html=True)
                    st.divider()
            else:
                st.info("No upcoming appointments.")

        with col_r:
            st.subheader("🚨 Urgent Triage (VAS ≥ 7)")
            urgent_patients = [p for p in db if int(p.get("level", 0)) >= 7]
            if urgent_patients:
                for p in urgent_patients:
                    st.markdown(f"""
                    <div class="priority-urgent">
                        <strong>{p.get('name','N/A')}</strong><br>
                        🦴 {p.get('location','N/A')} &nbsp; {vas_badge(p.get('level','?'))}
                        <br><small>📅 {p.get('date','')} {p.get('time','')}</small>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown('<div class="priority-routine">✅ No urgent cases. All patients in manageable pain range.</div>', unsafe_allow_html=True)

            st.subheader("👨‍⚕️ Therapist Workload")
            therapists = {}
            for p in db:
                t = p.get("therapist","")
                if t and t != "No preference":
                    therapists[t] = therapists.get(t, 0) + 1
            if therapists:
                max_val = max(therapists.values())
                for t, count in sorted(therapists.items(), key=lambda x: -x[1]):
                    st.markdown(f"**{t}** — {count}")
                    st.progress(count / max_val)
            else:
                st.info("No therapist assignments yet.")

    # ══════════════════════════════════════════════════════
    # BOOK APPOINTMENT
    # ══════════════════════════════════════════════════════
    elif page == "📅 Book Appointment":
        st.title("📅 Book a Physiotherapy Appointment")
        st.caption("Complete all required (*) fields to confirm your visit.")

        with st.form("booking_form", clear_on_submit=True):
            st.markdown('<div class="section-header">👤 Patient Information</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                first_name = st.text_input("First Name *")
                dob = st.date_input("Date of Birth *", min_value=date(1900,1,1), max_value=date.today(), value=date(1990,1,1))
            with c2:
                last_name = st.text_input("Last Name *")
                gender = st.selectbox("Gender", ["Prefer not to say","Male","Female","Other"])
            with c3:
                phone = st.text_input("Phone Number *")
                email = st.text_input("Email Address")

            st.markdown('<div class="section-header">📋 Medical Background</div>', unsafe_allow_html=True)
            c4, c5 = st.columns(2)
            with c4:
                prev_injury = st.selectbox("Previous injury / surgery in this area?", [
                    "No","Yes – previous injury","Yes – post-surgery","Yes – chronic condition"
                ])
                occupation = st.text_input("Occupation", placeholder="e.g. Office worker, Athlete")
            with c5:
                activity_level = st.selectbox("Activity Level", [
                    "Sedentary","Lightly active","Moderately active","Very active","Elite athlete"
                ])
                medications = st.text_input("Current medications", placeholder="e.g. Ibuprofen, Paracetamol")

            st.markdown('<div class="section-header">🦴 Condition Details</div>', unsafe_allow_html=True)
            c6, c7 = st.columns(2)
            with c6:
                pain_location = st.text_input("Primary Area of Pain *", placeholder="e.g. Lower back, Left knee")
                pain_level = st.slider("Pain Severity – VAS (0 = none, 10 = worst)", 0, 10, 5)
                pain_type = st.multiselect("Pain Characteristics", [
                    "Sharp","Burning","Aching","Throbbing","Shooting",
                    "Stabbing","Tingling / Numbness","Stiffness","Weakness"
                ])
            with c7:
                condition_duration = st.selectbox("How long have you had this?", [
                    "Less than 1 week","1–2 weeks","2–4 weeks",
                    "1–3 months","3–6 months","More than 6 months"
                ])
                pain_timing = st.selectbox("When is pain worst?", [
                    "Morning (after rest)","During activity","After activity",
                    "At night","Constant / all day","Random / unpredictable"
                ])
                referral = st.selectbox("Referral Source", [
                    "Self-referred","GP/Doctor referral","Specialist referral",
                    "Insurance referral","Word of mouth","Other"
                ])

            additional_notes = st.text_area(
                "Describe your symptoms in your own words",
                placeholder="What makes it better or worse? Any radiating pain, swelling, or locking?",
                height=90
            )

            st.markdown('<div class="section-header">📆 Appointment Preferences</div>', unsafe_allow_html=True)
            c8, c9, c10 = st.columns(3)
            with c8:
                appt_date = st.date_input("Preferred Date *", min_value=date.today())
            with c9:
                appt_time = st.selectbox("Preferred Time *", [
                    "9:00 AM","9:30 AM","10:00 AM","10:30 AM","11:00 AM","11:30 AM",
                    "1:00 PM","1:30 PM","2:00 PM","2:30 PM","3:00 PM","3:30 PM","4:00 PM","4:30 PM"
                ])
                session_type = st.selectbox("Session Type", [
                    "Initial Assessment (60 min)",
                    "Follow-up Treatment (45 min)",
                    "Hydrotherapy (45 min)",
                    "Sports Injury Assessment (60 min)",
                    "Post-Surgery Rehabilitation (60 min)",
                    "Dry Needling / Acupuncture (30 min)",
                    "Manual Therapy (45 min)"
                ])
            with c10:
                therapist_pref = st.selectbox("Therapist Preference", [
                    "No preference","Dr. Sarah Mitchell","Dr. James Okafor","Dr. Priya Nair"
                ])

            consent = st.checkbox("✅ I consent to my personal health information being used for treatment purposes. *")
            submitted = st.form_submit_button("📋 Confirm Booking", use_container_width=True)

            if submitted:
                errors = []
                if not first_name.strip(): errors.append("First Name")
                if not last_name.strip():  errors.append("Last Name")
                if not phone.strip():      errors.append("Phone Number")
                if not pain_location.strip(): errors.append("Pain Location")
                if not consent: errors.append("Consent checkbox")

                if errors:
                    st.error(f"⚠️ Please complete: {', '.join(errors)}")
                else:
                    full_name = f"{first_name.strip()} {last_name.strip()}"
                    booking = {
                        "name": full_name,
                        "dob": str(dob),
                        "gender": gender,
                        "phone": phone.strip(),
                        "email": email.strip(),
                        "occupation": occupation,
                        "activity_level": activity_level,
                        "medications": medications,
                        "prev_injury": prev_injury,
                        "location": pain_location.strip(),
                        "level": pain_level,
                        "pain_type": ", ".join(pain_type) if pain_type else "Not specified",
                        "pain_timing": pain_timing,
                        "duration": condition_duration,
                        "referral": referral,
                        "notes": additional_notes.strip(),
                        "date": str(appt_date),
                        "time": appt_time,
                        "therapist": therapist_pref,
                        "session": session_type,
                        "status": "Confirmed",
                        "booked_at": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    st.session_state.db.append(booking)
                    age = calc_age(str(dob))
                    st.success(f"✅ Booked: **{full_name}** (Age {age}) on **{appt_date}** at **{appt_time}**")
                    st.markdown(
                        f"🩺 **{session_type}** &nbsp;|&nbsp; 👨‍⚕️ **{therapist_pref}** &nbsp;|&nbsp; "
                        f"🦴 **{pain_location}** &nbsp;|&nbsp; {vas_badge(pain_level)}",
                        unsafe_allow_html=True
                    )

    # ══════════════════════════════════════════════════════
    # SCHEDULE
    # ══════════════════════════════════════════════════════
    elif page == "📆 Schedule":
        st.title("📆 Appointment Schedule")

        db = st.session_state.db
        if not db:
            st.info("📭 No appointments yet.")
            st.stop()

        fc1, fc2, fc3, fc4 = st.columns([2,2,2,1])
        with fc1:
            filter_date = st.date_input("Filter by date", value=date.today())
        with fc2:
            filter_therapist = st.selectbox("Therapist", ["All","Dr. Sarah Mitchell","Dr. James Okafor","Dr. Priya Nair"])
        with fc3:
            filter_status = st.selectbox("Status", ["All","Confirmed","Completed","Cancelled","Walk-in"])
        with fc4:
            show_all = st.checkbox("All dates", value=True)

        filtered = sorted([
            p for p in db
            if (show_all or p.get("date") == str(filter_date))
            and (filter_therapist == "All" or p.get("therapist") == filter_therapist)
            and (filter_status == "All" or filter_status.lower() in str(p.get("status","")).lower())
        ], key=lambda x: (x.get("date",""), x.get("time","")))

        if not filtered:
            st.info("No appointments match your filters.")
        else:
            st.caption(f"Showing {len(filtered)} appointment{'s' if len(filtered)>1 else ''}")
            for i, entry in enumerate(filtered):
                pid = patient_id(entry)
                age = calc_age(entry.get("dob",""))
                age_label = f"Age {age}" if age != "N/A" else ""

                with st.expander(
                    f"👤 {entry.get('name','N/A')}  {'• ' + age_label if age_label else ''}  "
                    f"  |  📅 {entry.get('date','')}  🕐 {entry.get('time','')}  "
                    f"  |  🦴 {entry.get('location','N/A')}",
                    expanded=False
                ):
                    st.markdown(
                        f"{status_badge(entry.get('status',''))} &nbsp; {vas_badge(entry.get('level','?'))}",
                        unsafe_allow_html=True
                    )
                    st.markdown("")

                    ca, cb, cc = st.columns(3)
                    with ca:
                        st.markdown("**👤 Patient**")
                        st.markdown(f"DOB: {entry.get('dob','N/A')} ({age_label})")
                        st.markdown(f"Gender: {entry.get('gender','N/A')}")
                        st.markdown(f"Phone: {entry.get('phone','N/A')}")
                        st.markdown(f"Email: {entry.get('email','N/A')}")
                        st.markdown(f"Occupation: {entry.get('occupation','N/A')}")
                        st.markdown(f"Activity: {entry.get('activity_level','N/A')}")
                    with cb:
                        st.markdown("**🦴 Clinical**")
                        st.markdown(f"Pain Area: **{entry.get('location','N/A')}**")
                        st.markdown(f"VAS: **{entry.get('level','N/A')} / 10**")
                        st.markdown(f"Pain Type: {entry.get('pain_type','N/A')}")
                        st.markdown(f"Worst Timing: {entry.get('pain_timing','N/A')}")
                        st.markdown(f"Duration: {entry.get('duration','N/A')}")
                        st.markdown(f"Prev. Injury: {entry.get('prev_injury','N/A')}")
                        st.markdown(f"Medications: {entry.get('medications','N/A')}")
                    with cc:
                        st.markdown("**📋 Appointment**")
                        st.markdown(f"Session: {entry.get('session','N/A')}")
                        st.markdown(f"Therapist: {entry.get('therapist','N/A')}")
                        st.markdown(f"Referral: {entry.get('referral','N/A')}")
                        st.markdown(f"Booked: {entry.get('booked_at','N/A')}")

                    if entry.get("notes"):
                        st.markdown(f"**💬 Patient Notes:** _{entry['notes']}_")

                    st.markdown("")

                    # Status update
                    stat_col, btn1, btn2 = st.columns([2, 1.5, 1.5])
                    with stat_col:
                        status_options = ["Confirmed","Completed","Cancelled","No-show"]
                        cur_status = entry.get("status","Confirmed")
                        idx = status_options.index(cur_status) if cur_status in status_options else 0
                        new_status = st.selectbox("Update Status", status_options, index=idx, key=f"stat_{pid}_{i}")
                        if st.button("💾 Save", key=f"save_{pid}_{i}"):
                            actual_idx = next((j for j, p in enumerate(st.session_state.db) if patient_id(p) == pid), None)
                            if actual_idx is not None:
                                st.session_state.db[actual_idx]["status"] = new_status
                                st.success("Status updated!")
                                st.rerun()
                    with btn1:
                        if st.button("🧠 AI Analysis", key=f"ai_{pid}_{i}", use_container_width=True):
                            with st.spinner("Analysing…"):
                                response = model.generate_content(build_analysis_prompt(entry))
                                st.session_state.analysis_cache[pid] = response.text
                    with btn2:
                        if st.button("📤 Full Page", key=f"fp_{pid}_{i}", use_container_width=True):
                            st.session_state.analysis_target = entry
                            st.rerun()

                    if pid in st.session_state.analysis_cache:
                        st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
                        st.markdown("#### 🧠 AI Clinical Report")
                        st.markdown(st.session_state.analysis_cache[pid])
                        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🗑️ Clear All Appointments", type="secondary"):
            st.session_state.db = []
            st.session_state.analysis_cache = {}
            st.rerun()

    # ══════════════════════════════════════════════════════
    # AI ANALYSIS
    # ══════════════════════════════════════════════════════
    elif page == "🩺 AI Analysis":
        st.title("🩺 AI Clinical Analysis")

        tab1, tab2 = st.tabs(["📋 Patient from Schedule", "✍️ Manual / Walk-in"])

        with tab1:
            if st.session_state.analysis_target:
                patient = st.session_state.analysis_target
                pid = patient_id(patient)
                age = calc_age(patient.get("dob",""))
                st.success(f"Loaded: **{patient.get('name')}** | Age {age} | {patient.get('location')} | VAS {patient.get('level')}")

                if st.button("🔍 Generate Full Clinical Report", use_container_width=True, type="primary"):
                    with st.spinner("Generating comprehensive AI clinical report…"):
                        response = model.generate_content(build_analysis_prompt(patient))
                        st.session_state.analysis_cache[pid] = response.text

                if pid in st.session_state.analysis_cache:
                    st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
                    st.markdown(st.session_state.analysis_cache[pid])
                    st.markdown('</div>', unsafe_allow_html=True)

                if st.button("✖ Clear & Use Manual Entry"):
                    st.session_state.analysis_target = None
                    st.rerun()
            else:
                st.info("No patient loaded. Click **📤 Full Page** from Schedule, or use the Manual tab below.")

        with tab2:
            st.caption("Quick assessment for walk-in or unscheduled patients")
            mc1, mc2 = st.columns(2)
            with mc1:
                q_name = st.text_input("Patient Name", placeholder="Optional")
                q_location = st.text_input("Pain Location *")
                q_vas = st.slider("VAS Pain Score", 0, 10, 5)
                q_duration = st.selectbox("Condition Duration", [
                    "Less than 1 week","1–2 weeks","2–4 weeks","1–3 months","3–6 months","More than 6 months"
                ])
                q_pain_type = st.multiselect("Pain Characteristics", [
                    "Sharp","Burning","Aching","Throbbing","Shooting","Stabbing","Tingling","Stiffness","Weakness"
                ])
            with mc2:
                q_gender = st.selectbox("Gender", ["Unknown","Male","Female","Other"])
                q_age = st.number_input("Approximate Age", 0, 120, 40)
                q_occupation = st.text_input("Occupation", placeholder="Optional")
                q_activity = st.selectbox("Activity Level", [
                    "Sedentary","Lightly active","Moderately active","Very active"
                ])
                q_prev = st.selectbox("Previous injury in this area?", [
                    "No","Yes – previous injury","Yes – post-surgery","Yes – chronic"
                ])
                q_notes = st.text_area("Additional Notes", height=80)

            if st.button("⚡ Quick Analyse", use_container_width=True):
                if not q_location:
                    st.error("Please enter the pain location.")
                else:
                    with st.spinner("Generating analysis…"):
                        quick_patient = {
                            "name": q_name or "Walk-in Patient",
                            "dob": "",
                            "gender": q_gender,
                            "occupation": q_occupation,
                            "activity_level": q_activity,
                            "prev_injury": q_prev,
                            "medications": "Not provided",
                            "location": q_location,
                            "level": q_vas,
                            "duration": q_duration,
                            "pain_type": ", ".join(q_pain_type) if q_pain_type else "Not specified",
                            "pain_timing": "Not specified",
                            "notes": q_notes,
                            "session": "Walk-in Assessment",
                            "therapist": "TBD",
                            "date": str(date.today()),
                            "time": "",
                            "status": "Walk-in",
                        }
                        prompt = build_analysis_prompt(quick_patient).replace(
                            "Age:                  Age unknown",
                            f"Age (approx):         {q_age} years"
                        )
                        response = model.generate_content(prompt)
                        st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
                        st.markdown("#### 🧠 AI Clinical Report")
                        st.markdown(response.text)
                        st.markdown('</div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════
    # CLINIC INSIGHTS
    # ══════════════════════════════════════════════════════
    elif page == "💡 Clinic Insights":
        st.title("💡 Clinic Insights & Analytics")

        db = st.session_state.db
        if not db:
            st.info("No data yet. Book appointments to see insights.")
            st.stop()

        total = len(db)
        avg_vas = round(sum(int(p.get("level",5)) for p in db)/total, 1)
        confirmed = sum(1 for p in db if "confirm" in str(p.get("status","")).lower())
        completed = sum(1 for p in db if "complete" in str(p.get("status","")).lower())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Patients", total)
        c2.metric("Avg VAS Score", avg_vas)
        c3.metric("Confirmed", confirmed)
        c4.metric("Completed", completed)

        st.markdown("---")
        ia, ib = st.columns(2)

        with ia:
            st.subheader("🦴 Most Common Pain Areas")
            area_count = {}
            for p in db:
                loc = p.get("location","Unknown").strip().title()
                area_count[loc] = area_count.get(loc, 0) + 1
            for area, count in sorted(area_count.items(), key=lambda x:-x[1]):
                st.markdown(f"**{area}** — {count}")
                st.progress(count / max(area_count.values()))

        with ib:
            st.subheader("📊 Pain Severity Distribution")
            buckets = {"Mild (0–3)": 0, "Moderate (4–6)": 0, "Severe (7–10)": 0}
            for p in db:
                v = int(p.get("level", 5))
                if v <= 3:   buckets["Mild (0–3)"] += 1
                elif v <= 6: buckets["Moderate (4–6)"] += 1
                else:        buckets["Severe (7–10)"] += 1
            for label, count in buckets.items():
                pct = int(count/total*100) if total else 0
                st.markdown(f"**{label}** — {count} ({pct}%)")
                st.progress(count/total if total else 0)

        st.markdown("---")
        ic, id_ = st.columns(2)

        with ic:
            st.subheader("🩺 Session Types")
            sess_count = {}
            for p in db:
                s = p.get("session","Unknown")
                sess_count[s] = sess_count.get(s, 0) + 1
            for s, count in sorted(sess_count.items(), key=lambda x:-x[1]):
                st.markdown(f"**{s}** — {count}")
                st.progress(count/total)

        with id_:
            st.subheader("⏱️ Condition Duration")
            dur_count = {}
            for p in db:
                d = p.get("duration","Unknown")
                dur_count[d] = dur_count.get(d, 0) + 1
            for d, count in sorted(dur_count.items(), key=lambda x:-x[1]):
                st.markdown(f"**{d}** — {count}")
                st.progress(count/total)

        st.markdown("---")
        st.subheader("🧠 AI Clinic-Wide Summary Report")
        st.caption("AI will analyse all patient data and surface clinical trends, risks, and operational recommendations.")
        if st.button("🔍 Generate AI Clinic Insights", use_container_width=True):
            summary_data = json.dumps([{
                "name": p.get("name"),
                "age": calc_age(p.get("dob","")),
                "gender": p.get("gender"),
                "occupation": p.get("occupation"),
                "activity_level": p.get("activity_level"),
                "location": p.get("location"),
                "vas": p.get("level"),
                "pain_type": p.get("pain_type"),
                "pain_timing": p.get("pain_timing"),
                "duration": p.get("duration"),
                "prev_injury": p.get("prev_injury"),
                "medications": p.get("medications"),
                "session": p.get("session"),
                "referral": p.get("referral"),
                "status": p.get("status"),
            } for p in db], indent=2)
            prompt = f"""You are a senior physiotherapy clinic manager reviewing patient intake data.
Given the cohort of {total} patients below, provide a structured clinic report with these sections:

## 🔍 Key Clinical Trends
## 🚨 Patients Requiring Urgent Attention
## 👨‍⚕️ Staffing & Resource Recommendations
## 💡 Top 5 Operational Improvements
## 📊 Demographic & Referral Observations
## 🏆 Positive Highlights

Be specific, evidence-based, and clinically focused. Reference actual patterns in the data.

Patient cohort:
{summary_data}"""
            with st.spinner("Generating clinic-wide AI insights…"):
                response = model.generate_content(prompt)
                st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
                st.markdown(response.text)
                st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# AUTH STATES
# ══════════════════════════════════════════════════════════
elif st.session_state["authentication_status"] is False:
    st.error("❌ Incorrect username or password. Please try again.")
elif st.session_state["authentication_status"] is None:
    st.markdown("## 🏥 PhysioClinic AI")
    st.markdown("Please log in to access the clinic management system.")
