# O2 Monitor

> **DISCLAIMER: NOT FOR MEDICAL USE**
>
> This project is a proof of concept and educational exercise only. It is **NOT** a certified medical device and should **NOT** be relied upon for medical monitoring, diagnosis, or treatment decisions. This system has not been validated, tested, or approved for clinical use. Do not use this system as a substitute for professional medical care or FDA-approved monitoring equipment. The authors assume no liability for any use of this software.

---

## Overview

O2 Monitor is a Raspberry Pi-based proof of concept that demonstrates integration of consumer health devices with home automation and alerting systems. It connects to a Bluetooth pulse oximeter and a smart plug to monitor oxygen saturation levels and therapy device usage.

**This is an educational project exploring:**
- Bluetooth Low Energy (BLE) device communication
- Smart home device integration (Kasa smart plugs)
- Real-time web dashboards with Flask
- Alert escalation patterns (local audio, PagerDuty, Healthchecks.io)
- State machine design for monitoring applications

## Hardware Used

- Raspberry Pi 4
- Checkme O2 Max wrist oximeter (BLE)
- Kasa KP115 smart plug (WiFi)
- Powered PC speakers

## Features (Proof of Concept)

- Real-time SpO2 and heart rate display
- Historical data logging and visualization
- Configurable alert thresholds
- Local audio alerts with text-to-speech
- PagerDuty integration for remote notifications
- Web-based dashboard
- **Vision-based sleep monitoring** (detects eyes closed without mask)

## Quick Start

**Before first run**, you must acknowledge that this is not a medical device:

```bash
echo "I understand this is not a medical device" > ACKNOWLEDGED_NOT_FOR_MEDICAL_USE.txt
```

Then start the application:

```bash
# Start the application
./start.sh

# Stop the application
./stop.sh

# View logs
tail -f /tmp/o2monitor.log
```

The application will not start without the acknowledgment file.

Web dashboard available at: `http://<pi-ip>:5000`

## Vision Service

The optional vision service runs on a separate Windows PC with GPU to provide camera-based sleep monitoring. It detects when the target person falls asleep without their AVAPS mask.

**Hardware required:**
- Windows PC with NVIDIA GPU (tested on RTX 3060)
- Reolink E1 Pro cameras (or similar with RTSP support)

**Quick start:**
```bash
# On Windows PC
cd vision
pip install -r requirements.txt
python -m vision.main --host 0.0.0.0 --port 8100
```

See [VISION.md](VISION.md) for full documentation.

## Documentation

- [DESIGN.md](DESIGN.md) - System architecture and design decisions
- [VISION.md](VISION.md) - Vision service design and API reference
- [TODO.md](TODO.md) - Implementation checklist and session notes
- [CLAUDE.md](CLAUDE.md) - Development notes

## License

This project is provided as-is for educational purposes only. See disclaimer above.

## Contributing

This is a personal proof of concept project and is not actively seeking contributions.
