from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

RETENTION_HOURS = 24
IMAGE_DIR = Path("images")  
IMAGE_DIR.mkdir(exist_ok=True, parents=True)

def cleanup_old_images():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    for sensor_folder in IMAGE_DIR.iterdir():
        if sensor_folder.is_dir():
            for img_file in sensor_folder.glob("*.jpg"):
                # Get file creation time
                if datetime.timestamp(img_file.stat().st_mtime) < cutoff:
                    try:
                        img_file.unlink()
                        print(f"Deleted old image: {img_file}")
                    except Exception as e:
                        print(f"Error deleting {img_file}: {e}")

