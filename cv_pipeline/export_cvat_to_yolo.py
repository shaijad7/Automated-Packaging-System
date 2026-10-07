import xml.etree.ElementTree as ET
import os
import argparse

def convert_cvat_xml_to_yolo(xml_file, output_dir):
    """
    Parses a CVAT 1.1 XML annotation file and outputs standard YOLO format TXT files.
    Only extracts the 'box' label and maps it to class 0.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return

    print("Parsing CVAT annotations...")
    total_boxes = 0
    total_images_with_boxes = 0

    for image in root.findall('image'):
        filename = image.get('name')
        img_width = float(image.get('width'))
        img_height = float(image.get('height'))
        
        boxes = image.findall('box')
        if not boxes:
            continue
            
        base_name = os.path.splitext(filename)[0]
        txt_path = os.path.join(output_dir, f"{base_name}.txt")
        
        box_lines = []
        for box in boxes:
            label = box.get('label')
            # Only accept 'box' or map everything to class 0 if there are no other valid classes.
            # The instructions explicitly say only 'box' should exist, class 0.
            if label.lower() != 'box':
                print(f"Warning: Found unexpected label '{label}' in {filename}. Ignoring.")
                continue
                
            xtl = float(box.get('xtl'))
            ytl = float(box.get('ytl'))
            xbr = float(box.get('xbr'))
            ybr = float(box.get('ybr'))
            
            # YOLO format conversion (normalized center_x, center_y, width, height)
            x_center = ((xtl + xbr) / 2) / img_width
            y_center = ((ytl + ybr) / 2) / img_height
            box_width = (xbr - xtl) / img_width
            box_height = (ybr - ytl) / img_height
            
            # Bound coordinates between 0 and 1 just in case annotations exceeded image bounds
            x_center = max(0.0, min(1.0, x_center))
            y_center = max(0.0, min(1.0, y_center))
            box_width = max(0.0, min(1.0, box_width))
            box_height = max(0.0, min(1.0, box_height))
            
            # Class ID is always 0
            box_lines.append(f"0 {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}")
            total_boxes += 1
            
        if box_lines:
            with open(txt_path, 'w') as f:
                f.write('\n'.join(box_lines) + '\n')
            total_images_with_boxes += 1

    print(f"Conversion complete!")
    print(f"Generated labels for {total_images_with_boxes} images.")
    print(f"Total boxes exported: {total_boxes}")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert CVAT Annotations XML to YOLO TXT format")
    parser.add_argument("--xml", required=True, help="Path to the downloaded annotations.xml file")
    parser.add_argument("--out", default="dataset/train_ready/labels", help="Output directory for YOLO labels")
    
    args = parser.parse_args()
    convert_cvat_xml_to_yolo(args.xml, args.out)
