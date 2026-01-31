import logging
from pathlib import Path

import timm  # type: ignore
import torch  # type: ignore
from PIL import Image  # type: ignore
from torchvision import transforms  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CKPT_PATH = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_binary_best_multiple_sources.pth"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class EfficientNetClassifier:
    def __init__(self, model_path: str, num_classes: int, device: str = "cpu", img_size: int = 224):
        """
        Args:
            model_path (str): Path to .pth file
            num_classes (int): Number of output classes
            device (str): 'cuda' or 'cpu' (auto if None)
            img_size (int): Input image size (default 224)
        """
        self.model_path = Path(model_path)
        self.num_classes = num_classes
        self.img_size = img_size
        logger.info(f"Initializing EfficientNetClassifier - model_path: {model_path}, num_classes: {num_classes}")

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")

        self._load_model()
        self._build_transforms()
        logger.info("EfficientNetClassifier initialization complete")

    def _load_model(self):
        """Create model and load weights"""
        logger.debug(f"Loading model from {self.model_path}")
        self.model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=self.num_classes).to(self.device)

        state_dict = torch.load(self.model_path, map_location=self.device)
        self.class_names = state_dict["classes"]
        self.model.load_state_dict(state_dict["model"])
        self.model.eval()
        logger.info(f"Model loaded successfully with {len(self.class_names)} classes")

    def _build_transforms(self):
        """Image preprocessing"""
        self.transform = transforms.Compose(
            [
                transforms.Resize((self.img_size, self.img_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def predict(self, image_path: str, top_k: int = 1, confidence_threshold: float = 0.0):
        """
        Args:
            image_path (str): Path to image
            top_k (int): Number of top predictions to return
            confidence_threshold (float): Minimum probability to keep prediction

        Returns:
            list of dicts
        """
        logger.debug(f"Starting prediction for image: {image_path} (top_k={top_k}, threshold={confidence_threshold})")
        image = Image.open(image_path).convert("RGB")
        x = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(x)
            probs = torch.softmax(logits, dim=1)[0]

        top_k = min(top_k, self.num_classes)
        values, indices = torch.topk(probs, top_k)

        results = []
        for score, idx in zip(values, indices, strict=True):
            score = score.item()
            if score >= confidence_threshold:
                class_name = self.class_names[idx.item()]
                logger.debug(f"Prediction: {class_name} ({score:.4f})")
                results.append({"class_name": class_name, "confidence": score})

        if not results:
            logger.warning(f"No predictions met confidence threshold for {image_path}")
            return [{"class_name": "Unknown", "confidence": max(probs).item()}]

        logger.info(f"Prediction complete for {image_path}: {len(results)} results")
        return results
