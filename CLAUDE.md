SparkTalk identity: Big_Bubba-O2Monitor-Claude
ClaudeTalk identity: Big_Bubba-O2Monitor
Shared environment - python, node, etc. instances must be killed with caution

# O2 Monitor v2 - Claude Code Notes

> **DISCLAIMER: NOT FOR MEDICAL USE**
>
> This project is a proof of concept and educational exercise only. It is NOT a certified medical device and should NOT be relied upon for medical monitoring, diagnosis, or treatment decisions. This system has not been validated, tested, or approved for clinical use. Do not use this system as a substitute for professional medical care or FDA-approved monitoring equipment. The authors assume no liability for any use of this software.

---

> **WARNING TO CLAUDE: DO NOT ADD SECRETS TO THIS FILE**
>
> This file is checked into git. Credentials belong in `.secrets.md` (gitignored).
> The pre-commit hook will block you if you try to add API keys, tokens, or passwords here.
>
> **NEVER use `git commit --no-verify`** - If the hook blocks you, fix the problem, don't bypass it.

## Project Status

**v2 Redesign** — Starting fresh. The Pi-based backend and Windows capture app are retired.

New architecture: Android-first BLE reader → Azure cloud backend → Web + Android frontends.

## Archive

All v1 code lives in `archive/`. Reference it for:
- BLE protocol (`archive/windows/protocol.py`) — cleanest implementation of Checkme O2 Max protocol
- Android BLE + relay app (`archive/android/`) — proven Kotlin BLE code
- Alert logic & thresholds (`archive/src/alert_evaluator.py`, `archive/src/config.py`)
- Data models (`archive/src/models.py`)
- Vision service (`archive/vision/`) — camera-based sleep monitoring (may revisit later)
- Original design docs (`archive/DESIGN.md`, `archive/VISION.md`, `archive/TODO.md`)

## Secrets Location

Credentials are stored in `.secrets.md` (gitignored). Contains:
- GitHub PAT
- PagerDuty routing key
- Healthchecks.io ping URL
- Azure credentials (TBD)

**If `.secrets.md` doesn't exist**, ask the user to create it or check their local setup.

## GitHub

- Repo: https://github.com/dmattox-sparkcodelabs/O2Monitor

## Hardware

- **Oximeters**: Checkme O2 Max (Wellue/Viatom) — two identical units
  - Dad's device MAC: C8:F1:6B:56:7B:F1
  - Dev device MAC: D4:30:77:4B:0F:C7
- **Phones**: Android (BLE readers + app UI)

## Key BLE Details

- Device names: "O2M ####" pattern
- BLE-GATT UUIDs:
  - RX (device→host): `0734594a-a8e7-4b1a-a6b1-cd5243059a57`
  - TX (host→device): `8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3`
- Command 0x17: real-time sensor reading (SpO2, HR, battery, movement)
- CRC-8-CCITT with polynomial 0x07
- See `archive/windows/protocol.py` for full protocol docs

## Port Assignments (Slot #11)
- Frontend (Next.js): 6013
- Azure Functions API: 7071
- Caddy HTTPS proxy: 7072
- Backend (reserved): 7013

## Process Cleanup
NEVER use blanket taskkill on python/node. Only kill processes on YOUR assigned ports.
