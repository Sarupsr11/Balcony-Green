from sqlalchemy.orm import declarative_base # type: ignore

# Base for all ORM models
Base = declarative_base()

# Import models **after** Base is defined
# This registers the models with Base.metadata
from balconygreen.db_implementation.schema.users import User
from balconygreen.db_implementation.schema.devices import Device
from balconygreen.db_implementation.schema.sensor import Sensor
from balconygreen.db_implementation.schema.reading import Reading
from balconygreen.db_implementation.schema.image import Image
from balconygreen.db_implementation.schema.upload import Upload

