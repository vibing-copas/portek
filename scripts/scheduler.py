import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_fast_scan():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Scheduler] Running fast scan (every 30 mins)...")
    try:
        subprocess.run([sys.executable, "-m", "carbon_tracker.daily_scan", "--fast"], cwd=str(ROOT), check=True)
        print("[Scheduler] Fast scan completed successfully.")
    except Exception as e:
        print(f"[Scheduler] Fast scan failed: {e}")

def run_full_scan():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [Scheduler] Running daily full scan...")
    try:
        subprocess.run([sys.executable, "-m", "carbon_tracker.daily_scan"], cwd=str(ROOT), check=True)
        print("[Scheduler] Daily full scan completed successfully.")
    except Exception as e:
        print(f"[Scheduler] Daily full scan failed: {e}")

def main():
    print("[+] Starting Carbon Vortex standalone background scheduler...")
    
    FAST_INTERVAL = 30 * 60  # 30 minutes
    FULL_INTERVAL = 24 * 60 * 60  # 24 hours
    
    # Run fast scan immediately on startup
    run_fast_scan()
    
    last_fast = time.time()
    last_full = time.time()
    
    try:
        while True:
            time.sleep(10)
            now = time.time()
            
            # Check fast scan (every 30 mins)
            if now - last_fast >= FAST_INTERVAL:
                run_fast_scan()
                last_fast = now
                
            # Check full scan (every 24 hours)
            if now - last_full >= FULL_INTERVAL:
                run_full_scan()
                last_full = now
    except KeyboardInterrupt:
        print("[+] Scheduler stopped by user.")

if __name__ == "__main__":
    main()
