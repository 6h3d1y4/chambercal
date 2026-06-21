import streamlit as st
import pandas as pd

from modules.db import get_activity_logs_by_category


def show_log_table(category):
    """
    Display activity logs for a selected category.

    Parameters
    ----------
    category : str
        The log category to display.
    """
    logs = get_activity_logs_by_category(category)

    if logs:
        log_table = []

        for log in logs:
            log_table.append(
                {
                    "Date / Time": log["created_at"],
                    "Actor": log["actor_username"],
                    "Action": log["action"],
                    "Target Type": log["target_type"],
                    "Target Name": log["target_name"],
                    "Details": log["details"],
                }
            )

        log_df = pd.DataFrame(log_table)

        st.dataframe(
            log_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No logs available for this category yet.")


def show_audit_tab():
    """
    Display audit logs for admin users.
    """
    st.subheader("Audit Logs")
    st.write("Review system activities grouped by category.")

    user_mgmt_tab, analysis_tab, uploads_tab, exports_tab = st.tabs(
        [
            "Admin / User Management",
            "Analysis Tracking",
            "File Uploads",
            "Exports / Backups",
        ]
    )

    with user_mgmt_tab:
        st.markdown("#### Admin / User Management Logs")
        show_log_table("admin_user_management")

    with analysis_tab:
        st.markdown("#### Analysis Tracking Logs")
        show_log_table("analysis_tracking")

    with uploads_tab:
        st.markdown("#### File Upload Logs")
        show_log_table("file_uploads")

    with exports_tab:
        st.markdown("#### Export / Backup Logs")
        show_log_table("exports_backups")