from typing import Any, Dict, Optional
import requests

class WeatherService:
    """
    A service to fetch real-time weather and soil data using the Open-Meteo API.
    
    Attributes:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.
        base_url (str): The API endpoint for Open-Meteo.
    """
    
    def __init__(self, lat: float = 52.52, lon: float = 13.41):
        """
        Initialize the WeatherService with a location.
        Default is Berlin (Open-Meteo default).
        """
        self.lat = lat
        self.lon = lon
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    def set_location(self, lat: float, lon: float):
        """Update the location coordinates."""
        self.lat = lat
        self.lon = lon

    def get_current_weather(self) -> Dict[str, Any]:
        """
        Fetches current weather variables including moisture.
        
        Returns:
            Dict containing temperature, humidity, rain, and soil moisture.
            Returns an empty dict with error info if the request fails.
        """
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "current": "temperature_2m,relative_humidity_2m,rain,soil_moisture_0_to_1cm"
        }
        
        try:
            # fast timeout to not block UI
            response = requests.get(self.base_url, params=params, timeout=3)
            response.raise_for_status()
            data = response.json()
            current = data.get("current", {})
            
            # Open-Meteo returns soil moisture in m³/m³. 
            # We convert it to % (0.5 m³/m³ is typically saturation, but simple *100 is easier for display)
            soil_moisture_raw = current.get("soil_moisture_0_to_1cm", 0)
            
            return {
                "temperature (°C)": current.get("temperature_2m"),
                "humidity (%)": current.get("relative_humidity_2m"),
                "rain (mm)": current.get("rain"),
                "soil_moisture": soil_moisture_raw  # Keep raw for logic, format in UI
            }
            
        except requests.RequestException as e:
            return {"error": f"Weather API Connection Error: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected Error: {str(e)}"}
