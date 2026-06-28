import streamlit as st

from modules.db import get_user_by_username, verify_password


def authenticate_user(username, password):
    """
    Authenticate a user using the SQLite database.
    """
    user = get_user_by_username(username)

    if user is None:
        return None

    if "is_active" in user.keys() and user["is_active"] != 1:
        return None

    if verify_password(password, user["password_hash"]):
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "name": user["full_name"],
            "role": user["role"],
        }

    return None


def show_forgot_password_message():
    """
    Show a demo-friendly forgot-password message.
    """
    with st.expander("Forgot password?"):
        st.info(
            "Please contact an administrator to reset your password. "
            "For this demo version, password reset is handled by the admin."
        )