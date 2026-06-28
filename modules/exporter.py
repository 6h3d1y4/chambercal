import json
import os
from datetime import datetime
from io import BytesIO, StringIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)

def get_value(report, key, default=None):
    """
    Safely get a value from either a dictionary or a pandas Series.
    """
    if hasattr(report, "get"):
        return report.get(key, default)

    return default


def parse_json_field(json_text):
    """
    Convert a JSON text field into a Python dictionary.

    Used for saved reports because statistics and settings snapshots
    are stored as JSON text in the database.
    """
    if not json_text:
        return {}

    if isinstance(json_text, dict):
        return json_text

    try:
        return json.loads(json_text)
    except Exception:
        return {}


def build_summary_df(report):
    """
    Build the summary section of the report.

    File and chamber are not included here because they are shown
    in the PDF footer.
    """
    return pd.DataFrame(
        [
            {"Field": "Start time", "Value": get_value(report, "start_time", "")},
            {
                "Field": "Total duration (min)",
                "Value": round(float(get_value(report, "total_duration_min", 0) or 0), 3),
            },
            {
                "Field": "Analysed duration (min)",
                "Value": round(float(get_value(report, "analysed_duration_min", 0) or 0), 3),
            },
            {
                "Field": "Propane before (g)",
                "Value": round(float(get_value(report, "propane_before_g", 0) or 0), 3),
            },
            {
                "Field": "Propane after (g)",
                "Value": round(float(get_value(report, "propane_after_g", 0) or 0), 3),
            },
            {
                "Field": "Propane burned (g)",
                "Value": round(float(get_value(report, "propane_burned_g", 0) or 0), 3),
            },
            {
                "Field": "Burning rate (g/min)",
                "Value": round(float(get_value(report, "burning_rate_g_min", 0) or 0), 4),
            },
            {
                "Field": "Overall quality",
                "Value": get_value(report, "overall_quality", ""),
            },
        ]
    )


def build_comparison_df(report):
    """
    Build the SOLL / IST comparison table.
    """
    return pd.DataFrame(
        [
            {
                "Metric": "VO2_c",
                "SOLL (L)": round(float(get_value(report, "vo2_soll_l", 0) or 0), 3),
                "IST (L)": round(float(get_value(report, "vo2_ist_l", 0) or 0), 3),
                "Recovery (%)": round(float(get_value(report, "vo2_recovery_percent", 0) or 0), 2),
                "Deviation (%)": round(float(get_value(report, "vo2_deviation_percent", 0) or 0), 2),
                "Quality": get_value(report, "vo2_quality", ""),
            },
            {
                "Metric": "VCO2_c",
                "SOLL (L)": round(float(get_value(report, "vco2_soll_l", 0) or 0), 3),
                "IST (L)": round(float(get_value(report, "vco2_ist_l", 0) or 0), 3),
                "Recovery (%)": round(float(get_value(report, "vco2_recovery_percent", 0) or 0), 2),
                "Deviation (%)": round(float(get_value(report, "vco2_deviation_percent", 0) or 0), 2),
                "Quality": get_value(report, "vco2_quality", ""),
            },
        ]
    )


def build_statistics_df(report):
    """
    Build the key statistics table.

    Works with:
        - current analysis result, where statistics is already a dict
        - saved report, where statistics_json is stored as text
    """
    statistics = get_value(report, "statistics", None)

    if statistics is None:
        statistics = parse_json_field(get_value(report, "statistics_json", ""))

    rows = []

    for parameter, values in statistics.items():
        rows.append(
            {
                "Parameter": parameter,
                "Mean": round(float(values.get("mean", 0) or 0), 4),
                "SD": round(float(values.get("sd", 0) or 0), 4),
                "Min": round(float(values.get("min", 0) or 0), 4),
                "Max": round(float(values.get("max", 0) or 0), 4),
            }
        )

    return pd.DataFrame(rows)


def build_settings_df(report):
    """
    Build the settings snapshot table.

    Works with:
        - current analysis result, where settings_snapshot is already a dict
        - saved report, where settings_snapshot_json is stored as text
    """
    settings = get_value(report, "settings_snapshot", None)

    if settings is None:
        settings = parse_json_field(get_value(report, "settings_snapshot_json", ""))

    rows = []

    for key, value in settings.items():
        rows.append(
            {
                "Setting Key": key,
                "Value": value,
            }
        )

    return pd.DataFrame(rows)

def get_report_value(report, key, default=""):
    """
    Safely get a value from either a dictionary or a pandas Series.

    This is useful because:
        - current analysis result is stored as a dictionary
        - saved report from the database is often a pandas Series
    """
    if hasattr(report, "get"):
        value = report.get(key, default)

        if value is None:
            return default

        return value

    return default

def build_metadata_df(report):
    """
    Build metadata shown at the top of the PDF report.

    This section explains:
        - who generated the report
        - when the analysis was run
        - when the export report was generated
        - which timezone is used
    """
    analysed_at = get_report_value(report, "analysed_at", "")

    report_generated_on = get_report_value(report, "report_generated_on", "")

    if not report_generated_on:
        report_generated_on = datetime.now().astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )

    user_name = get_report_value(report, "user_full_name", "")
    username = get_report_value(report, "username", "")

    if not user_name:
        user_name = username

    if not user_name:
        user_name = "Unknown user"

    timezone_used = get_report_value(report, "timezone_used", "")

    if not timezone_used:
        timezone_used = "Application local time"

    return pd.DataFrame(
        [
            {"Field": "Generated by", "Value": user_name},
            {"Field": "Username", "Value": username or "—"},
            {"Field": "Analysis run date/time", "Value": analysed_at or "—"},
            {"Field": "Report generated on", "Value": report_generated_on},
            {"Field": "Timezone used", "Value": timezone_used},
        ]
    )

def create_csv_report(report):
    """
    Create a CSV-style report as bytes.

    CSV does not support multiple sheets, so we write the report as sections.
    """
    output = StringIO()

    summary_df = build_summary_df(report)
    comparison_df = build_comparison_df(report)
    statistics_df = build_statistics_df(report)
    settings_df = build_settings_df(report)

    output.write("ChamberCal Propane Analysis Report\n\n")

    output.write("Summary\n")
    summary_df.to_csv(output, index=False)

    output.write("\nSOLL / IST Comparison\n")
    comparison_df.to_csv(output, index=False)

    output.write("\nKey Statistics - Trimmed Window\n")
    statistics_df.to_csv(output, index=False)

    output.write("\nAnalysis Settings Used\n")
    settings_df.to_csv(output, index=False)

    return output.getvalue().encode("utf-8")


def create_xlsx_report(report):
    """
    Create an Excel report as bytes.

    Excel is the best export format because it supports multiple sheets.
    """
    output = BytesIO()

    summary_df = build_summary_df(report)
    comparison_df = build_comparison_df(report)
    statistics_df = build_statistics_df(report)
    settings_df = build_settings_df(report)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        comparison_df.to_excel(writer, sheet_name="SOLL_IST", index=False)
        statistics_df.to_excel(writer, sheet_name="Statistics", index=False)
        settings_df.to_excel(writer, sheet_name="Settings_Used", index=False)

        trimmed_data = get_value(report, "trimmed_data", None)

        if isinstance(trimmed_data, pd.DataFrame):
            trimmed_data.to_excel(writer, sheet_name="Trimmed_Data", index=False)

    output.seek(0)

    return output.getvalue()


def get_quality_background_colour(quality):
    """
    Return a background colour for quality labels in the PDF table.
    """
    if quality == "Green":
        return colors.HexColor("#d4edda")
    if quality == "Yellow":
        return colors.HexColor("#fff3cd")
    if quality == "Orange":
        return colors.HexColor("#ffe0b2")
    if quality == "Red":
        return colors.HexColor("#f8d7da")

    return colors.white

def dataframe_to_reportlab_table(dataframe, styles):
    """
    Convert a pandas DataFrame into ReportLab table data.

    Long text values are wrapped using Paragraph objects so they do not
    overflow into neighbouring tables.
    """
    table_data = [list(dataframe.columns)]

    for _, row in dataframe.iterrows():
        table_row = []

        for value in row:
            value_text = str(value)

            table_row.append(
                Paragraph(
                    value_text,
                    styles["CompactNormal"],
                )
            )

        table_data.append(table_row)

    return table_data

def get_compact_pdf_styles():
    """
    Create compact left-aligned PDF styles.

    These sizes are slightly larger for readability while still trying
    to keep the report close to one page.
    """
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="CompactTitle",
            parent=styles["Title"],
            fontSize=16,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=4,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CompactHeading",
            parent=styles["Heading2"],
            fontSize=11,
            leading=12,
            alignment=TA_LEFT,
            spaceBefore=3,
            spaceAfter=4,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CompactNormal",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=10,
            alignment=TA_LEFT,
            spaceAfter=2,
        )
    )

    return styles


def create_styled_pdf_table(dataframe, styles, font_size=8, col_widths=None):
    """
    Create a compact, left-aligned ReportLab table from a pandas DataFrame.

    Fixed column widths prevent one table from expanding into another.
    """
    table_data = dataframe_to_reportlab_table(dataframe, styles)

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=col_widths,
    )

    table.hAlign = "LEFT"

    table_style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),

            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),

            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),

            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
    )

    if "Quality" in dataframe.columns:
        quality_col_index = list(dataframe.columns).index("Quality")

        for row_index, quality in enumerate(dataframe["Quality"], start=1):
            table_style.add(
                "BACKGROUND",
                (quality_col_index, row_index),
                (quality_col_index, row_index),
                get_quality_background_colour(quality),
            )

            table_style.add(
                "FONTNAME",
                (quality_col_index, row_index),
                (quality_col_index, row_index),
                "Helvetica-Bold",
            )

    if "Field" in dataframe.columns and "Value" in dataframe.columns:
        value_col_index = list(dataframe.columns).index("Value")

        for row_index, row in dataframe.iterrows():
            if row["Field"] == "Overall quality":
                quality = row["Value"]
                pdf_row_index = row_index + 1

                table_style.add(
                    "BACKGROUND",
                    (value_col_index, pdf_row_index),
                    (value_col_index, pdf_row_index),
                    get_quality_background_colour(quality),
                )

                table_style.add(
                    "FONTNAME",
                    (value_col_index, pdf_row_index),
                    (value_col_index, pdf_row_index),
                    "Helvetica-Bold",
                )

    table.setStyle(table_style)

    return table

def add_summary_and_settings_side_by_side(elements, summary_df, settings_df, styles):
    """
    Add Summary and Analysis Settings Used side by side.

    Fixed inner column widths prevent the two tables from overlapping.
    """
    summary_title = Paragraph("Summary", styles["CompactHeading"])
    settings_title = Paragraph("Analysis Settings Used", styles["CompactHeading"])

    summary_table = create_styled_pdf_table(
        dataframe=summary_df,
        styles=styles,
        font_size=7.8,
        col_widths=[105, 120],
    )

    if settings_df.empty:
        settings_table = Table([["No settings available."]])
    else:
        settings_table = create_styled_pdf_table(
            dataframe=settings_df,
            styles=styles,
            font_size=7.8,
            col_widths=[155, 45],
        )

    left_cell = [
        summary_title,
        summary_table,
    ]

    right_cell = [
        settings_title,
        settings_table,
    ]

    outer_table = Table(
        [[left_cell, right_cell]],
        colWidths=[240, 230],
    )

    outer_table.hAlign = "LEFT"

    outer_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    elements.append(outer_table)
    elements.append(Spacer(1, 6))

def add_dataframe_table(elements, dataframe, title, styles, font_size=8, col_widths=None):
    """
    Add a compact full-width dataframe table to the PDF.
    """
    elements.append(Paragraph(title, styles["CompactHeading"]))

    if dataframe.empty:
        elements.append(Paragraph("No data available.", styles["CompactNormal"]))
        elements.append(Spacer(1, 4))
        return

    table = create_styled_pdf_table(
        dataframe=dataframe,
        styles=styles,
        font_size=font_size,
        col_widths=col_widths,
    )

    elements.append(table)
    elements.append(Spacer(1, 6))


def draw_pdf_footer(canvas, document, chamber_name, file_name):
    """
    Draw a compact footer on each PDF page.

    The footer contains the chamber and source file name.
    """
    canvas.saveState()

    footer_text = f"Chamber: {chamber_name} | File: {file_name}"

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)

    page_width, page_height = A4

    footer_y = 10

    canvas.drawString(
        document.leftMargin,
        footer_y,
        footer_text,
    )

    canvas.setStrokeColor(colors.lightgrey)
    canvas.setLineWidth(0.25)
    canvas.line(
        document.leftMargin,
        footer_y + 9,
        page_width - document.rightMargin,
        footer_y + 9,
    )

    canvas.restoreState()

def create_pdf_report(report):
    """
    Create a compact PDF report as bytes.

    Layout:
        - Compact logo and title
        - User/report metadata
        - Summary and analysis settings side by side
        - SOLL / IST comparison
        - Key statistics
        - Chamber and file information as footer
    """
    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=18,
        bottomMargin=24,
    )

    styles = get_compact_pdf_styles()
    elements = []

    logo_path = os.path.join("assets", "chambercal_logo.png")
    title_text = "ChamberCal Propane Analysis Report"

    chamber_name = get_report_value(report, "chamber_name", "Unknown chamber")
    file_name = get_report_value(report, "file_name", "")

    if os.path.exists(logo_path):
        logo = Image(logo_path, width=70, height=40)

        header_table = Table(
            [
                [
                    logo,
                    Paragraph(title_text, styles["CompactTitle"]),
                ]
            ],
            colWidths=[82, 430],
        )

        header_table.hAlign = "LEFT"

        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        elements.append(header_table)

    else:
        elements.append(Paragraph(title_text, styles["CompactTitle"]))

    elements.append(Spacer(1, 4))

    metadata_df = build_metadata_df(report)
    summary_df = build_summary_df(report)
    comparison_df = build_comparison_df(report)
    statistics_df = build_statistics_df(report)
    settings_df = build_settings_df(report)

    add_dataframe_table(
        elements=elements,
        dataframe=metadata_df,
        title="Report Metadata",
        styles=styles,
        font_size=7.8,
        col_widths=[120, 300],
    )

    add_summary_and_settings_side_by_side(
        elements=elements,
        summary_df=summary_df,
        settings_df=settings_df,
        styles=styles,
    )

    add_dataframe_table(
        elements=elements,
        dataframe=comparison_df,
        title="SOLL / IST Comparison",
        styles=styles,
        font_size=8,
        col_widths=[70, 65, 65, 80, 80, 55],
    )

    add_dataframe_table(
        elements=elements,
        dataframe=statistics_df,
        title="Key Statistics - Trimmed Window",
        styles=styles,
        font_size=7.6,
        col_widths=[80, 60, 60, 60, 60],
    )

    document.build(
        elements,
        onFirstPage=lambda canvas, doc: draw_pdf_footer(
            canvas,
            doc,
            chamber_name,
            file_name,
        ),
        onLaterPages=lambda canvas, doc: draw_pdf_footer(
            canvas,
            doc,
            chamber_name,
            file_name,
        ),
    )

    output.seek(0)

    return output.getvalue()