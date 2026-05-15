# O2 Monitor v2

> **DISCLAIMER: NOT FOR MEDICAL USE**
>
> This project is a proof of concept and educational exercise only. It is **NOT** a certified medical device and should **NOT** be relied upon for medical monitoring, diagnosis, or treatment decisions.

## Overview

Cloud-connected pulse oximetry monitoring using Android phones as BLE readers, Azure as the backend, and web + mobile frontends for visualization and alerting.

**Design in progress** — see `docs/` for specs.

## Architecture

```
[Checkme O2 Max] --BLE--> [Android App] --HTTPS--> [Azure Backend] ---> [Web App / Alerts]
```

## Archive

Previous v1 implementation (Pi-based + Windows capture) is preserved in `archive/` for reference.

## License

This project is provided as-is for educational purposes only. See disclaimer above.
