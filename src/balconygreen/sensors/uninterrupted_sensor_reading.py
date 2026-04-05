# sensor_worker.py
import logging

from balconygreen.sensor_reading import SensorReader

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =========================
# CONFIG
# =========================

api_key = "https://api.open-meteo.com/v1/forecast"


# =========================
# MAIN LOOP
# =========================
def main():
    logger.info("🌱 Sensor worker started")

    try:
        sensor_reader = SensorReader(use_simulated=False, api_key=api_key)
        logger.info("SensorReader initialized successfully")
        sensor_reader.run_forever()
    except Exception as e:
        logger.error(f"Sensor worker error: {e}")
        raise


if __name__ == "__main__":
    main()
