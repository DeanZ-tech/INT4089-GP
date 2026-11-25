"""Smart Library MVP — real USB serial JSON Lines gateway and single-seat API."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from simulation import FLOORS, SCENARIOS, SimulationEngine
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
stop_serial = threading.Event()

PORT = os.getenv("SMART_LIBRARY_SERIAL_PORT", "").strip()
BAUD = int(os.getenv("SMART_LIBRARY_BAUD", "9600"))  # Must match original UNO V2.2.
ADMIN_TOKEN = os.getenv("SMART_LIBRARY_ADMIN_TOKEN", "")
DEMO = os.getenv("SMART_LIBRARY_DEMO", "0") == "1"
DB_PATH = Path(os.getenv("SMART_LIBRARY_DB", str(Path(__file__).with_name("events.db"))))
SEAT_ID = "A01"
# A literal canonical JSON line. UNO's low-memory parser accepts this exact form only.
RELEASE_LINE = '{"v":1,"type":"command","action":"RELEASE","id":"A01"}\n'


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def prepare_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS occupancy_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            floor_id TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            physically_occupied INTEGER NOT NULL,
            available INTEGER NOT NULL,
            away INTEGER NOT NULL,
            locked INTEGER NOT NULL,
            offline INTEGER NOT NULL,
            unknown INTEGER NOT NULL
        )""")


def record_event(kind: str, detail: dict) -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO events(created_at,kind,detail) VALUES (?,?,?)",
                   (timestamp(), kind, json.dumps(detail, ensure_ascii=False)))


def fetch_events() -> list[dict]:
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            "SELECT id,created_at,kind,detail FROM events ORDER BY id DESC LIMIT 35"
        ).fetchall()
    return [{"id": row[0], "time": row[1], "kind": row[2], "detail": json.loads(row[3])}
            for row in rows]


class Store:
    def __init__(self) -> None:
        self.current: dict | None = None
        self.last_rx: float | None = None
        self.boot: dict | None = None
        self.clients: set[WebSocket] = set()
        self.outbound: queue.Queue[str] = queue.Queue()
        self.pending_release = False
        self.last_ack: dict | None = None
        self.backend_error: str | None = None
        self.demo_locked = False
        self.demo_seq = 0
        self.demo_start = time.monotonic()
        self.running = True

    def snapshot(self) -> dict:
        connected = self.last_rx is not None and time.monotonic() - self.last_rx < 4.0
        effective = self.current.get("state", "UNKNOWN") if self.current else "UNKNOWN"
        physical = self.current.get("physical", "UNKNOWN") if self.current else "UNKNOWN"
        locked = bool(self.current.get("locked", False)) if self.current else bool(self.boot and self.boot.get("locked"))
        available = connected and not locked and physical == "FREE" and effective == "FREE"
        return {
            "seat_id": SEAT_ID, "connected": connected, "mode": "DEMO" if DEMO else "USB",
            "port": "SIMULATED" if DEMO else (PORT or "NOT CONFIGURED"),
            "physical": physical, "state": "LOCKED" if locked else effective,
            "locked": locked, "available": available,
            "reading": self.current, "boot": self.boot,
            "last_ack": self.last_ack, "pending_release": self.pending_release,
            "backend_error": self.backend_error,
        }

    async def broadcast(self) -> None:
        payload = {"kind": "update", "status": self.snapshot()}
        dead = []
        for ws in tuple(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def accept(self, payload: dict) -> None:
        # Reject non-protocol data rather than extracting from human-readable diagnostics.
        if not isinstance(payload, dict) or payload.get("v") != 1:
            return
        if payload.get("id") != SEAT_ID or payload.get("type") not in {"telemetry", "boot", "ack", "error"}:
            return
        kind = payload["type"]
        if kind == "ack" and (payload.get("action") != "RELEASE" or
                              payload.get("result") not in {"RELEASED", "NO_ACTIVE_LOCK"} or
                              type(payload.get("locked")) is not bool):
            self.backend_error = "Invalid RELEASE acknowledgement"
            return
        self.last_rx = time.monotonic()
        self.backend_error = None
        if kind == "telemetry":
            old = self.snapshot()
            self.current = payload
            updated = self.snapshot()
            if old["state"] != updated["state"] or old["locked"] != updated["locked"]:
                record_event("state_change", {"from": old["state"], "to": updated["state"],
                                              "locked": updated["locked"], "reason": payload.get("reason")})
            if old["state"] != updated["state"] or old["physical"] != updated["physical"] or old["locked"] != updated["locked"]:
                save_history(force=True)
        elif kind == "boot":
            self.boot = payload
            self.current = None
            self.pending_release = False  # Reconnect forces a fresh admin decision.
            record_event("boot", payload)
        elif kind == "ack":
            if self.boot is not None:
                self.boot = {**self.boot, "locked": payload["locked"]}
            self.last_ack = payload
            self.pending_release = False
            record_event("admin_ack", payload)
            # ACK provides immediate lock state; wait for next telemetry for full sensors.
            if self.current is not None and "locked" in payload:
                self.current = {**self.current, "locked": payload["locked"],
                                "state": "LOCKED" if payload["locked"] else "UNKNOWN"}
        elif kind == "error":
            self.backend_error = f"Device error: {payload.get('code', 'UNKNOWN')}"
            record_event("device_error", payload)
        await self.broadcast()
        await broadcast_world()


store = Store()
engine = SimulationEngine()


def serial_worker(loop: asyncio.AbstractEventLoop) -> None:
    """Only this worker opens/reads/writes the Arduino serial port."""
    try:
        import serial  # pyserial, not installed in some authoring environments
    except ImportError:
        store.backend_error = "Missing pyserial: pip install -r backend/requirements.txt"
        return
    while store.running:
        try:
            with serial.Serial(PORT, BAUD, timeout=0.3, write_timeout=1) as port:
                buffer = b""
                # Opening UNO USB serial usually causes automatic reset; await BOOT message.
                while store.running:
                    try:
                        line = store.outbound.get_nowait()
                    except queue.Empty:
                        line = None
                    if line:
                        port.write(line.encode("ascii"))
                        port.flush()
                    raw = port.read_until(b"\n", size=4096)
                    if raw:
                        buffer += raw
                        if len(buffer) > 4096:
                            raise ValueError("JSON line exceeds 4096 bytes")
                        if not buffer.endswith(b"\n"):
                            continue
                        try:
                            payload = json.loads(buffer.decode("utf-8").strip())
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            store.backend_error = f"Invalid serial JSON: {exc}"
                            logger.warning("%s", store.backend_error)
                            buffer = b""
                            continue
                        buffer = b""
                        future = asyncio.run_coroutine_threadsafe(store.accept(payload), loop)
                        future.add_done_callback(report_accept_error)
        except Exception as exc:
            store.backend_error = f"Serial {PORT} at {BAUD}: {type(exc).__name__}: {exc}"
            logger.warning("%s", store.backend_error)
            # Only device connectivity is affected; never mark a seat as available.
            store.last_rx = None
            # Never replay an obsolete admin release after reconnecting the USB device.
            while True:
                try:
                    store.outbound.get_nowait()
                except queue.Empty:
                    break
            store.pending_release = False
            stop_serial.wait(2)


def report_accept_error(future):
    if future.cancelled():
        return
    exc = future.exception()
    if exc is not None:
        store.backend_error = f"Serial message processing failed: {exc}"
        logger.error("%s", store.backend_error)


async def demo_loop() -> None:
    """Clearly marked simulated input, never reported as physical Arduino evidence."""
    await store.accept({"v": 1, "type": "boot", "id": "A01", "locked": False, "armed": True, "away_ms": 0})
    while store.running:
        elapsed = time.monotonic() - store.demo_start
        if elapsed < 5:
            physical, seat, tray, mm, away = "IN_USE", True, True, 90, 0
        elif elapsed < 8:
            physical, seat, tray, mm, away = "UNKNOWN", False, True, 172, 0
        else:
            physical, seat, tray, mm = ("AWAY", False, True, 172) if elapsed < 19 else ("IN_USE", True, True, 90)
            away = int(max(0, min(elapsed - 8, 11)) * 1000)
        if elapsed >= 18:
            store.demo_locked = True if not getattr(store, "demo_released", False) else False
        payload = {
            "v": 1, "type": "telemetry", "id": "A01", "seq": store.demo_seq,
            "ms": round(elapsed * 1000), "seat": seat, "tray_raw": 24 if tray else 800,
            "tray": tray, "distance_mm": mm, "distance_valid": True,
            "physical": physical, "state": "LOCKED" if store.demo_locked else physical,
            "locked": store.demo_locked, "armed": not store.demo_locked,
            "away_ms": away, "reason": "WAIT_ADMIN" if store.demo_locked else "NORMAL",
            "new_alert": store.demo_locked and store.demo_seq == 18,
        }
        store.demo_seq += 1
        await store.accept(payload)
        await asyncio.sleep(1)


def all_seats() -> list[dict]:
    seats = []
    status = store.snapshot()
    for floor_id, _, _ in FLOORS:
        for i in range(1, 21):
            sid = f"{floor_id}-{i:02d}"
            if floor_id == "F1" and i == 1:
                physical = status["physical"] if status["connected"] else "UNKNOWN"
                effective = status["state"] if status["connected"] else "OFFLINE"
                seats.append({
                    "id": sid, "hardware_id": "A01", "floor_id": floor_id,
                    "source": "ARDUINO" if not DEMO else "DEMO_INPUT",
                    "online": status["connected"], "physical": physical,
                    "state": effective, "locked": status["locked"],
                    "available": status["available"],
                    "away_ms": (status["reading"] or {}).get("away_ms", 0),
                    "reason": (status["reading"] or {}).get("reason", "NO_DATA"),
                })
            else:
                seats.append(engine.seats[sid].as_dict())
    return seats


def aggregate(rows: list[dict]) -> dict:
    capacity = len(rows)
    counted = {
        "capacity": capacity,
        "physically_occupied": sum(x["online"] and x["physical"] == "IN_USE" for x in rows),
        "occupied": sum(x["state"] == "IN_USE" for x in rows),
        "available": sum(x["available"] for x in rows),
        "away": sum(x["state"] == "AWAY" for x in rows),
        "locked": sum(x["locked"] for x in rows),
        "offline": sum(not x["online"] for x in rows),
        "unknown": sum(x["state"] == "UNKNOWN" for x in rows),
    }
    counted["occupancy_pct"] = round(100 * counted["physically_occupied"] / capacity, 1) if capacity else 0
    pct = counted["occupancy_pct"]
    counted["crowd_level"] = "HIGH" if pct >= 80 else "MODERATE" if pct >= 50 else "LOW"
    return counted


def world_snapshot() -> dict:
    seats = all_seats()
    floors = []
    for floor_id, title, area in FLOORS:
        row = [x for x in seats if x["floor_id"] == floor_id]
        floors.append({"id": floor_id, "name": title, "area": area, **aggregate(row)})
    real = [x for x in seats if x["source"] in ("ARDUINO", "DEMO_INPUT")]
    return {
        "generated_at": timestamp(), "seats": seats, "floors": floors,
        "summary": aggregate(seats), "real_summary": aggregate(real),
        "simulation": engine.as_dict(),
        "data_notice": "1 Arduino hardware seat + 59 simulated seats. Crowd level is a seat-occupancy proxy, NOT measured footfall.",
    }


async def broadcast_world() -> None:
    payload = {"kind": "world", "world": world_snapshot()}
    dead = []
    for ws in tuple(store.clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        store.clients.discard(ws)


last_history_at = 0.0

def save_history(force: bool = False) -> None:
    global last_history_at
    now = time.monotonic()
    if not force and now - last_history_at < 10:
        return
    world = world_snapshot()
    ts = timestamp()
    values = [(ts, f["id"], f["capacity"], f["physically_occupied"], f["available"],
               f["away"], f["locked"], f["offline"], f["unknown"]) for f in world["floors"]]
    values += [(ts, "ALL", world["summary"]["capacity"], world["summary"]["physically_occupied"],
                world["summary"]["available"], world["summary"]["away"], world["summary"]["locked"],
                world["summary"]["offline"], world["summary"]["unknown"])]
    # REAL row is for the hardware-only analysis filter.
    real = world["real_summary"]
    values.append((ts, "REAL", real["capacity"], real["physically_occupied"], real["available"],
                   real["away"], real["locked"], real["offline"], real["unknown"]))
    with sqlite3.connect(DB_PATH) as db:
        db.executemany("""INSERT INTO occupancy_samples(
            created_at,floor_id,capacity,physically_occupied,available,away,locked,offline,unknown
        ) VALUES (?,?,?,?,?,?,?,?,?)""", values)
        # limit history footprint; 5 samples per snapshot, 1000 snapshots retained
        db.execute("DELETE FROM occupancy_samples WHERE id <= (SELECT COALESCE(MAX(id),0)-5000 FROM occupancy_samples)")
    last_history_at = now


async def simulation_loop() -> None:
    previous = time.monotonic()
    save_history(force=True)
    while store.running:
        await asyncio.sleep(2)
        now = time.monotonic()
        changes = engine.tick(now - previous)
        previous = now
        for e in changes:
            if e["to"] == "LOCKED" or e["from"] == "LOCKED":
                record_event("sim_state_change", e)
        save_history(force=bool(changes))
        await store.broadcast()
        await broadcast_world()


class SimulationControl(BaseModel):
    scenario: str | None = None
    speed: int | None = None
    running: bool | None = None
    reset: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    prepare_db()
    store.running = True
    stop_serial.clear()
    if not DEMO and not PORT:
        store.backend_error = "SMART_LIBRARY_SERIAL_PORT is not configured"
    task = None
    simulation_task = asyncio.create_task(simulation_loop())
    thread = None
    if DEMO:
        task = asyncio.create_task(demo_loop())
    elif PORT:
        loop = asyncio.get_running_loop()
        thread = threading.Thread(target=serial_worker, args=(loop,), daemon=True)
        thread.start()
    try:
        yield
    finally:
        store.running = False
        stop_serial.set()
        for background in (simulation_task, task):
            if background:
                background.cancel()
                try:
                    await background
                except asyncio.CancelledError:
                    pass
        if thread:
            await asyncio.to_thread(thread.join, 3)
            if thread.is_alive():
                logger.error("Serial worker did not terminate within shutdown deadline")
        store.last_rx = None


app = FastAPI(title="Smart Library MVP", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/api/status")
async def status():
    return store.snapshot()


@app.get("/api/events")
async def events():
    return fetch_events()


@app.post("/api/seats/A01/release")
async def release(x_admin_token: str | None = Header(default=None)):
    if not ADMIN_TOKEN:
        raise HTTPException(503, "Set SMART_LIBRARY_ADMIN_TOKEN on the Python server before enabling release")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "Admin authorization failed")
    snapshot = store.snapshot()
    if not snapshot["connected"]:
        raise HTTPException(409, "Arduino is offline")
    if not snapshot["locked"]:
        raise HTTPException(409, "Seat is not locked")
    if store.pending_release:
        raise HTTPException(409, "Release command is already awaiting an Arduino response")
    store.pending_release = True
    record_event("release_requested", {"seat_id": SEAT_ID})
    if DEMO:
        store.demo_released = True
        store.demo_locked = False
        await store.accept({"v": 1, "type": "ack", "id": "A01", "action": "RELEASE",
                            "result": "RELEASED", "locked": False})
    else:
        store.outbound.put(RELEASE_LINE)
    await store.broadcast()
    return {"queued": True, "message": "Sent for Arduino execution; wait for ACK"}


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    store.clients.add(ws)
    await ws.send_json({"kind": "update", "status": store.snapshot()})
    await ws.send_json({"kind": "world", "world": world_snapshot()})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        store.clients.discard(ws)


@app.get("/api/world")
async def world():
    return world_snapshot()


@app.get("/api/floors")
async def floors():
    return world_snapshot()["floors"]


@app.get("/api/seats")
async def seats():
    return world_snapshot()["seats"]


@app.get("/api/analytics/overview")
async def analytics_overview():
    data = world_snapshot()
    return {"summary": data["summary"], "floors": data["floors"],
            "real_summary": data["real_summary"], "generated_at": data["generated_at"],
            "data_notice": data["data_notice"]}


@app.get("/api/analytics/occupancy")
async def analytics_occupancy(floor_id: str = "ALL", limit: int = 100):
    if floor_id not in {"ALL", "REAL", "F1", "F2", "F3"}:
        raise HTTPException(400, "Invalid floor filter")
    limit = max(1, min(240, limit))
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("""SELECT created_at,capacity,physically_occupied,available,away,
            locked,offline,unknown FROM occupancy_samples WHERE floor_id=?
            ORDER BY id DESC LIMIT ?""", (floor_id, limit)).fetchall()
    return {"floor_id": floor_id, "points": [
        {"time": r[0], "capacity": r[1], "physically_occupied": r[2],
         "available": r[3], "away": r[4], "locked": r[5], "offline": r[6],
         "unknown": r[7], "occupancy_pct": round(100*r[2]/r[1], 1) if r[1] else 0}
        for r in reversed(rows)
    ], "source": "RECORDED_SEAT_SNAPSHOTS", "footfall_measured": False}


@app.post("/api/simulation/control")
async def simulation_control(value: SimulationControl):
    try:
        engine.control(**value.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    record_event("simulation_control", engine.as_dict())
    save_history(force=True)
    await broadcast_world()
    return engine.as_dict()


@app.post("/api/simulated-seats/{seat_id}/release")
async def release_simulated(seat_id: str, x_admin_token: str | None = Header(default=None)):
    if not ADMIN_TOKEN:
        raise HTTPException(503, "Configure SMART_LIBRARY_ADMIN_TOKEN")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "Admin authorization failed")
    if seat_id not in engine.seats:
        raise HTTPException(404, "No such simulated seat")
    if not engine.release(seat_id):
        raise HTTPException(409, "Simulated seat is not locked")
    record_event("sim_admin_release", {"id": seat_id, "source": "SIMULATED"})
    save_history(force=True)
    await broadcast_world()
    return {"result": "RELEASED", "seat_id": seat_id, "source": "SIMULATED"}
