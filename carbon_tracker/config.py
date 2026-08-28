from pathlib import Path
import os, yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)


def load_config():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    return cfg


def rpc_for(chain_cfg):
    url = os.getenv(chain_cfg["rpc_env"], "").strip()
    if not url:
        raise RuntimeError(f"Missing RPC env var {chain_cfg['rpc_env']}")
    return url


def get_telegram_config():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")
    
    if not chat_id:
        chat_id_file = ROOT / "data" / "telegram_chat_id.txt"
        if chat_id_file.exists():
            try:
                chat_id = chat_id_file.read_text().strip()
            except Exception:
                pass

    try:
        min_discount_pct = float(os.getenv("TELEGRAM_MIN_DISCOUNT_PCT", "0.0"))
    except ValueError:
        min_discount_pct = 0.0

    return {
        "bot_token": bot_token,
        "chat_id": chat_id,
        "min_discount_pct": min_discount_pct,
        "is_configured": bool(bot_token and chat_id)
    }


