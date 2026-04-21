from __future__ import annotations

import requests  # type: ignore
import streamlit as st  # type: ignore
from streamlit_cookies_manager import EncryptedCookieManager  # type: ignore

try:
    from balconygreen.settings import API_BASE_URL, COOKIE_PASSWORD
except ModuleNotFoundError:
    from settings import API_BASE_URL, COOKIE_PASSWORD  # type: ignore


def _ensure_session_defaults() -> None:
    defaults = {
        "page": "landing",
        "authenticated": False,
        "guest": False,
        "access_token": None,
        "open_device_setup": False,
        "open_health_upload": False,
        "_pending_cookie_write": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _build_cookie_manager() -> EncryptedCookieManager:
    return EncryptedCookieManager(prefix="bg_", password=COOKIE_PASSWORD)


def _cookies_ready(cookies: EncryptedCookieManager) -> bool:
    try:
        return bool(cookies.ready())
    except Exception:
        return False


def _persist_cookie_token(cookies: EncryptedCookieManager, token: str) -> bool:
    if not _cookies_ready(cookies):
        st.session_state["_pending_cookie_write"] = token
        return False

    try:
        cookies["jwt"] = token
        cookies.save()
    except Exception:
        st.session_state["_pending_cookie_write"] = token
        return False

    st.session_state["_pending_cookie_write"] = None
    return True


def _flush_pending_cookie_write(cookies: EncryptedCookieManager) -> bool:
    pending_token = st.session_state.get("_pending_cookie_write")
    if pending_token is None:
        return True
    return _persist_cookie_token(cookies, str(pending_token))


def _restore_cookie_session(cookies: EncryptedCookieManager) -> None:
    if not _cookies_ready(cookies):
        st.info("Session storage is loading. Refresh once if login persistence does not appear yet.")
        return

    _flush_pending_cookie_write(cookies)

    try:
        saved_token = cookies.get("jwt")
    except Exception:
        saved_token = None

    if saved_token:
        st.session_state["authenticated"] = True
        st.session_state["guest"] = False
        st.session_state["access_token"] = saved_token
        if st.session_state["page"] == "landing":
            st.session_state["page"] = "home"


def _set_logged_out_state(next_page: str = "login") -> None:
    st.session_state["authenticated"] = False
    st.session_state["guest"] = False
    st.session_state["access_token"] = None
    st.session_state["page"] = next_page


class AuthClient:
    def __init__(self, api_url: str):
        self.api_url = api_url

    def signup(self, username: str, password: str, name: str | None):
        try:
            return requests.post(
                f"{self.api_url}/auth/signup",
                json={"username": username, "password": password, "name": name},
                timeout=5,
            )
        except requests.exceptions.RequestException as exc:
            st.error(f"Connection error: {exc}")
            return None

    def login(self, username: str, password: str):
        try:
            return requests.post(
                f"{self.api_url}/auth/login",
                json={"username": username, "password": password},
                timeout=5,
            )
        except requests.exceptions.RequestException as exc:
            st.error(f"Connection error: {exc}")
            return None


auth_client = AuthClient(API_BASE_URL)


def _inject_auth_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stDecoration"] {display: none;}
        header[data-testid="stHeader"] {background: transparent;}
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(48, 102, 66, 0.16), transparent 28%),
                linear-gradient(180deg, #0b0d12 0%, #0d1118 100%);
        }
        [data-testid="stSidebar"] {background: #11151d;}
        .block-container {max-width: 1150px; padding-top: 1.1rem; padding-bottom: 2rem;}
        .landing-hero {
            border: 1px solid rgba(255,255,255,0.08);
            background: linear-gradient(180deg, rgba(14,18,25,0.96), rgba(18,21,30,0.94));
            border-radius: 26px;
            padding: 1.6rem 1.8rem;
            margin-bottom: 1.2rem;
            box-shadow: 0 18px 40px rgba(0,0,0,0.28);
        }
        .landing-title {
            font-size: 3rem;
            line-height: 1.08;
            font-weight: 820;
            color: #f6f7fb;
            margin: 0 0 0.4rem 0;
        }
        .landing-subtitle {
            font-size: 1.15rem;
            color: #f6f7fb;
            font-weight: 700;
            margin: 1.3rem 0 0.35rem 0;
        }
        .landing-muted {
            color: #b9bfcb;
            font-size: 1rem;
            margin: 0;
        }
        .landing-card {
            border: 1px solid rgba(255,255,255,0.08);
            background: #12161f;
            border-radius: 22px;
            padding: 0.9rem 1rem;
            margin-top: 0.85rem;
        }
        .landing-option {
            color: #f2f4f8;
            font-size: 1.05rem;
            font-weight: 650;
            padding: 0.7rem 0.35rem;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .landing-option:last-child {border-bottom: 0;}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div {
            background: #232632;
            border-color: rgba(232, 77, 77, 0.9);
            border-radius: 16px;
            min-height: 3.35rem;
        }
        .stButton > button {
            border-radius: 12px;
            border: 0;
            background: #21a9f5;
            color: white;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


class Pages:
    def __init__(self, cookies: EncryptedCookieManager):
        self.cookies = cookies

    def landing_page(self):
        st.markdown(
            """
            <div class="landing-hero">
                <div class="landing-title">🌱 Balcony Green</div>
                <div class="landing-subtitle">Smart Plant Monitor</div>
                <p class="landing-muted">Monitor your balcony garden, detect plant diseases, and track watering schedules.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Sign Up", key="landing_signup_btn", use_container_width=True):
                st.session_state["page"] = "signup"
                st.rerun()
        with col2:
            if st.button("Login", key="landing_login_btn", use_container_width=True):
                st.session_state["page"] = "login"
                st.rerun()
        with col3:
            if st.button("Continue without Login", key="landing_guest_btn", use_container_width=True):
                st.session_state["guest"] = True
                st.session_state["authenticated"] = True
                st.session_state["access_token"] = None
                st.session_state["page"] = "home"
                st.rerun()

    def login_page(self):
        st.subheader("Login")
        username = st.text_input("Username", key="login_username_input")
        password = st.text_input("Password", type="password", key="login_pw_input")

        if st.button("Login", key="login_btn"):
            response = auth_client.login(username, password)
            if response and response.status_code == 200:
                token = response.json().get("access_token")
                if token:
                    _persist_cookie_token(self.cookies, token)
                    st.session_state["authenticated"] = True
                    st.session_state["guest"] = False
                    st.session_state["page"] = "home"
                    st.session_state["access_token"] = token
                    st.rerun()
            elif response is not None:
                detail = "Invalid credentials or server error"
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    detail = response.text or detail
                st.error(detail)

        if st.button("Back", key="login_back"):
            st.session_state["page"] = "landing"
            st.rerun()

        if st.button("Create Account", key="login_signup"):
            st.session_state["page"] = "signup"
            st.rerun()

    def signup_page(self):
        st.subheader("Sign Up")
        username = st.text_input("Username", key="signup_username_input")
        name = st.text_input("Name (optional)", key="signup_name_input")
        password = st.text_input("Password", type="password", key="signup_pw_input")
        confirm = st.text_input("Confirm Password", type="password", key="signup_pw2_input")

        if st.button("Create Account", key="signup_btn"):
            if password != confirm:
                st.error("Passwords do not match")
                return

            response = auth_client.signup(username, password, name)
            if response and response.status_code == 200:
                st.success("Account created. Please login.")
                st.session_state["page"] = "login"
                st.rerun()
            elif response is not None:
                detail = "Signup failed"
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

        with st.sidebar:
            st.markdown("---")
            if st.session_state.get("guest", False):
                if st.button("Login / Sign Up", key="guest_btn", use_container_width=True):
                    st.session_state["page"] = "login"
                    st.rerun()
            else:
                if st.button("Logout", key="logout_btn", use_container_width=True):
                    _persist_cookie_token(self.cookies, "")
                    _set_logged_out_state(next_page="login")
                    st.rerun()


def render_app() -> None:
    _ensure_session_defaults()
    cookies = _build_cookie_manager()
    _restore_cookie_session(cookies)
    _inject_auth_styles()
    pages = Pages(cookies)

    if st.session_state["page"] == "home" and not (
        st.session_state.get("authenticated", False) or st.session_state.get("guest", False)
    ):
        st.session_state["page"] = "landing"

    if st.session_state["page"] == "landing":
        pages.landing_page()
    elif st.session_state["page"] == "login":
        pages.login_page()
    elif st.session_state["page"] == "signup":
        pages.signup_page()
    elif st.session_state["page"] == "home":
        pages.dashboard()
