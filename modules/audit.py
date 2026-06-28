from datetime import date, timedelta, datetime
from io import BytesIO, StringIO
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import streamlit as st

from modules.db import get_activity_logs_by_category, log_activity


AUDIT_CATEGORIES = {
    "Admin / User Management": "admin_user_management",
    "Analysis Settings": "analysis_settings",
    "Analysis Tracking": "analysis_tracking",
    "File Uploads": "file_uploads",
    "Exports / Backups": "exports_backups",
    "Database Viewer": "database_viewer",
}


def logs_to_dataframe(logs):
    """
    Convert audit log rows from SQLite into a pandas DataFrame.
    """
    if not logs:
        return pd.DataFrame()

    logs_df = pd.DataFrame([dict(log) for log in logs])

    if "created_at" in logs_df.columns:
        logs_df["created_at"] = pd.to_datetime(
            logs_df["created_at"],
            errors="coerce",
        )

    return logs_df


def get_all_audit_logs_dataframe():
    """
    Load all audit categories into one DataFrame.

    This is mainly used to build global filter options,
    for example the username list.
    """
    all_logs = []

    for category_label, category_key in AUDIT_CATEGORIES.items():
        logs = get_activity_logs_by_category(category_key)

        for log in logs:
            log_dict = dict(log)
            log_dict["category_label"] = category_label
            all_logs.append(log_dict)

    return logs_to_dataframe(all_logs)


def show_global_audit_filters(all_logs_df):
    """
    Show global audit filters that apply to all audit tabs.
    """
    with st.container(border=True):
        st.markdown("#### Global Filters")

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

        today = date.today()
        default_from_date = today - timedelta(days=30)

        username_options = []

        if not all_logs_df.empty and "actor_username" in all_logs_df.columns:
            username_options = sorted(
                all_logs_df["actor_username"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        with filter_col1:
            selected_usernames = st.multiselect(
                "Username",
                options=username_options,
                default=[],
                help="Leave empty to include all users.",
                key="audit_global_usernames",
            )

        with filter_col2:
            from_date = st.date_input(
                "From date",
                value=default_from_date,
                key="audit_global_from_date",
            )

        with filter_col3:
            to_date = st.date_input(
                "To date",
                value=today,
                key="audit_global_to_date",
            )

        with filter_col4:
            global_search_text = st.text_input(
                "Global search",
                placeholder="Search user, action, target, details...",
                key="audit_global_search_text",
            )

    return {
        "selected_usernames": selected_usernames,
        "from_date": from_date,
        "to_date": to_date,
        "global_search_text": global_search_text,
    }


def apply_global_audit_filters(logs_df, global_filters):
    """
    Apply global username, date, and text filters.
    """
    if logs_df.empty:
        return logs_df

    filtered_df = logs_df.copy()

    selected_usernames = global_filters["selected_usernames"]
    from_date = global_filters["from_date"]
    to_date = global_filters["to_date"]
    global_search_text = global_filters["global_search_text"]

    if selected_usernames and "actor_username" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["actor_username"].isin(selected_usernames)
        ]

    if "created_at" in filtered_df.columns:
        filtered_df["created_at"] = pd.to_datetime(
            filtered_df["created_at"],
            errors="coerce",
        )

        filtered_df = filtered_df[
            filtered_df["created_at"].dt.date >= from_date
        ]

        filtered_df = filtered_df[
            filtered_df["created_at"].dt.date <= to_date
        ]

    if global_search_text:
        search_text_lower = global_search_text.lower()

        searchable_columns = [
            "created_at",
            "actor_username",
            "action",
            "target_type",
            "target_name",
            "details",
            "category_label",
        ]

        existing_columns = [
            column
            for column in searchable_columns
            if column in filtered_df.columns
        ]

        if existing_columns:
            search_mask = filtered_df[existing_columns].astype(str).apply(
                lambda row: search_text_lower in " ".join(row).lower(),
                axis=1,
            )

            filtered_df = filtered_df[search_mask]

    return filtered_df


def prepare_audit_display_dataframe(logs_df):
    """
    Prepare audit logs for display and export.

    This function standardizes column names so the table looks the same
    in Streamlit, XLSX export, and CSV export.
    """
    if logs_df.empty:
        return pd.DataFrame(
            [
                {
                    "Date / Time": "No logs available",
                    "Actor": "",
                    "Action": "",
                    "Target Type": "",
                    "Target Name": "",
                    "Details": "",
                }
            ]
        )

    display_columns = [
        "created_at",
        "actor_username",
        "action",
        "target_type",
        "target_name",
        "details",
    ]

    existing_columns = [
        column
        for column in display_columns
        if column in logs_df.columns
    ]

    display_df = logs_df[existing_columns].copy()

    if "created_at" in display_df.columns:
        display_df["created_at"] = pd.to_datetime(
            display_df["created_at"],
            errors="coerce",
        )

        display_df = display_df.sort_values(
            "created_at",
            ascending=False,
        )

        display_df["created_at"] = display_df["created_at"].dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    display_df = display_df.rename(
        columns={
            "created_at": "Date / Time",
            "actor_username": "Actor",
            "action": "Action",
            "target_type": "Target Type",
            "target_name": "Target Name",
            "details": "Details",
        }
    )

    return display_df


def get_filtered_audit_export_tables(global_filters):
    """
    Build one filtered audit table per audit category.

    The export uses global filters only.

    Tab-specific filters are used only for the currently visible tab table.
    """
    export_tables = {}

    for category_label, category_key in AUDIT_CATEGORIES.items():
        logs = get_activity_logs_by_category(category_key)
        logs_df = logs_to_dataframe(logs)

        filtered_df = apply_global_audit_filters(
            logs_df,
            global_filters,
        )

        export_tables[category_label] = prepare_audit_display_dataframe(
            filtered_df
        )

    return export_tables


def create_audit_export_metadata(global_filters):
    """
    Create an export metadata table.
    """
    selected_usernames = global_filters["selected_usernames"]

    if selected_usernames:
        username_text = ", ".join(selected_usernames)
    else:
        username_text = "All users"

    return pd.DataFrame(
        [
            {
                "Field": "Report generated on",
                "Value": datetime.now().astimezone().strftime(
                    "%Y-%m-%d %H:%M:%S %Z"
                ),
            },
            {
                "Field": "Generated by",
                "Value": st.session_state.get("name", ""),
            },
            {
                "Field": "Username",
                "Value": st.session_state.get("username", ""),
            },
            {
                "Field": "Username filter",
                "Value": username_text,
            },
            {
                "Field": "From date",
                "Value": str(global_filters["from_date"]),
            },
            {
                "Field": "To date",
                "Value": str(global_filters["to_date"]),
            },
            {
                "Field": "Global search",
                "Value": global_filters["global_search_text"] or "None",
            },
        ]
    )


def safe_excel_sheet_name(sheet_name):
    """
    Return a safe Excel sheet name.

    Excel sheet names:
        - cannot contain some special characters
        - must be 31 characters or fewer
    """
    cleaned_name = (
        sheet_name
        .replace("/", "-")
        .replace("\\", "-")
        .replace("*", "")
        .replace("?", "")
        .replace(":", "-")
        .replace("[", "")
        .replace("]", "")
    )

    return cleaned_name[:31]


def create_audit_xlsx_export(global_filters):
    """
    Create an XLSX audit report.

    Each audit category becomes a separate Excel sheet.
    """
    output = BytesIO()

    metadata_df = create_audit_export_metadata(global_filters)
    export_tables = get_filtered_audit_export_tables(global_filters)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        metadata_df.to_excel(
            writer,
            sheet_name="Export Metadata",
            index=False,
        )

        for category_label, export_df in export_tables.items():
            sheet_name = safe_excel_sheet_name(category_label)

            export_df.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )

            worksheet = writer.sheets[sheet_name]

            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter

                for cell in column_cells:
                    cell_value = str(cell.value) if cell.value is not None else ""
                    max_length = max(max_length, len(cell_value))

                worksheet.column_dimensions[column_letter].width = min(
                    max_length + 2,
                    60,
                )

        metadata_worksheet = writer.sheets["Export Metadata"]

        for column_cells in metadata_worksheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:
                cell_value = str(cell.value) if cell.value is not None else ""
                max_length = max(max_length, len(cell_value))

            metadata_worksheet.column_dimensions[column_letter].width = min(
                max_length + 2,
                60,
            )

    output.seek(0)

    return output.getvalue()


def safe_csv_file_name(name):
    """
    Create a safe filename for CSV files inside the ZIP export.
    """
    return (
        name.lower()
        .replace(" / ", "_")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


def create_audit_csv_zip_export(global_filters):
    """
    Create a ZIP file containing one CSV per audit category.
    """
    output = BytesIO()

    metadata_df = create_audit_export_metadata(global_filters)
    export_tables = get_filtered_audit_export_tables(global_filters)

    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as zip_file:
        metadata_csv = StringIO()
        metadata_df.to_csv(metadata_csv, index=False)

        zip_file.writestr(
            "export_metadata.csv",
            metadata_csv.getvalue(),
        )

        for category_label, export_df in export_tables.items():
            csv_buffer = StringIO()
            export_df.to_csv(csv_buffer, index=False)

            file_name = f"{safe_csv_file_name(category_label)}.csv"

            zip_file.writestr(
                file_name,
                csv_buffer.getvalue(),
            )

    output.seek(0)

    return output.getvalue()


def log_audit_export(export_format, file_name):
    """
    Log audit export activity.

    Note:
        The export file will include logs that existed before the click.
        The audit-export activity itself appears after the export button is clicked,
        so it will appear in later exports.
    """
    log_activity(
        category="exports_backups",
        action=f"audit_logs_exported_{export_format.lower()}",
        actor_user_id=st.session_state.user_id,
        actor_username=st.session_state.username,
        target_type="audit_export",
        target_id=None,
        target_name=file_name,
        details=f"Exported audit logs as {export_format.upper()}: {file_name}",
    )


def show_audit_export_buttons(global_filters):
    """
    Show XLSX and ZIP-CSV audit export buttons.
    """
    today_string = datetime.now().strftime("%Y%m%d")

    xlsx_file_name = f"{today_string}_chambercal_audit_logs.xlsx"
    zip_file_name = f"{today_string}_chambercal_audit_logs_csv.zip"

    xlsx_bytes = create_audit_xlsx_export(global_filters)
    zip_bytes = create_audit_csv_zip_export(global_filters)

    st.download_button(
        label="Export XLSX",
        data=xlsx_bytes,
        file_name=xlsx_file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_audit_logs_xlsx",
        on_click=log_audit_export,
        args=("xlsx", xlsx_file_name),
        use_container_width=True,
    )

    st.download_button(
        label="Export CSV ZIP",
        data=zip_bytes,
        file_name=zip_file_name,
        mime="application/zip",
        key="download_audit_logs_csv_zip",
        on_click=log_audit_export,
        args=("csv_zip", zip_file_name),
        use_container_width=True,
    )


def show_tab_audit_filters(logs_df, key_prefix):
    """
    Show filters that apply only to the selected audit tab.
    """
    with st.container(border=True):
        st.markdown("#### Tab Filters")

        filter_col1, filter_col2, filter_col3 = st.columns(3)

        action_options = []
        target_type_options = []

        if not logs_df.empty and "action" in logs_df.columns:
            action_options = sorted(
                logs_df["action"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        if not logs_df.empty and "target_type" in logs_df.columns:
            target_type_options = sorted(
                logs_df["target_type"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        with filter_col1:
            selected_actions = st.multiselect(
                "Action",
                options=action_options,
                default=[],
                help="Leave empty to include all actions.",
                key=f"{key_prefix}_actions",
            )

        with filter_col2:
            selected_target_types = st.multiselect(
                "Target type",
                options=target_type_options,
                default=[],
                help="Leave empty to include all target types.",
                key=f"{key_prefix}_target_types",
            )

        with filter_col3:
            tab_search_text = st.text_input(
                "Tab search",
                placeholder="Search target/details...",
                key=f"{key_prefix}_search",
            )

    return {
        "selected_actions": selected_actions,
        "selected_target_types": selected_target_types,
        "tab_search_text": tab_search_text,
    }


def apply_tab_audit_filters(logs_df, tab_filters):
    """
    Apply action, target type, and tab-specific text filters.
    """
    if logs_df.empty:
        return logs_df

    filtered_df = logs_df.copy()

    selected_actions = tab_filters["selected_actions"]
    selected_target_types = tab_filters["selected_target_types"]
    tab_search_text = tab_filters["tab_search_text"]

    if selected_actions and "action" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["action"].isin(selected_actions)
        ]

    if selected_target_types and "target_type" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["target_type"].isin(selected_target_types)
        ]

    if tab_search_text:
        search_text_lower = tab_search_text.lower()

        searchable_columns = [
            "action",
            "target_type",
            "target_name",
            "details",
        ]

        existing_columns = [
            column
            for column in searchable_columns
            if column in filtered_df.columns
        ]

        if existing_columns:
            search_mask = filtered_df[existing_columns].astype(str).apply(
                lambda row: search_text_lower in " ".join(row).lower(),
                axis=1,
            )

            filtered_df = filtered_df[search_mask]

    return filtered_df


def display_audit_logs_table(logs_df):
    """
    Display filtered audit logs in a readable table.
    """
    if logs_df.empty:
        st.info("No logs match the selected filters.")
        return

    display_df = prepare_audit_display_dataframe(logs_df)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


def show_single_audit_tab(category_label, category_key, global_filters):
    """
    Display one audit category tab.

    Global filters are applied first.
    Tab filters are applied second.
    """
    st.markdown(f"#### {category_label} Logs")

    logs = get_activity_logs_by_category(category_key)
    logs_df = logs_to_dataframe(logs)

    if logs_df.empty:
        st.info("No logs available for this category yet.")
        return

    globally_filtered_df = apply_global_audit_filters(
        logs_df,
        global_filters,
    )

    tab_filters = show_tab_audit_filters(
        logs_df=globally_filtered_df,
        key_prefix=f"audit_{category_key}",
    )

    final_filtered_df = apply_tab_audit_filters(
        logs_df=globally_filtered_df,
        tab_filters=tab_filters,
    )

    st.caption(
        f"Showing {len(final_filtered_df)} of {len(logs_df)} logs."
    )

    display_audit_logs_table(final_filtered_df)


def show_audit_tab():
    """
    Display audit logs for admin users.

    Includes:
        - Global filters across all tabs
        - Export buttons for full filtered audit report
        - Separate audit categories
        - Tab-specific filters inside each category
    """
    all_logs_df = get_all_audit_logs_dataframe()

    title_col, export_col = st.columns([3, 1])

    with title_col:
        st.subheader("Audit Logs")
        st.write("Review system activities grouped by category.")

    global_filters = show_global_audit_filters(all_logs_df)

    with export_col:
        st.markdown("##### Export")
        show_audit_export_buttons(global_filters)

    audit_tabs = st.tabs(list(AUDIT_CATEGORIES.keys()))

    for tab, (category_label, category_key) in zip(
        audit_tabs,
        AUDIT_CATEGORIES.items(),
    ):
        with tab:
            show_single_audit_tab(
                category_label=category_label,
                category_key=category_key,
                global_filters=global_filters,
            )