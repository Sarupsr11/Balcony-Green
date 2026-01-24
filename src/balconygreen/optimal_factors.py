
# ------ #
# optimal environmal factors for different plans #
# ------ #

class PlantOptimal:
    """
    Represents the optimal environmental conditions required for healthy
    growth of a plant.

    This class is used to store and manage ideal ranges for key environmental
    factors that influence plant growth, such as soil moisture, soil pH,
    temperature, humidity, and light exposure. It is designed to support
    balcony gardening, sensor-based monitoring (e.g., ESP32), rule-based
    decision systems, and machine learning applications.

    Each parameter is defined as a minimum and maximum value, allowing
    real-time sensor readings to be evaluated against plant-specific
    optimal conditions.

    Attributes
    ----------
    name : str
        Common name of the plant.
    soil_moisture : tuple(float, float)
        Optimal soil moisture range in percent (%).
    soil_ph : tuple(float, float)
        Optimal soil pH range.
    temperature : tuple(float, float)
        Optimal ambient temperature range in degrees Celsius.
    humidity : tuple(float, float)
        Optimal relative humidity range in percent (%).
    light_hours : tuple(float, float)
        Optimal daily light exposure in hours.

    Intended Use
    ------------
    - Comparing real-time sensor data with optimal plant conditions
    - Generating alerts when conditions fall outside safe ranges
    - Creating datasets for machine learning models
    - Extending to additional environmental parameters or plant species

    Example
    -------
    >>> potato = PlantOptimal(
    ...     name="Potato",
    ...     soil_moisture=(60, 80),
    ...     soil_ph=(5.0, 6.5),
    ...     temperature=(15, 25),
    ...     humidity=(55, 75),
    ...     light_hours=(6, 8)
    ... )
    """

    def __init__(
        self,
        name,
        soil_moisture_min,
        soil_moisture_max,
        ph_min,
        ph_max,
        temp_min,
        temp_max,
        humidity_min,
        humidity_max,
        light_min,
        light_max
    ):
        self.name = name

        self.soil_moisture_optimal = (soil_moisture_min, soil_moisture_max)
        self.soil_ph_optimal = (ph_min, ph_max)
        self.temperature_optimal = (temp_min, temp_max)
        self.humidity_optimal = (humidity_min, humidity_max)
        self.light_hours_optimal = (light_min, light_max)

    def __repr__(self):
        return f"Plant({self.name})"


tomato_optimal = PlantOptimal(
    name="Tomato",
    soil_moisture_min=60,
    soil_moisture_max=75,
    ph_min=6.0,
    ph_max=6.8,
    temp_min=20,
    temp_max=30,
    humidity_min=50,
    humidity_max=70,
    light_min=6,
    light_max=8
)

chili_optimal = PlantOptimal(
    name="Chili_Pepper",
    soil_moisture_min=55,
    soil_moisture_max=70,
    ph_min=6.0,
    ph_max=6.8,
    temp_min=22,
    temp_max=32,
    humidity_min=50,
    humidity_max=65,
    light_min=6,
    light_max=8
)

potato_optimal = PlantOptimal(
    name="Potato",
    soil_moisture_min=60,
    soil_moisture_max=80,
    ph_min=5.0,
    ph_max=6.5,
    temp_min=15,
    temp_max=25,
    humidity_min=55,
    humidity_max=75,
    light_min=6,
    light_max=8
)

mint_optimal = PlantOptimal(
    name="Mint",
    soil_moisture_min=65,
    soil_moisture_max=80,
    ph_min=6.0,
    ph_max=7.0,
    temp_min=15,
    temp_max=25,
    humidity_min=55,
    humidity_max=75,
    light_min=4,
    light_max=6
)

basil_optimal = PlantOptimal(
    name="Basil",
    soil_moisture_min=60,
    soil_moisture_max=75,
    ph_min=6.0,
    ph_max=7.0,
    temp_min=20,
    temp_max=30,
    humidity_min=50,
    humidity_max=70,
    light_min=6,
    light_max=8
)

coriander_optimal = PlantOptimal(
    name="Coriander",
    soil_moisture_min=55,
    soil_moisture_max=70,
    ph_min=6.2,
    ph_max=7.2,
    temp_min=15,
    temp_max=25,
    humidity_min=50,
    humidity_max=70,
    light_min=4,
    light_max=6
)

spinach_optimal = PlantOptimal(
    name="Spinach",
    soil_moisture_min=60,
    soil_moisture_max=80,
    ph_min=6.5,
    ph_max=7.5,
    temp_min=10,
    temp_max=22,
    humidity_min=55,
    humidity_max=75,
    light_min=4,
    light_max=6
)

aloe_vera_optimal = PlantOptimal(
    name="Aloe_Vera",
    soil_moisture_min=20,
    soil_moisture_max=40,
    ph_min=6.0,
    ph_max=7.5,
    temp_min=18,
    temp_max=30,
    humidity_min=30,
    humidity_max=50,
    light_min=6,
    light_max=8
)



