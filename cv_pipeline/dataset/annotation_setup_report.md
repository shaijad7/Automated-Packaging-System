# Phase 8 Annotation Setup Report

## 1. Dataset Verification
- **Expected Images**: 496
- **Actual Images**: 496 (Verified via script)
- **Format**: All images are confirmed as valid and readable JPG files.
- **Corruption**: 0 corrupted images found.

## 2. Annotation Directory
The dataset is structured correctly and ready for import:
```
cv_pipeline/dataset/train_ready/
├── images/
│   └── (496 JPG images)
└── labels/
    └── (Empty directory ready for tool export)
```

## 3. Annotation Tool
A suitable manual annotation tool such as **CVAT**, **Label Studio**, or **Roboflow** is recommended.
- **Local Setup Minimal Steps** (Example for Label Studio):
  1. `pip install label-studio`
  2. `label-studio start`
  3. Create a new project.
  4. Set the UI template to "Object Detection with Bounding Boxes".
  5. Import the 496 JPGs from `cv_pipeline/dataset/train_ready/images/`.

## 4. Class Configuration
You **MUST** configure exactly ONE class in your annotation tool:
- `box`

*(Ensure the internal class index maps to `0` upon export).*

## 5. Annotation Rules
- **Rule 1:** Draw bounding boxes as tight as reasonably possible around the physical box.
- **Rule 2:** Do not intentionally include large amounts of background (conveyor, table, etc.).
- **Rule 3:** Do not label QR codes, text, logos, hands, people, or the products themselves (phones, chargers) separately.
- **Rule 4:** Annotate all boxes regardless of orientation (top, side, angled) and size (small or large).

## 6. Multiple/Overlapping Box Rules
- **Multiple Boxes:** Each physical box gets its own distinct bounding box (e.g., 3 boxes = 3 bounding boxes). Do NOT merge separate boxes into one large box.
- **Touching Boxes:** If boundaries are distinguishable, draw separate bounding boxes.
- **Overlapping/Occluded:** Annotate each distinguishable box separately. Draw the box around the visible/determinable extent. Do not invent hidden boundaries. If a portion is too small or ambiguous to identify as a box, leave it unannotated.
- **Edge Cuts:** If a box is partially outside the image frame, only annotate the visible portion.

## 7. Shipping Carton Rule
- Shipping cartons/cardboard cartons MUST be labeled as the standard `box` class.
- Do NOT create a separate class for shipping cartons.

## 8. YOLO Export Format
- The final exported annotations must be in the standard YOLO format: `class_id x_center y_center width height`
- All coordinates must be normalized (0.0 to 1.0).
- Example: `0 0.512 0.438 0.321 0.276`
- Export the labels directly into `cv_pipeline/dataset/train_ready/labels/`.

## 9. Manual Annotation Instructions
1. Open your chosen annotation tool.
2. Ensure the class configuration has only `box` (class 0).
3. Systematically go through all 496 images and apply the rules above.
4. Export the final labels in YOLO format to the `labels/` directory.

## 10. Final Checklist
- [ ] 496 images loaded into the tool.
- [ ] Exactly 1 class (`box`) configured.
- [ ] All images manually annotated following the overlapping/touching rules.
- [ ] Labels exported in YOLO TXT format to `cv_pipeline/dataset/train_ready/labels/`.

READY FOR MANUAL ANNOTATION
