import sqlite3, os
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "records.db"
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "changeme")

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_name TEXT NOT NULL,
        event TEXT NOT NULL,
        timestamp TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS device_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        battery TEXT,
        location TEXT,
        device TEXT,
        weather TEXT,
        brightness TEXT,
        volume TEXT,
        timestamp TEXT NOT NULL)""")
    conn.commit()
    conn.close()

init_db()

app = FastAPI(title="查岗系统")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

class ReportBody(BaseModel):
    app_name: str
    event: str
    battery: Optional[str] = None
    location: Optional[str] = None
    device: Optional[str] = None
    weather: Optional[str] = None
    brightness: Optional[str] = None
    volume: Optional[str] = None

@app.post("/report")
async def report(body: ReportBody, req: Request):
    auth = req.headers.get("Authorization", "")
    if auth != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(401, "Unauthorized")
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO records (app_name, event, timestamp) VALUES (?, ?, ?)",
        (body.app_name, body.event, now))
    if any([body.battery, body.location, body.device, body.weather, body.brightness, body.volume]):
        conn.execute("""INSERT INTO device_status 
            (battery, location, device, weather, brightness, volume, timestamp) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.battery, body.location, body.device, body.weather, body.brightness, body.volume, now))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/ping")
async def ping():
    return "pong"

@app.get("/activity/summary")
async def summary():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT app_name, event, timestamp FROM records ORDER BY id DESC LIMIT 5")
    recent = cur.fetchall()
    cur.execute("SELECT app_name, event, timestamp FROM records ORDER BY id ASC")
    rows = cur.fetchall()
    # 获取最新设备状态
    cur.execute("SELECT battery, location, device, weather, brightness, volume, timestamp FROM device_status ORDER BY id DESC LIMIT 1")
    status = cur.fetchone()
    conn.close()
    sessions, opens = {}, {}
    for r in rows:
        app_name, ev, ts = r
        if ev == "open":
            opens[app_name] = datetime.fromisoformat(ts)
        elif ev == "close" and app_name in opens:
            gap = int((datetime.fromisoformat(ts) - opens[app_name]).total_seconds())
            sessions[app_name] = sessions.get(app_name, 0) + gap
            del opens[app_name]
    result = {"recent_apps": [r[0] for r in recent], "sessions": sessions}
    if status:
        result["device_status"] = {
            "battery": status[0],
            "location": status[1],
            "device": status[2],
            "weather": status[3],
            "brightness": status[4],
            "volume": status[5],
            "last_report": status[6]
        }
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
