import re
import sqlite3

import pandas as pd
import streamlit as st

from modules.db import log_activity


DB_PATH = "database/chambercal.db"


BLOCKED_SQL_KEYWORDS = [
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "replace",
    "vacuum",
    "attach",
    "detach",
    "reindex",
    "truncate",
]


def get_read_only_connection():
    """
    Open the SQLite database in read-only mode.

    This prevents accidental database modification from the SQL viewer.
    """
    connection_string = f"file:{DB_PATH}?mode=ro"

    conn = sqlite3.connect(
        connection_string,
        uri=True,
    )

    conn.row_factory = sqlite3.Row

    return conn


def get_database_tables():
    """
    Return all user-created database tables.

    SQLite internal tables are hidden.
    """
    conn = get_read_only_connection()

    query = """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """

    tables_df = pd.read_sql_query(query, conn)

    conn.close()

    return tables_df["name"].tolist()


def get_table_columns(table_name):
    """
    Return column information for one table.
    """
    conn = get_read_only_connection()

    query = f"PRAGMA table_info({table_name})"

    columns_df = pd.read_sql_query(query, conn)

    conn.close()

    return columns_df


def clean_sql_query(sql_query):
    """
    Clean and normalize the SQL query before validation.
    """
    if not sql_query:
        return ""

    cleaned_query = sql_query.strip()

    # Remove one trailing semicolon, but do not allow multiple statements.
    if cleaned_query.endswith(";"):
        cleaned_query = cleaned_query[:-1].strip()

    return cleaned_query


def validate_read_only_query(sql_query):
    """
    Validate that the SQL query is read-only.

    Allowed:
        SELECT ...
        WITH ...

    Blocked:
        INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, etc.
    """
    cleaned_query = clean_sql_query(sql_query)

    if not cleaned_query:
        return False, "Please enter a SQL query."

    # Block multiple statements.
    if ";" in cleaned_query:
        return False, "Only one SQL statement is allowed."

    lowered_query = cleaned_query.lower()

    if not (
        lowered_query.startswith("select ")
        or lowered_query.startswith("with ")
    ):
        return False, "Only SELECT or WITH queries are allowed."

    for keyword in BLOCKED_SQL_KEYWORDS:
        pattern = rf"\b{keyword}\b"

        if re.search(pattern, lowered_query):
            return False, f"The keyword '{keyword.upper()}' is not allowed."

    return True, cleaned_query


def add_limit_if_missing(sql_query, row_limit):
    """
    Add a LIMIT clause if the query does not already have one.

    This prevents accidentally loading too many rows.
    """
    lowered_query = sql_query.lower()

    if re.search(r"\blimit\b", lowered_query):
        return sql_query

    return f"{sql_query}\nLIMIT {row_limit}"


def run_read_only_query(sql_query, row_limit):
    """
    Run a validated read-only SQL query and return the result as a DataFrame.
    """
    is_valid, result = validate_read_only_query(sql_query)

    if not is_valid:
        raise ValueError(result)

    safe_query = add_limit_if_missing(
        sql_query=result,
        row_limit=row_limit,
    )

    conn = get_read_only_connection()

    result_df = pd.read_sql_query(
        safe_query,
        conn,
    )

    conn.close()

    return result_df, safe_query


def log_sql_viewer_query(sql_query, row_count):
    """
    Log SQL viewer usage in the audit logs.
    """
    log_activity(
        category="database_viewer",
        action="read_only_sql_query_executed",
        actor_user_id=st.session_state.user_id,
        actor_username=st.session_state.username,
        target_type="database",
        target_id=None,
        target_name="chambercal.db",
        details=(
            f"Executed read-only SQL query. "
            f"Rows returned: {row_count}. "
            f"Query: {sql_query[:500]}"
        ),
    )


def show_table_browser():
    """
    Display a simple table browser for admins.

    This is safer than asking admins to write SQL for every basic lookup.
    """
    st.markdown("#### Table Browser")

    tables = get_database_tables()

    if not tables:
        st.info("No database tables found.")
        return

    browser_col1, browser_col2 = st.columns([1, 2])

    with browser_col1:
        selected_table = st.selectbox(
            "Select table",
            options=tables,
            key="sql_viewer_selected_table",
        )

        preview_limit = st.number_input(
            "Preview rows",
            min_value=10,
            max_value=1000,
            value=100,
            step=10,
            key="sql_viewer_preview_limit",
        )

    with browser_col2:
        st.markdown("##### Table Columns")

        columns_df = get_table_columns(selected_table)

        st.dataframe(
            columns_df[["name", "type", "notnull", "pk"]],
            use_container_width=True,
            hide_index=True,
        )

    if st.button("Preview Selected Table", key="sql_viewer_preview_table"):
        query = f"SELECT * FROM {selected_table} LIMIT {preview_limit}"

        try:
            result_df, executed_query = run_read_only_query(
                sql_query=query,
                row_limit=preview_limit,
            )

            log_sql_viewer_query(
                sql_query=executed_query,
                row_count=len(result_df),
            )

            st.markdown("##### Preview Result")

            st.code(executed_query, language="sql")

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True,
            )

        except Exception as error:
            st.error(f"Could not preview table: {error}")


def show_custom_sql_runner():
    """
    Display a read-only custom SQL query runner.
    """
    st.markdown("#### Read-Only SQL Query")

    st.warning(
        "Only SELECT and WITH queries are allowed. "
        "Write operations such as INSERT, UPDATE, DELETE, DROP, and ALTER are blocked."
    )

    default_query = "SELECT * FROM users LIMIT 20"

    sql_query = st.text_area(
        "SQL query",
        value=default_query,
        height=160,
        key="sql_viewer_custom_query",
    )

    row_limit = st.number_input(
        "Maximum rows if query has no LIMIT",
        min_value=10,
        max_value=5000,
        value=500,
        step=50,
        key="sql_viewer_row_limit",
    )

    run_query_clicked = st.button(
        "Run Read-Only Query",
        type="primary",
        key="sql_viewer_run_query",
    )

    if run_query_clicked:
        try:
            result_df, executed_query = run_read_only_query(
                sql_query=sql_query,
                row_limit=row_limit,
            )

            log_sql_viewer_query(
                sql_query=executed_query,
                row_count=len(result_df),
            )

            st.success(f"Query executed successfully. Rows returned: {len(result_df)}")

            st.markdown("##### Executed Query")
            st.code(executed_query, language="sql")

            st.markdown("##### Query Result")

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True,
            )

            csv_data = result_df.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="Download Result as CSV",
                data=csv_data,
                file_name="sql_viewer_result.csv",
                mime="text/csv",
                key="sql_viewer_download_result_csv",
            )

        except Exception as error:
            st.error(f"Query failed: {error}")


def show_sql_viewer_tab():
    """
    Display the admin-only SQL viewer.

    This tool is intended for debugging, inspection, and admin transparency.
    It should remain read-only.
    """
    st.subheader("SQL Viewer")

    st.write(
        "Inspect the ChamberCal SQLite database using a read-only table browser "
        "or safe SELECT queries."
    )

    st.info(
        "This viewer opens the database in read-only mode and blocks write queries."
    )

    table_browser_tab, custom_query_tab = st.tabs(
        [
            "Table Browser",
            "Custom SQL Query",
        ]
    )

    with table_browser_tab:
        show_table_browser()

    with custom_query_tab:
        show_custom_sql_runner()