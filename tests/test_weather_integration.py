from src.balconygreen.weather_service import WeatherService
import json

def test_weather_service():
    print("Testing WeatherService...")
    
    # Initialize with Berlin coordinates
    service = WeatherService(lat=52.52, lon=13.41)
    
    print(f"Fetching data for Lat: {service.lat}, Lon: {service.lon}")
    data = service.get_current_weather()
    
    print("\nAPI Response:")
    print(json.dumps(data, indent=2))
    
    if "error" in data:
        print("\n❌ Test Failed: API returned an error.")
    else:
        # Check required keys
        required_keys = ["temperature (°C)", "humidity (%)", "rain (mm)", "soil_moisture"]
        missing = [key for key in required_keys if key not in data]
        
        if missing:
             print(f"\n❌ Test Failed: Missing keys: {missing}")
        else:
             print("\n✅ Test Passed: All weather data fields present.")
             print(f"Temperature: {data['temperature (°C)']}°C")
             print(f"Soil Moisture: {data['soil_moisture']} (raw)")

if __name__ == "__main__":
    test_weather_service()
