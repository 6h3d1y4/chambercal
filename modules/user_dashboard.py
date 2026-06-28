import json
import re
from datetime import date, timedelta, datetime

import pandas as pd
import streamlit as st

from modules.db import (
    get_all_chambers,
    get_analysis_settings_by_group,
    get_analysis_reports_for_user,
    save_analysis_report,
    log_activity,
)

from modules.analyzer import run_propane_analysis

from modules.exporter import (
    create_csv_report,
    create_xlsx_report,
    create_pdf_report,
)

def show_user_dashboard_message():
    """
    Display a saved success/info/error message after the page reruns.
    """
    if "user_dashboard_message" not in st.session_state:
        return

    message_type, message_text = st.session_state.user_dashboard_message

    if message_type == "success":
        st.success(message_text)
    elif message_type == "info":
        st.info(message_text)
    elif message_type == "error":
        st.error(message_text)
    else:
        st.write(message_text)

    del st.session_state.user_dashboard_message

def get_current_analysis_settings_dict():
    """
    Load all admin-controlled analysis settings as a simple dictionary.

    Example output:
        {
            "trim_start_min": 10,
            "trim_end_min": 11,
            "expected_rq": 0.6
        }
    """
    settings_dict = {}

    setting_groups = [
        "calculation_constant",
        "trim_setting",
        "quality_threshold",
    ]

    for group_key in setting_groups:
        settings = get_analysis_settings_by_group(group_key)

        for setting in settings:
            settings_dict[setting["setting_key"]] = float(setting["setting_value"])

    return settings_dict

def style_historical_summary_row(row):
    """
    Colour the 'Most common quality' value in the historical summary table.
    """
    row_styles = pd.Series("", index=row.index)

    if row.get("Statistic") == "Most common quality":
        quality_value = row.get("Value")
        row_styles["Value"] = style_quality_cells(quality_value)

    return row_styles

def style_quality_cells(value):
    """
    Add background colours to quality labels.

    This is used in dataframe tables where quality categories are shown.

    Supported quality values:
        Green
        Yellow
        Orange
        Red
    """
    if value == "Green":
        return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif value == "Yellow":
        return "background-color: #fff3cd; color: #856404; font-weight: bold;"
    elif value == "Orange":
        return "background-color: #ffe0b2; color: #8a4b00; font-weight: bold;"
    elif value == "Red":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
    else:
        return ""


def detect_chamber_from_filename(file_name):
    """
    Try to detect the chamber code from the uploaded filename.

    Example filename:
        200930_propane_10h#1_m2_extracted.txt

    In this case:
        m2 should be detected as the chamber code.

    Returns
    -------
    dict or None
        Returns the matching chamber row if found.
        Returns None if no chamber code is detected.
    """
    if not file_name:
        return None

    file_name_lower = file_name.lower()

    chambers = get_all_chambers()

    for chamber in chambers:
        chamber_code = str(chamber["chamber_code"]).lower()

        # This pattern looks for chamber codes such as m1 or m2
        # surrounded by separators like _, -, #, or .
        pattern = rf"(^|[_#\-.]){re.escape(chamber_code)}([_#\-.]|$)"

        if re.search(pattern, file_name_lower):
            return chamber

    return None

def show_upload_and_test_information():
    """
    Display the file upload area and propane input fields.

    This is the first step in the user workflow:
        - Upload measurement file
        - Enter propane before/after weights
        - Preview detected chamber
    """
    st.markdown("### New Propane Test")

    uploaded_file = None
    propane_before_g = None
    propane_after_g = None

    with st.container(border=True):
        upload_col, values_col = st.columns(2)

        with upload_col:
            st.markdown("#### Upload Measurement File")

            uploaded_file = st.file_uploader(
                "Upload propane measurement file",
                type=["txt"],
                help="Upload the tab-separated .txt file exported from the measurement system.",
            )

            if uploaded_file is None:
                st.info("Please upload a .txt measurement file.")

            else:
                st.success(f"Uploaded file: {uploaded_file.name}")

                uploaded_file_size = uploaded_file.getbuffer().nbytes
                uploaded_file_key = f"{uploaded_file.name}_{uploaded_file_size}"

                if st.session_state.get("last_logged_uploaded_file_key") != uploaded_file_key:
                    log_activity(
                        category="file_uploads",
                        action="measurement_file_uploaded",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="measurement_file",
                        target_id=None,
                        target_name=uploaded_file.name,
                        details=(
                            f"Uploaded measurement file '{uploaded_file.name}' "
                            f"with size {uploaded_file_size} bytes."
                        ),
                    )

                    st.session_state.last_logged_uploaded_file_key = uploaded_file_key

                detected_chamber = detect_chamber_from_filename(uploaded_file.name)

                if detected_chamber:
                    st.success(
                        f"Detected chamber: {detected_chamber['chamber_name']} "
                        f"({detected_chamber['chamber_code']})"
                    )
                else:
                    st.warning("No chamber could be detected from the filename.")

        with values_col:
            st.markdown("#### Propane Values")

            propane_before_g = st.number_input(
                "Propane before test (g)",
                min_value=0.0,
                value=None,
                step=0.1,
                format="%.3f",
                placeholder="Enter value before test",
            )

            propane_after_g = st.number_input(
                "Propane after test (g)",
                min_value=0.0,
                value=None,
                step=0.1,
                format="%.3f",
                placeholder="Enter value after test",
            )

            if propane_before_g is None or propane_after_g is None:
                st.info("Propane before and after values are required.")

            elif propane_after_g >= propane_before_g:
                st.warning(
                    "Propane after test must be lower than propane before test."
                )

            else:
                propane_burned_g = propane_before_g - propane_after_g

                st.metric(
                    "Calculated propane burned",
                    f"{propane_burned_g:.3f} g",
                )

    return uploaded_file, propane_before_g, propane_after_g

def get_historical_reports_df(from_date=None, to_date=None, chamber_id=None):
    """
    Fetch saved analysis reports for the logged-in user and return them as a DataFrame.

    Parameters
    ----------
    from_date : date, optional
        Start date selected by the user.

    to_date : date, optional
        End date selected by the user.

    chamber_id : int, optional
        Selected chamber ID. If None, all chambers are included.

    Returns
    -------
    pandas.DataFrame
        Historical analysis reports for the current user.
    """
    user_id = st.session_state.user_id

    reports = get_analysis_reports_for_user(
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        chamber_id=chamber_id,
    )

    if not reports:
        return pd.DataFrame()

    return pd.DataFrame([dict(report) for report in reports])

def show_historical_analysis_overview():
    """
    Display historical analysis chart and average statistics.

    This section reads saved reports from the analysis_reports table.

    Layout:
        - Filters at the top
        - Historical recovery chart on the left
        - Historical average statistics on the right
    """
    st.markdown("### Historical Analysis Overview")

    st.write(
        "Review previous propane analyses and compare the current test against "
        "historical recovery and quality trends."
    )

    with st.container(border=True):
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        today = date.today()
        default_from_date = today - timedelta(days=365)

        with filter_col1:
            from_date = st.date_input(
                "From date",
                value=default_from_date,
                key="history_from_date",
            )

        with filter_col2:
            to_date = st.date_input(
                "To date",
                value=today,
                key="history_to_date",
            )

        chambers = get_all_chambers()

        chamber_options = {
            "All chambers": None
        }

        for chamber in chambers:
            chamber_label = f"{chamber['chamber_code']} - {chamber['chamber_name']}"
            chamber_options[chamber_label] = chamber["chamber_id"]

        with filter_col3:
            selected_chamber_label = st.selectbox(
                "Chamber",
                options=list(chamber_options.keys()),
                key="history_chamber_filter",
            )

        selected_chamber_id = chamber_options[selected_chamber_label]

        if from_date > to_date:
            st.error("From date cannot be later than To date.")
            return

        history_df = get_historical_reports_df(
            from_date=from_date,
            to_date=to_date,
            chamber_id=selected_chamber_id,
        )

        chart_col, stats_col = st.columns([2, 1])

        with chart_col:
            st.markdown("#### Historical Trend Chart")

            if history_df.empty:
                st.info(
                    "No saved analyses found for the selected filters. "
                    "After reports are saved, selected value trends will appear here."
                )

            else:
                # These are the values the user can choose to plot.
                #
                # The key is the name shown to the user.
                # The value is the column name in the analysis_reports table.
                chart_metric_options = {
                    "VO₂ recovery %": "vo2_recovery_percent",
                    "VCO₂ recovery %": "vco2_recovery_percent",
                    "VO₂ deviation %": "vo2_deviation_percent",
                    "VCO₂ deviation %": "vco2_deviation_percent",
                    "Burning rate (g/min)": "burning_rate_g_min",
                    "Propane burned (g)": "propane_burned_g",
                    "Total duration (min)": "total_duration_min",
                    "Analysed duration (min)": "analysed_duration_min",
                    "Flow rate (L/min)": "flow_rate_l_min",
                    "VO₂ SOLL (L)": "vo2_soll_l",
                    "VO₂ IST (L)": "vo2_ist_l",
                    "VCO₂ SOLL (L)": "vco2_soll_l",
                    "VCO₂ IST (L)": "vco2_ist_l",
                    "RQ expected": "rq_expected",
                    "RQ measured": "rq_measured",
                }

                # Only keep metrics whose database columns actually exist.
                available_metric_options = {
                    label: column
                    for label, column in chart_metric_options.items()
                    if column in history_df.columns
                }

                default_selected_metrics = [
                    metric
                    for metric in ["VO₂ recovery %", "VCO₂ recovery %"]
                    if metric in available_metric_options
                ]

                selected_metrics = st.multiselect(
                    "Select values to show in chart",
                    options=list(available_metric_options.keys()),
                    default=default_selected_metrics,
                    key="historical_chart_selected_metrics",
                )

                normalize_chart = st.checkbox(
                    "Show normalized trend for easier comparison",
                    value=False,
                    key="historical_chart_normalized",
                    help=(
                        "Useful when selected values have different units, "
                        "for example %, L, g/min, and min."
                    ),
                )

                if not selected_metrics:
                    st.info("Select at least one value to display the chart.")

                else:
                    chart_df = history_df.copy()

                    chart_df["analysed_at"] = pd.to_datetime(
                        chart_df["analysed_at"]
                    )

                    chart_df = chart_df.sort_values("analysed_at")

                    selected_columns = [
                        available_metric_options[metric]
                        for metric in selected_metrics
                    ]

                    chart_df = chart_df[
                        ["analysed_at"] + selected_columns
                    ]

                    # Rename database column names to user-friendly labels.
                    reverse_label_map = {
                        column: label
                        for label, column in available_metric_options.items()
                    }

                    chart_df = chart_df.rename(
                        columns={
                            "analysed_at": "Analysis date",
                            **reverse_label_map,
                        }
                    )

                    chart_df = chart_df.set_index("Analysis date")

                    # Convert all selected columns to numeric values.
                    # This prevents chart errors if any value was stored as text.
                    for column in chart_df.columns:
                        chart_df[column] = pd.to_numeric(
                            chart_df[column],
                            errors="coerce",
                        )

                    if normalize_chart:
                        normalized_df = chart_df.copy()

                        for column in normalized_df.columns:
                            min_value = normalized_df[column].min()
                            max_value = normalized_df[column].max()

                            if pd.isna(min_value) or pd.isna(max_value):
                                continue

                            if max_value == min_value:
                                normalized_df[column] = 100
                            else:
                                normalized_df[column] = (
                                    (normalized_df[column] - min_value)
                                    / (max_value - min_value)
                                    * 100
                                )

                        st.line_chart(normalized_df)

                        st.caption(
                            "Normalized view: each selected value is scaled from 0 to 100 "
                            "based on its own minimum and maximum in the filtered data."
                        )

                    else:
                        st.line_chart(chart_df)

                        st.caption(
                            "Raw value view: selected values are shown using their original units."
                        )

        with stats_col:
            st.markdown("#### Historical Summary")

            if history_df.empty:
                summary_df = pd.DataFrame(
                    [
                        {"Statistic": "Files analysed", "Value": "0"},
                        {"Statistic": "Avg VO₂ recovery", "Value": "—"},
                        {"Statistic": "Avg VCO₂ recovery", "Value": "—"},
                        {"Statistic": "Avg VO₂ deviation", "Value": "—"},
                        {"Statistic": "Avg VCO₂ deviation", "Value": "—"},
                        {"Statistic": "Avg burning rate", "Value": "—"},
                        {"Statistic": "Avg analysed duration", "Value": "—"},
                        {"Statistic": "Most common quality", "Value": "—"},
                    ]
                )

                styled_summary_df = summary_df.style.apply(
                    style_historical_summary_row,
                    axis=1,
                )

                st.dataframe(
                    styled_summary_df,
                    use_container_width=True,
                    hide_index=True,
                )

            else:
                files_analysed = len(history_df)

                avg_vo2_recovery = history_df["vo2_recovery_percent"].mean()
                avg_vco2_recovery = history_df["vco2_recovery_percent"].mean()
                avg_vo2_deviation = history_df["vo2_deviation_percent"].mean()
                avg_vco2_deviation = history_df["vco2_deviation_percent"].mean()
                avg_burning_rate = history_df["burning_rate_g_min"].mean()
                avg_analysed_duration = history_df["analysed_duration_min"].mean()

                quality_values = history_df["overall_quality"].dropna()

                if quality_values.empty:
                    most_common_quality = "—"
                else:
                    most_common_quality = quality_values.mode().iloc[0]

                summary_df = pd.DataFrame(
                    [
                        {
                            "Statistic": "Files analysed",
                            "Value": files_analysed,
                        },
                        {
                            "Statistic": "Avg VO₂ recovery",
                            "Value": f"{avg_vo2_recovery:.2f} %",
                        },
                        {
                            "Statistic": "Avg VCO₂ recovery",
                            "Value": f"{avg_vco2_recovery:.2f} %",
                        },
                        {
                            "Statistic": "Avg VO₂ deviation",
                            "Value": f"{avg_vo2_deviation:.2f} %",
                        },
                        {
                            "Statistic": "Avg VCO₂ deviation",
                            "Value": f"{avg_vco2_deviation:.2f} %",
                        },
                        {
                            "Statistic": "Avg burning rate",
                            "Value": f"{avg_burning_rate:.4f} g/min",
                        },
                        {
                            "Statistic": "Avg analysed duration",
                            "Value": f"{avg_analysed_duration:.1f} min",
                        },
                        {
                            "Statistic": "Most common quality",
                            "Value": most_common_quality,
                        },
                    ]
                )

                styled_summary_df = summary_df.style.apply(
                    style_historical_summary_row,
                    axis=1,
                )

                st.dataframe(
                    styled_summary_df,
                    use_container_width=True,
                    hide_index=True,
                )

                quality_counts = (
                    history_df["overall_quality"]
                    .fillna("Unknown")
                    .value_counts()
                    .reset_index()
                )

                quality_counts.columns = ["Quality", "Count"]

                st.markdown("##### Quality Counts")

                styled_quality_counts = quality_counts.style.map(
                    style_quality_cells,
                    subset=["Quality"],
                )

                st.dataframe(
                    styled_quality_counts,
                    use_container_width=True,
                    hide_index=True,
                )

def show_analysis_settings_used():
    """
    Display the current admin-controlled analysis settings.

    These values come from Admin → Analysis Settings.

    They will later be used by the analyzer when the user clicks Run Analysis.
    """
    st.markdown("### Analysis Settings Used")

    settings_rows = []

    setting_groups = [
        ("calculation_constant", "Calculation Constant"),
        ("trim_setting", "Trim Setting"),
        ("quality_threshold", "Quality Threshold"),
    ]

    for group_key, group_label in setting_groups:
        settings = get_analysis_settings_by_group(group_key)

        for setting in settings:
            settings_rows.append(
                {
                    "Group": group_label,
                    "Parameter": setting["setting_label"],
                    "Key": setting["setting_key"],
                    "Value": setting["setting_value"],
                    "Unit": setting["unit"],
                }
            )

    if not settings_rows:
        st.warning("No analysis settings found. Please check Admin → Analysis Settings.")
        return

    settings_df = pd.DataFrame(settings_rows)

    st.dataframe(
        settings_df,
        use_container_width=True,
        hide_index=True,
    )

def show_run_analysis_placeholder(uploaded_file, propane_before_g, propane_after_g):
    """
    Display the Run Analysis button.

    The button is disabled until the required inputs are valid.
    """
    st.markdown("### Run Analysis")

    file_is_ready = uploaded_file is not None

    propane_values_are_ready = (
        propane_before_g is not None
        and propane_after_g is not None
        and propane_before_g > 0
        and propane_after_g >= 0
        and propane_after_g < propane_before_g
    )

    inputs_are_ready = file_is_ready and propane_values_are_ready

    if not inputs_are_ready:
        st.info(
            "Upload a measurement file and enter valid propane values to enable analysis."
        )

    run_clicked = st.button(
        "Run Analysis",
        type="primary",
        disabled=not inputs_are_ready,
    )

    if run_clicked:
        detected_chamber = detect_chamber_from_filename(uploaded_file.name)

        settings_dict = get_current_analysis_settings_dict()

        try:
            analysis_result = run_propane_analysis(
                uploaded_file=uploaded_file,
                propane_before_g=propane_before_g,
                propane_after_g=propane_after_g,
                chamber=detected_chamber,
                settings_dict=settings_dict,
            )

            current_time = datetime.now().astimezone()

            # Store the actual analysis run time.
            # This is different from the export/download generation time.
            analysis_result["analysed_at"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
            analysis_result["timezone_used"] = current_time.tzname() or "Application local time"

            st.session_state.current_analysis_result = analysis_result

            # Reset saved report ID whenever a new analysis is run.
            # This prevents an old saved status from being reused for a new analysis.
            st.session_state.current_analysis_saved_report_id = None

            st.success("Analysis completed successfully.")

        except Exception as error:
            st.error(f"Analysis failed: {error}")

def build_report_file_prefix(report, fallback_id="unsaved"):
    """
    Build a standard export filename prefix.

    Required format:
        yyyymmdd_chambercal_<report_id>

    Examples:
        20260628_chambercal_12
        20260628_chambercal_unsaved
    """
    today_string = datetime.now().strftime("%Y%m%d")

    report_id = None

    if hasattr(report, "get"):
        report_id = report.get("report_id", None)

    if report_id is None:
        report_id = fallback_id

    return f"{today_string}_chambercal_{report_id}"

def log_report_export(export_format, report, file_prefix):
    """
    Log when a user clicks a report export/download button.

    Note:
        Streamlit can log that the download button was clicked.
        It cannot fully verify whether the browser completed the download.
    """
    report_id = report.get("report_id", None)

    if report_id is None:
        report_id = "unsaved"

    exported_file_name = f"{file_prefix}.{export_format.lower()}"

    log_activity(
        category="exports_backups",
        action=f"report_exported_{export_format.lower()}",
        actor_user_id=st.session_state.user_id,
        actor_username=st.session_state.username,
        target_type="analysis_report_export",
        target_id=report_id,
        target_name=exported_file_name,
        details=(
            f"Exported report as {export_format.upper()}. "
            f"Source report ID: {report_id}. "
            f"Export file: {exported_file_name}."
        ),
    )

def show_report_download_buttons(report, file_prefix=None, key_context="report"):
    """
    Display CSV, XLSX, and PDF download buttons for one report.

    File naming format:
        yyyymmdd_chambercal_<report_id>

    key_context is used only for Streamlit widget keys.
    It prevents duplicate keys when the same report is shown in more than one place.
    """
    report = dict(report)

    report["username"] = st.session_state.get("username", "")
    report["user_full_name"] = st.session_state.get("name", "")

    current_time = datetime.now().astimezone()

    report["report_generated_on"] = current_time.strftime("%Y-%m-%d %H:%M:%S %Z")

    if not report.get("timezone_used"):
        report["timezone_used"] = current_time.tzname() or "Application local time"

    if not report.get("analysed_at"):
        report["analysed_at"] = current_time.strftime("%Y-%m-%d %H:%M:%S")

    if file_prefix is None:
        file_prefix = build_report_file_prefix(report)

    csv_bytes = create_csv_report(report)
    xlsx_bytes = create_xlsx_report(report)
    pdf_bytes = create_pdf_report(report)

    # This affects only Streamlit widget keys, not downloaded filenames.
    safe_key_context = re.sub(
        r"[^a-zA-Z0-9_]",
        "_",
        str(key_context),
    )

    widget_key_prefix = f"{safe_key_context}_{file_prefix}"

    download_col1, download_col2, download_col3 = st.columns(3)

    with download_col1:
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name=f"{file_prefix}.csv",
            mime="text/csv",
            key=f"download_csv_{widget_key_prefix}",
            on_click=log_report_export,
            args=("csv", report, file_prefix),
        )

    with download_col2:
        st.download_button(
            label="Download XLSX",
            data=xlsx_bytes,
            file_name=f"{file_prefix}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_xlsx_{widget_key_prefix}",
            on_click=log_report_export,
            args=("xlsx", report, file_prefix),
        )

    with download_col3:
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=f"{file_prefix}.pdf",
            mime="application/pdf",
            key=f"download_pdf_{widget_key_prefix}",
            on_click=log_report_export,
            args=("pdf", report, file_prefix),
        )



def show_save_report_section(result):
    """
    Display the Save Report section for the current analysis.

    This saves the final analysis result into the analysis_reports table.
    """
    st.markdown("#### Save / Export Report")

    with st.container(border=True):
        saved_report_id = st.session_state.get(
            "current_analysis_saved_report_id",
            None,
        )

        if saved_report_id is not None:
            st.success(f"This analysis has already been saved as report ID {saved_report_id}.")

            # The current analysis result does not naturally contain the
            # database report_id, so we add it here for correct export filenames.
            result_with_report_id = result.copy()
            result_with_report_id["report_id"] = saved_report_id

            show_report_download_buttons(
                report=result_with_report_id,
                file_prefix=build_report_file_prefix(result_with_report_id),
                key_context="current_saved_analysis",
            )

            return

        st.write(
            "Save this completed analysis to the database so it appears in the "
            "historical chart and Reports tab."
        )

        st.markdown("Download this analysis without saving:")

        show_report_download_buttons(
            report=result,
            file_prefix=build_report_file_prefix(result, fallback_id="unsaved"),
            key_context="current_unsaved_analysis",
        )

        st.divider()

        save_clicked = st.button(
            "Save Report to Database",
            type="primary",
            key="save_current_analysis_report",
        )

        if save_clicked:
            report_to_save = result.copy()

            report_to_save["user_id"] = st.session_state.user_id

            if not report_to_save.get("analysed_at"):
                current_time = datetime.now().astimezone()
                report_to_save["analysed_at"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
                report_to_save["timezone_used"] = current_time.tzname() or "Application local time"

            report_id = save_analysis_report(report_to_save)

            log_activity(
                category="analysis_tracking",
                action="analysis_report_saved",
                actor_user_id=st.session_state.user_id,
                actor_username=st.session_state.username,
                target_type="analysis_report",
                target_id=report_id,
                target_name=result["file_name"],
                details=(
                    f"Saved analysis report for file '{result['file_name']}' "
                    f"with overall quality '{result['overall_quality']}'."
                ),
            )

            st.session_state.current_analysis_saved_report_id = report_id

            st.session_state.user_dashboard_message = (
                "success",
                f"Analysis report saved successfully as report ID {report_id}.",
            )

            st.rerun()

def show_current_analysis_result():
    """
    Display the most recent analysis result after Run Analysis is clicked.
    """
    if "current_analysis_result" not in st.session_state:
        return

    result = st.session_state.current_analysis_result

    st.markdown("### Current Analysis Result")

    with st.container(border=True):
        st.markdown(
            f"#### RESULTS | {result.get('chamber_name') or 'Unknown chamber'}"
        )

        st.caption(f"File: {result['file_name']}")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Start time", result["start_time"])
        col2.metric("Total duration", f"{result['total_duration_min']:.1f} min")
        col3.metric("Analysed duration", f"{result['analysed_duration_min']:.1f} min")
        col4.metric("Propane burned", f"{result['propane_burned_g']:.3f} g")

        col5, col6 = st.columns(2)

        col5.metric("Burning rate", f"{result['burning_rate_g_min']:.4f} g/min")
        col6.metric("Overall quality", result["overall_quality"])

        st.markdown("#### SOLL / IST Comparison")

        comparison_df = pd.DataFrame(
            [
                {
                    "Metric": "VO₂_c",
                    "SOLL (L)": round(result["vo2_soll_l"], 3),
                    "IST (L)": round(result["vo2_ist_l"], 3),
                    "Recovery (%)": round(result["vo2_recovery_percent"], 2),
                    "Deviation (%)": round(result["vo2_deviation_percent"], 2),
                    "Quality": result["vo2_quality"],
                },
                {
                    "Metric": "VCO₂_c",
                    "SOLL (L)": round(result["vco2_soll_l"], 3),
                    "IST (L)": round(result["vco2_ist_l"], 3),
                    "Recovery (%)": round(result["vco2_recovery_percent"], 2),
                    "Deviation (%)": round(result["vco2_deviation_percent"], 2),
                    "Quality": result["vco2_quality"],
                },
            ]
        )

        styled_comparison_df = comparison_df.style.map(
            style_quality_cells,
            subset=["Quality"],
        )

        st.dataframe(
            styled_comparison_df,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### Key Statistics - Trimmed Window")

        statistics_rows = []

        for parameter, values in result["statistics"].items():
            statistics_rows.append(
                {
                    "Parameter": parameter,
                    "Mean": round(values["mean"], 4),
                    "SD": round(values["sd"], 4),
                    "Min": round(values["min"], 4),
                    "Max": round(values["max"], 4),
                }
            )

        statistics_df = pd.DataFrame(statistics_rows)

        st.dataframe(
            statistics_df,
            use_container_width=True,
            hide_index=True,
        )

        show_save_report_section(result)

def parse_json_field(json_text):
    """
    Safely convert a JSON text field from the database into a Python dictionary.

    Some report details, such as key statistics and settings snapshots,
    are stored as JSON text in the database.

    If the field is empty or invalid, this function returns an empty dictionary.
    """
    if not json_text:
        return {}

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return {}

def show_reports_tab():
    """
    Display saved propane analysis reports for the logged-in user.

    This tab reads from the analysis_reports table.

    Features:
        - Date filter
        - Chamber filter
        - Quality filter
        - Saved report table
        - Selected report details
    """
    st.subheader("Reports")

    st.write(
        "View previously saved propane analysis reports for your account."
    )

    with st.container(border=True):
        st.markdown("#### Report Filters")

        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

        today = date.today()
        default_from_date = today - timedelta(days=365)

        with filter_col1:
            from_date = st.date_input(
                "From date",
                value=default_from_date,
                key="reports_from_date",
            )

        with filter_col2:
            to_date = st.date_input(
                "To date",
                value=today,
                key="reports_to_date",
            )

        chambers = get_all_chambers()

        chamber_options = {
            "All chambers": None
        }

        for chamber in chambers:
            chamber_label = f"{chamber['chamber_code']} - {chamber['chamber_name']}"
            chamber_options[chamber_label] = chamber["chamber_id"]

        with filter_col3:
            selected_chamber_label = st.selectbox(
                "Chamber",
                options=list(chamber_options.keys()),
                key="reports_chamber_filter",
            )

        with filter_col4:
            selected_quality = st.selectbox(
                "Quality",
                options=[
                    "All",
                    "Green",
                    "Yellow",
                    "Orange",
                    "Red",
                ],
                key="reports_quality_filter",
            )

        if from_date > to_date:
            st.error("From date cannot be later than To date.")
            return

        selected_chamber_id = chamber_options[selected_chamber_label]

        reports_df = get_historical_reports_df(
            from_date=from_date,
            to_date=to_date,
            chamber_id=selected_chamber_id,
        )

        if reports_df.empty:
            st.info("No saved reports found for the selected filters.")
            return

        if selected_quality != "All":
            reports_df = reports_df[
                reports_df["overall_quality"] == selected_quality
            ]

        if reports_df.empty:
            st.info("No saved reports match the selected quality filter.")
            return

        reports_df["analysed_at"] = pd.to_datetime(
            reports_df["analysed_at"],
            errors="coerce",
        )

        reports_df = reports_df.sort_values(
            "analysed_at",
            ascending=False,
        )

        display_reports_df = reports_df[
            [
                "report_id",
                "analysed_at",
                "file_name",
                "chamber_code",
                "chamber_name",
                "analysed_duration_min",
                "propane_burned_g",
                "burning_rate_g_min",
                "vo2_recovery_percent",
                "vco2_recovery_percent",
                "overall_quality",
            ]
        ].copy()

        display_reports_df = display_reports_df.rename(
            columns={
                "report_id": "Report ID",
                "analysed_at": "Analysed At",
                "file_name": "File",
                "chamber_code": "Chamber Code",
                "chamber_name": "Chamber",
                "analysed_duration_min": "Analysed Duration (min)",
                "propane_burned_g": "Propane Burned (g)",
                "burning_rate_g_min": "Burning Rate (g/min)",
                "vo2_recovery_percent": "VO₂ Recovery (%)",
                "vco2_recovery_percent": "VCO₂ Recovery (%)",
                "overall_quality": "Quality",
            }
        )

        display_reports_df["Analysed At"] = display_reports_df[
            "Analysed At"
        ].dt.strftime("%Y-%m-%d %H:%M")

        numeric_columns = [
            "Analysed Duration (min)",
            "Propane Burned (g)",
            "Burning Rate (g/min)",
            "VO₂ Recovery (%)",
            "VCO₂ Recovery (%)",
        ]

        for column in numeric_columns:
            display_reports_df[column] = pd.to_numeric(
                display_reports_df[column],
                errors="coerce",
            ).round(3)

        st.markdown("#### Saved Reports")

        styled_reports_df = display_reports_df.style.map(
            style_quality_cells,
            subset=["Quality"],
        )

        st.dataframe(
            styled_reports_df,
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        st.markdown("#### View Report Details")

        report_options = {}

        for _, row in reports_df.iterrows():
            report_label = (
                f"Report {row['report_id']} | "
                f"{row['analysed_at'].strftime('%Y-%m-%d %H:%M')} | "
                f"{row['file_name']}"
            )

            report_options[report_label] = row["report_id"]

        selected_report_label = st.selectbox(
            "Select a report",
            options=list(report_options.keys()),
            key="selected_report_details",
        )

        selected_report_id = report_options[selected_report_label]

        selected_report = reports_df[
            reports_df["report_id"] == selected_report_id
        ].iloc[0]

        with st.container(border=True):
            st.markdown(
                f"### RESULTS | {selected_report.get('chamber_name') or 'Unknown chamber'}"
            )

            st.caption(f"File: {selected_report['file_name']}")
            st.caption(
                f"Analysed at: {selected_report['analysed_at'].strftime('%Y-%m-%d %H:%M')}"
            )

            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

            summary_col1.metric(
                "Total duration",
                f"{selected_report['total_duration_min']:.1f} min",
            )

            summary_col2.metric(
                "Analysed duration",
                f"{selected_report['analysed_duration_min']:.1f} min",
            )

            summary_col3.metric(
                "Propane burned",
                f"{selected_report['propane_burned_g']:.3f} g",
            )

            summary_col4.metric(
                "Overall quality",
                selected_report["overall_quality"],
            )

            summary_col5, summary_col6 = st.columns(2)

            summary_col5.metric(
                "Burning rate",
                f"{selected_report['burning_rate_g_min']:.4f} g/min",
            )

            if pd.notna(selected_report["rq_measured"]):
                summary_col6.metric(
                    "RQ measured",
                    f"{selected_report['rq_measured']:.4f}",
                )
            else:
                summary_col6.metric("RQ measured", "—")

            st.markdown("#### SOLL / IST Comparison")

            comparison_df = pd.DataFrame(
                [
                    {
                        "Metric": "VO₂_c",
                        "SOLL (L)": round(selected_report["vo2_soll_l"], 3),
                        "IST (L)": round(selected_report["vo2_ist_l"], 3),
                        "Recovery (%)": round(
                            selected_report["vo2_recovery_percent"],
                            2,
                        ),
                        "Deviation (%)": round(
                            selected_report["vo2_deviation_percent"],
                            2,
                        ),
                        "Quality": selected_report["vo2_quality"],
                    },
                    {
                        "Metric": "VCO₂_c",
                        "SOLL (L)": round(selected_report["vco2_soll_l"], 3),
                        "IST (L)": round(selected_report["vco2_ist_l"], 3),
                        "Recovery (%)": round(
                            selected_report["vco2_recovery_percent"],
                            2,
                        ),
                        "Deviation (%)": round(
                            selected_report["vco2_deviation_percent"],
                            2,
                        ),
                        "Quality": selected_report["vco2_quality"],
                    },
                ]
            )

            styled_comparison_df = comparison_df.style.map(
                style_quality_cells,
                subset=["Quality"],
            )

            st.dataframe(
                styled_comparison_df,
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("#### Key Statistics - Trimmed Window")

            statistics = parse_json_field(selected_report["statistics_json"])

            if not statistics:
                st.info("No key statistics were saved for this report.")
            else:
                statistics_rows = []

                for parameter, values in statistics.items():
                    statistics_rows.append(
                        {
                            "Parameter": parameter,
                            "Mean": round(values.get("mean", 0), 4),
                            "SD": round(values.get("sd", 0), 4),
                            "Min": round(values.get("min", 0), 4),
                            "Max": round(values.get("max", 0), 4),
                        }
                    )

                statistics_df = pd.DataFrame(statistics_rows)

                st.dataframe(
                    statistics_df,
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("#### Analysis Settings Used")

            settings_snapshot = parse_json_field(
                selected_report["settings_snapshot_json"]
            )

            if not settings_snapshot:
                st.info("No settings snapshot was saved for this report.")
            else:
                settings_rows = []

                for key, value in settings_snapshot.items():
                    settings_rows.append(
                        {
                            "Setting Key": key,
                            "Value": value,
                        }
                    )

                settings_df = pd.DataFrame(settings_rows)

                st.dataframe(
                    settings_df,
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("#### Download Report")

            show_report_download_buttons(
                report=selected_report,
                file_prefix=build_report_file_prefix(selected_report),
                key_context=f"reports_tab_{selected_report_id}",
            )

def show_user_dashboard():
    """
    Display the user area with top-level tabs.

    Tabs:
        1. User Dashboard
        2. Reports
    """
    user_dashboard_tab, reports_tab = st.tabs(
        ["User Dashboard", "Reports"]
    )

    with user_dashboard_tab:
        st.subheader("User Dashboard")

        show_user_dashboard_message()

        st.write(
            "Upload a propane test file, review historical analysis trends, "
            "check the current analysis settings, and run a new analysis."
        )

        uploaded_file, propane_before_g, propane_after_g = show_upload_and_test_information()

        st.divider()

        show_historical_analysis_overview()

        st.divider()

        show_analysis_settings_used()

        st.divider()

        show_run_analysis_placeholder(
            uploaded_file=uploaded_file,
            propane_before_g=propane_before_g,
            propane_after_g=propane_after_g,
        )

        show_current_analysis_result()

    with reports_tab:
        show_reports_tab()