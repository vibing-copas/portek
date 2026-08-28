import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    print("[+] Starting Carbon Vortex Railway Master Entrypoint...")

    processes = []
    try:
        # 1. Start Telegram Bot polling process in background
        print("[+] Starting Telegram Bot listener process...")
        bot_proc = subprocess.Popen(
            [sys.executable, "-m", "carbon_tracker.telegram_bot"],
            cwd=str(ROOT)
        )
        processes.append(bot_proc)

        # 2. Start Web Dashboard & Background Scanner (which listens on $PORT for Railway)
        print("[+] Starting Web Dashboard & Scheduler process...")
        dashboard_script = ROOT / "scripts" / "run_dashboard.py"
        dash_proc = subprocess.Popen(
            [sys.executable, str(dashboard_script)],
            cwd=str(ROOT)
        )
        processes.append(dash_proc)

        print("[+] All services launched successfully on Railway!")
        
        # Monitor processes
        while True:
            time.sleep(5)
            for proc in processes:
                if proc.poll() is not None:
                    print(f"[!] Process {proc.pid} exited with code {proc.returncode}")

    except KeyboardInterrupt:
        print("\n[+] Stopping Railway master entrypoint...")
        for proc in processes:
            try:
                proc.terminate()
            except Exception:
                pass
        sys.exit(0)

if __name__ == "__main__":
    main()
