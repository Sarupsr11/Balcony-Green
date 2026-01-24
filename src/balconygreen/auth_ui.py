# auth_ui_oop_fixed.py
import streamlit as st # type: ignore
import requests # type: ignore
from streamlit_cookies_manager import EncryptedCookieManager # type: ignore

API_URL = "http://localhost:8000"

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

    def signup(self, email, password, name):
        try:
            return requests.post(f"{self.api_url}/auth/signup",
                                 json={"email": email, "password": password, "name": name})
        except requests.exceptions.RequestException as e:
            st.error(f"Connection error: {e}")
            return None

    def login(self, email, password):
        try:
            return requests.post(f"{self.api_url}/auth/login",
                                 json={"email": email, "password": password})
        except requests.exceptions.RequestException as e:
            st.error(f"Connection error: {e}")
            return None

auth_client = AuthClient(API_URL)

# -------------------------
# Pages Controller
# -------------------------
class Pages:
    # -------------------------
    # Landing Page
    # -------------------------
    def landing_page(self):
        st.title("🌱 Welcome to Balcony Green")

        # Radio options without default selection
        choice = st.radio(
            "Proceed as:",
            ["Login", "Sign Up", "Continue without Login"],
            index=None,  # <- ensures no option is selected initially
            key="landing_radio"
        )

        # Only navigate when user actively selects an option
        if choice:
            if choice == "Login":
                st.session_state["page"] = "login"
                
            elif choice == "Sign Up":
                st.session_state["page"] = "signup"
                
            elif choice == "Continue without Login":
                st.session_state["guest"] = True
                st.session_state["authenticated"] = True
                st.session_state["page"] = "home"
                

            
    # -------------------------
    # Login Page
    # -------------------------
    def login_page(self):
        st.subheader("Login")
        email = st.text_input("Email", key="login_email_input")
        password = st.text_input("Password", type="password", key="login_pw_input")

        if st.button("Login", key="login_btn"):
            r = auth_client.login(email, password)
            if r and r.status_code == 200:
                data = r.json()
                token = data.get("access_token")
                if token:
                    cookies["jwt"] = token
                    cookies.save()
                    st.session_state["authenticated"] = True
                    st.session_state["guest"] = False
                    st.session_state["page"] = "home"
                    st.session_state["access_token"] = token
                    
            else:
                st.error("Invalid credentials or server error")

        if st.button("⬅ Back", key="login_back"):
            st.session_state["page"] = "landing"
            

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
                
            else:
                st.error(r.json().get("detail", "Signup failed"))

        if st.button("⬅ Back", key="signup_back"):
            st.session_state["page"] = "landing"
            

    # -------------------------
    # Dashboard Page
    # -------------------------
    def dashboard(self):
        from dashboard import main_page
        main_page(
            access = None if st.session_state.get("guest", False) else st.session_state["access_token"]
        )

        if st.session_state.get("guest", False):
            if st.button("🔹 Sign in option", key="guest_btn"):
                st.session_state["page"] = "landing"
                
                # Optional: navigate or refresh dashboard if needed
        else:
            if st.button("Logout", key="logout_btn"):
                cookies["jwt"] = ""
                cookies.save()
                st.session_state["authenticated"] = False
                st.session_state["guest"] = False
                st.session_state["page"] = "landing"
            
# -------------------------
# Router
# -------------------------
pages = Pages()

if st.session_state["page"] == "landing":
    pages.landing_page()
elif st.session_state["page"] == "login":
    pages.login_page()
elif st.session_state["page"] == "signup":
    pages.signup_page()
elif st.session_state["page"] == "home":
    pages.dashboard()
