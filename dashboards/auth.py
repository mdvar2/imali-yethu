"""Simple role-based sign-in for the dashboard.

Roles and passwords come from the environment (never from the code):
    DASHBOARD_FINANCE_PASSWORD   Finance office: oversight pages, submit invoices
    DASHBOARD_CFO_PASSWORD       CFO: everything, including controls and limits
If a password is not set, that role cannot sign in (fails closed).
"""
from __future__ import annotations

import hmac
import os

import streamlit as st

ROLES = {
    "cfo": ("CFO", "DASHBOARD_CFO_PASSWORD"),
    "finance": ("Finance office", "DASHBOARD_FINANCE_PASSWORD"),
}
MAX_ATTEMPTS = 5


def role() -> str | None:
    return st.session_state.get("iy_role")


def role_label() -> str:
    current = role()
    return ROLES[current][0] if current in ROLES else "Public view"


def check_password(role_key: str, password: str) -> bool:
    expected = os.getenv(ROLES[role_key][1], "")
    if not expected or not password:
        return False
    return hmac.compare_digest(password.encode(), expected.encode())


def sign_out() -> None:
    st.session_state.pop("iy_role", None)
