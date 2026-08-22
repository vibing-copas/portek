import os
import json
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))
TEMPLATES_DIR = ROOT / "carbon_tracker" / "ui" / "templates"

app = FastAPI(title="Carbon Vortex API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/data")
def get_data():
    if not os.path.exists(DB_PATH):
        return []
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.chain_id, s.kind, s.level, s.payload_json, s.ts
            FROM snapshots s
            INNER JOIN (
                SELECT chain_id, MAX(ts) as max_ts
                FROM snapshots
                GROUP BY chain_id
            ) latest ON s.chain_id = latest.chain_id AND s.ts = latest.max_ts
        """)
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for r in rows:
            try:
                payload = json.loads(r[3])
            except Exception:
                payload = {}
            results.append({
                "chain_id": r[0],
                "kind": r[1],
                "level": r[2],
                "payload": payload,
                "timestamp": r[4]
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reload")
def reload_data():
    try:
        import subprocess
        import sys
        
        # Run daily_scan with --fast flag
        subprocess.run([sys.executable, "-m", "carbon_tracker.daily_scan", "--fast"], check=True)
        return get_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan and reload data: {str(e)}")

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend dashboard template not found.")
    return FileResponse(str(index_file))

