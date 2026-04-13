import pandas as pd # type: ignore
import numpy as np # type: ignore


class BasilikumPlant:

    def __init__(self, df:pd.DataFrame):
        self.plant_name = 'basilikum'
        self.optimal_day_temperature_min = 21
        self.optimal_day_temperature_max = 32
        self.optimal_night_temperature_min = 15
        self.optimal_night_temperature_max = 32
        self.optimal_humidity_min = 40
        self.optimal_humidity_max = 60
        self.optimal_soil_moisture_min = 60
        self.optimal_soil_moisture_max = 80

        self.basil_df = df

        self.transform_df()

        self.window_days = 30

    def transform_df(self):

        # -------------------
        # TEMPERATURE
        # -------------------
        self.basil_df['rel_temp_day_diff_from_opt_ext'] = 0

        temp_less_day = (self.basil_df['temperature'] < self.optimal_day_temperature_min)
        temp_greater_day = (self.basil_df['temperature'] > self.optimal_day_temperature_max)

        self.basil_df.loc[temp_less_day, 'rel_temp_day_diff_from_opt_ext'] = (
            (self.optimal_day_temperature_min - self.basil_df.loc[temp_less_day, 'temperature'])
            / self.optimal_day_temperature_min
        ).abs()

        self.basil_df.loc[temp_greater_day, 'rel_temp_day_diff_from_opt_ext'] = (
            (self.basil_df.loc[temp_greater_day, 'temperature'] - self.optimal_day_temperature_max)
            / self.optimal_day_temperature_max
        ).abs()

        # -------------------
        # HUMIDITY
        # -------------------
        self.basil_df['rel_humidity_diff_from_opt_ext'] = 0

        hum_less = (self.basil_df['humidity'] < self.optimal_humidity_min)
        hum_greater = (self.basil_df['humidity'] > self.optimal_humidity_max)

        self.basil_df.loc[hum_less, 'rel_humidity_diff_from_opt_ext'] = (
            (self.optimal_humidity_min - self.basil_df.loc[hum_less, 'humidity'])
            / self.optimal_humidity_min
        ).abs()

        self.basil_df.loc[hum_greater, 'rel_humidity_diff_from_opt_ext'] = (
            (self.basil_df.loc[hum_greater, 'humidity'] - self.optimal_humidity_max)
            / self.optimal_humidity_max
        ).abs()

        # -------------------
        # SOIL MOISTURE
        # -------------------
        self.basil_df['rel_soil_moisture_diff_from_opt_ext'] = 0

        soil_less = (self.basil_df['soil_moisture'] < self.optimal_soil_moisture_min)
        soil_greater = (self.basil_df['soil_moisture'] > self.optimal_soil_moisture_max)

        self.basil_df.loc[soil_less, 'rel_soil_moisture_diff_from_opt_ext'] = (
            (self.optimal_soil_moisture_min - self.basil_df.loc[soil_less, 'soil_moisture'])
            / self.optimal_soil_moisture_min
        ).abs()

        self.basil_df.loc[soil_greater, 'rel_soil_moisture_diff_from_opt_ext'] = (
            (self.basil_df.loc[soil_greater, 'soil_moisture'] - self.optimal_soil_moisture_max)
            / self.optimal_soil_moisture_max
        ).abs()

        
        # -------------------
        # HEALTH CLASSIFICATION
        # -------------------
        temp_ok = self.basil_df['temperature'].between(
            self.optimal_day_temperature_min,
            self.optimal_day_temperature_max
        )

        hum_ok = self.basil_df['humidity'].between(
            self.optimal_humidity_min,
            self.optimal_humidity_max
        )

        soil_ok = self.basil_df['soil_moisture'].between(
            self.optimal_soil_moisture_min,
            self.optimal_soil_moisture_max
        )

        not_ok_count = (~temp_ok).astype(int) + (~hum_ok).astype(int) + (~soil_ok).astype(int)

        self.basil_df['health_based_on_opt'] = 'moderate'
        self.basil_df.loc[not_ok_count == 0, 'health_based_on_opt'] = 'good'
        self.basil_df.loc[not_ok_count >= 2, 'health_based_on_opt'] = 'critical'

        # -------------------------------------------------
        # (3) overall health dynamics model 
        # -------------------------------------------------

        self.basil_df['overall_health_on_ext'] = 100

        for i in range(1, len(self.basil_df)):
            prev = self.basil_df.loc[i - 1, 'overall_health_on_ext']

            hum = self.basil_df.loc[i, 'rel_humidity_diff_from_opt_ext']
            soil = self.basil_df.loc[i, 'rel_soil_moisture_diff_from_opt_ext']
            temp = self.basil_df.loc[i, 'rel_temp_day_diff_from_opt_ext']

            # penalty (0–1 approx)
            penalty = (hum + soil + temp) / 3

            # logistic health sensitivity
            health_factor = 1 / (1 + np.exp(-(prev - 75) / 10))

            decay = penalty * (0.1 + 0.9 * health_factor)

            if self.basil_df.loc[i, 'health_based_on_opt'] == 'good':
                recovery = (1 - prev / 100) * health_factor
                new_health = prev + recovery
            else:
                new_health = prev - decay

            # clamp
            self.basil_df.loc[i, 'overall_health_on_ext'] = max(0, min(100, new_health))
