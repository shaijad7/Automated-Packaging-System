# Computer Vision Based Automated System for Smart Inventory Management

A computer-vision-based inventory management system that detects and tracks product boxes, counts them when they cross a configured line, reads QR codes, validates products against a database, and displays inventory information through a web dashboard.

## Overview

In a packaging or inventory environment, manually counting boxes and identifying their product type can be slow and error-prone.

This project automates the process using a camera, computer vision, QR validation, a backend API, MongoDB Atlas, and a web dashboard.

Implemented processing flow:

**Camera → YOLOv8 Detection → ByteTrack Tracking → Line Crossing → QR Detection/Validation → Inventory Event → MongoDB → Dashboard**

The system is designed around real camera input and real database records. It does not generate fake detections, counts, QR results, or inventory events.

## Problem Statement

Manual inventory counting can lead to:

- Incorrect box counts
- Difficulty identifying products
- Missed or unreadable product labels
- Delayed inventory updates
- Limited visibility into inventory exceptions

The goal of this project is to provide an automated computer-vision pipeline that can detect moving boxes, count unique tracked boxes, validate their QR information, and update inventory records.

## Key Features

### Computer Vision

- OpenCV camera capture
- Integrated camera and USB webcam support
- YOLOv8 object detection
- Single generic `box` detection class
- ByteTrack object tracking
- Stable track IDs across frames
- Configurable line-crossing detection
- Unique counting per tracked object
- Native OpenCV QR detection
- QR association with detected/tracked boxes
- QR result smoothing across frames

### QR Validation

QR payload format:

```text
INV|SKU
```

Examples:

```text
INV|EAR-001
INV|ADP-001
INV|MOB-001
```

Supported QR states:

- `VALID_QR`
- `NO_QR`
- `UNREADABLE_QR`
- `INVALID_QR`

Only a valid QR associated with a known active product is eligible for the corresponding inventory event.

### Backend

- FastAPI REST API
- JWT authentication
- bcrypt password hashing
- Admin-only application authorization
- MongoDB Atlas integration
- Product management
- Inventory records
- Event records
- Alert management
- Dashboard summary APIs
- Analytics APIs
- Health endpoint

### Product Management

Administrators can:

- Register products
- Set product SKU
- Add product descriptions
- Activate/deactivate products
- Generate standard QR labels
- Download QR labels
- Delete products

The backend generates:

```text
INV|<SKU>
```

for each registered product.

### Dashboard

The Next.js dashboard provides:

- Overall box count
- Valid QR count
- QR exception count
- Inventory added
- Current inventory
- Recent events
- Processing trend
- QR status distribution
- Inventory-by-product chart
- 24-hour, 7-day, 30-day and all-time analytics views

### Alerts

The backend detects QR exception spikes using a configurable threshold.

Default configuration:

- Exception threshold: `5`
- Time window: `10 minutes`
- Alert type: `QR_EXCEPTION_SPIKE`
- Severity: `WARNING`

Alerts can be:

- Open
- Acknowledged
- Resolved

Resolution information can include a reason, note, user, and timestamp.

### Reports

The dashboard provides report functionality based on recorded system events.

Reports use real stored event data rather than generated sample data.

## System Architecture

```text
                    ┌─────────────────────┐
                    │   Camera / Webcam   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   OpenCV Capture    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       YOLOv8        │
                    │    Box Detection    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      ByteTrack      │
                    │      Tracking       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Line Counter     │
                    │ Unique Box Counting │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    QR Detector      │
                    │ Association & Valid.│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      FastAPI        │
                    │       Backend       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    MongoDB Atlas    │
                    │ Products / Inventory│
                    │ Events / Alerts     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Next.js Dashboard │
                    │ Analytics / Alerts  │
                    │ Products / Reports  │
                    └─────────────────────┘
```

## Technology Stack

| Layer | Technology |
|---|---|
| Computer Vision | Python, OpenCV |
| Object Detection | YOLOv8 |
| Object Tracking | ByteTrack |
| QR Detection | OpenCV QRCodeDetector |
| Backend | FastAPI |
| Authentication | JWT + bcrypt |
| Database | MongoDB Atlas |
| Database Driver | PyMongo Async |
| Frontend | Next.js + TypeScript |
| UI | Tailwind CSS |
| Charts | Recharts |
| Runtime Platform | Windows |

## Project Structure

```text
smart-inventory-system/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   └── services/
│   ├── requirements.txt
│   └── .env.example
│
├── cv_pipeline/
│   ├── counting/
│   ├── models/
│   │   └── best.pt
│   ├── qr/
│   ├── dataset/
│   │   └── train_ready/
│   │       └── data.yaml
│   ├── camera.py
│   ├── detector.py
│   ├── run_pipeline.py
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   └── lib/
│   ├── package.json
│   └── package-lock.json
│
├── audit_dataset.py
└── .gitignore
```

## Hardware Requirements

The system was developed and tested with:

- Windows PC
- Integrated camera support
- External USB webcam
- USB webcam tested at 1920×1080 with a nominal 30 FPS driver setting
- Boxes/products for physical testing

The application supports selecting the configured camera source through environment configuration.

## Software Requirements

Recommended environment:

- Windows
- Python 3.x
- Node.js
- npm
- MongoDB Atlas account
- Git

Python dependencies are listed in:

```text
backend/requirements.txt
cv_pipeline/requirements.txt
```

Frontend dependencies are defined in:

```text
frontend/package.json
```

## Configuration

The repository contains example environment files:

```text
backend/.env.example
cv_pipeline/.env.example
```

Create local `.env` files from these examples.

### Backend

The backend requires configuration for:

- MongoDB Atlas connection
- JWT secret/configuration
- API settings
- Alert threshold/window

### Computer Vision

The CV pipeline requires configuration for:

- Camera source
- YOLO model path
- Detection confidence
- Camera resolution/FPS request
- Counting line configuration
- Backend event API configuration

**Do not commit `.env` files or real credentials to GitHub.**

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/shaijad7/Automated-Packaging-System.git
cd Automated-Packaging-System
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create:

```text
backend/.env
```

using:

```text
backend/.env.example
```

Configure the MongoDB Atlas connection and required secrets.

### 3. Computer vision setup

From the project root:

```bash
cd cv_pipeline
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create:

```text
cv_pipeline/.env
```

using:

```text
cv_pipeline/.env.example
```

The trained model is included at:

```text
cv_pipeline/models/best.pt
```

### 4. Frontend setup

Open another terminal:

```bash
cd frontend
npm install
```

## Running the Application

### Start the backend

From `backend`:

```bash
uvicorn app.main:app --reload
```

### Start the frontend

From `frontend`:

```bash
npm run dev
```

Open the local Next.js application in a browser.

### Start the computer-vision pipeline

From `cv_pipeline`:

```bash
python run_pipeline.py
```

The CV application opens the native AI processing window and uses the configured camera.

Press:

```text
q
```

to exit the processing window.

## Product and QR Workflow

A product is registered with:

```text
Product Name
SKU
Description
Active Status
```

The backend automatically generates:

```text
INV|SKU
```

For example:

```text
SKU: ADP-001
QR payload: INV|ADP-001
```

The generated label contains:

- Product name
- Standard black-and-white QR code

During processing:

```text
QR detected
     ↓
QR decoded
     ↓
SKU extracted
     ↓
Tracked box association
     ↓
Product lookup
     ↓
Valid / Invalid result
```

## Inventory Event Workflow

When a tracked box crosses the configured counting line, the system creates a counting event.

Events contain information such as:

- Event ID
- Track ID
- Direction
- QR status
- QR data when available
- SKU when available
- Timestamp

Overall physical box counting is independent of QR success:

```text
Overall Boxes =
VALID_QR
+ NO_QR
+ UNREADABLE_QR
+ INVALID_QR
```

A QR exception does not automatically mean that the physical box was not counted.

## QR Status Definitions

### `VALID_QR`

A QR code was detected and decoded, the payload is usable, the QR was associated with the tracked box, and the SKU belongs to a known active product.

### `NO_QR`

No QR region/code was detected.

### `UNREADABLE_QR`

A QR-like region was detected, but its payload could not be decoded successfully.

### `INVALID_QR`

A QR payload was decoded, but it could not be accepted as a valid registered product identifier or the association was invalid/ambiguous.

## Dashboard

The dashboard is designed as an industrial production-control interface.

It includes:

- Dashboard overview
- Product and inventory management
- Alerts
- Reports
- Settings
- Responsive desktop, tablet, and mobile layouts

The dashboard uses real backend data. When there are no records, the interface shows an empty state rather than fabricated values.

## Analytics

Analytics supports:

- All-time
- Last 24 hours
- Last 7 days
- Last 30 days

The processing trend contains:

- Overall boxes
- Valid QR
- Exceptions

QR distribution contains:

- Valid QR
- No QR
- Unreadable QR
- Invalid QR

Inventory analytics are based on current inventory records.

## Alerts

QR exception alerts are generated from real event data.

Default configuration:

```text
Threshold: 5 exceptions
Window: 10 minutes
Alert: QR_EXCEPTION_SPIKE
Severity: WARNING
```

The system avoids creating duplicate alerts for the same active exception spike.

Alert lifecycle:

```text
OPEN
  ↓
ACKNOWLEDGED
  ↓
RESOLVED
```

Direct resolution from `OPEN` is also supported.

## Authentication

The application uses:

- JWT access tokens
- bcrypt password hashing
- Admin-only application authorization
- Browser session storage for frontend authentication

The computer-vision edge/event API uses its separate API-key mechanism rather than treating the camera process as a normal browser user.

## Model and Dataset

The project uses a custom YOLOv8 model trained for one object class:

```text
box
```

The dataset contains real images of:

- Mobile phone boxes
- Charger boxes
- Type-C converter/adapter boxes
- Shipping cartons

The dataset includes variation in:

- Backgrounds
- Object orientation
- Distance
- Multiple/touching boxes
- Partial occlusion
- Lighting
- Empty scenes
- Hands/persons
- Motion and reflections

The trained model included in this repository is:

```text
cv_pipeline/models/best.pt
```

The complete training dataset is **not included in this Git repository** because of its size.

## Model Training

The model was trained using:

- YOLOv8n
- 396 training images
- 100 validation images
- Image size: 640
- Batch size: 2
- 50 epochs
- CPU training
- Deterministic split with seed 42

Recorded validation metrics:

```text
Precision:      0.9866
Recall:         1.0000
mAP@50:         0.9936
mAP@50-95:      0.8700
```

These metrics are from dataset validation and should not be interpreted as guaranteed real-world performance.

## Testing

Testing during development included:

### Backend

- Authentication
- JWT validation
- Password hashing
- Product registration
- Duplicate SKU validation
- QR label generation
- Dashboard APIs
- Analytics
- Inventory
- Events
- Alerts
- Alert state transitions
- Admin authorization

### Computer Vision

- Camera discovery
- Camera connection/reconnection
- YOLO model loading
- Empty detections
- ByteTrack tracking
- Line crossing
- QR detection
- QR association
- QR status handling
- Physical camera testing

### Frontend

- Login flow
- Dashboard navigation
- Product management
- QR label download
- Alerts
- Reports
- Settings
- Responsive layouts
- TypeScript compilation
- Production build

## Current Limitations

### Model Generalization

The trained model showed false positives when the live camera background differed significantly from the training dataset.

The training dataset was affected by background bias, so further dataset improvement/retraining is recommended.

### Conveyor Validation

The project has been tested with real camera input and manually moved/static boxes, but a complete physical conveyor setup was not available for final end-to-end validation.

Therefore, conveyor-specific performance such as belt speed, final camera geometry, exact line placement, production lighting, and high-speed motion blur has not been fully validated.

### CPU Performance

The project was developed and trained on CPU hardware.

Real-world inference speed depends on camera resolution, CPU performance, model size, scene complexity, lighting, and exposure time.

### QR Reading Conditions

QR recognition can vary with distance, angle, lighting, motion blur, reflections, print quality, and occlusion.

QR smoothing was added to reduce frame-to-frame status instability.

### Production Deployment

The current repository is primarily a Windows-first development/project implementation. A fresh-machine production deployment process and final physical production validation remain future work.

## Future Improvements

Possible future improvements include:

- Retraining the detector with more diverse backgrounds
- Adding more conveyor-distance images
- Final conveyor-based calibration
- GPU acceleration
- Improved camera exposure handling
- More robust QR recognition under motion
- Production deployment automation
- Additional dataset expansion
- Further real-world performance evaluation

## Project Status

### Implemented

- Camera capture
- YOLOv8 detection
- ByteTrack tracking
- Line-crossing counting
- QR detection
- QR association and validation
- Product registration
- QR label generation
- MongoDB inventory
- Event processing
- Dashboard
- Analytics
- Alerts
- Reports
- Authentication
- Responsive frontend
- Trained YOLOv8 model

### Remaining Validation

- Full physical conveyor end-to-end validation
- Further model generalization/retraining
- Final production deployment validation

## Repository

GitHub: https://github.com/shaijad7/Automated-Packaging-System

## Author

**Shaik**

Final-Year Project

**Computer Vision Based Automated System for Smart Inventory Management**
