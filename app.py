# app.py
# Dr. Yousra AKT/CSA Platform — Streamlit + Supabase (client auth + admin tools)
# All Rights Reserved © Dr. Yousra Abdelatti, MD, MRCGP [INT]
# Developed by Dr. Mohammedelnagi Mohammed

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import streamlit as st

# Supabase SDK v2
from supabase import create_client, Client

# --------- App Constants ----------
APP_TITLE = "Dr. Yousra Abdelatti — MRCGP AKT/CSA Preparations Platform"
COPYRIGHT = "All Rights Reserved © Dr. Yousra Abdelatti, MD, MRCGP [INT]"
DEV_FOOTER = "Developed by Dr. Mohammedelnagi Mohammed"

BRAND_IMAGE = Path("assets/brand/DrYousra.jpg")
ITEMS_PATH = Path("data/items.jsonl")

# --------- Secrets / Config ----------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")
# Optional but required for Admin panel features (invite/list/delete users)
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", None)

# Comma-separated list of admin emails in secrets.toml (e.g., "admin1@x.com, admin2@x.com")
ADMIN_EMAILS = [e.strip().lower() for e in st.secrets.get("ADMIN_EMAILS", "").split(",") if e.strip()]

# --------- Guardrails ----------
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error(
        "Supabase credentials are missing. Add SUPABASE_URL and SUPABASE_ANON_KEY to `.streamlit/secrets.toml`."
    )
    st.stop()

# --------- Clients ----------
def get_client_user() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def get_client_admin() -> Optional[Client]:
    if not SUPABASE_SERVICE_ROLE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

supabase_user = get_client_user()
supabase_admin = get_client_admin()

# --------- Helpers ----------
def load_items(jsonl_path: Path) -> pd.DataFrame:
    if not jsonl_path.exists():
        st.warning(f"Question bank not found at `{jsonl_path}`. Using empty dataset.")
        return pd.DataFrame(columns=["case_id", "domain", "sub_specialty", "topic", "question", "options", "correct_answer", "explanation", "guideline_reference"])
    rows = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    # Normalize options dict to stable order A-E
    if "options" in df.columns:
        def order_opts(d):
            keys = ["A", "B", "C", "D", "E"]
            return {k: d[k] for k in keys if k in d}
        df["options"] = df["options"].apply(lambda d: order_opts(d) if isinstance(d, dict) else d)
    return df

def is_logged_in() -> bool:
    return st.session_state.get("auth_user") is not None

def current_user_email() -> Optional[str]:
    user = st.session_state.get("auth_user")
    return (user.get("email") or "").lower() if user else None

def is_admin() -> bool:
    email = current_user_email()
    return email in ADMIN_EMAILS

def brand_header():
    col1, col2 = st.columns([1, 5])
    with col1:
        if BRAND_IMAGE.exists():
            st.image(str(BRAND_IMAGE), use_container_width=True)
    with col2:
        st.title(APP_TITLE)
        st.caption(COPYRIGHT)

def footer():
    st.write("---")
    st.markdown(
        f"<div style='text-align:center; opacity:0.85'>{COPYRIGHT}<br/>{DEV_FOOTER}</div>",
        unsafe_allow_html=True,
    )

def init_session():
    st.session_state.setdefault("auth_user", None)
    st.session_state.setdefault("quiz_index", 0)
    st.session_state.setdefault("quiz_score", 0)
    st.session_state.setdefault("responses", {})  # case_id -> chosen

def sign_out():
    try:
        supabase_user.auth.sign_out()
    except Exception:
        pass
    st.session_state["auth_user"] = None
    st.session_state["quiz_index"] = 0
    st.session_state["quiz_score"] = 0
    st.session_state["responses"] = {}

def sign_in(email: str, password: str) -> Optional[Dict[str, Any]]:
    try:
        res = supabase_user.auth.sign_in_with_password({"email": email, "password": password})
        # res.user, res.session
        return {"email": res.user.email, "id": res.user.id}
    except Exception as e:
        st.error(f"Sign-in failed: {e}")
        return None

def sign_up(email: str, password: str) -> bool:
    try:
        supabase_user.auth.sign_up({"email": email, "password": password})
        return True
    except Exception as e:
        st.error(f"Sign-up failed: {e}")
        return False

def admin_list_users() -> List[Dict[str, Any]]:
    if not supabase_admin:
        st.error("Admin functions require SUPABASE_SERVICE_ROLE_KEY in secrets.")
        return []
    try:
        page = supabase_admin.auth.admin.list_users()
        # page is a dict with 'users'
        return page.get("users", []) if isinstance(page, dict) else getattr(page, "users", [])
    except Exception as e:
        st.error(f"List users failed: {e}")
        return []

def admin_invite_user(email: str, temp_password: str) -> Optional[str]:
    """
    Creates a user with a temporary password and marks email as confirmed.
    The user should change password on first login (you can implement this via your own flow).
    """
    if not supabase_admin:
        st.error("Admin functions require SUPABASE_SERVICE_ROLE_KEY in secrets.")
        return None
    try:
        payload = {
            "email": email,
            "password": temp_password,
            "email_confirm": True,
            "user_metadata": {"role": "trainee"},
        }
        created = supabase_admin.auth.admin.create_user(payload)
        # return id
        if isinstance(created, dict):
            user_id = created.get("user", {}).get("id")
        else:
            # SDK sometimes returns object with .user
            user_id = getattr(getattr(created, "user", None), "id", None)
        return user_id
    except Exception as e:
        st.error(f"Invite user failed: {e}")
        return None

def admin_delete_user(user_id: str) -> bool:
    if not supabase_admin:
        st.error("Admin functions require SUPABASE_SERVICE_ROLE_KEY in secrets.")
        return False
    try:
        supabase_admin.auth.admin.delete_user(user_id)
        return True
    except Exception as e:
        st.error(f"Delete user failed: {e}")
        return False

# --------- UI Blocks ----------
def auth_block():
    st.subheader("Sign In")
    with st.form("signin"):
        email = st.text_input("Email", key="signin_email")
        pw = st.text_input("Password", type="password", key="signin_pw")
        do = st.form_submit_button("Sign in")
        if do:
            user = sign_in(email, pw)
            if user:
                st.session_state["auth_user"] = user
                st.success("Signed in.")
                st.rerun()

    st.divider()
    st.subheader("Create a new account")
    with st.form("signup"):
        email2 = st.text_input("Email (new account)", key="signup_email")
        pw2 = st.text_input("Password", type="password", key="signup_pw")
        do2 = st.form_submit_button("Create account")
        if do2:
            if sign_up(email2, pw2):
                st.success("Account created. Please sign in above.")

def admin_panel():
    st.header("🔐 Admin Panel")
    st.info("Admin features require `SUPABASE_SERVICE_ROLE_KEY` in secrets and your email in `ADMIN_EMAILS`.")
    # Invite
    with st.expander("Invite / Create User"):
        inv_email = st.text_input("User email", key="admin_inv_email")
        inv_temp = st.text_input("Temporary password", type="password", key="admin_inv_pw")
        if st.button("Create user"):
            if not inv_email or not inv_temp:
                st.warning("Provide email and temporary password.")
            else:
                user_id = admin_invite_user(inv_email, inv_temp)
                if user_id:
                    st.success(f"User created with id: {user_id}")

    # List & delete
    with st.expander("List / Delete Users"):
        users = admin_list_users()
        if users:
            st.write(f"Total: {len(users)}")
            for u in users:
                uid = u.get("id")
                uemail = (u.get("email") or "").lower()
                st.write(f"- **{uemail}** — id: `{uid}`")
                if st.button(f"Delete {uemail}", key=f"del_{uid}"):
                    if admin_delete_user(uid):
                        st.success(f"Deleted {uemail}")
                        st.rerun()
        else:
            st.write("No users or failed to load.")

def mcq_player(df: pd.DataFrame):
    st.header("📚 AKT MCQ Practice")
    if df.empty:
        st.warning("No items found. Add lines to `data/items.jsonl`.")
        return
    # Filters
    with st.expander("Filters"):
        domains = ["All"] + sorted([d for d in df["domain"].dropna().unique()])
        sub_specs = ["All"] + sorted([d for d in df["sub_specialty"].dropna().unique()])
        dom_choice = st.selectbox("Domain", domains, index=0)
        sub_choice = st.selectbox("Sub-specialty", sub_specs, index=0)

    filtered = df.copy()
    if dom_choice != "All":
        filtered = filtered[filtered["domain"] == dom_choice]
    if sub_choice != "All":
        filtered = filtered[filtered["sub_specialty"] == sub_choice]

    # Quiz navigation
    idx = st.session_state["quiz_index"]
    if idx >= len(filtered):
        idx = 0
        st.session_state["quiz_index"] = 0

    st.write(f"Items available: **{len(filtered)}**")
    if len(filtered) == 0:
        return

    row = filtered.iloc[idx]
    case_id = row.get("case_id")
    st.subheader(f"Question {idx+1} / {len(filtered)}  —  `{case_id}`")
    st.write(f"**Topic:** {row.get('topic', '')}")
    st.write(row.get("question", ""))

    options = row.get("options", {})
    # Keep stable order A-E
    keys = ["A", "B", "C", "D", "E"]
    labels = [f"{k}. {options[k]}" for k in keys if k in options]
    key_to_label = {k: options[k] for k in keys if k in options}

    prev_choice = st.session_state["responses"].get(case_id)
    choice = st.radio("Select one:", options=list(key_to_label.keys()), format_func=lambda k: f"{k}. {key_to_label[k]}", index=(list(key_to_label.keys()).index(prev_choice) if prev_choice in key_to_label else 0), key=f"choice_{case_id}")

    cols = st.columns(3)
    with cols[0]:
        if st.button("Submit"):
            st.session_state["responses"][case_id] = choice
            if choice == row.get("correct_answer"):
                st.session_state["quiz_score"] += 1
            st.success("Answer submitted. See explanation below.")
    with cols[1]:
        if st.button("Previous"):
            st.session_state["quiz_index"] = max(0, idx - 1)
            st.rerun()
    with cols[2]:
        if st.button("Next"):
            st.session_state["quiz_index"] = min(len(filtered) - 1, idx + 1)
            st.rerun()

    # Feedback
    if st.session_state["responses"].get(case_id):
        chosen = st.session_state["responses"][case_id]
        correct = row.get("correct_answer")
        if chosen == correct:
            st.success(f"✅ Correct: {correct}")
        else:
            st.error(f"❌ Incorrect. Your answer: {chosen}. Correct: {correct}")

        expl = row.get("explanation", {})
        if isinstance(expl, dict):
            st.markdown("**Rationale**")
            st.write(expl.get("rationale", ""))
            wrongs = expl.get("why_others_incorrect", [])
            if wrongs:
                st.markdown("**Why others are incorrect**")
                for w in wrongs:
                    st.write(f"- {w}")

        refs = row.get("guideline_reference", [])
        if refs:
            st.markdown("**Guideline references:**")
            for r in refs:
                st.write(f"- {r}")

    # Score
    st.info(f"Score: {st.session_state['quiz_score']} / {len(st.session_state['responses'])}")

def profile_box():
    email = current_user_email()
    st.caption(f"Signed in as **{email}**")
    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("Sign out"):
            sign_out()
            st.rerun()

# --------- Main ----------
def main():
    st.set_page_config(page_title="Dr. Yousra AKT/CSA", layout="wide")
    init_session()
    brand_header()

    tabs = ["Practice", "My Account"]
    if is_logged_in() and is_admin():
        tabs.append("Admin")
    active = st.tabs(tabs)

    # Unauthed view forces auth in Practice tab
    with active[0]:
        if not is_logged_in():
            st.warning("Please sign in to start practicing.")
            auth_block()
        else:
            df = load_items(ITEMS_PATH)
            profile_box()
            mcq_player(df)

    with active[1]:
        if not is_logged_in():
            st.info("Create an account or sign in below.")
            auth_block()
        else:
            st.subheader("My Account")
            profile_box()
            st.write("Welcome! Your progress is stored in this session. (Persisting analytics requires a DB table — add later if needed.)")

    if is_logged_in() and is_admin() and len(tabs) == 3:
        with active[2]:
            admin_panel()

    footer()

if __name__ == "__main__":
    main()
