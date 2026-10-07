import os
import glob
import cv2

def audit_dataset():
    dataset_dir = r"c:\Users\shaik\Downloads\ProjectWork\smart-inventory-system\cv_pipeline\dataset\train_ready"
    images_dir = os.path.join(dataset_dir, "images")
    labels_dir = os.path.join(dataset_dir, "labels")
    
    prod_add_dir = r"c:\Users\shaik\Downloads\ProjectWork\smart-inventory-system\cv_pipeline\dataset\production_additional"
    
    if not os.path.exists(images_dir) or not os.path.exists(labels_dir):
        print(f"Dataset dir not found: {dataset_dir}")
        return
        
    image_files = glob.glob(os.path.join(images_dir, "**", "*.jpg"), recursive=True) + glob.glob(os.path.join(images_dir, "*.jpg"))
    # filter duplicates
    image_files = list(set(image_files))
    
    print(f"Total training images found: {len(image_files)}")
    
    negative_images = 0
    positive_images = 0
    total_boxes = 0
    box_areas = []
    
    for img_path in image_files:
        # find corresponding label
        base = os.path.splitext(os.path.basename(img_path))[0]
        # Determine if it's in a subdirectory like 'train' or 'val'
        rel_path = os.path.relpath(os.path.dirname(img_path), images_dir)
        if rel_path == '.':
            label_path = os.path.join(labels_dir, base + ".txt")
        else:
            label_path = os.path.join(labels_dir, rel_path, base + ".txt")
            
        if not os.path.exists(label_path):
            negative_images += 1
            continue
            
        with open(label_path, 'r') as f:
            lines = f.readlines()
            
        # some labels might exist but be empty
        lines = [l for l in lines if l.strip()]
        
        if len(lines) == 0:
            negative_images += 1
        else:
            positive_images += 1
            total_boxes += len(lines)
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 5:
                    w, h = float(parts[3]), float(parts[4])
                    box_areas.append(w * h)
                    
    print(f"Positive Images (with boxes): {positive_images}")
    print(f"Negative Images (no boxes): {negative_images}")
    print(f"Total boxes: {total_boxes}")
    
    if box_areas:
        avg_area = sum(box_areas) / len(box_areas)
        small_boxes = sum(1 for a in box_areas if a < 0.05) # less than 5% of image
        print(f"Average box area: {avg_area:.3f} (as fraction of image)")
        print(f"Small/Far boxes (<5% area): {small_boxes} out of {total_boxes}")
        
    print(f"\nChecking production_additional...")
    if os.path.exists(prod_add_dir):
        prod_images = glob.glob(os.path.join(prod_add_dir, "*.jpg"))
        print(f"Found {len(prod_images)} images in {prod_add_dir}")
    else:
        print(f"Directory {prod_add_dir} not found.")
        
    # Check for conveyor video
    videos = glob.glob(r"c:\Users\shaik\Downloads\ProjectWork\smart-inventory-system\cv_pipeline\dataset\**\*.mp4", recursive=True)
    if videos:
        print(f"\nVideos found in dataset dir: {videos}")
    else:
        print("\nNo .mp4 videos found in dataset dir.")
        
if __name__ == '__main__':
    audit_dataset()
