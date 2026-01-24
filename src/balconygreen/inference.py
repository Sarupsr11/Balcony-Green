from pathlib import Path

import timm # type: ignore
import torch # type: ignore
from PIL import Image # type: ignore
from torchvision import transforms # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CKPT_PATH  = PROJECT_ROOT / "disease-detection"/"Tomatoes" /"Models"/"efficientnet_binary_best_multiple_sources.pth"



class EfficientNetClassifier:
    def __init__(
        self,
        model_path: str,
        num_classes: int,
        device: str = "cpu",
        img_size: int = 224
    ):
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

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self._load_model()
        self._build_transforms()

    def _load_model(self):
        """Create model and load weights"""
        self.model = timm.create_model(
            "efficientnet_b0",
            pretrained=False,
            num_classes=self.num_classes
        ).to(self.device)

        state_dict = torch.load(self.model_path, map_location=self.device)
        self.class_names = state_dict["classes"]
        self.model.load_state_dict(state_dict["model"])
        self.model.eval()

    def _build_transforms(self):
        """Image preprocessing"""
        self.transform = transforms.Compose([
            transforms.Resize((self.img_size, self.img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

                   
    def predict(
        self,
        image_path: str,
        top_k: int = 1,
        confidence_threshold: float = 0.0
    ):
        """
        Args:
            image_path (str): Path to image
            top_k (int): Number of top predictions to return
            confidence_threshold (float): Minimum probability to keep prediction

        Returns:
            list of dicts
        """
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
                results.append({
                    "class_name": self.class_names[idx.item()],
                    "confidence": score
                })

        if not results:
            return [{
                "class_name": "Unknown",
                "confidence": max(probs).item()
            }]

        return results


