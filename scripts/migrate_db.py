import os
import sys
import argparse
import urllib.request
import urllib.error
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "tracker.db"

def main():
    parser = argparse.ArgumentParser(description="Migrate local SQLite database to Railway deployed app.")
    parser.add_argument("--url", type=str, required=True, help="Railway deployed app base URL (e.g. https://your-app.up.railway.app)")
    parser.add_argument("--secret", type=str, default=os.getenv("MIGRATION_SECRET", "default-temp-secret-key-12345"), help="Migration secret key")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to local sqlite db file (default: data/tracker.db)")
    
    args = parser.parse_args()
    
    db_file = Path(args.db).resolve()
    if not db_file.exists():
        print(f"[-] Error: Database file not found at: {db_file}")
        sys.exit(1)
        
    file_size_mb = db_file.stat().st_size / (1024 * 1024)
    print(f"[+] Local DB file found: {db_file} ({file_size_mb:.2f} MB)")
    
    endpoint = args.url.rstrip("/") + "/api/admin/migrate-db"
    print(f"[+] Target migration endpoint: {endpoint}")
    
    import gzip
    with open(db_file, "rb") as f:
        raw_bytes = f.read()
        
    compressed_bytes = gzip.compress(raw_bytes)
    compressed_mb = len(compressed_bytes) / (1024 * 1024)
    print(f"[+] Compressed payload using gzip: {file_size_mb:.2f} MB -> {compressed_mb:.2f} MB")
    
    import base64
    CHUNK_SIZE = 250 * 1024  # 250 KB per chunk
    chunks = [compressed_bytes[i:i + CHUNK_SIZE] for i in range(0, len(compressed_bytes), CHUNK_SIZE)]
    total_chunks = len(chunks)
    chunk_endpoint = args.url.rstrip("/") + "/api/admin/upload-db-chunk-json"
    
    print(f"[+] Uploading database in {total_chunks} small Base64 JSON chunks to Railway...")
    
    for idx, chunk_data in enumerate(chunks):
        b64_str = base64.b64encode(chunk_data).decode("utf-8")
        payload = {
            "secret": args.secret,
            "chunk_index": idx,
            "total_chunks": total_chunks,
            "data_b64": b64_str
        }
        json_bytes = json.dumps(payload).encode("utf-8")
        
        req = urllib.request.Request(
            chunk_endpoint,
            data=json_bytes,
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                res_body = resp.read().decode("utf-8")
                res_data = json.loads(res_body)
                if res_data.get("status") == "success":
                    print(f"\n[✓] Chunked JSON Migration Successful! (All {total_chunks} chunks reassembled on Railway)")
                    print(json.dumps(res_data, indent=2))
                else:
                    print(f"  [+] Chunk {idx + 1}/{total_chunks} uploaded successfully ({len(chunk_data)} bytes)...")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"\n[-] HTTP Error uploading chunk {idx + 1}/{total_chunks} ({e.code}): {e.reason}")
            print(err_body)
            sys.exit(1)
        except Exception as e:
            print(f"\n[-] Failed uploading chunk {idx + 1}/{total_chunks}: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
