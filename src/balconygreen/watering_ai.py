from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


MODEL_DIR = Path(__file__).resolve().parent / "models" / "watering_ai"


@dataclass
class WateringPrediction:
    should_water: bool
    watering_probability: float
    decision_threshold: float
    recommended_pump_ms: int
    probable_next_watering_hours: float
    reasons: list[str]
    missing_inputs: list[str]
    normalized_inputs: dict[str, float]


class WateringAIService:
    def __init__(self) -> None:
        summary_path = MODEL_DIR / "watering_ai_training_summary.json"
        should_water_path = MODEL_DIR / "watering_should_water_model.joblib"
        pump_path = MODEL_DIR / "watering_pump_ms_model.joblib"
        profiles_path = MODEL_DIR / "plant_profiles.json"

        self.summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.classifier = joblib.load(should_water_path)
        self.regressor = joblib.load(pump_path)
        self.feature_columns: list[str] = self.summary["metrics"]["feature_columns"]
        self.decision_threshold = float(self.summary["metrics"]["decision_threshold"])
        self.profiles = json.loads(profiles_path.read_text(encoding="utf-8"))

    def predict(
        self,
        sensor_readings: dict[str, Any],
        plant_type: str,
        disease_label: str = "healthy",
        disease_confidence: float = 0.0,
        history: list[dict[str, Any]] | None = None,
        feedback_rows: list[dict[str, Any]] | None = None,
        calibration: dict[str, Any] | None = None,
    ) -> WateringPrediction | None:
        history = history or []
        feedback_rows = feedback_rows or []
        payload, missing_inputs = self._build_feature_payload(
            sensor_readings,
            plant_type,
            disease_label,
            disease_confidence,
            history,
            calibration,
        )

        if payload["soil_moisture_pct"] < 0:
            return None

        frame = pd.DataFrame([payload], columns=self.feature_columns)
        watering_probability = float(self.classifier.predict_proba(frame)[:, 1][0])
        feedback_adjustment = self._derive_feedback_adjustment(plant_type, feedback_rows)
        decision_threshold = min(0.6, max(0.05, self.decision_threshold + feedback_adjustment["threshold_delta"]))
        should_water = watering_probability >= decision_threshold
        recommended_pump_ms = int(max(0, round(float(self.regressor.predict(frame)[0]) * feedback_adjustment["pump_multiplier"])))

        if not should_water and recommended_pump_ms < 500:
            recommended_pump_ms = 0
        elif should_water:
            recommended_pump_ms = max(800, recommended_pump_ms)

        probable_next_watering_hours = self._estimate_next_watering_hours(
            payload,
            plant_type,
            history,
            calibration,
        )
        probable_next_watering_hours = round(
            max(0.0, probable_next_watering_hours * feedback_adjustment["hours_multiplier"]),
            1,
        )

        reasons = self._build_reasons(payload, plant_type, disease_label, calibration)
        if feedback_adjustment["note"]:
            reasons.insert(0, feedback_adjustment["note"])

        return WateringPrediction(
            should_water=should_water,
            watering_probability=round(watering_probability, 4),
            decision_threshold=round(decision_threshold, 3),
            recommended_pump_ms=recommended_pump_ms,
            probable_next_watering_hours=probable_next_watering_hours,
            reasons=reasons,
            missing_inputs=missing_inputs,
            normalized_inputs={feature: round(float(payload[feature]), 3) for feature in self.feature_columns},
        )

    def _normalize_plant_type(self, plant_type: str) -> str:
        normalized = plant_type.strip().lower()
        aliases = {
            "tomato": "tomato_indoor",
            "basil": "basilikum",
            "mint": "houseplant_generic",
            "potato": "houseplant_generic",
            "houseplant": "houseplant_generic",
            "succulent": "succulent_cactus",
        }
        return aliases.get(normalized, normalized if normalized in self.profiles else "houseplant_generic")

    def _estimate_raw_from_moisture(self, soil_moisture_pct: float, calibration: dict[str, Any] | None = None) -> int:
        raw_wet = int((calibration or {}).get("soil_raw_wet", 1200))
        raw_dry = int((calibration or {}).get("soil_raw_dry", 3200))
        return int(round(raw_dry - ((soil_moisture_pct / 100.0) * (raw_dry - raw_wet))))

    def _safe_timestamp(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _build_feature_payload(
        self,
        sensor_readings: dict[str, Any],
        plant_type: str,
        disease_label: str,
        disease_confidence: float,
        history: list[dict[str, Any]],
        calibration: dict[str, Any] | None,
    ) -> tuple[dict[str, float], list[str]]:
        missing_inputs: list[str] = []
        raw_wet = int((calibration or {}).get("soil_raw_wet", 1200))
        raw_dry = int((calibration or {}).get("soil_raw_dry", 3200))

        temperature_c = float(sensor_readings.get("temperature_c", sensor_readings.get("temperature", 0.0)) or 0.0)
        humidity_pct = float(sensor_readings.get("humidity_pct", sensor_readings.get("humidity", 0.0)) or 0.0)
        soil_moisture_pct = sensor_readings.get("soil_moisture_pct", sensor_readings.get("soil_moisture"))
        soil_raw = sensor_readings.get("soil_raw")
        light_lux = float(sensor_readings.get("light_lux", sensor_readings.get("light", 0.0)) or 0.0)
        weather_temp_c = float(sensor_readings.get("weather_temp_c", temperature_c) or temperature_c)
        weather_humidity_pct = float(sensor_readings.get("weather_humidity_pct", humidity_pct) or humidity_pct)
        forecast_rain_mm = float(sensor_readings.get("forecast_rain_mm", 0.0) or 0.0)

        if soil_moisture_pct is None and soil_raw is None:
            missing_inputs.append("soil_moisture_pct")
            soil_moisture_pct = -1.0
        elif soil_moisture_pct is None:
            soil_raw = int(soil_raw)
            span = max(1.0, float(raw_dry - raw_wet))
            soil_moisture_pct = max(0.0, min(100.0, ((raw_dry - soil_raw) * 100.0) / span))
        else:
            soil_moisture_pct = float(soil_moisture_pct)

        if soil_raw is None and soil_moisture_pct >= 0:
            soil_raw = self._estimate_raw_from_moisture(float(soil_moisture_pct), calibration)
        soil_raw = int(soil_raw or 0)

        if light_lux <= 0:
            missing_inputs.append("light_lux")
            light_lux = 3500.0
        if temperature_c == 0:
            missing_inputs.append("temperature_c")
        if humidity_pct == 0:
            missing_inputs.append("humidity_pct")

        previous = history[-1] if history else {}
        previous_moisture = float(previous.get("soil_moisture_pct", previous.get("soil_moisture", soil_moisture_pct)) or soil_moisture_pct)
        previous_raw = int(previous.get("soil_raw", soil_raw) or soil_raw)

        timestamp_now = self._safe_timestamp(sensor_readings.get("timestamp")) or datetime.utcnow()
        timestamp_prev = self._safe_timestamp(previous.get("timestamp"))
        minutes_since_prev = (
            max(1.0, (timestamp_now - timestamp_prev).total_seconds() / 60.0)
            if timestamp_prev is not None
            else 15.0
        )

        last_four = history[-4:] if len(history) >= 4 else history
        last_eight = history[-8:] if len(history) >= 8 else history
        moisture_1h_delta = soil_moisture_pct - float(last_four[0].get("soil_moisture_pct", last_four[0].get("soil_moisture", soil_moisture_pct))) if last_four else 0.0
        raw_1h_delta = soil_raw - int(last_four[0].get("soil_raw", soil_raw)) if last_four else 0.0
        moisture_2h_delta = soil_moisture_pct - float(last_eight[0].get("soil_moisture_pct", last_eight[0].get("soil_moisture", soil_moisture_pct))) if last_eight else 0.0

        hour = timestamp_now.hour + timestamp_now.minute / 60.0
        hour_sin = math.sin(2 * math.pi * hour / 24.0)
        hour_cos = math.cos(2 * math.pi * hour / 24.0)

        disease_penalty = 0.0
        normalized_label = (disease_label or "healthy").strip().lower()
        if normalized_label not in {"healthy", "unknown", "other_plant", "unknown_non_target"}:
            disease_penalty = min(1.0, 0.35 + float(disease_confidence) * 0.65)

        payload = {
            "temperature_c": temperature_c,
            "humidity_pct": humidity_pct,
            "soil_raw": float(soil_raw),
            "soil_moisture_pct": float(soil_moisture_pct),
            "minutes_since_prev": minutes_since_prev,
            "soil_moisture_delta": float(soil_moisture_pct - previous_moisture),
            "soil_raw_delta": float(soil_raw - previous_raw),
            "moisture_1h_delta": float(moisture_1h_delta),
            "raw_1h_delta": float(raw_1h_delta),
            "moisture_2h_delta": float(moisture_2h_delta),
            "hour_sin": float(hour_sin),
            "hour_cos": float(hour_cos),
            "light_lux": light_lux,
            "weather_temp_c": weather_temp_c,
            "weather_humidity_pct": weather_humidity_pct,
            "forecast_rain_mm": forecast_rain_mm,
            "disease_score": disease_penalty,
            "disease_confidence": float(disease_confidence if disease_penalty > 0 else 0.0),
        }
        return payload, missing_inputs

    def _estimate_next_watering_hours(
        self,
        payload: dict[str, float],
        plant_type: str,
        history: list[dict[str, Any]],
        calibration: dict[str, Any] | None = None,
    ) -> float:
        profile = self.profiles[self._normalize_plant_type(plant_type)]
        threshold = float((calibration or {}).get("moisture_target_pct", profile["moisture_threshold_pct"]))
        current_moisture = payload["soil_moisture_pct"]
        if current_moisture <= threshold:
            return 0.0

        if history:
            oldest = history[0]
            oldest_moisture = float(oldest.get("soil_moisture_pct", oldest.get("soil_moisture", current_moisture)) or current_moisture)
            oldest_ts = self._safe_timestamp(oldest.get("timestamp"))
            newest_ts = self._safe_timestamp(history[-1].get("timestamp"))
            if oldest_ts and newest_ts and newest_ts > oldest_ts:
                hours = max(0.1, (newest_ts - oldest_ts).total_seconds() / 3600.0)
                dry_rate = max(0.4, (oldest_moisture - current_moisture) / hours)
            else:
                dry_rate = max(0.5, abs(payload["moisture_1h_delta"]))
        else:
            dry_rate = max(0.5, abs(payload["moisture_1h_delta"]))

        return round(max(0.0, (current_moisture - threshold) / max(dry_rate, 0.4)), 1)

    def _derive_feedback_adjustment(self, plant_type: str, feedback_rows: list[dict[str, Any]]) -> dict[str, float | str]:
        normalized_plant = self._normalize_plant_type(plant_type)
        relevant_rows = [
            row
            for row in feedback_rows
            if self._normalize_plant_type(str(row.get("plant_type", "") or plant_type)) == normalized_plant
        ]
        if not relevant_rows:
            return {"threshold_delta": 0.0, "pump_multiplier": 1.0, "hours_multiplier": 1.0, "note": ""}

        weighted_signal = 0.0
        weight_total = 0.0
        for index, row in enumerate(relevant_rows[:12]):
            label = str(row.get("feedback_label", "") or "").strip().lower()
            signal = 0.0
            if label == "underwatered":
                signal = -1.0
            elif label == "overwatered":
                signal = 1.0
            elif label == "worse":
                signal = -0.35
            elif label == "better":
                signal = 0.1

            if signal == 0.0:
                continue

            weight = max(0.35, 1.0 - (index * 0.08))
            weighted_signal += signal * weight
            weight_total += weight

        if weight_total == 0.0:
            return {"threshold_delta": 0.0, "pump_multiplier": 1.0, "hours_multiplier": 1.0, "note": ""}

        feedback_bias = max(-1.0, min(1.0, weighted_signal / weight_total))
        threshold_delta = round(0.08 * feedback_bias, 3)
        pump_multiplier = min(1.3, max(0.75, 1.0 - (0.2 * feedback_bias)))
        hours_multiplier = min(1.35, max(0.7, 1.0 + (0.3 * feedback_bias)))

        if feedback_bias <= -0.15:
            note = "Feedback learning is shifting watering earlier because recent labels suggest underwatering."
        elif feedback_bias >= 0.15:
            note = "Feedback learning is delaying watering slightly because recent labels suggest overwatering."
        else:
            note = "Recent feedback is being blended into the watering recommendation."

        return {
            "threshold_delta": threshold_delta,
            "pump_multiplier": pump_multiplier,
            "hours_multiplier": hours_multiplier,
            "note": note,
        }

    def _build_reasons(
        self,
        payload: dict[str, float],
        plant_type: str,
        disease_label: str,
        calibration: dict[str, Any] | None = None,
    ) -> list[str]:
        profile = self.profiles[self._normalize_plant_type(plant_type)]
        reasons: list[str] = []
        threshold = float((calibration or {}).get("moisture_target_pct", profile["moisture_threshold_pct"]))

        if payload["soil_moisture_pct"] <= threshold + 3:
            reasons.append("Soil moisture is near or below the plant threshold.")
        if payload["light_lux"] >= float(profile["light_reference_lux"]) * 0.9:
            reasons.append("Strong light suggests faster water use.")
        if payload["weather_temp_c"] >= float(profile["temperature_pivot_c"]) + 3:
            reasons.append("Warm weather increases evaporation.")
        if payload["forecast_rain_mm"] >= 1.0:
            reasons.append("Forecast rain reduces watering urgency.")
        if payload["disease_score"] > 0:
            reasons.append(f"Disease stress from {disease_label} increases caution.")
        if payload["moisture_1h_delta"] <= -2:
            reasons.append("Recent moisture trend is falling.")
        if calibration is not None:
            reasons.append("Custom calibration is applied for this soil sensor.")

        return reasons[:4] or ["No strong alert, conditions are relatively stable."]
