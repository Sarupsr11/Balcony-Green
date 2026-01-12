"""
To run it successfully, change the dataset directory.

"""





# =========================
# 0. INSTALL & IMPORTS
# =========================

import os
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns
import timm
import torch
import torch.nn as nn
from PIL import Image, ImageFile
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from torch.utils.data import DataLoader, Dataset, random_split
from torchvision import transforms
from tqdm import tqdm

ImageFile.LOAD_TRUNCATED_IMAGES = True
device = "cuda" if torch.cuda.is_available() else "cpu"
print("Using device:", device)

# =========================
# 1. CONFIG
# =========================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "Dataset"

TRAIN_ROOT = DATA_ROOT / "train"
TEST_ROOT  = DATA_ROOT / "test"

CKPT_PATH  = PROJECT_ROOT / "Models"/"efficientnet_binary_best_multiple_sources.pth"

BATCH_SIZE = 16
EPOCHS = 10
LR = 1e-4
IMG_SIZE = 224
PATIENCE = 3
VAL_SPLIT = 0.2


# =========================
# 2. DATASET 
# =========================
class TomatoDataset(Dataset):
    
    def __init__(self, image_root, transform=None, binary = False):
        self.samples = []
        self.transform = transform
        if binary:
            self.classes = ["Healthy", "Unhealthy"]
            for folder in os.listdir(image_root):
                folder_path = os.path.join(image_root, folder)
                if not os.path.isdir(folder_path):
                    continue

                
                label = 0 if folder.lower() == "healthy" else 1

                for img in os.listdir(folder_path):
                    if img.lower().endswith((".jpg", ".png", ".jpeg")):
                        self.samples.append((os.path.join(folder_path, img), label))
            print(f"{image_root} samples: {len(self.samples)}")
        else:
            self.classes = sorted([
            d for d in os.listdir(image_root)
            if os.path.isdir(os.path.join(image_root, d))])
            self.class_to_idx = {c: i for i, c in enumerate(self.classes)}

            for cls in self.classes:
                cls_dir = os.path.join(image_root, cls)
                for img in os.listdir(cls_dir):
                    if img.lower().endswith((".jpg", ".png", ".jpeg")):
                        self.samples.append(
                            (os.path.join(cls_dir, img), self.class_to_idx[cls])
                        )

            print(f"Loaded {len(self.samples)} images")
            print("Classes:", self.classes)


        

        

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = Image.open(img_path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, label

# =========================
# 3. TRANSFORMS
# =========================
tfms = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485,0.456,0.406],
                         [0.229,0.224,0.225])
])

# =========================
# 4. DATASETS & SPLIT
# =========================
full_train_dataset = TomatoDataset(TRAIN_ROOT, tfms, True)
test_dataset       = TomatoDataset(TEST_ROOT, tfms, True)

val_size = int(len(full_train_dataset) * VAL_SPLIT)
train_size = len(full_train_dataset) - val_size

train_dataset, val_dataset = random_split(
    full_train_dataset, [train_size, val_size]
)

train_loader = DataLoader(train_dataset, BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(val_dataset, BATCH_SIZE, shuffle=False)
test_loader  = DataLoader(test_dataset, BATCH_SIZE, shuffle=False)

# =========================
# 5. CLASS WEIGHTS (FROM TRAIN ONLY)
# =========================



def compute_class_weights(labels, device):
    """
    labels: list or 1D tensor of class indices
    device: 'cpu' or 'cuda'
    """
    counts = Counter(labels)
    num_classes = len(counts)
    total_samples = sum(counts.values())

    weights = torch.zeros(num_classes)

    for cls_idx, count in counts.items():
        weights[cls_idx] = total_samples / count

    return weights.to(device)


def get_subset_labels(subset):
    """
    Works for torch.utils.data.Subset
    """
    base_dataset = subset.dataset
    indices = subset.indices
    return [base_dataset.samples[i][1] for i in indices]


train_labels = get_subset_labels(train_dataset)

class_weights = compute_class_weights(train_labels, device)

print("Class weights:", class_weights)

# =========================
# 6. MODEL
# =========================
model = timm.create_model(
    "efficientnet_b0",
    pretrained=True,
    num_classes= len(full_train_dataset.classes)
).to(device)

criterion = nn.CrossEntropyLoss(weight=class_weights)
optimizer = torch.optim.AdamW(model.parameters(), lr=LR)



# =========================
# 7. RESUME CHECKPOINT
# =========================
# start_epoch = 0
# if os.path.exists(CKPT_PATH):
#     ckpt = torch.load(CKPT_PATH, map_location=device)
#     model.load_state_dict(ckpt["model"])
#     optimizer.load_state_dict(ckpt["optimizer"])
#     start_epoch = ckpt["epoch"] + 1
#     print(f"Resuming from epoch {start_epoch}")

# =========================
# 8. TRAIN & VALIDATE
# =========================


def train_epoch(loader):
    model.train()
    loss_sum, correct, total = 0, 0, 0

    for x, y in tqdm(loader):
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()
        out = model(x)
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()

        loss_sum += loss.item()
        correct += (out.argmax(1) == y).sum().item()
        total += y.size(0)

    return loss_sum / len(loader), correct / total

def eval_epoch(loader):
    model.eval()
    loss_sum, correct, total = 0, 0, 0

    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            out = model(x)
            loss = criterion(out, y)

            loss_sum += loss.item()
            correct += (out.argmax(1) == y).sum().item()
            total += y.size(0)

    return loss_sum / len(loader), correct / total

# =========================
# 8. TRAIN LOOP + EARLY STOP
# =========================
best_val_acc = 0
patience_ctr = 0

for epoch in range(EPOCHS):
    tr_loss, tr_acc = train_epoch(train_loader)
    val_loss, val_acc = eval_epoch(val_loader)

    print(
        f"Epoch {epoch+1}/{EPOCHS} | "
        f"Train Acc: {tr_acc:.4f} | "
        f"Val Acc: {val_acc:.4f}"
    )

    if val_acc > best_val_acc:
        best_val_acc = val_acc
        patience_ctr = 0
        torch.save({
            "model": model.state_dict(),
            "classes": full_train_dataset.classes
        }, CKPT_PATH)
        
        print("✅ Best model saved")
    else:
        patience_ctr += 1

    if patience_ctr >= PATIENCE:
        print("🛑 Early stopping")
        break

# =========================
# 9. FINAL TEST EVALUATION
# =========================

model.load_state_dict(torch.load(CKPT_PATH)["model"])
model.eval()

all_preds, all_labels, all_probs = [], [], []

with torch.no_grad():
    for x, y in test_loader:
        x = x.to(device)
        out = model(x)
        probs = torch.softmax(out, 1)[:, 1]
        preds = out.argmax(1)

        all_preds.extend(preds.cpu().numpy())
        all_probs.extend(probs.cpu().numpy())
        all_labels.extend(y.numpy())

acc = accuracy_score(all_labels, all_preds)
prec = precision_score(all_labels, all_preds, average="macro")
rec = recall_score(all_labels, all_preds, average="macro")
f1 = f1_score(all_labels, all_preds, average="macro")

cm = confusion_matrix(all_labels, all_preds)

print("\n===== TEST RESULTS =====")
print(f"Accuracy : {acc:.4f}")
print(f"Precision: {prec:.4f}")
print(f"Recall   : {rec:.4f}")
print(f"F1-score : {f1:.4f}")

plt.figure(figsize=(6,5))
sns.heatmap(cm, annot=True, fmt="d",
            xticklabels=test_dataset.classes,
            yticklabels=test_dataset.classes,
            cmap="Blues")
plt.xlabel("Predicted")
plt.ylabel("True")
plt.title("Test Confusion Matrix")
plt.show()

