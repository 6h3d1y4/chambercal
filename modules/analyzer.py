import pandas as pd


def get_setting_value(settings_dict, key, default_value):
    """
    Safely get one setting value from a settings dictionary.

    If the key is missing, the default value is used.
    """
    return float(settings_dict.get(key, default_value))


def calculate_quality_category(deviation_percent, settings_dict):
    """
    Convert a recovery deviation into a quality category.

    Example:
        deviation = abs(recovery_percent - 100)

    Default thresholds:
        <= 1 %  Green
        <= 3 %  Yellow
        <= 5 %  Orange
        > 5 %   Red
    """
    green_limit = get_setting_value(settings_dict, "green_limit_percent", 1.0)
    yellow_limit = get_setting_value(settings_dict, "yellow_limit_percent", 3.0)
    orange_limit = get_setting_value(settings_dict, "orange_limit_percent", 5.0)

    if deviation_percent <= green_limit:
        return "Green"
    elif deviation_percent <= yellow_limit:
        return "Yellow"
    elif deviation_percent <= orange_limit:
        return "Orange"
    else:
        return "Red"


def read_measurement_file(uploaded_file):
    """
    Read the uploaded propane measurement .txt file.

    The expected file format is:
        - tab-separated
        - European decimal commas
        - datetime column named 'datetime'

    Example decimal:
        0,6805

    Returns
    -------
    pandas.DataFrame
        Cleaned dataframe with parsed datetime column.
    """
    uploaded_file.seek(0)

    df = pd.read_csv(
        uploaded_file,
        sep="\t",
        decimal=",",
    )

    # Remove accidental spaces from column names.
    df.columns = df.columns.str.strip()

    if "datetime" not in df.columns:
        raise ValueError("The uploaded file must contain a 'datetime' column.")

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        format="%d.%m.%Y %H:%M:%S",
        errors="coerce",
    )

    df = df.dropna(subset=["datetime"])

    if df.empty:
        raise ValueError("No valid datetime values could be read from the file.")

    return df


def trim_measurement_data(df, trim_start_min, trim_end_min):
    """
    Trim the measurement file using timestamp-based trimming.

    Example:
        trim_start_min = 10
        trim_end_min = 11

    This removes:
        - first 10 minutes
        - last 11 minutes
    """
    start_time = df["datetime"].min()
    end_time = df["datetime"].max()

    trim_start_time = start_time + pd.Timedelta(minutes=trim_start_min)
    trim_end_time = end_time - pd.Timedelta(minutes=trim_end_min)

    trimmed_df = df[
        (df["datetime"] >= trim_start_time)
        & (df["datetime"] <= trim_end_time)
    ].copy()

    if trimmed_df.empty:
        raise ValueError("No data remains after trimming. Check trim settings.")

    return trimmed_df


def calculate_key_statistics(trimmed_df):
    """
    Calculate mean, standard deviation, minimum, and maximum for numeric columns.

    Returns
    -------
    dict
        Example:
        {
            "VO2_c": {
                "mean": 0.6805,
                "sd": 0.0286,
                "min": 0.5876,
                "max": 0.7406
            }
        }
    """
    numeric_df = trimmed_df.select_dtypes(include="number")

    statistics = {}

    for column in numeric_df.columns:
        statistics[column] = {
            "mean": float(numeric_df[column].mean()),
            "sd": float(numeric_df[column].std()),
            "min": float(numeric_df[column].min()),
            "max": float(numeric_df[column].max()),
        }

    return statistics


def run_propane_analysis(
    uploaded_file,
    propane_before_g,
    propane_after_g,
    chamber,
    settings_dict,
):
    """
    Run the complete propane test analysis.

    Steps:
        1. Read uploaded file
        2. Trim warm-up and cool-down window
        3. Calculate propane burned and burning rate
        4. Calculate theoretical SOLL values
        5. Calculate measured IST values
        6. Calculate recovery and deviation
        7. Assign quality categories
        8. Calculate key statistics

    Returns
    -------
    dict
        Final analysis report data.
    """
    df = read_measurement_file(uploaded_file)

    trim_start_min = get_setting_value(settings_dict, "trim_start_min", 10.0)
    trim_end_min = get_setting_value(settings_dict, "trim_end_min", 11.0)

    trimmed_df = trim_measurement_data(
        df=df,
        trim_start_min=trim_start_min,
        trim_end_min=trim_end_min,
    )

    start_time = df["datetime"].min()
    end_time = df["datetime"].max()

    total_duration_min = (end_time - start_time).total_seconds() / 60

    analysed_start_time = trimmed_df["datetime"].min()
    analysed_end_time = trimmed_df["datetime"].max()

    analysed_duration_min = (
        analysed_end_time - analysed_start_time
    ).total_seconds() / 60

    propane_burned_g = propane_before_g - propane_after_g

    if propane_burned_g <= 0:
        raise ValueError("Propane burned must be greater than zero.")

    if analysed_duration_min <= 0:
        raise ValueError("Analysed duration must be greater than zero.")

    burning_rate_g_min = propane_burned_g / analysed_duration_min

    propane_molar_mass = get_setting_value(
        settings_dict,
        "propane_molar_mass_g_mol",
        44.0,
    )

    molar_volume = get_setting_value(
        settings_dict,
        "molar_volume_l_mol",
        22.4,
    )

    o2_factor = get_setting_value(
        settings_dict,
        "o2_stoichiometric_factor",
        5.0,
    )

    co2_factor = get_setting_value(
        settings_dict,
        "co2_stoichiometric_factor",
        3.0,
    )

    rq_expected = get_setting_value(
        settings_dict,
        "expected_rq",
        0.6,
    )

    vo2_soll_l = (
        propane_burned_g
        / propane_molar_mass
        * o2_factor
        * molar_volume
    )

    vco2_soll_l = (
        propane_burned_g
        / propane_molar_mass
        * co2_factor
        * molar_volume
    )

    if "VO2_c" not in trimmed_df.columns:
        raise ValueError("The uploaded file must contain a 'VO2_c' column.")

    if "VCO2_c" not in trimmed_df.columns:
        raise ValueError("The uploaded file must contain a 'VCO2_c' column.")

    vo2_ist_l = float(trimmed_df["VO2_c"].sum())
    vco2_ist_l = float(trimmed_df["VCO2_c"].sum())

    vo2_recovery_percent = vo2_ist_l / vo2_soll_l * 100
    vco2_recovery_percent = vco2_ist_l / vco2_soll_l * 100

    vo2_deviation_percent = abs(vo2_recovery_percent - 100)
    vco2_deviation_percent = abs(vco2_recovery_percent - 100)

    vo2_quality = calculate_quality_category(
        vo2_deviation_percent,
        settings_dict,
    )

    vco2_quality = calculate_quality_category(
        vco2_deviation_percent,
        settings_dict,
    )

    worst_quality_order = {
        "Green": 1,
        "Yellow": 2,
        "Orange": 3,
        "Red": 4,
    }

    overall_quality = max(
        [vo2_quality, vco2_quality],
        key=lambda quality: worst_quality_order[quality],
    )

    if "RQ_c" in trimmed_df.columns:
        rq_measured = float(trimmed_df["RQ_c"].mean())
    else:
        rq_measured = None

    statistics = calculate_key_statistics(trimmed_df)

    report_data = {
        "file_name": uploaded_file.name,

        "chamber_id": chamber["chamber_id"] if chamber else None,
        "chamber_code": chamber["chamber_code"] if chamber else None,
        "chamber_name": chamber["chamber_name"] if chamber else None,

        "start_time": start_time.strftime("%H:%M"),

        "total_duration_min": total_duration_min,
        "analysed_duration_min": analysed_duration_min,

        "propane_before_g": propane_before_g,
        "propane_after_g": propane_after_g,
        "propane_burned_g": propane_burned_g,
        "burning_rate_g_min": burning_rate_g_min,

        "flow_rate_l_min": None,

        "vo2_soll_l": vo2_soll_l,
        "vo2_ist_l": vo2_ist_l,
        "vo2_recovery_percent": vo2_recovery_percent,
        "vo2_deviation_percent": vo2_deviation_percent,
        "vo2_quality": vo2_quality,

        "vco2_soll_l": vco2_soll_l,
        "vco2_ist_l": vco2_ist_l,
        "vco2_recovery_percent": vco2_recovery_percent,
        "vco2_deviation_percent": vco2_deviation_percent,
        "vco2_quality": vco2_quality,

        "rq_expected": rq_expected,
        "rq_measured": rq_measured,

        "overall_quality": overall_quality,

        "statistics": statistics,
        "settings_snapshot": settings_dict,
        "trimmed_data": trimmed_df,
    }

    return report_data