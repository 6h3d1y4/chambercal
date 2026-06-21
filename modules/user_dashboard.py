import streamlit as st

def show_user_dashboard():
    """
    Display the user area with top-level tabs.
    """
    user_dashboard_tab, reports_tab = st.tabs(
        ["User Dashboard", "Reports"]
    )

    with user_dashboard_tab:
        st.subheader("User Dashboard")
        st.write("Here users will later upload propane test files and view their analyses.")

    with reports_tab:
        st.subheader("Reports")
        st.info("Past analysis reports will be shown here later.")