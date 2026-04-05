# auth_ui_oop_fixed.py
import logging
import os
import requests  # type: ignore
import streamlit as st  # type: ignore
from streamlit_cookies_manager import EncryptedCookieManager  # type: ignore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FASTAPI_URL = os.getenv("FASTAPI","https://balconygreen-production.up.railway.app")


# -------------------------
# Cookies
# -------------------------
cookies = EncryptedCookieManager(prefix="bg_", password="CHANGE_ME_TO_ENV_SECRET")
if not cookies.ready():
    st.stop()

# -------------------------
# Session State Defaults
# -------------------------
if "page" not in st.session_state:
    st.session_state["page"] = "landing"
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "guest" not in st.session_state:
    st.session_state["guest"] = False
if "access_token" not in st.session_state:
    st.session_state["access_token"] = None


# -------------------------
# Auth Client
# -------------------------
class AuthClient:
    def __init__(self, api_url: str):
        self.api_url = api_url
        logger.info(f"AuthClient initialized with API URL: {api_url}")

    def signup(self, email, password, name):
        logger.info(f"Attempting signup for: {email}")
        try:
            response = requests.post(f"{self.api_url}/auth/signup", json={"email": email, "password": password, "name": name})
            logger.debug(f"Signup response status: {response.status_code}")
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Signup connection error: {e}")
            st.error(f"Connection error: {e}")
            return None

    def login(self, email, password):
        logger.info(f"Attempting login for: {email}")
        try:
            response = requests.post(f"{self.api_url}/auth/login", json={"email": email, "password": password})
            logger.debug(f"Login response status: {response.status_code}")
            if response.status_code == 200:
                logger.info(f"Login successful for: {email}")
            else:
                logger.warning(f"Login failed for {email}: {response.status_code}")
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Login connection error: {e}")
            st.error(f"Connection error: {e}")
            return None


auth_client = AuthClient(FASTAPI_URL)


# -------------------------
# Pages Controller
# -------------------------
class Pages:
    # -------------------------
    # Landing Page
    # -------------------------
    def landing_page(self):
        logger.info("Landing page loaded")
        st.title("🌱 Welcome to Balcony Green")

        # Radio options without default selection
        choice = st.radio(
            "Proceed as:",
            ["Login", "Sign Up", "Continue without Login"],
            index=None,  # <- ensures no option is selected initially
            key="landing_radio",
        )

        # Only navigate when user actively selects an option
        if choice:
            logger.debug(f"User selected: {choice}")
            if choice == "Login":
                st.session_state["page"] = "login"
                st.rerun()

            elif choice == "Sign Up":
                st.session_state["page"] = "signup"
                st.rerun()

            elif choice == "Continue without Login":
                logger.info("User proceeding as guest")
                st.session_state["guest"] = True
                st.session_state["authenticated"] = True
                st.session_state["page"] = "home"
                st.rerun()

    # -------------------------
    # Login Page
    # -------------------------
    def login_page(self):
        logger.info("Login page loaded")
        st.subheader("Login")
        email = st.text_input("Email", key="login_email_input")
        password = st.text_input("Password", type="password", key="login_pw_input")

        if st.button("Login", key="login_btn"):
            logger.debug(f"Login button clicked for email: {email}")
            r = auth_client.login(email, password)
            if r and r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                if token:
                    logger.info(f"Login successful for {email}")
                    cookies["jwt"] = token
                    cookies.save()
                    st.session_state["authenticated"] = True
                    st.session_state["guest"] = False
                    st.session_state["page"] = "home"
                    st.session_state["access_token"] = token
                    st.rerun()

            else:
                st.error("Invalid credentials or server error")
                st.rerun()

        if st.button("⬅ Back", key="login_back"):
            st.session_state["page"] = "landing"
            st.rerun()

    # -------------------------
    # Signup Page
    # -------------------------
    def signup_page(self):
        st.subheader("Sign Up")
        email = st.text_input("Email", key="signup_email_input")
        name = st.text_input("Name (optional)", key="signup_name_input")
        password = st.text_input("Password", type="password", key="signup_pw_input")
        confirm = st.text_input("Confirm Password", type="password", key="signup_pw2_input")

        if st.button("Create Account", key="signup_btn"):
            if password != confirm:
                st.error("Passwords do not match")
                return

            r = auth_client.signup(email, password, name)
            if r and r.status_code == 200:
                st.success("Account created! Please login.")
                st.session_state["page"] = "login"
                st.rerun()

            else:
                print(r)
                st.error(r.json().get("detail", "Signup failed"))
                st.rerun()

        if st.button("⬅ Back", key="signup_back"):
            st.session_state["page"] = "landing"
            st.rerun()

    # -------------------------
    # Dashboard Page
    # -------------------------
    def dashboard(self):
        from balconygreen.frontend.home_page import main_page

        main_page(st.session_state["access_token"])

        if st.session_state.get("guest", False):
            if st.button("🔹 Sign in option", key="guest_btn"):
                st.session_state["page"] = "landing"
                st.rerun()

                # Optional: navigate or refresh dashboard if needed
        else:
            if st.button("Logout", key="logout_btn"):
                cookies["jwt"] = ""
                cookies.save()
                st.session_state["authenticated"] = False
                st.session_state["guest"] = False
                st.session_state["page"] = "landing"
                st.rerun()


# -------------------------
# Router
# -------------------------
pages = Pages()

if st.session_state["page"] == "landing":
    pages.landing_page()
if st.session_state["page"] == "login":
    pages.login_page()
if st.session_state["page"] == "signup":
    pages.signup_page()
if st.session_state["page"] == "home":
    pages.dashboard()
