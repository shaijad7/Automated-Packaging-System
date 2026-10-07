import os
import random
from PIL import Image
from pillow_heif import register_heif_opener
import json

register_heif_opener()

img_dir = "cv_pipeline/dataset/images"
out_dir = "cv_pipeline/dataset/tmp_jpgs"
os.makedirs(out_dir, exist_ok=True)

files = [f for f in os.listdir(img_dir) if f.lower().endswith('.heic')]
files.sort()

stats = {
    "total_files": len(os.listdir(img_dir)),
    "heic_files": len(files),
    "dimensions": set(),
    "readable_sample": 0,
    "corrupt_sample": 0
}

# Select a subset of images to sample thoroughly for visual inspection
sample_indices = [0, 42, 85, 128, 170, 212, 255, 298, 340, 382, 410, 427]
sample_files = [files[i] for i in sample_indices if i < len(files)]

print(f"Total files in dir: {stats['total_files']}")
print(f"Total HEIC files: {stats['heic_files']}")

for i, f in enumerate(files):
    if i % 50 == 0 or f in sample_files:
        try:
            img_path = os.path.join(img_dir, f)
            with Image.open(img_path) as img:
                stats["dimensions"].add(f"{img.width}x{img.height}")
                stats["readable_sample"] += 1
                
                # Convert sample files to JPG for the agent to view
                if f in sample_files:
                    out_path = os.path.join(out_dir, f.replace(".heic", ".jpg"))
                    img.convert("RGB").save(out_path, "JPEG")
        except Exception as e:
            stats["corrupt_sample"] += 1
            print(f"Error reading {f}: {e}")

stats["dimensions"] = list(stats["dimensions"])
with open("audit_stats.json", "w") as out_f:
    json.dump(stats, out_f, indent=2)

print("Audit script finished successfully.")
