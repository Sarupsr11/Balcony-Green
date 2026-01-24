import requests
from typing import Optional, List, Dict

class LocationService:
    """
    Service to handle Geolocation via IP and City Search (Geocoding).
    """

    @staticmethod
    def get_ip_location() -> Optional[Dict]:
        """
        Get approximate location based on public IP using ip-api.com.
        Note: ip-api.com is free for non-commercial use (45 requests/minute).
        """
        try:
            # Using http because the free endpoint doesn't support https sometimes or has stricter limits
            response = requests.get("http://ip-api.com/json/", timeout=2)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'success':
                return {
                    "lat": float(data['lat']),
                    "lon": float(data['lon']),
                    "city": data.get('city', 'Unknown'),
                    "country": data.get('country', '')
                }
        except Exception as e:
            # In production, use logging
            print(f"IP Location lookup failed: {e}")
        return None

    @staticmethod
    def search_city(query: str) -> List[Dict]:
        """
        Search for a city using Open-Meteo Geocoding API.
        Returns a list of matching locations.
        """
        if not query or len(query) < 3:
            return []
            
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            "name": query,
            "count": 5,
            "language": "en",
            "format": "json"
        }
        
        try:
            response = requests.get(url, params=params, timeout=3)
            if response.status_code != 200:
                return []
                
            data = response.json()
            results = data.get("results", [])
            
            clean_results = []
            for r in results:
                # Build a discrete summary
                fragments = [r.get("name"), r.get("admin1"), r.get("country")]
                display_name = ", ".join([f for f in fragments if f])
                
                clean_results.append({
                    "lat": r["latitude"],
                    "lon": r["longitude"],
                    "name": r["name"],
                    "display": display_name
                })
            return clean_results
            
        except Exception as e:
            print(f"Geocoding search failed: {e}")
            return []

    @staticmethod
    def reverse_geocode(lat: float, lon: float) -> str:
        """
        Get address/city from coordinates using OpenStreetMap Nominatim.
        """
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                "lat": lat,
                "lon": lon,
                "format": "json"
            }
            # Nominatim requires a User-Agent
            headers = {"User-Agent": "BalconyGreenBot/1.0"}
            
            response = requests.get(url, params=params, headers=headers, timeout=3)
            if response.status_code == 200:
                data = response.json()
                return data.get("display_name", "Unknown Location")
        except Exception as e:
            print(f"Reverse geocoding failed: {e}")
            
        return "Unknown Coords"
