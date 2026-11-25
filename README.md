# SeatSense

![SeatSense](images/branding/seatsense-logo.png)

SeatSense is the INT4089 Group G smart library seat prototype. An Arduino UNO reads a seat pressure mat, a tray pressure sensor and a VL53L0X distance sensor, displays status on an OLED, and sends JSON Lines over USB to a FastAPI backend and React dashboard.

The dashboard represents 60 seats across three floors: **one hardware seat (A01, shown as F1-01) and 59 simulated seats**. A timeout creates a software review lock. Staff inspect the seat and use Review & Release; a device acknowledgement confirms the release. The lock does not physically lock a chair.

## Supporting materials

| Material | Files |
| --- | --- |
| Complete English user manual | [Illustrated manual](docs/SeatSense_User_Manual.pdf) |
| Circuit and wiring references | [Signal diagram](images/wiring/signal-connections.png), [overall wiring 1](images/wiring/overall-wiring-01.png), [overall wiring 2](images/wiring/overall-wiring-02.png), [pin table and hardware guide](hardware/README.md) |
| Arduino sketch | [SeatMonitorOLED_V2_3_JSONL.ino](arduino/SeatMonitorOLED_V2_3_JSONL/SeatMonitorOLED_V2_3_JSONL.ino) |
| Arduino libraries | [Library versions, installation and official links](docs/Arduino_Libraries.md) |
| Backend and frontend source | [Python backend](backend), [React frontend](frontend), [serial protocol](PROTOCOL.md) |
| 3D prototype design pictures | [Combined preview](hardware/3d-design/preview.png), [table](hardware/3d-design/table_preview.png), [chair](hardware/3d-design/chair_preview.png) |
| Printable STL files | [Table STL](hardware/3d-design/table_model.stl), [chair STL](hardware/3d-design/chair_model.stl) |
| Editable 3D design | [Table SCAD](hardware/3d-design/table_model.scad), [chair SCAD](hardware/3d-design/chair_model.scad), [dimensions](hardware/3d-design/README.md) |
| Component and assembly photographs | [Hardware guide](hardware/README.md), [components](images/components), [assembly](images/assembly) |
| Dashboard and OLED screenshots | [Illustrated gallery](docs/Image_Gallery.md) |
| Video | No video is included in this submission. |

The diagram shows signal connections; the bench photographs document assembly. Check module voltage markings and wire endpoints against the hardware guide. Printable design files are provided alongside the photographed prototype.

## Run the project

Use Arduino IDE with the Arduino UNO board selected, Python 3.12, and a Node.js installation compatible with the supplied Vite frontend. Frontend dependencies are recorded in `frontend/package-lock.json`; Python dependencies are in `backend/requirements.txt`.

### 1 Upload the Arduino sketch

Install the [Arduino libraries](docs/Arduino_Libraries.md), open the sketch and upload it to the UNO. Serial communication uses **9600 baud**. Close Serial Monitor before starting the backend, because both applications need the same serial port.

The supplied sketch uses a **10-second away timeout for the accelerated demonstration**, not a 15-minute deployed policy. Relevant constants, including the 140 mm distance boundary and tray hysteresis values of 300/500, are in the sketch and need to match the physical installation.

### 2 Start the backend

From the repository root, Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:SMART_LIBRARY_SERIAL_PORT="COM5" # Replace with the actual UNO port
$env:SMART_LIBRARY_BAUD="9600"
$env:SMART_LIBRARY_ADMIN_TOKEN="replace-with-your-own-private-token"
Remove-Item Env:SMART_LIBRARY_DEMO -ErrorAction SilentlyContinue
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

macOS/Linux, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export SMART_LIBRARY_SERIAL_PORT="/dev/cu.usbmodemXXXX" # Replace with the actual UNO port
export SMART_LIBRARY_BAUD="9600"
export SMART_LIBRARY_ADMIN_TOKEN="replace-with-your-own-private-token"
unset SMART_LIBRARY_DEMO
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Run one backend process. `SMART_LIBRARY_DB` optionally selects the SQLite database path; otherwise it is `backend/events.db`. This is a local demonstration application with a shared administrative token.

### 3 Start the dashboard

In a separate terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. The backend API documentation is at <http://127.0.0.1:8000/docs>. These are local runtime addresses; the supporting-material links above are repository links.

### Optional software demonstration

Set `SMART_LIBRARY_DEMO=1` before starting the backend to generate the A01 input without a connected Arduino. In this mode A01 is also simulated. Leave the variable unset for hardware operation. The other 59 seats are simulated in either mode.

### Software checks

```bash
pip install -r requirements-dev.txt
python -m pytest backend -q
```

Build the frontend with `npm run build` from `frontend`. For a separate real serial check, close the backend and Serial Monitor, then run `python backend/serial_smoke_test.py <actual-port>`. Software tests and screenshots do not constitute calibration or hardware acceptance measurements.

## Group G

| Member | Student number |
| --- | --- |
| ZHONG DIAN | 11537876 |
| LI YANYAO | 11684980 |
| GUAN LIQIAN | 11534575 |
