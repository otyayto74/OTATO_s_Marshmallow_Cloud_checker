import os
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from supabase import create_client
import uvicorn

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "changeme")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    supabase.table("records").insert({
        "app_name": body.app_name,
        "event": body.event,
        "timestamp": now
    }).execute()
    if any([body.battery, body.location, body.device, body.weather, body.brightness, body.volume]):
        supabase.table("device_status").insert({
            "battery": body.battery,
            "location": body.location,
            "device": body.device,
            "weather": body.weather,
            "brightness": body.brightness,
            "volume": body.volume,
            "timestamp": now
        }).execute()
    return {"status": "ok"}

@app.get("/ping")
async def ping():
    return "pong"

@app.get("/activity/summary")
async def summary():
    recent_res = supabase.table("records").select("app_name, event, timestamp").order("id", desc=True).limit(5).execute()
    recent = recent_res.data
    all_res = supabase.table("records").select("app_name, event, timestamp").order("id").execute()
    rows = all_res.data
    status_res = supabase.table("device_status").select("*").order("id", desc=True).limit(1).execute()
    status = status_res.data[0] if status_res.data else None
    sessions, opens = {}, {}
    for r in rows:
        app_name, ev, ts = r["app_name"], r["event"], r["timestamp"]
        if ev == "open":
            opens[app_name] = datetime.fromisoformat(ts)
        elif ev == "close" and app_name in opens:
            gap = int((datetime.fromisoformat(ts) - opens[app_name]).total_seconds())
            sessions[app_name] = sessions.get(app_name, 0) + gap
            del opens[app_name]
    result = {"recent_apps": [r["app_name"] for r in recent], "sessions": sessions}
    if status:
        result["device_status"] = {
            "battery": status.get("battery"),
            "location": status.get("location"),
            "device": status.get("device"),
            "weather": status.get("weather"),
            "brightness": status.get("brightness"),
            "volume": status.get("volume"),
            "last_report": status.get("timestamp")
        }
    return result

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
