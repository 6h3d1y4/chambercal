from pathlib import Path
import base64

import streamlit as st

from modules.auth import authenticate_user
from modules.dashboard import show_dashboard
from modules.db import setup_database

# ---------------------------------------------------------
# Page configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="ChamberCal",
    page_icon="🔥",
    layout="wide",
)

setup_database()

# ---------------------------------------------------------
# File paths
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "assets" / "chambercal_logo.png"

# ---------------------------------------------------------
# Helper function
# ---------------------------------------------------------

def image_to_base64(image_path):
    """
    Convert an image file into a base64 string.

    This allows us to place the logo directly inside an HTML block.
    """
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()

    return encoded_string

# ---------------------------------------------------------
# Custom styling
# ---------------------------------------------------------

st.markdown(
    """
    <style>
    .stApp {
        background-color: #FFFFFF;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    .brand-section {
        height: 78vh;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
    }

    .brand-logo {
        width: 500px;
        max-width: 90%;
        margin-bottom: 8px;
    }

    .brand-project-title {
        font-size: 24px;
        font-weight: 700;
        color: #1F2937;
        margin-top: 0px;
        margin-bottom: 10px;
    }

    .brand-description {
        font-size: 16px;
        color: #4B5563;
        margin-top: 0px;
        margin-bottom: 12px;
        max-width: 650px;
        line-height: 1.5;
    }

    .brand-authors {
        font-size: 15px;
        color: #6B7280;
        margin-top: 0px;
    }

    .login-title {
        font-size: 28px;
        font-weight: 700;
        color: #1F2937;
        margin-bottom: 10px;
    }

    div.stButton > button {
        width: 100%;
        background-color: #0EA5E9;
        color: white;
        border-radius: 8px;
        border: none;
        height: 42px;
        font-weight: 600;
    }

    div.stButton > button:hover {
        background-color: #0284C7;
        color: white;
    }
    
    /* ---------------------------------------------------------
       Tab styling
    --------------------------------------------------------- */
    
    div[data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #D1D5DB;
    }
    
    button[data-baseweb="tab"] {
        border: 1px solid #D1D5DB;
        border-bottom: none;
        border-radius: 8px 8px 0px 0px;
        padding: 10px 18px;
        background-color: #F3F4F6;
        color: #374151;
        font-weight: 600;
    }
    
    button[data-baseweb="tab"]:hover {
        background-color: #E0F2FE;
        color: #0369A1;
    }
    
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #FFFFFF;
        color: #0284C7;
        border-top: 3px solid #0EA5E9;
        border-left: 1px solid #D1D5DB;
        border-right: 1px solid #D1D5DB;
        border-bottom: 2px solid #FFFFFF;
    }
        
    </style>
    """,
    unsafe_allow_html=True
)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "name" not in st.session_state:
    st.session_state.name = None
if "role" not in st.session_state:
    st.session_state.role = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None

if st.session_state.logged_in:
    show_dashboard()
    st.stop()

# ---------------------------------------------------------
# Landing page layout
# ---------------------------------------------------------

left_col, right_col = st.columns([4, 1.2])


# ---------------------------------------------------------
# Left side: project identity
# ---------------------------------------------------------

with left_col:
    if LOGO_PATH.exists():
        logo_base64 = image_to_base64(LOGO_PATH)

        st.html(
            f"""
            <div class="brand-section">
                <img src="data:image/png;base64,{logo_base64}" class="brand-logo">

                <p class="brand-project-title">
                    Propane Combustion Test Analysis Platform
                </p>

                <p class="brand-description">
                    Developed as a project for the Applied Python Programming course provided by opencampus.sh
                </p>

                <p class="brand-authors">
                    Authors: Rebecca Dörner, Rohan Sasidharan Nair
                </p>
            </div>
            """
        )
    else:
        st.warning("Logo not found. Please check assets/chambercal_logo.png")

# ---------------------------------------------------------
# Right side: login card
# ---------------------------------------------------------

with right_col:
    st.markdown("<br><br><br><br><br>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<p class="login-title">Sign in</p>', unsafe_allow_html=True)

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        sign_in_button = st.button("Sign in")

        if sign_in_button:
            user = authenticate_user(username, password)

            if user is not None:
                st.session_state.logged_in = True
                st.session_state.user_id = user["user_id"]
                st.session_state.username = user["username"]
                st.session_state.name = user["name"]
                st.session_state.role = user["role"]
                st.rerun()
            else:
                st.error("Invalid username or password.")
        st.caption("Forgot password?")