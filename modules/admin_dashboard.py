import streamlit as st
import pandas as pd

from modules.audit import show_audit_tab
from modules.analysis_settings import show_analysis_settings_tab
from modules.sql_viewer import show_sql_viewer_tab

from modules.db import (
    count_active_users,
    count_analysis_reports,
    count_chambers,
    get_all_users,
    create_user,
    update_user_active_status,
    update_user_password,
    log_activity,
)

def show_create_user_form():
    """
    Display the form for creating a new user.
    """
    st.divider()

    st.subheader("Create New User")

    with st.form("create_user_form"):
        new_full_name = st.text_input("Full name")
        new_username = st.text_input("Username")
        new_password = st.text_input("Temporary password", type="password")
        new_role = st.selectbox("Role", ["user", "admin"])

        submitted = st.form_submit_button("Create user")

        if submitted:
            if not new_full_name or not new_username or not new_password:
                st.error("Please fill in all required fields.")
            else:
                user_created = create_user(
                    username=new_username,
                    password=new_password,
                    full_name=new_full_name,
                    role=new_role,
                )

                if user_created:
                    log_activity(
                        category="admin_user_management",
                        action="user_created",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="user",
                        target_name=new_username,
                        details=f"Created user '{new_username}' with role '{new_role}'."
                    )

                    st.success(f"User '{new_username}' was created successfully.")
                    st.rerun()
                else:
                    st.error("This username already exists.")

def show_admin_metrics():
    """
    Display admin overview metrics.
    """
    col1, col2, col3 = st.columns(3)

    col1.metric("Active users", count_active_users())
    col2.metric("Analysis reports", count_analysis_reports())
    col3.metric("Chambers", count_chambers())

def show_admin_home_tab():
    """
    Display the dashboard for admin users.
    """

    st.subheader("Admin Dashboard")
    st.write("Manage users, review system status, and access admin tools.")

    show_admin_metrics()
    show_registered_users_table()
    show_reset_password_form()
    show_create_user_form()

def show_registered_users_table():

    # ---------------------------------------------------------
    # Registered users table
    # ---------------------------------------------------------

    st.divider()

    title_col, button_col = st.columns([3, 1])

    with title_col:
        st.subheader("Registered Users")

    with button_col:
        save_changes = st.button("Save Changes", use_container_width=True)

    if "user_status_message" in st.session_state:
        st.success(st.session_state.user_status_message)
        del st.session_state.user_status_message

    users = get_all_users()

    if users:
        user_table = []

        for user in users:
            user_table.append(
                {
                    "User ID": user["user_id"],
                    "Username": user["username"],
                    "Full Name": user["full_name"],
                    "Role": user["role"],
                    "Status": "Active" if user["is_active"] == 1 else "Inactive",
                    "Active": bool(user["is_active"]),
                    "Created At": user["created_at"],
                }
            )

        user_df = pd.DataFrame(user_table)

        edited_user_df = st.data_editor(
            user_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "User ID",
                "Username",
                "Full Name",
                "Role",
                "Status",
                "Created At",
            ],
            column_config={
                "Active": st.column_config.CheckboxColumn(
                    "Active",
                    help="Tick to keep the user active. Untick to disable the user.",
                    default=True,
                )
            },
            key="user_status_editor",
        )

        if save_changes:
            changes_made = 0
            blocked_self_deactivation = False

            for _, row in edited_user_df.iterrows():
                user_id = int(row["User ID"])
                new_active_status = bool(row["Active"])

                original_row = user_df[user_df["User ID"] == user_id].iloc[0]
                old_active_status = bool(original_row["Active"])

                if new_active_status != old_active_status:
                    if user_id == st.session_state.user_id and new_active_status is False:
                        blocked_self_deactivation = True
                        continue

                    updated = update_user_active_status(
                        user_id=user_id,
                        is_active=new_active_status,
                    )

                    if updated:
                        changes_made += 1

                        action_name = "user_activated" if new_active_status else "user_deactivated"
                        status_text = "active" if new_active_status else "inactive"

                        log_activity(
                            category="admin_user_management",
                            action=action_name,
                            actor_user_id=st.session_state.user_id,
                            actor_username=st.session_state.username,
                            target_type="user",
                            target_id=user_id,
                            target_name=row["Username"],
                            details=f"Changed user '{row['Username']}' status to {status_text}."
                        )

            if blocked_self_deactivation:
                st.error("You cannot deactivate your own account.")

            if changes_made > 0:
                st.session_state.user_status_message = (
                    f"{changes_made} user status change(s) saved successfully."
                )
                st.rerun()
            elif not blocked_self_deactivation:
                st.info("No user status changes were made.")

    else:
        st.info("No users found.")

def show_reset_password_form():
    """
    Display an admin-only form for resetting a user's password.

    This is the demo-friendly replacement for a full email-based
    forgot-password workflow.
    """
    st.divider()

    st.subheader("Reset User Password")

    users = get_all_users()

    if not users:
        st.info("No users available.")
        return

    user_options = {}

    for user in users:
        label = (
            f"{user['username']} | {user['full_name']} | "
            f"{user['role']}"
        )

        user_options[label] = user["user_id"]

    with st.form("reset_user_password_form"):
        selected_user_label = st.selectbox(
            "Select user",
            options=list(user_options.keys()),
        )

        new_password = st.text_input(
            "New temporary password",
            type="password",
        )

        confirm_password = st.text_input(
            "Confirm temporary password",
            type="password",
        )

        submitted = st.form_submit_button("Reset Password")

        if submitted:
            if not new_password or not confirm_password:
                st.error("Please enter and confirm the new password.")

            elif new_password != confirm_password:
                st.error("The two password fields do not match.")

            elif len(new_password) < 6:
                st.error("Temporary password should be at least 6 characters.")

            else:
                selected_user_id = user_options[selected_user_label]

                updated = update_user_password(
                    user_id=selected_user_id,
                    new_password=new_password,
                )

                if updated:
                    selected_username = selected_user_label.split(" | ")[0]

                    log_activity(
                        category="admin_user_management",
                        action="user_password_reset",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="user",
                        target_id=selected_user_id,
                        target_name=selected_username,
                        details=(
                            f"Reset password for user '{selected_username}'. "
                            "The password value was not stored in the audit log."
                        ),
                    )

                    st.success(
                        f"Password for '{selected_username}' was reset successfully."
                    )

                else:
                    st.error("Password reset failed.")

def show_admin_dashboard():
    """
    Display the admin area with top-level tabs.

    The admin area currently contains:

    1. Admin Dashboard
       User management and overview metrics.

    2. Analysis Settings
       Chamber setup, calculation constants, trim settings,
       and quality thresholds.

    3. Audit
       Activity logs grouped by category.
    """
    admin_dashboard_tab, analysis_settings_tab, audit_tab, sql_viewer_tab = st.tabs(
        ["Admin Dashboard", "Analysis Settings", "Audit", "SQL Viewer"]
    )

    with admin_dashboard_tab:
        show_admin_home_tab()

    with analysis_settings_tab:
        show_analysis_settings_tab()

    with audit_tab:
        show_audit_tab()

    with sql_viewer_tab:
        show_sql_viewer_tab()



