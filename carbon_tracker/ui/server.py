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

def parse_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

@app.get("/api/runs")
def get_runs():
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT ts FROM snapshots ORDER BY ts DESC")
        timestamps = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        runs = []
        current_run = []
        for ts in timestamps:
            if not current_run:
                current_run.append(ts)
            else:
                if current_run[-1] - ts <= 600:
                    current_run.append(ts)
                else:
                    runs.append(current_run)
                    current_run = [ts]
        if current_run:
            runs.append(current_run)
            
        formatted_runs = []
        for r in runs:
            max_ts = r[0]
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in r)
            cursor.execute(f"SELECT COUNT(DISTINCT chain_id) FROM snapshots WHERE ts IN ({placeholders})", r)
            chain_count = cursor.fetchone()[0]
            conn.close()
            
            formatted_runs.append({
                "run_id": max_ts,
                "timestamp": max_ts,
                "chain_count": chain_count
            })
        return formatted_runs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data")
def get_data(run_id: int = None):
    if not os.path.exists(DB_PATH):
        return []
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Get the target timestamp per chain
        if run_id is None:
            cursor.execute("SELECT chain_id, MAX(ts) FROM snapshots GROUP BY chain_id")
        else:
            cursor.execute("SELECT chain_id, MAX(ts) FROM snapshots WHERE ts <= ? GROUP BY chain_id", (run_id,))
        latest_ts_map = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 2. Get the previous timestamp per chain
        prev_ts_map = {}
        for chain_id, max_ts in latest_ts_map.items():
            cursor.execute("SELECT MAX(ts) FROM snapshots WHERE chain_id = ? AND ts < ?", (chain_id, max_ts))
            row = cursor.fetchone()
            if row and row[0] is not None:
                prev_ts_map[chain_id] = row[0]
                
        # 3. Fetch all target snapshots (along with token_address)
        latest_rows = []
        if latest_ts_map:
            conds = []
            params = []
            for cid, max_ts in latest_ts_map.items():
                conds.append("(chain_id = ? AND ts = ?)")
                params.extend([cid, max_ts])
            
            query = f"""
                SELECT chain_id, kind, level, token_address, payload_json, ts
                FROM snapshots
                WHERE {" OR ".join(conds)}
            """
            cursor.execute(query, params)
            latest_rows = cursor.fetchall()
        
        # 4. Fetch previous snapshots if they exist
        prev_map = {}
        if prev_ts_map:
            conds = []
            params = []
            for cid, pts in prev_ts_map.items():
                conds.append("(chain_id = ? AND ts = ?)")
                params.extend([cid, pts])
                
            prev_query = f"""
                SELECT chain_id, kind, level, token_address, payload_json
                FROM snapshots
                WHERE {" OR ".join(conds)}
            """
            cursor.execute(prev_query, params)
            for r in cursor.fetchall():
                cid, kind, level, token_addr, payload_json = r
                try:
                    payload = json.loads(payload_json)
                except Exception:
                    payload = {}
                prev_map[(cid, kind, level, token_addr.lower())] = payload
                
        conn.close()
        
        # 5. Build results with comparisons
        results = []
        for r in latest_rows:
            cid, kind, level, token_addr, payload_json, ts = r
            try:
                payload = json.loads(payload_json)
            except Exception:
                payload = {}
                
            trends = {}
            prev_payload = prev_map.get((cid, kind, level, token_addr.lower()))
            if prev_payload:
                # Compare available amount
                curr_av = parse_float(payload.get("available"))
                prev_av = parse_float(prev_payload.get("available"))
                if curr_av is not None and prev_av is not None:
                    trends["available"] = "UP" if curr_av > prev_av else ("DOWN" if curr_av < prev_av else "FLAT")
                    
                # Compare market price
                curr_m = parse_float(payload.get("market_usd"))
                prev_m = parse_float(prev_payload.get("market_usd"))
                if curr_m is not None and prev_m is not None:
                    trends["market_usd"] = "UP" if curr_m > prev_m else ("DOWN" if curr_m < prev_m else "FLAT")
                    
                # Compare profit or reward
                if kind == "trade":
                    curr_p = parse_float(payload.get("estimated_profit_usd"))
                    prev_p = parse_float(prev_payload.get("estimated_profit_usd"))
                    if curr_p is not None and prev_p is not None:
                        trends["estimated_profit_usd"] = "UP" if curr_p > prev_p else ("DOWN" if curr_p < prev_p else "FLAT")
                elif kind == "execute":
                    curr_r = parse_float(payload.get("reward_usd"))
                    prev_r = parse_float(prev_payload.get("reward_usd"))
                    if curr_r is not None and prev_r is not None:
                        trends["reward_usd"] = "UP" if curr_r > prev_r else ("DOWN" if curr_r < prev_r else "FLAT")
                        
            results.append({
                "chain_id": cid,
                "kind": kind,
                "level": level,
                "payload": payload,
                "trends": trends,
                "timestamp": ts
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

