import os
import json
import sqlite3
import sys
import time
import threading
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))
TEMPLATES_DIR = ROOT / "carbon_tracker" / "ui" / "templates"

def background_scheduler():
    print("[Scheduler] Background scheduler thread started.")
    time.sleep(5)  # Let uvicorn start up completely
    
    FAST_INTERVAL = 30 * 60  # 30 minutes
    FULL_INTERVAL = 24 * 60 * 60  # 24 hours
    
    last_fast = 0  # Run immediately on start
    last_full = time.time()  # Start counting daily scan interval
    
    while True:
        now = time.time()
        
        # Check full daily scan
        if now - last_full >= FULL_INTERVAL:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Scheduler] Triggering automatic daily full scan...")
            try:
                subprocess.run([sys.executable, "-m", "carbon_tracker.daily_scan"], cwd=str(ROOT), check=True)
                print("[Scheduler] Daily full scan completed successfully.")
            except Exception as e:
                print(f"[Scheduler] Daily full scan failed: {e}")
            last_full = now
            
        # Check half-hourly fast scan
        elif now - last_fast >= FAST_INTERVAL:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Scheduler] Triggering automatic fast scan...")
            try:
                subprocess.run([sys.executable, "-m", "carbon_tracker.daily_scan", "--fast"], cwd=str(ROOT), check=True)
                print("[Scheduler] Fast scan completed successfully.")
            except Exception as e:
                print(f"[Scheduler] Fast scan failed: {e}")
            last_fast = now
            
        time.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler daemon thread
    t = threading.Thread(target=background_scheduler, daemon=True)
    t.start()
    yield

app = FastAPI(title="Carbon Vortex API", lifespan=lifespan)

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
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA query_only = ON;")
        cursor = conn.cursor()
        
        # Single query to fetch all timestamps and distinct chain counts indexed
        cursor.execute("SELECT ts, COUNT(DISTINCT chain_id) FROM snapshots GROUP BY ts ORDER BY ts DESC")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return []

        ts_chain_map = {row[0]: row[1] for row in rows}
        timestamps = [row[0] for row in rows]
        
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
            chain_count = max(ts_chain_map.get(ts, 1) for ts in r)
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
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA query_only = ON;")
        cursor = conn.cursor()
        
        # 1. Get the target timestamp per chain
        if run_id is None:
            cursor.execute("SELECT chain_id, MAX(ts) FROM snapshots GROUP BY chain_id")
        else:
            cursor.execute("SELECT chain_id, MAX(ts) FROM snapshots WHERE ts <= ? GROUP BY chain_id", (run_id,))
        latest_ts_map = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 2. Get the previous day's timestamp per chain (using index-backed ts range)
        prev_ts_map = {}
        for chain_id, max_ts in latest_ts_map.items():
            cursor.execute("""
                SELECT MAX(ts) FROM snapshots 
                WHERE chain_id = ? AND ts < ? - 43200
            """, (chain_id, max_ts))
            row = cursor.fetchone()
            if row and row[0] is not None:
                prev_ts_map[chain_id] = row[0]
                
        # 3. Fetch all target snapshots
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
        
        # 5. Build results with comparisons and deduplicate by (cid, kind, level, token_addr.lower())
        results = []
        seen_keys = set()
        for r in latest_rows:
            cid, kind, level, token_addr, payload_json, ts = r
            dedup_key = (cid, kind, level, str(token_addr).lower())
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

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
                    # Calculate percentage change
                    if prev_av > 0:
                        trends["available_pct"] = round(((curr_av - prev_av) / prev_av) * 100, 2)
                    else:
                        trends["available_pct"] = 0.0
                    
                # Compare market price
                curr_m = parse_float(payload.get("market_usd"))
                prev_m = parse_float(prev_payload.get("market_usd"))
                if curr_m is not None and prev_m is not None:
                    trends["market_usd"] = "UP" if curr_m > prev_m else ("DOWN" if curr_m < prev_m else "FLAT")
                    if prev_m > 0:
                        trends["market_usd_pct"] = round(((curr_m - prev_m) / prev_m) * 100, 2)
                    else:
                        trends["market_usd_pct"] = 0.0
                    
                # Compare profit or reward
                if kind == "trade":
                    curr_p = parse_float(payload.get("estimated_profit_usd"))
                    prev_p = parse_float(prev_payload.get("estimated_profit_usd"))
                    if curr_p is not None and prev_p is not None:
                        trends["estimated_profit_usd"] = "UP" if curr_p > prev_p else ("DOWN" if curr_p < prev_p else "FLAT")
                        if prev_p > 0:
                            trends["estimated_profit_usd_pct"] = round(((curr_p - prev_p) / prev_p) * 100, 2)
                        elif curr_p > 0:
                            trends["estimated_profit_usd_pct"] = 100.0
                        else:
                            trends["estimated_profit_usd_pct"] = 0.0
                elif kind == "execute":
                    curr_r = parse_float(payload.get("reward_usd"))
                    prev_r = parse_float(prev_payload.get("reward_usd"))
                    if curr_r is not None and prev_r is not None:
                        trends["reward_usd"] = "UP" if curr_r > prev_r else ("DOWN" if curr_r < prev_r else "FLAT")
                        if prev_r > 0:
                            trends["reward_usd_pct"] = round(((curr_r - prev_r) / prev_r) * 100, 2)
                        elif curr_r > 0:
                            trends["reward_usd_pct"] = 100.0
                        else:
                            trends["reward_usd_pct"] = 0.0
                        
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

@app.post("/api/admin/upload-db-chunk-json")
async def upload_db_chunk_json(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
        
    secret = payload.get("secret", "")
    expected_secret = os.getenv("MIGRATION_SECRET", "default-temp-secret-key-12345")
    if secret != expected_secret:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid migration secret.")
        
    chunk_index = int(payload.get("chunk_index", 0))
    total_chunks = int(payload.get("total_chunks", 1))
    data_b64 = payload.get("data_b64", "")
    
    if not data_b64:
        raise HTTPException(status_code=400, detail="Empty data_b64 payload.")
        
    import base64, gzip, shutil
    chunk_bytes = base64.b64decode(data_b64)
    
    temp_dir = Path(DB_PATH).parent / ".chunks_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_file = temp_dir / f"chunk_{chunk_index}.bin"
    with open(chunk_file, "wb") as f:
        f.write(chunk_bytes)
        
    received_chunks = list(temp_dir.glob("chunk_*.bin"))
    if len(received_chunks) == total_chunks:
        combined_bytes = bytearray()
        for i in range(total_chunks):
            cf = temp_dir / f"chunk_{i}.bin"
            if not cf.exists():
                return {"status": "in_progress", "received": len(received_chunks), "total": total_chunks}
            with open(cf, "rb") as f:
                combined_bytes.extend(f.read())
                
        final_bytes = bytes(combined_bytes)
        if final_bytes.startswith(b"\x1f\x8b"):
            try:
                final_bytes = gzip.decompress(final_bytes)
            except Exception as e:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail=f"Gzip decompress error: {e}")
                
        if not final_bytes.startswith(b"SQLite format 3\x00"):
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Reassembled data is not valid SQLite database.")
            
        target_path = Path(DB_PATH)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        tmp_migrate = target_path.with_suffix(".tmp_migrate")
        with open(tmp_migrate, "wb") as f:
            f.write(final_bytes)
            
        if target_path.exists():
            for ext in ["-wal", "-shm"]:
                wf = target_path.with_name(target_path.name + ext)
                if wf.exists():
                    try: wf.unlink()
                    except Exception: pass
                    
        os.replace(tmp_migrate, target_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        stats = {}
        try:
            conn = sqlite3.connect(str(target_path))
            c = conn.cursor()
            for t in ["token_registry", "snapshots", "scan_progress"]:
                try:
                    c.execute(f"SELECT COUNT(*) FROM {t}")
                    stats[t] = c.fetchone()[0]
                except Exception:
                    stats[t] = 0
            conn.close()
        except Exception as e:
            stats["error"] = str(e)
            
        return {
            "status": "success",
            "message": "Database chunked upload & migration completed successfully!",
            "file_size_bytes": len(final_bytes),
            "table_stats": stats
        }
        
    return {
        "status": "in_progress",
        "received_chunks": len(received_chunks),
        "total_chunks": total_chunks
    }

@app.post("/api/admin/migrate-db")
async def migrate_db(request: Request, x_migration_secret: str = Header(None)):
    expected_secret = os.getenv("MIGRATION_SECRET", "default-temp-secret-key-12345")
    if not x_migration_secret or x_migration_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid migration secret header.")
    
    body_bytes = await request.body()
    if not body_bytes:
        raise HTTPException(status_code=400, detail="Invalid payload: Empty data.")
        
    if body_bytes.startswith(b"\x1f\x8b"):
        import gzip
        try:
            body_bytes = gzip.decompress(body_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decompress gzip payload: {str(e)}")

    if not body_bytes.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Invalid payload: Uploaded data is not a valid SQLite database file.")
    
    target_path = Path(DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    temp_path = target_path.with_suffix(".tmp_migrate")
    with open(temp_path, "wb") as f:
        f.write(body_bytes)
        
    if target_path.exists():
        wal_file = target_path.with_name(target_path.name + "-wal")
        shm_file = target_path.with_name(target_path.name + "-shm")
        if wal_file.exists():
            try: wal_file.unlink()
            except Exception: pass
        if shm_file.exists():
            try: shm_file.unlink()
            except Exception: pass
            
    os.replace(temp_path, target_path)
    
    stats = {}
    try:
        conn = sqlite3.connect(str(target_path))
        c = conn.cursor()
        for table in ["token_registry", "snapshots", "scan_progress"]:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = c.fetchone()[0]
            except Exception:
                stats[table] = 0
        conn.close()
    except Exception as e:
        stats["error"] = str(e)
        
    return {
        "status": "success",
        "message": "Database migrated successfully!",
        "file_size_bytes": len(body_bytes),
        "table_stats": stats
    }

@app.get("/api/admin/find-db")
def find_db_files():
    """Diagnostic endpoint to find all .db files on disk (including attached volume paths) and display snapshot stats."""
    search_paths = ["/data", "/app/data", "/mnt", "/tmp", str(ROOT / "data"), str(Path(DB_PATH).parent)]
    env_db = os.getenv("DB_PATH")
    if env_db:
        search_paths.append(str(Path(env_db).parent))

    found_files = {}
    seen = set()

    for p_str in search_paths:
        p = Path(p_str)
        if not p.exists() or not p.is_dir():
            continue
        try:
            for f in p.glob("**/*.db"):
                real_p = str(f.resolve())
                if real_p in seen:
                    continue
                seen.add(real_p)

                stat_info = f.stat()
                file_size_mb = round(stat_info.st_size / (1024 * 1024), 2)
                
                db_stats = {"size_mb": file_size_mb, "path": real_p}
                try:
                    conn = sqlite3.connect(real_p, timeout=5.0)
                    c = conn.cursor()
                    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                    db_stats["tables"] = tables
                    if "snapshots" in tables:
                        s_cnt = c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
                        min_ts = c.execute("SELECT MIN(ts) FROM snapshots").fetchone()[0]
                        max_ts = c.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
                        
                        from datetime import datetime, timezone
                        db_stats["snapshots_count"] = s_cnt
                        db_stats["oldest_snapshot"] = datetime.fromtimestamp(min_ts, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if min_ts else None
                        db_stats["newest_snapshot"] = datetime.fromtimestamp(max_ts, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if max_ts else None
                    if "token_registry" in tables:
                        t_cnt = c.execute("SELECT COUNT(*) FROM token_registry").fetchone()[0]
                        db_stats["token_count"] = t_cnt
                    conn.close()
                except Exception as db_err:
                    db_stats["error"] = str(db_err)

                found_files[real_p] = db_stats
        except Exception as err:
            found_files[p_str] = {"error": str(err)}

    return {
        "active_DB_PATH": DB_PATH,
        "env_DB_PATH": os.getenv("DB_PATH"),
        "found_database_files": found_files
    }

EXPLORER_CHAINS = {
    1: {"name": "Ethereum", "file": "data/vortex_eth_trade_totals.json", "explorer": "https://etherscan.io/tx/"},
    1329: {"name": "Sei Network", "file": "data/vortex_sei_trade_totals.json", "explorer": "https://seitrace.com/tx/"},
    42220: {"name": "Celo Mainnet", "file": "data/vortex_celo_trade_totals.json", "explorer": "https://celoscan.io/tx/"},
    239: {"name": "TAC Network", "file": "data/vortex_tac_trade_totals.json", "explorer": "https://turntrade.build/tx/"},
    2632500: {"name": "COTI Network", "file": "data/vortex_coti_trade_totals.json", "explorer": "https://coti-explorer.coti.io/tx/"}
}

_trades_cache = None
_trades_cache_mtime = 0

def load_explorer_trades():
    global _trades_cache, _trades_cache_mtime
    
    current_mtime = 0
    for cfg in EXPLORER_CHAINS.values():
        fpath = str(ROOT / cfg["file"])
        if os.path.exists(fpath):
            current_mtime = max(current_mtime, os.path.getmtime(fpath))
            
    if _trades_cache is not None and _trades_cache_mtime == current_mtime:
        return _trades_cache
        
    trades = []
    for cid, cfg in EXPLORER_CHAINS.items():
        fpath = str(ROOT / cfg["file"])
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    token_items = json.load(f)
                    for tok in token_items:
                        symbol = tok.get("symbol", "UNKNOWN")
                        token_addr = tok.get("address", "")
                        for t in tok.get("trades", []):
                            tx_h = t.get("tx_hash", "")
                            explorer_url = f"{cfg['explorer']}{tx_h}" if tx_h else ""
                            trades.append({
                                "chain_id": cid,
                                "chain_name": cfg["name"],
                                "token_symbol": symbol,
                                "token_address": token_addr,
                                "tx_hash": tx_h,
                                "explorer_url": explorer_url,
                                "block_number": t.get("block_number", 0),
                                "timestamp": t.get("timestamp", ""),
                                "timestamp_raw": t.get("timestamp_raw", 0),
                                "caller": t.get("caller", ""),
                                "level": t.get("level", 2),
                                "pair_name": t.get("pair_name", ""),
                                "source_symbol": t.get("source_symbol", ""),
                                "source_formatted": t.get("source_formatted", 0),
                                "target_formatted": t.get("target_formatted", 0),
                                "unit_price": t.get("unit_price", 0),
                                "usd_value": t.get("usd_value", 0)
                            })
            except Exception as e:
                print(f"[Explorer] Error loading {fpath}: {e}")
                
    # Sort BY TIME DESCENDING (newest at top)
    trades.sort(key=lambda x: x["timestamp_raw"], reverse=True)
    _trades_cache = trades
    _trades_cache_mtime = current_mtime
    return trades

@app.get("/api/explorer/trades")
def get_explorer_trades(chain_id: str = "ALL", q: str = None, limit: int = 100, offset: int = 0):
    all_trades = load_explorer_trades()
    
    filtered = all_trades
    if chain_id != "ALL" and chain_id.isdigit():
        target_cid = int(chain_id)
        filtered = [t for t in filtered if t["chain_id"] == target_cid]
        
    if q:
        query_str = q.strip().lower()
        filtered = [
            t for t in filtered if (
                query_str in t["token_symbol"].lower() or
                query_str in t["token_address"].lower() or
                query_str in t["tx_hash"].lower() or
                query_str in t["pair_name"].lower() or
                query_str in t["caller"].lower()
            )
        ]
        
    total_count = len(filtered)
    total_volume_usd = sum(t["usd_value"] for t in filtered)
    paginated = filtered[offset : offset + limit]
    
    return {
        "total": total_count,
        "total_volume_usd": total_volume_usd,
        "limit": limit,
        "offset": offset,
        "trades": paginated
    }

@app.get("/explorer", response_class=HTMLResponse)
def read_explorer():
    explorer_file = TEMPLATES_DIR / "explorer.html"
    if not explorer_file.exists():
        raise HTTPException(status_code=404, detail="Explorer template not found.")
    return FileResponse(str(explorer_file))

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend dashboard template not found.")
    return FileResponse(str(index_file))


