import logging
from pathlib import Path

import timm  # type: ignore
import torch  # type: ignore
from PIL import Image  # type: ignore
from torchvision import transforms  # type: ignore




PROJECT_ROOT = Path(__file__).resolve().parents[1]

CKPT_PATH_TOMATO_BINARY = (
    PROJECT_ROOT
    / "model_prediction"
    / "Models"
    / "efficientnet_binary_best_multiple_sources.pth"
)


CKPT_PATH_TOMATO_VARIOUS = PROJECT_ROOT / "model_prediction" /  "Models" / "efficientnet_best_multiple_sources.pth"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from balconygreen.model_prediction.inference import EfficientNetClassifier

def load_models(plant, no_classes , binary = False):
    model = None
    if "tomato" in plant.lower() and binary:
        model = EfficientNetClassifier(CKPT_PATH_TOMATO_BINARY, num_classes=2 )
    elif "tomato" in plant.lower() and not binary:
        model = EfficientNetClassifier(CKPT_PATH_TOMATO_VARIOUS, num_classes=no_classes )

    return model

MODEL_CACHE = {}

def get_model(plant: str, mode: str):
    key = f"{plant}_{mode}"

    if key in MODEL_CACHE:
        return MODEL_CACHE[key]

    if mode == "binary":
        model = load_models(plant, no_classes=2, binary=True)
    else:
        # adjust class count per plant if needed
        model = load_models(plant, no_classes=11, binary=False)

    if model is None:
        raise ValueError(f"No model available for plant: {plant}")

    MODEL_CACHE[key] = model
    return model
