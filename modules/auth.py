from modules.db import get_user_by_username, verify_password


def authenticate_user(username, password):
    """
    Authenticate a user using the SQLite database.

    Parameters
    ----------
    username : str
        Username entered in the login form.
    password : str
        Password entered in the login form.

    Returns
    -------
    dict or None
        Returns user information if login is successful.
        Returns None if login fails.
    """
    user = get_user_by_username(username)

    if user is None:
        return None

    if verify_password(password, user["password_hash"]):
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "name": user["full_name"],
            "role": user["role"]
        }

    return None