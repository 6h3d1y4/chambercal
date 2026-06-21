from pathlib import Path
import sqlite3
import hashlib
import os


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

    connection.commit()
    connection.close()

