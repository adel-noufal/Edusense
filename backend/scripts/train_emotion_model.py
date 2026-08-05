"""
EduSense - Emotion Model Training Script
Fine-tunes a Convolutional Neural Network (EfficientNet / MobileNet / ResNet) 
on a facial emotion dataset (such as RAF-DB, AffectNet, or FER-2013).

Usage:
  python scripts/train_emotion_model.py --data_dir /path/to/dataset --epochs 15 --batch_size 32
"""

import argparse
import os
import sys
from pathlib import Path

def train_with_pytorch(data_dir: str, epochs: int, batch_size: int, lr: float, output_path: str):
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torchvision import datasets, models, transforms
    from torch.utils.data import DataLoader

    print("=" * 60)
    print("  EduSense Emotion Model Training (PyTorch)")
    print("=" * 60)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Using compute device: {device}")

    # Standard data augmentation and normalization for FER
    data_transforms = {
        'train': transforms.Compose([
            transforms.RandomResizedCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.2, contrast=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
        'val': transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ]),
    }

    train_dir = os.path.join(data_dir, 'train')
    val_dir = os.path.join(data_dir, 'val') if os.path.exists(os.path.join(data_dir, 'val')) else train_dir

    print(f"[INFO] Loading datasets from: {data_dir}")
    image_datasets = {
        'train': datasets.ImageFolder(train_dir, data_transforms['train']),
        'val': datasets.ImageFolder(val_dir, data_transforms['val'])
    }

    dataloaders = {
        'train': DataLoader(image_datasets['train'], batch_size=batch_size, shuffle=True, num_workers=2),
        'val': DataLoader(image_datasets['val'], batch_size=batch_size, shuffle=False, num_workers=2)
    }

    class_names = image_datasets['train'].classes
    num_classes = len(class_names)
    print(f"[INFO] Emotion classes ({num_classes}): {class_names}")

    # Load pre-trained EfficientNet-B0 or ResNet18 backbone
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_acc = 0.0

    for epoch in range(1, epochs + 1):
        print(f"\nEpoch {epoch}/{epochs}")
        print("-" * 20)

        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()
            else:
                model.eval()

            running_loss = 0.0
            running_corrects = 0

            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                optimizer.zero_grad()

                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            if phase == 'train':
                scheduler.step()

            epoch_loss = running_loss / len(image_datasets[phase])
            epoch_acc = running_corrects.double() / len(image_datasets[phase])

            print(f"{phase.capitalize()} Loss: {epoch_loss:.4f} Acc: {epoch_acc * 100:.2f}%")

            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': model.state_dict(),
                    'class_names': class_names,
                    'accuracy': best_acc,
                }, output_path)
                print(f" [★] Saved new best model checkpoint to {output_path} (Acc: {best_acc * 100:.2f}%)")

    print("\n[OK] Training completed!")
    print(f"Best Validation Accuracy: {best_acc * 100:.2f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EduSense Emotion Model Trainer")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to dataset folder containing train/ and val/ subdirectories")
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--output", type=str, default="app/static/models/custom_emotion_model.pth", help="Output path for trained weights")

    args = parser.parse_args()
    train_with_pytorch(args.data_dir, args.epochs, args.batch_size, args.lr, args.output)
