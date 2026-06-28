import streamlit as st

from modules.admin_dashboard import show_admin_dashboard
from modules.user_dashboard import show_user_dashboard
from modules.db import (
    get_user_by_username,
    verify_password,
    update_user_password,
    log_activity,
)


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

def show_change_password_section():
    """
    Allow the logged-in user to change their own password.

    This is useful after an admin gives the user a temporary password.
    """
    with st.expander("Change password"):
        with st.form("change_own_password_form"):
            current_password = st.text_input(
                "Current password",
                type="password",
            )

            new_password = st.text_input(
                "New password",
                type="password",
            )

            confirm_new_password = st.text_input(
                "Confirm new password",
                type="password",
            )

            submitted = st.form_submit_button("Update password")

            if submitted:
                if not current_password or not new_password or not confirm_new_password:
                    st.error("Please fill in all password fields.")

                elif new_password != confirm_new_password:
                    st.error("The new password fields do not match.")

                elif len(new_password) < 6:
                    st.error("New password should be at least 6 characters.")

                elif current_password == new_password:
                    st.error("New password must be different from the current password.")

                else:
                    user = get_user_by_username(st.session_state.username)

                    if user is None:
                        st.error("User account could not be found.")

                    elif not verify_password(current_password, user["password_hash"]):
                        st.error("Current password is incorrect.")

                    else:
                        updated = update_user_password(
                            user_id=st.session_state.user_id,
                            new_password=new_password,
                        )

                        if updated:
                            log_activity(
                                category="admin_user_management",
                                action="own_password_changed",
                                actor_user_id=st.session_state.user_id,
                                actor_username=st.session_state.username,
                                target_type="user",
                                target_id=st.session_state.user_id,
                                target_name=st.session_state.username,
                                details=(
                                    f"User '{st.session_state.username}' changed their own password. "
                                    "The password value was not stored in the audit log."
                                ),
                            )

                            st.success("Password updated successfully.")

                        else:
                            st.error("Password update failed.")

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

        show_change_password_section()


def show_dashboard():
    """
    Decide which dashboard should be shown based on the user's role.
    """
    show_dashboard_header()

    if st.session_state.role == "admin":
        show_admin_dashboard()
    else:
        show_user_dashboard()

