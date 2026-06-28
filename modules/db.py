from pathlib import Path
import sqlite3
import hashlib
import os
import json


# ---------------------------------------------------------
# Database path
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR /"database"
DATABASE_PATH = DATABASE_DIR / "chambercal.db"

def hash_password(password):
    """
    Convert a plain-text password into a salted hash.

    We do not store the original password in the database.
    Instead, we store:
        salt + password hash

    This is safer than storing plain passwords.
    """
    salt = os.urandom(16).hex()

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        100000
    ).hex()

    return f"{salt}${password_hash}"

def verify_password(password,stored_password_hash):
    """
    Check whether a plain-text password matches the stored salted hash.

    Parameters
    ----------
    password : str
        Password entered by the user.
    stored_password_hash : str
        Stored value from the database in the format:
        salt$password_hash

    Returns
    -------
    bool
        True if the password matches.
        False if the password does not match.
    """
    salt, saved_hash = stored_password_hash.split("$")

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        100000
    ).hex()

    return password_hash == saved_hash



# ---------------------------------------------------------
# Database connection
# ---------------------------------------------------------

def get_connection():
    """
    Create and return a connection to the SQLite database.
    The database folder is created automatically if it does not exist.
    The row_factory setting allows us to access database rows like dictionaries.
    """
    DATABASE_DIR.mkdir(exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def create_user(username, password, full_name, role):
    """
    Add a new user to the database.

    Returns
    -------
    bool
        True if the user was created.
        False if the username already exists.
    """
    connection = get_connection()
    cursor = connection.cursor()

    password_hash = hash_password(password)

    cursor.execute(
        """
        INSERT OR IGNORE INTO users (
            username,
            password_hash,
            full_name,
            role
        )
        VALUES (?, ?, ?, ?)
        """,
        (username, password_hash, full_name, role)
    )

    connection.commit()

    user_created = cursor.rowcount == 1

    connection.close()

    return user_created

def create_default_users():
    """
    Create default users for the first version of the app.

    These users are only inserted if they do not already exist.
    """
    create_user(
        username="admin",
        password="admin123",
        full_name="Admin User",
        role="admin"
    )

    create_user(
        username="rebecca",
        password="user123",
        full_name="Rebecca Dörner",
        role="user"
    )

    create_user(
        username="rohan",
        password="user123",
        full_name="Rohan Sasidharan Nair",
        role="user"
    )

def get_user_by_username(username):
    """
    Fetch one active user from the database using the username.

    Parameters
    ----------
    username : str
        Username entered in the login form.

    Returns
    -------
    sqlite3.Row or None
        Returns the user row if the username exists and the user is active.
        Returns None if no matching active user is found.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            user_id,
            username,
            password_hash,
            full_name,
            role,
            is_active,
            created_at
        FROM users
        WHERE username = ?
        AND is_active = 1
        """,
        (username,)
    )

    user = cursor.fetchone()

    connection.close()

    return user

def count_active_users():
    """
    Count all active users in the database.

    Returns
    -------
    int
        Number of active users.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS total_users
        FROM users
        WHERE is_active = 1
        """
    )

    result = cursor.fetchone()
    connection.close()

    return result["total_users"]

def get_active_users():
    """
    Fetch all active users from the database.

    Returns
    -------
    list
        A list of active users.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            user_id,
            username,
            full_name,
            role,
            created_at
        FROM users
        WHERE is_active = 1
        ORDER BY user_id
        """
    )

    users = cursor.fetchall()
    connection.close()

    return users

def get_all_users():
    """
    Fetch all users from the database, including active and inactive users.

    Returns
    -------
    list
        A list of users with their active/inactive status.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            user_id,
            username,
            full_name,
            role,
            is_active,
            created_at
        FROM users
        ORDER BY user_id
        """
    )

    users = cursor.fetchall()
    connection.close()

    return users


def update_user_active_status(user_id, is_active):
    """
    Update whether a user account is active or inactive.

    Parameters
    ----------
    user_id : int
        ID of the user to update.
    is_active : bool
        True means active.
        False means inactive.

    Returns
    -------
    bool
        True if the user status was updated.
        False if no matching user was found.
    """
    connection = get_connection()
    cursor = connection.cursor()

    active_value = 1 if is_active else 0

    cursor.execute(
        """
        UPDATE users
        SET is_active = ?
        WHERE user_id = ?
        """,
        (active_value, user_id)
    )

    connection.commit()

    user_updated = cursor.rowcount == 1

    connection.close()

    return user_updated

def deactivate_user(user_id):
    """
    Deactivate a user account.

    The user is not deleted from the database.
    Instead, is_active is set to 0.

    Parameters
    ----------
    user_id : int
        ID of the user to deactivate.

    Returns
    -------
    bool
        True if a user was deactivated.
        False if no matching user was found.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET is_active = 0
        WHERE user_id = ?
        """,
        (user_id,)
    )

    connection.commit()

    user_deactivated = cursor.rowcount == 1

    connection.close()

    return user_deactivated

def log_activity(
    category,
    action,
    actor_user_id=None,
    actor_username=None,
    target_type=None,
    target_id=None,
    target_name=None,
    details=None,
):
    """
    Insert a new activity log entry into the database.

    Parameters
    ----------
    category : str
        Log category, for example:
        admin_user_management, analysis_tracking, file_uploads, exports_backups

    action : str
        Specific action performed, for example:
        user_created, user_activated, user_deactivated

    actor_user_id : int, optional
        User ID of the person who performed the action.

    actor_username : str, optional
        Username of the person who performed the action.

    target_type : str, optional
        Type of object affected, for example: user, test, file, backup.

    target_id : int, optional
        ID of the affected object.

    target_name : str, optional
        Human-readable name of the affected object.

    details : str, optional
        Extra description of the activity.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO activity_logs (
            category,
            action,
            actor_user_id,
            actor_username,
            target_type,
            target_id,
            target_name,
            details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            category,
            action,
            actor_user_id,
            actor_username,
            target_type,
            target_id,
            target_name,
            details,
        )
    )

    connection.commit()
    connection.close()


def get_activity_logs_by_category(category):
    """
    Fetch activity logs for a specific category.

    Parameters
    ----------
    category : str
        Log category to filter by.

    Returns
    -------
    list
        Activity log rows for the selected category.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            log_id,
            category,
            action,
            actor_user_id,
            actor_username,
            target_type,
            target_id,
            target_name,
            details,
            created_at
        FROM activity_logs
        WHERE category = ?
        ORDER BY created_at DESC, log_id DESC
        """,
        (category,)
    )

    logs = cursor.fetchall()
    connection.close()

    return logs

# ---------------------------------------------------------
# Database initialization
# ---------------------------------------------------------
def initialize_database():
    """
    Create the required database tables if they do not already exist.
    For now, we only create the users table.
    Later, we will add tables for tests, statistics, and recovery results.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_user_id INTEGER,
            actor_username TEXT,
            target_type TEXT,
            target_id INTEGER,
            target_name TEXT,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ---------------------------------------------------------
    # Chambers table
    # ---------------------------------------------------------
    # This table stores the available metabolic chambers.
    #
    # Example:
    #   chamber_code = "m1"  → Chamber 1
    #   chamber_code = "m2"  → Chamber 2
    #
    # The chamber_code is important because we will later detect
    # the chamber automatically from uploaded file names such as:
    #   200930_propane_10h#1_m2_extracted.txt
    #
    # is_active allows the admin to temporarily disable a chamber
    # without deleting it from the database.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chambers (
            chamber_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chamber_code TEXT NOT NULL UNIQUE,
            chamber_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ---------------------------------------------------------
    # Analysis settings table
    # ---------------------------------------------------------
    # This table stores editable scientific and analysis settings.
    #
    # We use a flexible key-value style table instead of creating
    # many separate columns. This makes it easier to add new settings
    # later without changing the database structure.
    #
    # setting_group examples:
    #   calculation_constant
    #   trim_setting
    #   quality_threshold
    #
    # setting_key examples:
    #   propane_molar_mass_g_mol
    #   trim_start_min
    #   green_limit_percent
    #
    # setting_value is stored as REAL because most values are numeric.
    #
    # is_editable controls whether the admin is allowed to edit the value
    # from the Streamlit interface.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_settings (
            setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_group TEXT NOT NULL,
            setting_key TEXT NOT NULL UNIQUE,
            setting_label TEXT NOT NULL,
            setting_value REAL NOT NULL,
            unit TEXT,
            description TEXT,
            is_editable INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.commit()
    connection.close()

def create_default_chambers():
    """
    Create default chamber records if they do not already exist.

    The metabolic chamber is detected from the uploaded file name.
    For example:
        200930_propane_10h#1_m2_extracted.txt

    In this file name, "m2" indicates Chamber 2.

    We insert the default chambers only once. The SQL command
    'INSERT OR IGNORE' prevents duplicate entries if the app is
    restarted multiple times.
    """
    connection = get_connection()
    cursor = connection.cursor()

    default_chambers = [
        {
            "chamber_code": "m1",
            "chamber_name": "Chamber 1",
            "notes": "Default metabolic chamber 1",
        },
        {
            "chamber_code": "m2",
            "chamber_name": "Chamber 2",
            "notes": "Default metabolic chamber 2",
        },
    ]

    for chamber in default_chambers:
        cursor.execute(
            """
            INSERT OR IGNORE INTO chambers (
                chamber_code,
                chamber_name,
                is_active,
                notes
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                chamber["chamber_code"],
                chamber["chamber_name"],
                1,
                chamber["notes"],
            ),
        )

    connection.commit()
    connection.close()

def create_default_analysis_settings():
    """
    Create the default propane analysis settings.

    These settings are inserted only once. If the admin later edits
    a value from the app, the edited value will remain unchanged.

    The settings are grouped into:

    1. calculation_constant
       Scientific constants used for propane combustion calculations.

    2. trim_setting
       The number of minutes removed from the beginning and end
       of the measurement file before analysis.

    3. quality_threshold
       Percentage deviation limits used to assign colour categories
       to recovery values.
    """
    connection = get_connection()
    cursor = connection.cursor()

    default_settings = [
        # -----------------------------------------------------
        # Propane combustion constants
        # -----------------------------------------------------
        {
            "setting_group": "calculation_constant",
            "setting_key": "propane_molar_mass_g_mol",
            "setting_label": "Propane molar mass",
            "setting_value": 44.0,
            "unit": "g/mol",
            "description": "Molar mass of propane used for SOLL VO₂ and SOLL VCO₂ calculations.",
        },
        {
            "setting_group": "calculation_constant",
            "setting_key": "molar_volume_l_mol",
            "setting_label": "Molar volume",
            "setting_value": 22.4,
            "unit": "L/mol",
            "description": "Molar gas volume used in the propane combustion calculation.",
        },
        {
            "setting_group": "calculation_constant",
            "setting_key": "o2_stoichiometric_factor",
            "setting_label": "O₂ stoichiometric factor",
            "setting_value": 5.0,
            "unit": "-",
            "description": "Moles of O₂ consumed per mole of propane.",
        },
        {
            "setting_group": "calculation_constant",
            "setting_key": "co2_stoichiometric_factor",
            "setting_label": "CO₂ stoichiometric factor",
            "setting_value": 3.0,
            "unit": "-",
            "description": "Moles of CO₂ produced per mole of propane.",
        },
        {
            "setting_group": "calculation_constant",
            "setting_key": "expected_rq",
            "setting_label": "Expected RQ",
            "setting_value": 0.6,
            "unit": "-",
            "description": "Expected respiratory quotient for propane combustion.",
        },

        # -----------------------------------------------------
        # Trim settings
        # -----------------------------------------------------
        {
            "setting_group": "trim_setting",
            "setting_key": "trim_start_min",
            "setting_label": "Exclude first minutes",
            "setting_value": 10.0,
            "unit": "min",
            "description": "Warm-up period removed from the beginning of the test.",
        },
        {
            "setting_group": "trim_setting",
            "setting_key": "trim_end_min",
            "setting_label": "Exclude last minutes",
            "setting_value": 11.0,
            "unit": "min",
            "description": "Cool-down period removed from the end of the test.",
        },

        # -----------------------------------------------------
        # Quality thresholds
        # -----------------------------------------------------
        {
            "setting_group": "quality_threshold",
            "setting_key": "green_limit_percent",
            "setting_label": "Green deviation limit",
            "setting_value": 1.0,
            "unit": "%",
            "description": "Deviation up to this value is classified as green.",
        },
        {
            "setting_group": "quality_threshold",
            "setting_key": "yellow_limit_percent",
            "setting_label": "Yellow deviation limit",
            "setting_value": 3.0,
            "unit": "%",
            "description": "Deviation up to this value is classified as yellow.",
        },
        {
            "setting_group": "quality_threshold",
            "setting_key": "orange_limit_percent",
            "setting_label": "Orange deviation limit",
            "setting_value": 5.0,
            "unit": "%",
            "description": "Deviation up to this value is classified as orange. Values above this are red.",
        },
    ]

    for setting in default_settings:
        cursor.execute(
            """
            INSERT OR IGNORE INTO analysis_settings (
                setting_group,
                setting_key,
                setting_label,
                setting_value,
                unit,
                description,
                is_editable
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                setting["setting_group"],
                setting["setting_key"],
                setting["setting_label"],
                setting["setting_value"],
                setting["unit"],
                setting["description"],
                1,
            ),
        )

    connection.commit()
    connection.close()

def get_all_chambers():
    """
    Return all chambers from the database.

    This function is used by the admin Analysis Settings page.
    It returns both active and inactive chambers so the admin can
    reactivate a chamber if needed.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            chamber_id,
            chamber_code,
            chamber_name,
            is_active,
            notes,
            created_at,
            updated_at
        FROM chambers
        ORDER BY chamber_id
        """
    )

    chambers = cursor.fetchall()
    connection.close()

    return chambers


def update_chamber(chamber_id, chamber_name, is_active, notes):
    """
    Update an existing chamber record.

    Parameters
    ----------
    chamber_id : int
        The database ID of the chamber.

    chamber_name : str
        The display name of the chamber.

    is_active : bool
        True means the chamber can be used for analysis.
        False means the chamber is disabled.

    notes : str
        Optional admin notes about the chamber.

    Returns
    -------
    bool
        True if the chamber was updated successfully.
        False if no matching chamber was found.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE chambers
        SET
            chamber_name = ?,
            is_active = ?,
            notes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE chamber_id = ?
        """,
        (
            chamber_name,
            1 if is_active else 0,
            notes,
            chamber_id,
        ),
    )

    updated = cursor.rowcount == 1

    connection.commit()
    connection.close()

    return updated


def get_analysis_settings_by_group(setting_group):
    """
    Return all analysis settings for one setting group.

    Examples of setting groups:
        calculation_constant
        trim_setting
        quality_threshold

    This keeps the admin interface simple because each subtab can
    request only the settings it needs to display.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            setting_id,
            setting_group,
            setting_key,
            setting_label,
            setting_value,
            unit,
            description,
            is_editable,
            created_at,
            updated_at
        FROM analysis_settings
        WHERE setting_group = ?
        ORDER BY setting_id
        """,
        (setting_group,),
    )

    settings = cursor.fetchall()
    connection.close()

    return settings


def update_analysis_setting(setting_id, setting_value):
    """
    Update the numeric value of one analysis setting.

    Only the value is editable from the admin page.
    The setting_key and setting_label stay fixed because the analysis
    code will later depend on those exact keys.

    Parameters
    ----------
    setting_id : int
        The database ID of the setting.

    setting_value : float
        The new numeric setting value.

    Returns
    -------
    bool
        True if the setting was updated successfully.
        False if no editable setting matched the ID.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE analysis_settings
        SET
            setting_value = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE setting_id = ?
        AND is_editable = 1
        """,
        (
            setting_value,
            setting_id,
        ),
    )

    updated = cursor.rowcount == 1

    connection.commit()
    connection.close()

    return updated

def add_chamber(chamber_code, chamber_name, notes=""):
    """
    Add a new chamber to the database.

    Parameters
    ----------
    chamber_code : str
        Short code used to detect the chamber from uploaded filenames.

        Examples:
            m1
            m2
            m3

        If a file name contains '_m2_', the app can later connect
        that file to the chamber with chamber_code = 'm2'.

    chamber_name : str
        Human-readable name displayed in the app.

        Example:
            Chamber 2

    notes : str
        Optional admin notes about the chamber.

    Returns
    -------
    bool
        True if the chamber was created successfully.
        False if the chamber_code already exists.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO chambers (
            chamber_code,
            chamber_name,
            is_active,
            notes
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            chamber_code,
            chamber_name,
            1,
            notes,
        ),
    )

    created = cursor.rowcount == 1

    connection.commit()
    connection.close()

    return created

def add_analysis_setting(
    setting_group,
    setting_key,
    setting_label,
    setting_value,
    unit="",
    description="",
):
    """
    Add a new analysis setting to the database.

    Parameters
    ----------
    setting_group : str
        The group/category of the setting.

        Examples:
            calculation_constant
            trim_setting
            quality_threshold

    setting_key : str
        Internal machine-readable key.

        Examples:
            expected_rq
            trim_start_min
            green_limit_percent

        This must be unique because the analysis code will later use
        setting_key to find specific values.

    setting_label : str
        Human-readable name shown in the admin interface.

    setting_value : float
        Numeric value of the setting.

    unit : str
        Unit shown in the admin interface.

        Examples:
            g/mol
            L/mol
            min
            %

    description : str
        Explanation of what the setting is used for.

    Returns
    -------
    bool
        True if the setting was created successfully.
        False if the setting_key already exists.
    """
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO analysis_settings (
            setting_group,
            setting_key,
            setting_label,
            setting_value,
            unit,
            description,
            is_editable
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            setting_group,
            setting_key,
            setting_label,
            setting_value,
            unit,
            description,
            1,
        ),
    )

    created = cursor.rowcount == 1

    connection.commit()
    connection.close()

    return created

def setup_database():
    """
    Set up the complete application database.

    This function is called once when the Streamlit app starts.

    It performs four steps:

    1. Creates all required database tables if they do not exist.
    2. Creates default login users.
    3. Creates default chambers such as m1 and m2.
    4. Creates default propane analysis settings.

    The default insert functions use INSERT OR IGNORE, so calling this
    function every time the app starts will not create duplicate records.
    """
    initialize_database()
    create_analysis_reports_table()

    create_default_users()
    create_default_chambers()
    create_default_analysis_settings()

def delete_analysis_setting(setting_id):
    """
    Delete one analysis setting from the database.

    Parameters
    ----------
    setting_id : int
        The database ID of the setting to delete.

    Returns
    -------
    bool
        True if one setting was deleted.
        False if no matching setting was found.
    """
    conn = sqlite3.connect("database/chambercal.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM analysis_settings
        WHERE setting_id = ?
        """,
        (setting_id,),
    )

    conn.commit()

    deleted = cursor.rowcount > 0

    conn.close()

    return deleted

def delete_chamber(chamber_id):
    """
    Delete one chamber from the database.

    Parameters
    ----------
    chamber_id : int
        The database ID of the chamber to delete.

    Returns
    -------
    bool
        True if one chamber was deleted.
        False if no matching chamber was found.
    """
    conn = sqlite3.connect("database/chambercal.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM chambers
        WHERE chamber_id = ?
        """,
        (chamber_id,),
    )

    conn.commit()

    deleted = cursor.rowcount > 0

    conn.close()

    return deleted

def create_analysis_reports_table():
    """
    Create the analysis_reports table.

    This table stores one row for each completed propane analysis.

    Why this table is needed
    ------------------------
    The user dashboard needs historical information such as:
        - previous files analysed
        - VO2 recovery trend
        - VCO2 recovery trend
        - average burning rate
        - average duration
        - quality category history

    The Reports tab also needs this table to show saved reports.

    Some detailed information is stored as JSON text:
        - statistics_json
        - settings_snapshot_json

    This keeps the database simple while still allowing us to save
    detailed report information.
    """
    conn = sqlite3.connect("database/chambercal.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            file_name TEXT NOT NULL,

            chamber_id INTEGER,
            chamber_code TEXT,
            chamber_name TEXT,

            analysed_at TEXT DEFAULT CURRENT_TIMESTAMP,

            start_time TEXT,

            total_duration_min REAL,
            analysed_duration_min REAL,

            propane_before_g REAL,
            propane_after_g REAL,
            propane_burned_g REAL,
            burning_rate_g_min REAL,

            flow_rate_l_min REAL,

            vo2_soll_l REAL,
            vo2_ist_l REAL,
            vo2_recovery_percent REAL,
            vo2_deviation_percent REAL,
            vo2_quality TEXT,

            vco2_soll_l REAL,
            vco2_ist_l REAL,
            vco2_recovery_percent REAL,
            vco2_deviation_percent REAL,
            vco2_quality TEXT,

            rq_expected REAL,
            rq_measured REAL,

            overall_quality TEXT,

            statistics_json TEXT,
            settings_snapshot_json TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()

def save_analysis_report(report_data):
    """
    Save one completed propane analysis report.

    Parameters
    ----------
    report_data : dict
        Dictionary containing the final calculated analysis result.

    Returns
    -------
    int
        The report_id of the newly saved report.
    """
    conn = sqlite3.connect("database/chambercal.db")
    cursor = conn.cursor()

    statistics_json = json.dumps(
        report_data.get("statistics", {}),
        ensure_ascii=False,
    )

    settings_snapshot_json = json.dumps(
        report_data.get("settings_snapshot", {}),
        ensure_ascii=False,
    )

    cursor.execute(
        """
        INSERT INTO analysis_reports (
            user_id,
            file_name,

            chamber_id,
            chamber_code,
            chamber_name,

            analysed_at,
            start_time,

            total_duration_min,
            analysed_duration_min,

            propane_before_g,
            propane_after_g,
            propane_burned_g,
            burning_rate_g_min,

            flow_rate_l_min,

            vo2_soll_l,
            vo2_ist_l,
            vo2_recovery_percent,
            vo2_deviation_percent,
            vo2_quality,

            vco2_soll_l,
            vco2_ist_l,
            vco2_recovery_percent,
            vco2_deviation_percent,
            vco2_quality,

            rq_expected,
            rq_measured,

            overall_quality,

            statistics_json,
            settings_snapshot_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report_data.get("user_id"),
            report_data.get("file_name"),

            report_data.get("chamber_id"),
            report_data.get("chamber_code"),
            report_data.get("chamber_name"),

            report_data.get("analysed_at"),
            report_data.get("start_time"),

            report_data.get("total_duration_min"),
            report_data.get("analysed_duration_min"),

            report_data.get("propane_before_g"),
            report_data.get("propane_after_g"),
            report_data.get("propane_burned_g"),
            report_data.get("burning_rate_g_min"),

            report_data.get("flow_rate_l_min"),

            report_data.get("vo2_soll_l"),
            report_data.get("vo2_ist_l"),
            report_data.get("vo2_recovery_percent"),
            report_data.get("vo2_deviation_percent"),
            report_data.get("vo2_quality"),

            report_data.get("vco2_soll_l"),
            report_data.get("vco2_ist_l"),
            report_data.get("vco2_recovery_percent"),
            report_data.get("vco2_deviation_percent"),
            report_data.get("vco2_quality"),

            report_data.get("rq_expected"),
            report_data.get("rq_measured"),

            report_data.get("overall_quality"),

            statistics_json,
            settings_snapshot_json,
        ),
    )

    conn.commit()

    report_id = cursor.lastrowid

    conn.close()

    return report_id

def delete_sample_analysis_reports_for_user(user_id):
    """
    Delete temporary sample reports for one user.

    This is only used while developing the dashboard.

    We identify sample reports by filenames that start with:
        sample_

    Parameters
    ----------
    user_id : int
        The logged-in user's ID.

    Returns
    -------
    int
        Number of sample reports deleted.
    """
    conn = sqlite3.connect("database/chambercal.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM analysis_reports
        WHERE user_id = ?
        AND file_name LIKE 'sample_%'
        """,
        (user_id,),
    )

    conn.commit()

    deleted_count = cursor.rowcount

    conn.close()

    return deleted_count

def get_analysis_reports_for_user(user_id, from_date=None, to_date=None, chamber_id=None):
    """
    Fetch saved analysis reports for one user.

    Parameters
    ----------
    user_id : int
        The logged-in user's ID.

    from_date : date or str, optional
        Start date for filtering reports.

    to_date : date or str, optional
        End date for filtering reports.

    chamber_id : int, optional
        If provided, only reports from this chamber are returned.

    Returns
    -------
    list
        A list of sqlite3.Row objects.
    """
    conn = sqlite3.connect("database/chambercal.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT *
        FROM analysis_reports
        WHERE user_id = ?
    """

    params = [user_id]

    if from_date is not None:
        query += " AND DATE(analysed_at) >= DATE(?)"
        params.append(str(from_date))

    if to_date is not None:
        query += " AND DATE(analysed_at) <= DATE(?)"
        params.append(str(to_date))

    if chamber_id is not None:
        query += " AND chamber_id = ?"
        params.append(chamber_id)

    query += " ORDER BY analysed_at ASC"

    cursor.execute(query, params)

    reports = cursor.fetchall()

    conn.close()

    return reports