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

| Component | Verified Version | Notes |
|---|---|---|
| **Operating System** | Windows 10 / 11 (64-bit AMD64) | Tested on Windows 11 AMD64. |
| **Python** | 3.10, 3.11, 3.12, 3.13 (64-bit) | Verified on Python 3.13.7 (64-bit). Prebuilt binary wheels used; **no C/C++ compiler or MSVC required**. |
| **Node.js** | 20.x or 22.x LTS | Verified on Node.js v22.17.1. |
| **npm** | 10.x | Verified on npm 10.9.2. |
| **Database** | MongoDB Atlas or local MongoDB | PyMongo Async client with TLS support. |
| **Git** | 2.x | Standard Git client. |

---

## Configuration & Environment Variables

The repository includes template files for each component:
- `backend/.env.example`
- `cv_pipeline/.env.example`
- `frontend/.env.example`

### 1. Backend (`backend/.env`)

Copy `backend/.env.example` to `backend/.env`:

```ini
# Database Configuration
MONGODB_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=smart_inventory

# Security Configuration
JWT_SECRET_KEY=generate_a_long_random_secret_key_here
EDGE_NODE_API_KEY=your_shared_edge_node_api_key_12345

# CORS Configuration (Frontend origin)
API_CORS_ORIGINS=http://localhost:3000

# Alert Thresholds
ALERT_EXCEPTION_THRESHOLD=5
ALERT_EXCEPTION_WINDOW_MINUTES=10
```

> **IMPORTANT**: `EDGE_NODE_API_KEY` is a dedicated machine-to-machine key used by the computer-vision edge node. It is **not** a user JWT token.

### 2. Computer Vision Pipeline (`cv_pipeline/.env`)

Copy `cv_pipeline/.env.example` to `cv_pipeline/.env`:

```ini
# Edge Node Identity (MUST exactly match EDGE_NODE_API_KEY in backend/.env)
EDGE_NODE_API_KEY=your_shared_edge_node_api_key_12345

# Backend API URL
BACKEND_API_URL=http://localhost:8000

# Camera Source: 0 is usually integrated camera, 1 is usually first external USB webcam
CAMERA_SOURCE=0
CAMERA_WIDTH=1280
CAMERA_HEIGHT=720
CAMERA_FPS=30

# YOLO Model Configuration (Path relative to cv_pipeline/ or repo root)
YOLO_MODEL_PATH=models/best.pt
YOLO_CONFIDENCE_THRESHOLD=0.5
TARGET_CLASS_NAME=box

# Counting Line Configuration (adjust for conveyor/feed geometry)
LINE_START_X=0
LINE_START_Y=400
LINE_END_X=1280
LINE_END_Y=400

# Event Spool Configuration (defaults to data/event_spool.db, max 10000 events)
EVENT_SPOOL_PATH=data/event_spool.db
EVENT_SPOOL_MAX_SIZE=10000
```

### 3. Frontend (`frontend/.env.local`)

Create `frontend/.env.local` (optional, defaults to `http://localhost:8000/api`):

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

---

## Installation Guide (Windows)

All commands are shown for both **PowerShell** and **Command Prompt (`cmd.exe`)**. Works across VS Code Terminal, Windows Terminal, and IDE integrated terminals.

### Step 1: Clone the Repository

```powershell
git clone https://github.com/shaijad7/Automated-Packaging-System.git
cd Automated-Packaging-System
```

---

### Step 2: Backend Setup

#### Using PowerShell:
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your MongoDB Atlas URI and secrets
```

#### Using Command Prompt (`cmd.exe`):
```cmd
cd backend
python -m venv venv
venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

---

### Step 3: Computer Vision Pipeline Setup

Open a second terminal window.

#### Using PowerShell:
```powershell
cd cv_pipeline
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Verify that EDGE_NODE_API_KEY in cv_pipeline/.env matches backend/.env
```

#### Using Command Prompt (`cmd.exe`):
```cmd
cd cv_pipeline
python -m venv venv
venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

> **Note on Prebuilt Wheels**: `cv_pipeline/requirements.txt` specifies `ultralytics>=8.3.40` and `lap>=0.5.12`, which install 100% prebuilt binary wheels for Python 3.13 Windows 64-bit (`numpy-2.5.4`, `lap-0.5.13`, `opencv-python-5.0.0.93`, `torch-2.14.1`). No local C compiler or build tools are needed.

---

### Step 4: Frontend Setup

Open a third terminal window.

```powershell
cd frontend
npm install
```

> **CRITICAL WARNING**: **Never run `npm audit fix --force`**. This command attempts to downgrade `eslint-config-next` to version 14.2.35, which breaks Next.js 16 flat-config exports and crashes both ESLint and `next build`.

---

## Running the Application

### 1. Start the Backend API

From `backend` directory with `venv` activated:

```powershell
uvicorn app.main:app --reload --port 8000
```
- API Base URL: `http://localhost:8000`
- Interactive Swagger API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/health`

### 2. Start the Frontend Dashboard

From `frontend` directory:

```powershell
npm run dev
```
- Open `http://localhost:3000` in your browser.
- Production build alternative:
  ```powershell
  npm run build
  npm start
  ```

### 3. Run Camera Discovery (Optional)

Before starting the CV pipeline, you can discover all connected camera devices and their supported backends:

From `cv_pipeline` directory with `venv` activated:
```powershell
python discover_cameras.py
```
Note the detected index (e.g., `0` for integrated webcam, `1` for external USB camera) and update `CAMERA_SOURCE` in `cv_pipeline/.env`.

### 4. Start the Computer Vision Pipeline

From `cv_pipeline` directory with `venv` activated:

```powershell
python run_pipeline.py
```

- Opens the OpenCV real-time visual feed with tracking boxes, centroid tracks, counting line, and QR status overlay.
- Transmits line-crossing events to `http://localhost:8000/api/events/` via background worker.
- Press `q` or `Ctrl+C` in the terminal to stop gracefully.

---

## Running Tests

All tests are verified and can be executed independently.

### Backend Tests (100% Database Isolated)

> **Database Safety Guarantee**: All test scripts run against dedicated temporary test databases (`smart_inventory_test_*`) and drop them immediately upon completion. Real inventory records, production events, and real administrator credentials are never modified, overwritten, or deleted.

From `backend` directory with `venv` activated:

```powershell
# Authentication, JWT, and RBAC tests
python test_auth_logic.py

# Inventory counting and duplicate event idempotency tests
python test_phase10b_backend.py

# Ambiguous QR status and API key security tests
python test_ambiguous_backend.py

# Product registration, duplicate SKU, and label PNG tests
python test_registration.py

# Alert threshold, state transitions, and deduplication tests
python test_phase14a_final.py
```

### Computer Vision Tests (69 Unit Tests)

From project root or `cv_pipeline` directory with `venv` activated:

```powershell
pytest cv_pipeline/tests/ -v
```

Tests cover:
- `test_api_client.py`: `X-API-Key` headers, event submission, production worker acknowledgement validation, retry logic, 401 response handling.
- `test_association.py`: Spatial IoU bounding box association, multi-box deduplication.
- `test_counting_independence.py`: Counting line independence from QR success, double-count prevention.
- `test_event_spool.py`: Durable SQLite WAL event spooling, restart recovery, retry backoff, bounded 401 handling, capacity limits, idempotent duplicate acknowledgement.
- `test_model_and_camera.py`: Missing model honesty, class 0 (`box`) verification, camera disconnect handling.
- `test_payload_validator.py`: `INV|<SKU>` syntax validation, corrupted prefix/separator rejection.
- `test_qr_detector.py`: Native OpenCV QR detector, crop ROI offsets, duplicate suppression.
- `test_smoother.py`: Multi-frame QR payload smoothing, expiration, reappearing track reset.

### Frontend Quality Checks

From `frontend` directory:

```powershell
# Lint check (0 errors)
npm run lint

# TypeScript verification and production build
npm run build
```

---

## Troubleshooting Guide

### 1. `numpy` build failure during `pip install` on Python 3.13
- **Cause**: Older packages pinned `numpy<2.0.0`, for which no prebuilt wheels exist on Python 3.13 Windows. Pip attempts to build NumPy from source using local MinGW/GCC and fails.
- **Fix**: Use our updated `cv_pipeline/requirements.txt` with `ultralytics>=8.3.40`, which allows `numpy>=2.1.0` prebuilt binary wheels.

### 2. `ModuleNotFoundError: No module named 'lap'` during CV tracking
- **Cause**: ByteTrack tracker requires `lap` (Linear Assignment Problem solver).
- **Fix**: Install `lap>=0.5.12`. Prebuilt wheels (`lap-0.5.13-cp313-win_amd64.whl`) are now included in `cv_pipeline/requirements.txt`.

### 3. HTTP 401 Unauthorized when CV submits events to `POST /api/events/`
- **Cause**: `EDGE_NODE_API_KEY` in `cv_pipeline/.env` does not match `EDGE_NODE_API_KEY` in `backend/.env`.
- **Fix**: Ensure both files have identical values for `EDGE_NODE_API_KEY`. The CV client transmits this key via the `X-API-Key` HTTP header.

### 4. Next.js ESLint crash: `Cannot find module 'eslint-config-next'` or flat config errors
- **Cause**: Running `npm audit fix --force` forcibly downgrades `eslint-config-next` to version 14.
- **Fix**: Keep `eslint-config-next` at `16.3.8` (matching `next@16.3.8`). Do not use `--force`. The 5 high vulnerabilities reported by `npm audit` are strictly development dependencies of ESLint and do not affect the production app.

### 5. Camera fails to open on Windows (`cv2.VideoCapture` returns `False`)
- **Cause**: Incorrect `CAMERA_SOURCE` index, camera in use by another application (Zoom, Teams, Camera app), or Windows Privacy permissions blocking desktop camera access.
- **Fix**:
  1. Run `python discover_cameras.py` to identify the correct device index.
  2. Close any apps using the camera.
  3. Ensure **Settings > Privacy & security > Camera > Let desktop apps access your camera** is enabled.
  4. The pipeline uses `cv2.CAP_DSHOW` (DirectShow) backend on Windows for reliable low-latency capture.

### 6. Missing model file
- **Behavior**: If `models/best.pt` is missing, `YoloDetector` honestly logs `[Detector] Model unavailable: File 'models/best.pt' not found on disk.` and safely yields empty detections without crashing or fabricating bounding boxes.
- **Resolution**: Verify that `cv_pipeline/models/best.pt` (6.24 MB) is present in the repository.


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

### Durable Event Spooling & Recovery

Outbound inventory line-crossing events are durably persisted to an on-disk SQLite database (`outbound_spool` table with Write-Ahead Logging) before attempting network transmission to the backend. If network connectivity drops, the process crashes, or power is interrupted, unacknowledged events remain safely spooled on disk and are automatically recovered and transmitted in chronological order upon pipeline restart. For complete architecture, durability guarantees, maintenance commands, and safe spool-clearing procedures, see [docs/EVENT_SPOOLING.md](docs/EVENT_SPOOLING.md).

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
