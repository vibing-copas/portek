from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

# Load variables, cleaning any potential enclosing quotes
mexc_host = os.getenv("mexc_host", "https://api.mexc.com").strip().strip('"').strip("'")
api_key = os.getenv("api_key", "").strip().strip('"').strip("'")
secret_key = os.getenv("secret_key", "").strip().strip('"').strip("'")
