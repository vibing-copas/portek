import os
import sys
import time
import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .config import load_config, get_telegram_config, ROOT
from .storage.db import connect as db_connect, get_scan_progress

logger = logging.getLogger("telegram_bot")


def save_active_chat_id(chat_id: str):
    """Save latest chat_id to data/telegram_chat_id.txt so alerts can find it automatically."""
    try:
        data_dir = ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "telegram_chat_id.txt").write_text(str(chat_id).strip())
    except Exception as e:
        logger.warning(f"Failed to auto-save chat_id: {e}")


def send_telegram_message(
    message: str,
    chat_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    parse_mode: str = "HTML"
) -> bool:
    """Send a message via Telegram Bot API using urllib with auto-retry on connection resets."""
    tg_cfg = get_telegram_config()
    token = bot_token or tg_cfg["bot_token"]
    cid = chat_id or tg_cfg["chat_id"]

    if not token or not cid:
        logger.warning("Telegram bot token or chat ID is missing. Message not sent.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                return res_json.get("ok", False)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                logger.error(f"Failed to send Telegram message after {max_retries} attempts: {e}")
                return False
    return False


def format_num(val: Optional[float], decimals: int = 2) -> str:
    """Format token amounts matching Web UI (supports T, B, M, K and scientific notation e-5)."""
    if val is None:
        return "-"
    abs_v = abs(val)
    if abs_v == 0:
        return "0"
    if abs_v >= 1_000_000_000_000:
        return f"{val / 1_000_000_000_000:.2f}T"
    if abs_v >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    if abs_v >= 10_000:
        return f"{val / 1_000:.1f}K"
    if abs_v >= 1_000:
        return f"{val / 1_000:.2f}K"
    if abs_v >= 0.001:
        return f"{val:.{decimals}f}"
    return f"{val:.2e}"


def format_usd(val: Optional[float], show_sign: bool = False) -> str:
    """Format USD values matching Web UI (supports T, B, M, K and scientific notation)."""
    if val is None:
        return "-"
    sign = "+" if (show_sign and val > 0) else ("-" if val < 0 else "")
    abs_v = abs(val)
    if abs_v == 0:
        return "$0"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000_000:.2f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.2f}M"
    if abs_v >= 1_000:
        return f"{sign}${abs_v / 1_000:.1f}K"
    if abs_v >= 0.01:
        return f"{sign}${abs_v:.2f}"
    if abs_v >= 0.0001:
        return f"{sign}${abs_v:.4f}"
    return f"{sign}${abs_v:.2e}"


def format_pct(val: Optional[float]) -> str:
    """Format percentage values matching Web UI with compact suffixes (e.g. +100%, +11.3B%, +56M%)."""
    if val is None:
        return "-"
    sign = "+" if val > 0 else ("-" if val < 0 else "")
    abs_v = abs(val)
    if abs_v == 0:
        return "0%"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T%"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B%"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.1f}M%"
    if abs_v >= 10_000:
        return f"{sign}{abs_v / 1_000:.1f}K%"
    if abs_v >= 100:
        return f"{sign}{abs_v:.0f}%"
    return f"{sign}{abs_v:.1f}%"


def format_table_report(
    title: str,
    items: List[Dict[str, Any]],
    avail_changes: Optional[List[Dict[str, Any]]] = None,
    eta_reached: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Format combined L1 and L2 trade opportunities into a clean ASCII / Monospace HTML table (<pre>)."""
    if not items and not avail_changes and not eta_reached:
        return f"<b>{title}</b>\n\nNo active trade opportunities found."

    header_text = f"<b>{title}</b>\n"

    rows = []
    changed_tokens = set()
    if avail_changes:
        for chg in avail_changes:
            changed_tokens.add(chg.get("token", "").lower())
            changed_tokens.add(chg.get("symbol", "").upper())

    eta_tokens = set()
    if eta_reached:
        for e in eta_reached:
            eta_tokens.add(e.get("token", "").lower())
            eta_tokens.add(str(e.get("symbol", "")).upper())

    for item in items:
        symbol = str(item.get("symbol", "UNK")).upper()
        t_addr = item.get("token", "").lower()
        is_changed = (t_addr in changed_tokens) or (symbol in changed_tokens)
        is_eta = (t_addr in eta_tokens) or (symbol in eta_tokens)

        prefix = ""
        if is_changed and is_eta:
            prefix = "*🎯"
        elif is_changed:
            prefix = "*"
        elif is_eta:
            prefix = "🎯"

        tkn_str = f"{symbol}{prefix}"
        if len(tkn_str) > 8:
            tkn_str = tkn_str[:8]

        # Available
        avail_amt = item.get("available")
        mkt_val = item.get("market_value_usd") or item.get("size_usd")
        if mkt_val is not None:
            avail_str = f"{format_num(avail_amt)}({format_usd(mkt_val)})"
        else:
            avail_str = f"{format_num(avail_amt)}"

        # Required Input (handles L1 feeToken and L2 targetToken input symbols)
        req_amt = item.get("required_source")
        src_sym = item.get("source_symbol", "")
        cost_usd = item.get("cost_usd")
        if req_amt is not None and req_amt > 0:
            req_str = f"{format_num(req_amt)} {src_sym}"
            if cost_usd is not None:
                req_str += f"({format_usd(cost_usd)})"
        else:
            req_str = "-"

        # Profit USD & %
        pl_usd = item.get("estimated_profit_usd") if item.get("estimated_profit_usd") is not None else item.get("expected_pl_usd")
        disc_pct = item.get("discount_pct", 0.0) or 0.0
        if pl_usd is not None and pl_usd != 0:
            prof_str = f"{format_usd(pl_usd, show_sign=True)}({format_pct(disc_pct)})"
        else:
            prof_str = f"{format_pct(disc_pct)}"

        # ETA
        eta_days = item.get("eta_days")
        eta_str_raw = item.get("eta_str")
        if eta_str_raw and eta_str_raw != "N/A":
            eta_str = eta_str_raw
        elif eta_days is not None:
            if eta_days <= 0:
                eta_str = "Ready"
            elif eta_days < 1:
                hours = int(eta_days * 24)
                mins = int((eta_days * 24 - hours) * 60)
                eta_str = f"{hours}h{mins}m" if hours > 0 else f"{mins}m"
            else:
                eta_str = f"{eta_days:.1f}d"
        else:
            eta_str = "-"

        rows.append({
            "tkn": tkn_str,
            "avail": avail_str,
            "req": req_str,
            "prof": prof_str,
            "eta": eta_str
        })

    if not rows:
        return f"<b>{title}</b>\n\nNo active trade opportunities found."

    # Render Monospace Table
    w_tkn = max(len("TOKEN"), max((len(r["tkn"]) for r in rows), default=0))
    w_avail = max(len("AVAIL (USD)"), max((len(r["avail"]) for r in rows), default=0))
    w_req = max(len("REQ INPUT"), max((len(r["req"]) for r in rows), default=0))
    w_prof = max(len("PROFIT"), max((len(r["prof"]) for r in rows), default=0))
    w_eta = max(len("ETA"), max((len(r["eta"]) for r in rows), default=0))

    lines = []
    header_line = f"{'TOKEN':<{w_tkn}}  {'AVAIL (USD)':<{w_avail}}  {'REQ INPUT':<{w_req}}  {'PROFIT':<{w_prof}}  {'ETA':<{w_eta}}"
    sep_line = "-" * len(header_line)
    lines.append(header_line)
    lines.append(sep_line)

    for r in rows:
        line = f"{r['tkn']:<{w_tkn}}  {r['avail']:<{w_avail}}  {r['req']:<{w_req}}  {r['prof']:<{w_prof}}  {r['eta']:<{w_eta}}"
        lines.append(line)

    table_body = "\n".join(lines)
    full_msg = header_text + f"<pre>\n{table_body}\n</pre>"

    if avail_changes:
        chg_lines = ["\n<b>🔄 Availability Changes:</b>"]
        for c in avail_changes:
            sym = c.get("symbol", "TOKEN")
            delta_amt = c.get("delta_amt", 0.0)
            delta_usd = c.get("delta_usd", 0.0)
            sign_amt = "+" if delta_amt > 0 else ""
            sign_usd = "+" if delta_usd > 0 else ""
            
            line = f"• <b>{sym}</b>: {sign_amt}{format_num(delta_amt)}"
            if delta_usd != 0:
                line += f" ({sign_usd}{format_usd(delta_usd)})"
            chg_lines.append(line)
            
        full_msg += "\n".join(chg_lines)

    if eta_reached:
        eta_lines = ["\n<b>🎯 Newly Reached ETA / Fair Price:</b>"]
        for e in eta_reached:
            sym = e.get("symbol", "TOKEN")
            disc = e.get("discount_pct", 0.0) or 0.0
            eta_lines.append(f"• <b>{sym}</b>: Reached Fair Price (Discount: {format_pct(disc)})")
            
        full_msg += "\n".join(eta_lines)

    return full_msg


def is_valid_trade_opportunity(item: Dict[str, Any]) -> bool:
    """Check if trade item is valid (status OK and available balance > 0)."""
    status = item.get("status", "OK")
    avail = float(item.get("available") or 0.0)
    avail_raw = int(item.get("available_raw") or 0)
    return status != "SKIP" and (avail > 0 or avail_raw > 0)


def detect_snapshot_events(db_path: str, chain_id: int, current_opportunities: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compare current scan opportunities against previous snapshot in DB.
    Returns (avail_changes, eta_reached).
    - avail_changes: list of dicts describing tokens with supply balance changes
    - eta_reached: list of trade items that JUST reached ETA/fairprice in this scan
    """
    p = Path(db_path)
    if not p.exists():
        return [], []

    try:
        db = db_connect(db_path)
        timestamps = [
            row[0] for row in db.execute(
                "SELECT DISTINCT ts FROM snapshots WHERE chain_id=? ORDER BY ts DESC LIMIT 2",
                (chain_id,)
            ).fetchall()
        ]

        current_items = [
            i for i in (current_opportunities.get("trade_l1", []) + current_opportunities.get("trade_l2", []))
            if is_valid_trade_opportunity(i)
        ]

        if len(timestamps) < 2:
            db.close()
            # If initial scan with no prior snapshots, treat tokens with eta_days <= 0 as newly reached ETA
            eta_reached = [item for item in current_items if item.get("eta_days") is not None and item.get("eta_days") <= 0]
            return [], eta_reached

        prev_ts = timestamps[1]

        rows = db.execute(
            "SELECT token_address, payload_json FROM snapshots WHERE chain_id=? AND ts=?",
            (chain_id, prev_ts)
        ).fetchall()

        prev_map = {}
        for addr, payload_str in rows:
            try:
                payload = json.loads(payload_str)
                if is_valid_trade_opportunity(payload):
                    prev_map[addr.lower()] = payload
            except Exception:
                pass

        db.close()

        avail_changes = []
        eta_reached = []

        for item in current_items:
            addr = item.get("token", "").lower()
            if not addr:
                continue

            curr_avail = float(item.get("available") or 0.0)
            curr_usd = float(item.get("market_value_usd") or item.get("size_usd") or 0.0)
            curr_eta = item.get("eta_days")

            if addr in prev_map:
                prev_item = prev_map[addr]
                prev_avail = float(prev_item.get("available") or 0.0)
                prev_usd = float(prev_item.get("market_value_usd") or prev_item.get("size_usd") or 0.0)
                prev_eta = prev_item.get("eta_days")

                delta_avail = curr_avail - prev_avail
                delta_usd = curr_usd - prev_usd

                # Condition 1: Supply token available amount changed
                if abs(delta_avail) >= 1e-5:
                    avail_changes.append({
                        "token": addr,
                        "symbol": item.get("symbol", addr[:6]),
                        "delta_amt": delta_avail,
                        "delta_usd": delta_usd,
                        "curr_avail": curr_avail,
                        "prev_avail": prev_avail
                    })

                # Condition 2: Token JUST reached ETA / fairprice (prev_eta > 0 -> curr_eta <= 0)
                if (prev_eta is not None and prev_eta > 0) and (curr_eta is not None and curr_eta <= 0):
                    eta_reached.append(item)
            else:
                if curr_avail > 0:
                    avail_changes.append({
                        "token": addr,
                        "symbol": item.get("symbol", addr[:6]),
                        "delta_amt": curr_avail,
                        "delta_usd": curr_usd,
                        "curr_avail": curr_avail,
                        "prev_avail": 0.0
                    })
                    if curr_eta is not None and curr_eta <= 0:
                        eta_reached.append(item)

        return avail_changes, eta_reached
    except Exception as e:
        logger.error(f"Error detecting snapshot events: {e}")
        return [], []


def detect_availability_changes(db_path: str, chain_id: int, current_opportunities: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Backwards compatibility helper wrapper for detect_snapshot_events."""
    avail_changes, _ = detect_snapshot_events(db_path, chain_id, current_opportunities)
    return avail_changes


def send_opportunity_alert(chain_name: str, opportunities: Dict[str, Any]) -> bool:
    """Evaluate scan results and dispatch Telegram alert ONLY if supply changed or token just reached ETA/fairprice."""
    tg_cfg = get_telegram_config()
    if not tg_cfg["is_configured"]:
        return False

    db_path = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))
    cfg = load_config()
    chain_id = cfg["chains"].get(chain_name.lower(), {}).get("chain_id")

    avail_changes, eta_reached = detect_snapshot_events(db_path, chain_id, opportunities) if chain_id else ([], [])

    # ONLY send notification if supply changed OR token just reached ETA/fairprice!
    if not avail_changes and not eta_reached:
        return False

    min_discount = tg_cfg["min_discount_pct"]
    all_trade_items = [
        r for r in (opportunities.get("trade_l2", []) + opportunities.get("trade_l1", []))
        if is_valid_trade_opportunity(r)
    ]
    
    event_addrs = {c["token"].lower() for c in avail_changes}.union({e.get("token", "").lower() for e in eta_reached})
    matching_items = [
        r for r in all_trade_items
        if r.get("token", "").lower() in event_addrs or (r.get("discount_pct") or 0.0) >= min_discount
    ]

    matching_items.sort(key=lambda x: x.get("discount_pct", -999.0) or -999.0, reverse=True)

    title = f"🚀 Carbon Vortex Alert [{chain_name.upper()}]"
    table_msg = format_table_report(title, matching_items, avail_changes, eta_reached)
    return send_telegram_message(table_msg)


def get_all_chains_dashboard(db_path: Optional[str] = None) -> str:
    """Generate overall multi-chain dashboard table showing active opps (>0 avail), total avail USD, and best profit per chain."""
    if not db_path:
        db_path = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))

    p = Path(db_path)
    if not p.exists():
        return "⚠️ Database file not found. Run a scan first!"

    try:
        db = db_connect(db_path)
        cfg = load_config()

        rows = []
        total_global_avail_usd = 0.0
        total_global_opps = 0

        for cname, cinfo in cfg["chains"].items():
            cid = cinfo["chain_id"]
            progress = get_scan_progress(db, cid)
            last_block = str(progress["last_scanned_block"]) if progress else "-"

            latest_ts_row = db.execute(
                "SELECT MAX(ts) FROM snapshots WHERE chain_id=?", (cid,)
            ).fetchone()
            latest_ts = latest_ts_row[0] if latest_ts_row and latest_ts_row[0] else None

            if not latest_ts:
                rows.append({
                    "chain": cname.upper(),
                    "opps": "0",
                    "best": "-",
                    "avail_usd": "$0",
                    "block": last_block
                })
                continue

            trade_rows = db.execute(
                "SELECT payload_json FROM snapshots WHERE chain_id=? AND ts=? AND kind='trade'",
                (cid, latest_ts)
            ).fetchall()

            valid_items = []
            for (payload_str,) in trade_rows:
                try:
                    payload = json.loads(payload_str)
                    if is_valid_trade_opportunity(payload):
                        valid_items.append(payload)
                except Exception:
                    pass

            opp_count = len(valid_items)
            total_global_opps += opp_count

            best_profit_str = "-"
            chain_avail_usd = 0.0
            best_disc = -999.0

            for item in valid_items:
                disc = item.get("discount_pct", -999.0) or -999.0
                symbol = item.get("symbol", "UNK").upper()
                mkt_val = float(item.get("market_value_usd") or item.get("size_usd") or 0.0)
                chain_avail_usd += mkt_val

                if disc > best_disc:
                    best_disc = disc
                    best_profit_str = f"{symbol}({format_pct(disc)})"

            total_global_avail_usd += chain_avail_usd

            rows.append({
                "chain": cname.upper()[:8],
                "opps": str(opp_count),
                "best": best_profit_str[:16],
                "avail_usd": format_usd(chain_avail_usd),
                "block": last_block
            })

        db.close()

        # Render Dashboard ASCII Table
        w_chain = max(len("CHAIN"), max((len(r["chain"]) for r in rows), default=0))
        w_opps = max(len("OPPS"), max((len(r["opps"]) for r in rows), default=0))
        w_best = max(len("BEST PROFIT"), max((len(r["best"]) for r in rows), default=0))
        w_avail = max(len("TOTAL AVAIL"), max((len(r["avail_usd"]) for r in rows), default=0))
        w_block = max(len("LAST BLOCK"), max((len(r["block"]) for r in rows), default=0))

        lines = []
        header_line = f"{'CHAIN':<{w_chain}}  {'OPPS':<{w_opps}}  {'BEST PROFIT':<{w_best}}  {'TOTAL AVAIL':<{w_avail}}  {'LAST BLOCK':<{w_block}}"
        sep_line = "-" * len(header_line)
        lines.append(header_line)
        lines.append(sep_line)

        for r in rows:
            line = f"{r['chain']:<{w_chain}}  {r['opps']:<{w_opps}}  {r['best']:<{w_best}}  {r['avail_usd']:<{w_avail}}  {r['block']:<{w_block}}"
            lines.append(line)

        table_body = "\n".join(lines)
        
        msg = "🌐 <b>Carbon Vortex Overall Dashboard</b>\n\n"
        msg += f"<pre>\n{table_body}\n</pre>\n"
        msg += f"• Total Active Trade Opportunities (Bal > 0): <b>{total_global_opps}</b>\n"
        msg += f"• Total Global Available Inventory: <b>{format_usd(total_global_avail_usd)}</b>"
        return msg

    except Exception as e:
        return f"⚠️ Error building overall dashboard: {e}"


def get_execute_opportunities(chain_filter: Optional[str] = None, limit: int = 15, db_path: Optional[str] = None) -> str:
    """Query execute reward opportunities from SQLite DB, filtering out 0-balance tokens and rendering a clean ASCII Table."""
    if not db_path:
        db_path = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))

    p = Path(db_path)
    if not p.exists():
        return "⚠️ Database file not found. Run a scan first!"

    try:
        db = db_connect(db_path)
        cfg = load_config()

        chains_to_query = {}
        if chain_filter:
            cname = chain_filter.lower().strip()
            if cname in cfg["chains"]:
                chains_to_query[cname] = cfg["chains"][cname]
            else:
                db.close()
                return f"⚠️ Unknown chain '{chain_filter}'. Available: {', '.join(cfg['chains'].keys())}"
        else:
            chains_to_query = cfg["chains"]

        msg_parts = []
        for cname, cinfo in chains_to_query.items():
            cid = cinfo["chain_id"]
            latest_ts_row = db.execute(
                "SELECT MAX(ts) FROM snapshots WHERE chain_id=?", (cid,)
            ).fetchone()
            latest_ts = latest_ts_row[0] if latest_ts_row and latest_ts_row[0] else None

            if not latest_ts:
                msg_parts.append(f"<b>⚡ Execute Rewards [{cname.upper()}]</b>\nNo execute snapshot data found.")
                continue

            rows = db.execute(
                "SELECT payload_json FROM snapshots WHERE chain_id=? AND ts=? AND kind='execute'",
                (cid, latest_ts)
            ).fetchall()

            items = []
            for (payload_str,) in rows:
                try:
                    payload = json.loads(payload_str)
                    avail_amt = float(payload.get("available") or 0.0)
                    avail_raw = int(payload.get("available_raw") or 0)
                    reason = payload.get("reason", "")
                    if (avail_amt > 0 or avail_raw > 0) and reason not in ("targetToken", "finalTargetToken"):
                        items.append(payload)
                except Exception:
                    pass

            items.sort(
                key=lambda x: (x.get("reward_usd") or 0.0, x.get("size_usd") or 0.0, x.get("available") or 0.0),
                reverse=True
            )

            total_active_cnt = len(items)
            display_items = items[:limit]

            if not display_items:
                msg_parts.append(f"<b>⚡ Execute Rewards [{cname.upper()}]</b>\nNo tokens currently available for execution (0 balance across all).")
                continue

            table_rows = []
            for item in display_items:
                sym = str(item.get("symbol", "UNK")).upper()
                avail_amt = item.get("available")
                mkt_usd = item.get("size_usd")
                avail_str = f"{format_num(avail_amt)}({format_usd(mkt_usd)})" if mkt_usd else f"{format_num(avail_amt)}"

                reward_amt = item.get("reward")
                reward_usd = item.get("reward_usd")
                reward_str = f"{format_num(reward_amt)}({format_usd(reward_usd)})" if reward_usd else f"{format_num(reward_amt)}"

                ppm_str = str(item.get("ppm", "-"))

                table_rows.append({
                    "tkn": sym[:7],
                    "avail": avail_str,
                    "reward": reward_str,
                    "ppm": ppm_str
                })

            w_tkn = max(len("TOKEN"), max((len(r["tkn"]) for r in table_rows), default=0))
            w_avail = max(len("AVAIL (USD)"), max((len(r["avail"]) for r in table_rows), default=0))
            w_rew = max(len("REWARD (USD)"), max((len(r["reward"]) for r in table_rows), default=0))
            w_ppm = max(len("PPM"), max((len(r["ppm"]) for r in table_rows), default=0))

            t_lines = []
            h_line = f"{'TOKEN':<{w_tkn}}  {'AVAIL (USD)':<{w_avail}}  {'REWARD (USD)':<{w_rew}}  {'PPM':<{w_ppm}}"
            s_line = "-" * len(h_line)
            t_lines.append(h_line)
            t_lines.append(s_line)

            for r in table_rows:
                t_lines.append(f"{r['tkn']:<{w_tkn}}  {r['avail']:<{w_avail}}  {r['reward']:<{w_rew}}  {r['ppm']:<{w_ppm}}")

            t_body = "\n".join(t_lines)

            exec_text = f"<b>⚡ Execute Rewards [{cname.upper()}]</b>\n"
            exec_text += f"<pre>\n{t_body}\n</pre>"
            if total_active_cnt > limit:
                exec_text += f"\n<i>ℹ️ Showing top {limit} of {total_active_cnt} execute tokens with balance > 0.</i>"

            msg_parts.append(exec_text)

        db.close()
        return "\n\n".join(msg_parts)
    except Exception as e:
        return f"⚠️ Error querying execute opportunities: {e}"


def get_top_opportunities(chain_filter: Optional[str] = None, limit: int = 5, db_path: Optional[str] = None) -> str:
    """Query recent top valid trade opportunities (status OK & balance > 0) from SQLite DB formatted in ASCII Table style."""
    if not db_path:
        db_path = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))

    p = Path(db_path)
    if not p.exists():
        return "⚠️ Database file not found. Run a scan first!"

    try:
        db = db_connect(db_path)
        cfg = load_config()

        chains_to_query = {}
        if chain_filter:
            cname = chain_filter.lower().strip()
            if cname in cfg["chains"]:
                chains_to_query[cname] = cfg["chains"][cname]
            else:
                db.close()
                return f"⚠️ Unknown chain '{chain_filter}'. Available: {', '.join(cfg['chains'].keys())}"
        else:
            chains_to_query = cfg["chains"]

        msg_parts = []
        for cname, cinfo in chains_to_query.items():
            cid = cinfo["chain_id"]
            latest_ts_row = db.execute(
                "SELECT MAX(ts) FROM snapshots WHERE chain_id=?", (cid,)
            ).fetchone()
            latest_ts = latest_ts_row[0] if latest_ts_row and latest_ts_row[0] else None

            if not latest_ts:
                msg_parts.append(f"<b>[{cname.upper()}]</b>: No scan snapshot data found.")
                continue

            rows = db.execute(
                "SELECT level, payload_json FROM snapshots WHERE chain_id=? AND ts=? AND kind='trade'",
                (cid, latest_ts)
            ).fetchall()

            items = []
            for r_level, payload_str in rows:
                try:
                    payload = json.loads(payload_str)
                    payload["_level"] = r_level
                    if is_valid_trade_opportunity(payload):
                        items.append(payload)
                except Exception:
                    pass

            items.sort(key=lambda x: x.get("discount_pct", -999.0) or -999.0, reverse=True)
            top_items = items[:limit]

            title = f"🎯 Top Opportunities [{cname.upper()}]"
            table_text = format_table_report(title, top_items)
            msg_parts.append(table_text)

        db.close()
        return "\n\n".join(msg_parts)
    except Exception as e:
        return f"⚠️ Error querying top opportunities: {e}"


def get_db_summary(db_path: Optional[str] = None) -> str:
    """Get overall tracker summary text from SQLite DB."""
    if not db_path:
        db_path = os.getenv("DB_PATH", str(ROOT / "data/tracker.db"))

    p = Path(db_path)
    if not p.exists():
        return "⚠️ Database file not found. Run a scan first!"

    try:
        db = db_connect(db_path)
        cfg = load_config()

        total_tokens = db.execute("SELECT COUNT(*) FROM token_registry").fetchone()[0]

        chain_summaries = []
        for cname, cinfo in cfg["chains"].items():
            cid = cinfo["chain_id"]
            progress = get_scan_progress(db, cid)
            last_block = progress["last_scanned_block"] if progress else "Never"

            latest_ts_row = db.execute(
                "SELECT MAX(ts) FROM snapshots WHERE chain_id=?", (cid,)
            ).fetchone()
            latest_ts = latest_ts_row[0] if latest_ts_row and latest_ts_row[0] else None

            l1_cnt = 0
            l2_cnt = 0
            if latest_ts:
                rows = db.execute(
                    "SELECT level, payload_json FROM snapshots WHERE chain_id=? AND ts=? AND kind='trade'",
                    (cid, latest_ts)
                ).fetchall()
                for level, payload_str in rows:
                    try:
                        p = json.loads(payload_str)
                        if is_valid_trade_opportunity(p):
                            if level == 2:
                                l2_cnt += 1
                            else:
                                l1_cnt += 1
                    except Exception:
                        pass

            chain_summaries.append(
                f"• <b>{cname.upper()}</b> (Chain ID: {cid}):\n"
                f"  - Last Block: <code>{last_block}</code>\n"
                f"  - Active Trade Opps (Bal > 0): <b>{l1_cnt + l2_cnt}</b> (L2: {l2_cnt}, L1: {l1_cnt})"
            )

        db.close()

        msg = "📊 <b>Carbon Vortex Tracker Summary</b>\n\n"
        msg += f"• Registered Tokens: <b>{total_tokens}</b>\n\n"
        msg += "<b>Chains:</b>\n" + "\n".join(chain_summaries)
        return msg
    except Exception as e:
        return f"⚠️ Error querying database: {e}"


class TelegramBotRunner:
    """Long-polling Telegram Bot command handler."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.offset = 0
        self.running = False

    def get_updates(self) -> List[Dict[str, Any]]:
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        payload = {"offset": self.offset, "timeout": 10}
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                if res_json.get("ok"):
                    return res_json.get("result", [])
        except Exception as e:
            logger.debug(f"Error fetching updates: {e}")
        return []

    def handle_message(self, message: Dict[str, Any]):
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if not chat_id or not text:
            return

        save_active_chat_id(str(chat_id))

        parts = text.split()
        command = parts[0].lower()
        args = parts[1:]

        logger.info(f"Received command '{text}' from chat_id {chat_id}")

        if command in ("/start", "/help"):
            help_msg = (
                "<b>🤖 Carbon Vortex Tracker Bot</b>\n\n"
                "Available Commands:\n"
                "• <code>/all</code> - View overall multi-chain dashboard table\n"
                "• <code>/top [chain]</code> - View top active trade opportunities\n"
                "• <code>/execute [chain]</code> - View active execute reward opportunities\n"
                "• <code>/summary</code> - View system & opportunities summary\n"
                "• <code>/scan [chain]</code> - Trigger fast scan on demand\n"
                "• <code>/status</code> - Check tracker system status\n"
                "• <code>/help</code> - Show this menu"
            )
            send_telegram_message(help_msg, chat_id=chat_id, bot_token=self.bot_token)

        elif command in ("/all", "/dashboard"):
            dash_msg = get_all_chains_dashboard()
            send_telegram_message(dash_msg, chat_id=chat_id, bot_token=self.bot_token)

        elif command in ("/execute", "/exec"):
            chain = args[0] if args else None
            exec_msg = get_execute_opportunities(chain_filter=chain)
            send_telegram_message(exec_msg, chat_id=chat_id, bot_token=self.bot_token)

        elif command == "/summary":
            summary_msg = get_db_summary()
            send_telegram_message(summary_msg, chat_id=chat_id, bot_token=self.bot_token)

        elif command == "/top":
            chain = args[0] if args else None
            top_msg = get_top_opportunities(chain_filter=chain)
            send_telegram_message(top_msg, chat_id=chat_id, bot_token=self.bot_token)

        elif command == "/status":
            cfg = load_config()
            tg_cfg = get_telegram_config()
            status_msg = (
                "<b>⚙️ Carbon Vortex System Status</b>\n\n"
                f"• Configured Chains: <b>{', '.join(cfg['chains'].keys())}</b>\n"
                f"• Active Chat ID: <code>{tg_cfg['chat_id'] or chat_id}</code>\n"
                f"• Min Discount Threshold: <b>{tg_cfg['min_discount_pct']:.1f}%</b>\n"
                f"• System Time: <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>"
            )
            send_telegram_message(status_msg, chat_id=chat_id, bot_token=self.bot_token)

        elif command == "/scan":
            chain_arg = args[0] if args else "all"
            send_telegram_message(
                f"⏳ Starting fast scan for <b>{chain_arg}</b>...",
                chat_id=chat_id,
                bot_token=self.bot_token
            )
            import subprocess
            try:
                cmd = [sys.executable, "-m", "carbon_tracker.daily_scan", "--fast"]
                if args:
                    cmd.append(args[0])
                subprocess.run(cmd, cwd=str(ROOT), check=True)

                res_msg = f"✅ Fast scan for <b>{chain_arg}</b> completed successfully!\n\n"
                res_msg += get_top_opportunities(chain_filter=args[0] if args else None, limit=5)
                send_telegram_message(res_msg, chat_id=chat_id, bot_token=self.bot_token)
            except Exception as scan_err:
                send_telegram_message(
                    f"❌ Scan failed: {scan_err}",
                    chat_id=chat_id,
                    bot_token=self.bot_token
                )
        else:
            send_telegram_message(
                "❓ Unknown command. Type <code>/help</code> for available commands.",
                chat_id=chat_id,
                bot_token=self.bot_token
            )

    def start(self):
        self.running = True
        logger.info("Telegram Bot listener started...")
        print("[+] Telegram Bot polling service is running... Press Ctrl+C to stop.")

        while self.running:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.offset = update["update_id"] + 1
                    if "message" in update:
                        self.handle_message(update["message"])
            except KeyboardInterrupt:
                print("\n[+] Stopping Telegram Bot listener...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(2)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s"
    )
    tg_cfg = get_telegram_config()
    if not tg_cfg["bot_token"]:
        print("[-] Error: TELEGRAM_BOT_TOKEN is not set in environment or .env file.")
        sys.exit(1)

    runner = TelegramBotRunner(tg_cfg["bot_token"])
    runner.start()


if __name__ == "__main__":
    main()
