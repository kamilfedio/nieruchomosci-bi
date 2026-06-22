"""Login form and credential checking for the Streamlit dashboard."""

from __future__ import annotations

import hashlib
import secrets

import streamlit as st
from src.api.config import Config


def _sha256(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_credentials(username: str, password: str, config: Config) -> str | None:
    """Return 'admin' | 'analyst' on success, None on failure."""
    digest = _sha256(password)
    if username == "admin" and secrets.compare_digest(digest, config.admin_password_hash):
        return "admin"
    if username == "analyst" and secrets.compare_digest(
        digest, config.analyst_password_hash
    ):
        return "analyst"
    return None


def render_login_form(config: Config) -> None:
    """Render a centered login form and set st.session_state['role'] on success."""
    _, col_m, _ = st.columns([1, 1, 1])
    with col_m:
        st.markdown("## Logowanie")
        username = st.text_input("Użytkownik", key="_login_username")
        password = st.text_input("Hasło", type="password", key="_login_password")

        if st.button("Zaloguj", use_container_width=True):
            role = check_credentials(username, password, config)
            if role:
                st.session_state["role"] = role
                st.rerun()
            else:
                st.error("Nieprawidłowy użytkownik lub hasło.")
