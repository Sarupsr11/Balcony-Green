from __future__ import annotations

import requests  # type: ignore
import streamlit as st  # type: ignore
from streamlit_cookies_manager import EncryptedCookieManager  # type: ignore

try:
    from balconygreen.settings import API_BASE_URL, COOKIE_PASSWORD
except ModuleNotFoundError:
    from settings import API_BASE_URL, COOKIE_PASSWORD  # type: ignore


cookies = EncryptedCookieManager(prefix="bg_", password=COOKIE_PASSWORD)
try:
    COOKIES_READY = cookies.ready()
except Exception:
    COOKIES_READY = False

def _ensure_session_defaults() -> None:
    if "page" not in st.session_state:
        st.session_state["page"] = "landing"
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if "guest" not in st.session_state:
        st.session_state["guest"] = False
    if "access_token" not in st.session_state:
        st.session_state["access_token"] = None


def _restore_cookie_session() -> None:
    if not COOKIES_READY:
        st.info("Session storage is still loading. The page may need one refresh before login persistence works.")
        return

    try:
        saved_token = cookies.get("jwt")
    except Exception:
        saved_token = None

    if saved_token and not st.session_state.get("guest", False):
        st.session_state["authenticated"] = True
        st.session_state["access_token"] = saved_token
        if st.session_state["page"] == "landing":
            st.session_state["page"] = "home"


class AuthClient:
    def __init__(self, api_url: str):
        self.api_url = api_url

    def signup(self, email: str, password: str, name: str | None):
        try:
            return requests.post(
                f"{self.api_url}/auth/signup",
                json={"email": email, "password": password, "name": name},
                timeout=5,
            )
        except requests.exceptions.RequestException as exc:
            st.error(f"Connection error: {exc}")
            return None

    def login(self, email: str, password: str):
        try:
            return requests.post(
                f"{self.api_url}/auth/login",
                json={"email": email, "password": password},
                timeout=5,
            )
        except requests.exceptions.RequestException as exc:
            st.error(f"Connection error: {exc}")
            return None


auth_client = AuthClient(API_BASE_URL)


class Pages:
    def landing_page(self):
        st.title("Welcome to Balcony Green")
        choice = st.radio(
            "Proceed as:",
            ["Login", "Sign Up", "Continue without Login"],
            index=None,
            key="landing_radio",
        )

        if choice == "Login":
            st.session_state["page"] = "login"
            st.rerun()
        if choice == "Sign Up":
            st.session_state["page"] = "signup"
            st.rerun()
        if choice == "Continue without Login":
            st.session_state["guest"] = True
            st.session_state["authenticated"] = True
            st.session_state["access_token"] = None
            st.session_state["page"] = "home"
            st.rerun()

    def login_page(self):
        st.subheader("Login")
        email = st.text_input("Email", key="login_email_input")
        password = st.text_input("Password", type="password", key="login_pw_input")

        if st.button("Login", key="login_btn"):
            response = auth_client.login(email, password)
            if response and response.status_code == 200:
                token = response.json().get("access_token")
                if token:
                    if COOKIES_READY:
                        cookies["jwt"] = token
                        cookies.save()
                    st.session_state["authenticated"] = True
                    st.session_state["guest"] = False
                    st.session_state["page"] = "home"
                    st.session_state["access_token"] = token
                    st.rerun()
            else:
                st.error("Invalid credentials or server error")

        if st.button("Back", key="login_back"):
            st.session_state["page"] = "landing"
            st.rerun()

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

            response = auth_client.signup(email, password, name)
            if response and response.status_code == 200:
                st.success("Account created. Please login.")
                st.session_state["page"] = "login"
                st.rerun()

            detail = "Signup failed"
            if response is not None:
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    detail = response.text or detail
            st.error(detail)

        if st.button("Back", key="signup_back"):
            st.session_state["page"] = "landing"
            st.rerun()

    def dashboard(self):
        try:
            from balconygreen.dashboard import main_page
        except ModuleNotFoundError:
            from dashboard import main_page  # type: ignore

        main_page(
            access=None if st.session_state.get("guest", False) else st.session_state["access_token"]
        )

        if st.session_state.get("guest", False):
            if st.button("Sign in option", key="guest_btn"):
                st.session_state["page"] = "landing"
                st.rerun()
        else:
            if st.button("Logout", key="logout_btn"):
                if COOKIES_READY:
                    cookies["jwt"] = ""
                    cookies.save()
                st.session_state["authenticated"] = False
                st.session_state["guest"] = False
                st.session_state["access_token"] = None
                st.session_state["page"] = "landing"
                st.rerun()


def render_app() -> None:
    _ensure_session_defaults()
    _restore_cookie_session()
    pages = Pages()

    if st.session_state["page"] == "landing":
        pages.landing_page()
    elif st.session_state["page"] == "login":
        pages.login_page()
    elif st.session_state["page"] == "signup":
        pages.signup_page()
    elif st.session_state["page"] == "home":
        pages.dashboard()
