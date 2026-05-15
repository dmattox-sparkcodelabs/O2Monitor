# Vision-Based Sleep Monitoring Service

> **DISCLAIMER: NOT FOR MEDICAL USE**
>
> This software is a proof of concept for educational purposes only. It is NOT a certified medical device and should NOT be relied upon for medical monitoring, diagnosis, or treatment decisions.

## Overview

The Vision Service adds camera-based monitoring to detect when the target person (dad) falls asleep without their AVAPS mask. It runs on a Windows PC with GPU (RTX 3060) and provides an API that the Raspberry Pi polls for status.

**Alert Logic:**
```
IF face_detected AND is_dad AND eyes_closed > 5min AND no_mask → ALERT
```

## Architecture

```
┌─────────────────┐     RTSP     ┌──────────────────────────────────┐
│ Reolink Cameras │ ──────────── │     Vision Service (Windows)     │
│   (E1 Pro)      │              │         RTX 3060 GPU             │
└─────────────────┘              │                                  │
                                 │  ┌─────────────────────────────┐ │
                                 │  │     Detection Pipeline      │ │
                                 │  │  1. Face Recognition        │ │
                                 │  │  2. Eye State (EAR)         │ │
                                 │  │  3. Mask Detection          │ │
                                 │  └─────────────────────────────┘ │
                                 │                                  │
                                 │  ┌─────────────────────────────┐ │
                                 │  │    FastAPI Server :8100     │ │
                                 │  │  GET /status                │ │
                                 │  │  GET /health                │ │
                                 │  │  POST /cameras              │ │
                                 │  │  POST /enroll               │ │
                                 │  └─────────────────────────────┘ │
                                 └────────────────┬─────────────────┘
                                                  │
                                                  │ GET /status (30s)
                                                  │
                                 ┌────────────────┴─────────────────┐
                                 │     O2Monitor (Raspberry Pi)     │
                                 │                                  │
                                 │  VisionClient polls /status      │
                                 │  → Triggers PagerDuty on alert   │
                                 └──────────────────────────────────┘
```

## Camera State Machine

```
┌───────────────┐    dad detected    ┌────────────────┐    eyes closed + no mask    ┌───────────────┐
│     IDLE      │ ─────────────────► │     ACTIVE     │ ─────────────────────────► │     ALERT     │
│   poll: 5min  │ ◄───────────────── │   poll: 1min   │ ◄───────────────────────── │   poll: 1min  │
└───────────────┘  dad gone 10min    └────────────────┘   eyes open or mask on     └───────────────┘
```

**State Descriptions:**
- **IDLE**: Dad not detected in frame. Poll every 5 minutes.
- **ACTIVE**: Dad detected but conditions normal. Poll every 1 minute.
- **ALERT**: Dad's eyes closed for 5+ minutes without mask. Poll every 1 minute, trigger alert to Pi.

**Staggered Scheduling** (3 cameras, 5-min idle):
- Camera 1: 0:00, 5:00, 10:00...
- Camera 2: 1:40, 6:40, 11:40...
- Camera 3: 3:20, 8:20, 13:20...

## Project Structure

```
vision/
├── __init__.py                     # Package root
├── main.py                         # Entry point (python -m vision.main)
├── config.py                       # Pydantic Settings configuration
├── models/
│   ├── __init__.py
│   └── camera.py                   # CameraState, Camera, DetectionResult, VisionStatus
├── api/
│   ├── __init__.py
│   ├── server.py                   # FastAPI app factory
│   └── routes/
│       ├── __init__.py
│       ├── health.py               # GET /health
│       ├── status.py               # GET /status (Pi polls this)
│       ├── cameras.py              # Camera CRUD + snapshots
│       ├── enrollment.py           # POST /enroll
│       └── config_routes.py        # POST /config
├── detection/
│   ├── __init__.py
│   ├── pipeline.py                 # DetectionPipeline orchestrator
│   ├── face_recognition.py         # InsightFace/ArcFace wrapper
│   ├── eye_state.py                # MediaPipe + EAR algorithm
│   └── mask_detection.py           # YOLO/heuristic mask detector
├── capture/
│   ├── __init__.py
│   ├── http_snapshot.py            # HTTP snapshot capture (Amcrest)
│   ├── rtsp_stream.py              # OpenCV RTSP frame capture
│   └── camera_manager.py           # State machine + scheduler
├── data/                           # gitignored
│   ├── cameras.json                # Camera configurations
│   └── embeddings/                 # Face embeddings (*.npy)
└── requirements.txt                # Dependencies
```

## Detection Pipeline

The pipeline runs three stages on each captured frame:

### Stage 1: Face Recognition (InsightFace)

Uses the `buffalo_l` model from InsightFace for face detection and embedding extraction.

- **Detection**: Finds faces in frame with bounding boxes
- **Embedding**: Extracts 512-dimensional face embedding
- **Recognition**: Compares against enrolled embeddings using cosine similarity
- **Threshold**: Default 0.6 (60% similarity required for match)

### Stage 2: Eye State Detection (MediaPipe + EAR)

Uses MediaPipe Face Mesh to extract eye landmarks, then calculates Eye Aspect Ratio (EAR).

**EAR Formula:**
```
EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
```

Where p1-p6 are eye landmark points:
- p1, p4: Horizontal corners
- p2, p3: Upper eyelid
- p5, p6: Lower eyelid

**Thresholds with Hysteresis:**
- EAR < 0.2 → Eyes CLOSED
- EAR > 0.25 → Eyes OPEN

### Stage 3: Mask Detection (Heuristic)

Analyzes the lower face region for AVAPS mask characteristics:

1. **Color Variance**: Masks have uniform color (low hue variance)
2. **Edge Density**: Mask straps create distinctive edges
3. **Saturation**: Masks typically have lower saturation than skin

Requires 2 of 3 indicators for mask detection. A custom YOLO model trained on AVAPS mask images would improve accuracy.

## API Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check for load balancers |
| `/status` | GET | **Main endpoint** - Pi polls this for alerts |

**Status Response:**
```json
{
  "timestamp": "2026-01-18T15:30:00",
  "alert_active": true,
  "alert_reason": "Eyes closed without mask for 312s",
  "alert_camera_id": "cam_001",
  "alert_camera_name": "Bedroom",
  "eyes_closed_seconds": 312.5,
  "cameras": [...],
  "system": {
    "models_loaded": true,
    "gpu_available": true,
    "gpu_memory_used_mb": 2048.5,
    "uptime_seconds": 3600.0,
    "enrolled_faces": 5
  }
}
```

### Camera Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/cameras` | GET | List all cameras |
| `/cameras` | POST | Add camera |
| `/cameras/{id}` | GET | Get camera details |
| `/cameras/{id}` | PUT | Update camera |
| `/cameras/{id}` | DELETE | Remove camera |
| `/cameras/{id}/status` | GET | Detailed camera status |
| `/cameras/{id}/snapshot` | GET | Live JPEG snapshot |
| `/cameras/{id}/poll` | POST | Manually trigger detection |
| `/cameras/{id}/enable` | POST | Enable camera |
| `/cameras/{id}/disable` | POST | Disable camera |
| `/cameras/{id}/test` | POST | Test connection |

**Add Camera Request (HTTP snapshot - recommended):**
```json
{
  "name": "Bedroom Camera",
  "capture_type": "http",
  "snapshot_url": "http://admin:password@192.168.1.50/cgi-bin/snapshot.cgi",
  "enabled": true
}
```

**Add Camera Request (RTSP stream):**
```json
{
  "name": "Bedroom Camera",
  "capture_type": "rtsp",
  "rtsp_url": "rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=1",
  "enabled": true
}
```

### Enrollment

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/enroll` | POST | Upload face photos (multipart) |
| `/enroll/camera/{id}` | POST | Enroll from live camera |
| `/enroll/status` | GET | Get enrollment count |
| `/enroll` | DELETE | Delete all enrollments |

### Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/config` | GET | Get current config |
| `/config` | POST | Update config |
| `/config/reset` | POST | Reset to defaults |

## Configuration

Environment variables (prefix `VISION_`):

```bash
# Detection thresholds
VISION_DETECTION__EYES_CLOSED_ALERT_SECONDS=300    # 5 min
VISION_DETECTION__DAD_GONE_TIMEOUT_SECONDS=600     # 10 min
VISION_DETECTION__FACE_SIMILARITY_THRESHOLD=0.6
VISION_DETECTION__EAR_CLOSED_THRESHOLD=0.2
VISION_DETECTION__EAR_OPEN_THRESHOLD=0.25

# Polling intervals
VISION_CAMERA__IDLE_POLL_SECONDS=300               # 5 min
VISION_CAMERA__ACTIVE_POLL_SECONDS=60              # 1 min
VISION_CAMERA__ALERT_POLL_SECONDS=60               # 1 min
VISION_CAMERA__RTSP_TIMEOUT_SECONDS=10
VISION_CAMERA__MAX_RETRIES=3

# Server
VISION_SERVER__API_HOST=0.0.0.0
VISION_SERVER__API_PORT=8100

# GPU
VISION_GPU__DEVICE=0
```

## Installation

### Windows PC (Vision Service)

1. **Install Python 3.10+** and create virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

2. **Install PyTorch with CUDA:**
   ```bash
   pip install torch==2.1.2+cu121 --index-url https://download.pytorch.org/whl/cu121
   ```

3. **Install vision dependencies:**
   ```bash
   cd vision
   pip install -r requirements.txt
   ```

4. **Start the service:**
   ```bash
   python -m vision.main --host 0.0.0.0 --port 8100
   ```

### Raspberry Pi (Vision Client)

The vision client is included in the main O2Monitor application. Configure the vision service URL:

```bash
# In .env or environment
VISION_SERVICE_URL=http://192.168.1.100:8100
```

## Usage

### 1. Start the Vision Service

```bash
python -m vision.main
```

### 2. Add Cameras

```bash
# Using HTTP snapshot (recommended for Amcrest)
curl -X POST http://localhost:8100/cameras \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bedroom",
    "capture_type": "http",
    "snapshot_url": "http://admin:password@192.168.1.50/cgi-bin/snapshot.cgi"
  }'
```

### 3. Enroll Face

Upload photos of dad:
```bash
curl -X POST http://localhost:8100/enroll \
  -F "files=@photo1.jpg" \
  -F "files=@photo2.jpg" \
  -F "files=@photo3.jpg"
```

Or capture from camera:
```bash
curl -X POST http://localhost:8100/enroll/camera/cam_001
```

### 4. Test Detection

View snapshot:
```bash
curl http://localhost:8100/cameras/cam_001/snapshot > snapshot.jpg
```

Trigger manual poll:
```bash
curl -X POST http://localhost:8100/cameras/cam_001/poll
```

### 5. Check Status

```bash
curl http://localhost:8100/status
```

## Camera Setup

### Recommended Camera: Amcrest IP4M-1041B

The **Amcrest IP4M-1041B** (~$35) is recommended for this project:
- WiFi (no wiring needed)
- Native RTSP AND HTTP snapshot support
- Pan/Tilt for flexible positioning
- 4MP resolution
- Night vision
- HTTP snapshot endpoint (simpler than RTSP for single-frame capture)

**Note:** Reolink E1/E1 Pro cameras do NOT have standalone RTSP - they require a Reolink Home Hub or NVR. Avoid these cameras.

### Capture Methods

The vision service supports two capture methods:

1. **HTTP Snapshot (Recommended)** - Simpler, more reliable for single-frame capture
2. **RTSP Stream** - Traditional video stream, higher resource usage

HTTP snapshot is preferred for Amcrest cameras as it's simpler and more reliable.

### Amcrest URL Formats

**HTTP Snapshot (Recommended):**
```
http://admin:password@ip_address/cgi-bin/snapshot.cgi
http://admin:password@ip_address/cgi-bin/snapshot.cgi?channel=1
```

**RTSP Stream:**
```
rtsp://admin:password@ip_address:554/cam/realmonitor?channel=1&subtype=1
```

**RTSP Stream options:**
- Main stream (high res): `subtype=0`
- Sub stream (low res): `subtype=1` ← Recommended for detection

### Amcrest Camera Setup

1. **Power on camera** and wait for it to initialize
2. Install **Amcrest Smart Home** app on phone
3. Add camera and connect to WiFi
4. Find the camera's IP address:
   - Check your router's DHCP client list, or
   - Use the Amcrest app to view device info
5. Access web interface at `http://camera-ip`
6. Default credentials: `admin` / (set during setup)
7. Test snapshot: Open `http://admin:password@camera-ip/cgi-bin/snapshot.cgi` in browser

### Adding Amcrest Camera to Vision Service

**Using HTTP snapshot (recommended):**
```bash
curl -X POST http://localhost:8100/cameras \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bedroom",
    "capture_type": "http",
    "snapshot_url": "http://admin:password@192.168.1.50/cgi-bin/snapshot.cgi"
  }'
```

**Using RTSP stream:**
```bash
curl -X POST http://localhost:8100/cameras \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bedroom",
    "capture_type": "rtsp",
    "rtsp_url": "rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=1"
  }'
```

### Camera Settings

For optimal detection:
- Resolution: 640x480 or higher
- Frame rate: 10-15 fps is sufficient (for RTSP)
- Compression: H.264
- Night vision: Auto or IR mode

## Troubleshooting

### Vision Service Won't Start

1. **Check GPU drivers:**
   ```bash
   nvidia-smi
   ```

2. **Check CUDA availability:**
   ```python
   import torch
   print(torch.cuda.is_available())
   ```

3. **Check model downloads:**
   InsightFace downloads models on first use (~200MB).

### Camera Connection Failed

1. **Test RTSP URL with VLC:**
   ```
   vlc rtsp://admin:password@192.168.1.50:554/h264Preview_01_sub
   ```

2. **Check firewall rules** on camera and PC.

3. **Verify credentials** in camera web interface.

### Face Not Recognized

1. **Check enrollment count:**
   ```bash
   curl http://localhost:8100/enroll/status
   ```

2. **Enroll more photos** from different angles and lighting.

3. **Lower threshold** (default 0.6, try 0.5):
   ```bash
   curl -X POST http://localhost:8100/config \
     -H "Content-Type: application/json" \
     -d '{"face_similarity_threshold": 0.5}'
   ```

### Eyes Always Detected as Closed

1. **Check lighting** - EAR needs clear eye visibility.

2. **Adjust thresholds:**
   ```bash
   curl -X POST http://localhost:8100/config \
     -H "Content-Type: application/json" \
     -d '{"ear_closed_threshold": 0.15}'
   ```

### High GPU Memory Usage

- InsightFace buffalo_l: ~500MB
- MediaPipe: ~200MB
- YOLO (optional): ~300MB

Total: ~1GB VRAM typical

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.109.0 | Web framework |
| uvicorn | 0.27.0 | ASGI server |
| opencv-python | 4.9.0 | Image processing |
| insightface | 0.7.3 | Face recognition |
| mediapipe | 0.10.9 | Eye landmarks |
| ultralytics | 8.1.0 | YOLO detection |
| torch | 2.1.2+cu121 | GPU compute |
| pydantic-settings | 2.1.0 | Configuration |
