import sqlite3, json
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS token_registry(
 chain_id INTEGER NOT NULL, token_address TEXT NOT NULL, symbol TEXT, decimals INTEGER,
 first_seen_block INTEGER, last_seen_block INTEGER, events INTEGER, last_fee_raw TEXT,
 last_trade_source TEXT, last_trade_target TEXT, 
 last_trade_source_amount TEXT, last_trade_target_amount TEXT, last_trade_block INTEGER,
 PRIMARY KEY(chain_id, token_address));
CREATE TABLE IF NOT EXISTS snapshots(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, chain_id INTEGER NOT NULL,
 kind TEXT NOT NULL, level INTEGER, token_address TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_snapshots_chain_ts ON snapshots(chain_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts_chain ON snapshots(ts DESC, chain_id);
CREATE TABLE IF NOT EXISTS scan_progress(
 chain_id INTEGER PRIMARY KEY,
 first_scanned_block INTEGER,
 last_scanned_block INTEGER NOT NULL);
'''

def connect(path, timeout=60.0):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(p, timeout=timeout)
    db.execute("PRAGMA journal_mode=WAL;")
    db.executescript(SCHEMA)
    
    # Dynamic migration to add last_trade_* columns if they don't exist
    columns = [row[1] for row in db.execute("PRAGMA table_info(token_registry)").fetchall()]
    new_cols = {
        "last_trade_source": "TEXT",
        "last_trade_target": "TEXT",
        "last_trade_source_amount": "TEXT",
        "last_trade_target_amount": "TEXT",
        "last_trade_block": "INTEGER"
    }
    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            db.execute(f"ALTER TABLE token_registry ADD COLUMN {col_name} {col_type}")
            
    # Dynamic migration to add first_scanned_block column if it doesn't exist
    progress_cols = [row[1] for row in db.execute("PRAGMA table_info(scan_progress)").fetchall()]
    if "first_scanned_block" not in progress_cols:
        db.execute("ALTER TABLE scan_progress ADD COLUMN first_scanned_block INTEGER")
            
    return db

def get_scan_progress(db, chain_id):
    row = db.execute('SELECT first_scanned_block, last_scanned_block FROM scan_progress WHERE chain_id=?', (chain_id,)).fetchone()
    if row:
        return {"first_scanned_block": row[0], "last_scanned_block": row[1]}
    return None

def save_scan_progress(db, chain_id, first_block, last_block):
    existing = get_scan_progress(db, chain_id)
    if existing:
        fb = first_block if first_block is not None else existing["first_scanned_block"]
        lb = last_block if last_block is not None else existing["last_scanned_block"]
        if fb is not None and existing["first_scanned_block"] is not None:
            fb = min(fb, existing["first_scanned_block"])
        elif fb is None:
            fb = existing["first_scanned_block"]
            
        if lb is not None and existing["last_scanned_block"] is not None:
            lb = max(lb, existing["last_scanned_block"])
        elif lb is None:
            lb = existing["last_scanned_block"]
    else:
        fb = first_block
        lb = last_block
        
    db.execute('INSERT OR REPLACE INTO scan_progress (chain_id, first_scanned_block, last_scanned_block) VALUES(?,?,?)', (chain_id, fb, lb))

def upsert_token(db, chain_id, addr, meta, info):
    addr = str(addr).lower()
    db.execute('''
    INSERT INTO token_registry (
        chain_id, token_address, symbol, decimals, 
        first_seen_block, last_seen_block, events, last_fee_raw,
        last_trade_source, last_trade_target, 
        last_trade_source_amount, last_trade_target_amount, last_trade_block
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(chain_id,token_address) DO UPDATE SET 
        symbol=excluded.symbol,
        decimals=excluded.decimals,
        first_seen_block=MIN(token_registry.first_seen_block,excluded.first_seen_block),
        last_seen_block=MAX(token_registry.last_seen_block,excluded.last_seen_block),
        events=COALESCE(token_registry.events, 0) + excluded.events,
        last_fee_raw=excluded.last_fee_raw,
        last_trade_source=excluded.last_trade_source,
        last_trade_target=excluded.last_trade_target,
        last_trade_source_amount=excluded.last_trade_source_amount,
        last_trade_target_amount=excluded.last_trade_target_amount,
        last_trade_block=excluded.last_trade_block
    ''',
    (
        chain_id, addr, meta["symbol"], meta["decimals"], 
        info.get("first_seen_block"), info.get("last_seen_block"), info.get("events", 0), str(info.get("last_fee_raw", 0)),
        info.get("last_trade_source"), info.get("last_trade_target"),
        info.get("last_trade_source_amount"), info.get("last_trade_target_amount"), info.get("last_trade_block")
    ))

def snapshot(db, ts, chain_id, kind, level, token, payload):
    token = str(token).lower()
    db.execute('INSERT INTO snapshots(ts,chain_id,kind,level,token_address,payload_json) VALUES(?,?,?,?,?,?)',
               (ts,chain_id,kind,level,token,json.dumps(payload)))
