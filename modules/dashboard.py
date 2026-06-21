import streamlit as st

from modules.admin_dashboard import show_admin_dashboard
from modules.user_dashboard import show_user_dashboard


def logout_user():
    """
    Clear the current user session and return to the landing page.
    """
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.name = None
    st.session_state.role = None
    st.rerun()


def show_dashboard_header():
    """
    Display the common dashboard header with logout button on the top right.
    """
    left_col, right_col = st.columns([4, 1])

    with left_col:
        st.title(f"Welcome, {st.session_state.name}")
        st.write(f"You are logged in as: **{st.session_state.role}**")
        st.caption(f"User ID: {st.session_state.user_id}")

    with right_col:
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Logout", use_container_width=True):
            logout_user()


def show_dashboard():
    """
    Decide which dashboard should be shown based on the user's role.
    """
    show_dashboard_header()

    if st.session_state.role == "admin":
        show_admin_dashboard()
    else:
        show_user_dashboard()