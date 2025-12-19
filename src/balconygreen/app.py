import streamlit as st
import time
import random

st.set_page_config(page_title="Balcony Green Stream", layout="centered")

st.title("🌱 Balcony Green – Live Stream")

start = st.button("Start Stream")
stop = st.button("Stop Stream")

if "streaming" not in st.session_state:
    st.session_state.streaming = False

if start:
    st.session_state.streaming = True

if stop:
    st.session_state.streaming = False

placeholder = st.empty()

while st.session_state.streaming:
    data_point = {
        "temperature": round(random.uniform(20, 30), 2),
        "humidity": round(random.uniform(40, 70), 2),
        "soil_moisture": round(random.uniform(10, 60), 2),
    }

    placeholder.json(data_point)
    time.sleep(1)
