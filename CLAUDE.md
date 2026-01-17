# O2 Monitor - Claude Code Notes

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

## Secrets Location

Credentials are stored in `.secrets.md` (gitignored). Contains:
- GitHub PAT
- PagerDuty routing key
- Healthchecks.io ping URL

**If `.secrets.md` doesn't exist**, ask the user to create it or check their local setup.

## GitHub

- Repo: https://github.com/dmattox-sparkcodelabs/O2Monitor

## Running the App

**First time only** - create acknowledgment file:
```bash
echo "I understand this is not a medical device" > ACKNOWLEDGED_NOT_FOR_MEDICAL_USE.txt
```

Then use the scripts in the project root:
```bash
./start.sh    # Start the app
./stop.sh     # Stop the app
./restart.sh  # Restart the app
```

These scripts auto-detect whether the systemd service is installed and use the appropriate method.

**Logs:**
- If using systemd: `journalctl -u o2monitor -f`
- If running manually: `/tmp/o2monitor.log`

## Important: Bounce app after web changes

Flask caches templates and static files. After modifying any files in `src/web/`, restart the app:
```bash
./restart.sh
```

## Key Settings

- BLE polling: 5 seconds
- Late reading threshold: 30 seconds
- AVAPS on: >30W in 5-min window (otherwise off)
- Kasa plug IP: 192.168.4.126
- Oximeter MAC: C8:F1:6B:56:7B:F1

## Multi-Instance Development

Multiple Claude Code instances may work on this project simultaneously (e.g., Pi for backend, Windows for Android app).

**File ownership:**
- **Pi instance**: `src/` (Python backend, Flask API)
- **Windows instance**: `android/` (Android app)

**Coordination rules:**
1. Always `git pull origin main` before starting work
2. Commit and push when done with a logical chunk
3. If editing shared files, coordinate via commit messages
4. Check `android/TODO.md` for current task status

**Android app docs:**
- Design: `android/DESIGN.md`
- Tasks: `android/TODO.md`
