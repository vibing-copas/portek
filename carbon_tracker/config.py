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
