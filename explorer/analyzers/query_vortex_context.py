#!/usr/bin/env python3
import os
import sys
import json
import yaml
import dotenv
from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

dotenv.load_dotenv()
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
ABI_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "abis", "CarbonVortex.json")

def query_contexts():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with open(ABI_PATH, "r", encoding="utf-8") as f:
        vortex_abi = json.load(f)

    print("=" * 80)
    print("QUERYING VORTEX CONTRACT CONTEXT (targetToken & finalTargetToken)")
    print("=" * 80)

    contexts = {}
    for chain_name, chain_cfg in config["chains"].items():
        chain_id = chain_cfg["chain_id"]
        vortex_addr = chain_cfg["carbon_vortex"]
        
        # Resolve RPC URL
        rpc_env = chain_cfg.get("rpc_env", "")
        rpc_url = os.getenv(rpc_env, "").strip() if rpc_env else ""
        if not rpc_url:
            rpc_url = chain_cfg.get("public_rpc", "").strip()

        print(f"\n[+] Chain: {chain_name.upper()} (Chain ID {chain_id})")
        print(f"    RPC URL : {rpc_url}")
        print(f"    Vortex  : {vortex_addr}")

        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not w3.is_connected():
                print(f"    [-] Could not connect to RPC {rpc_url}")
                continue

            contract = w3.eth.contract(address=Web3.to_checksum_address(vortex_addr), abi=vortex_abi)
            
            target_token = contract.functions.targetToken().call()
            final_target_token = contract.functions.finalTargetToken().call()
            
            # Fetch symbols for target and final target
            meta_abi = [
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
            ]

            target_sym = "ETH" if target_token.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" else "NATIVE"
            if target_token.lower() != "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
                try:
                    c_tgt = w3.eth.contract(address=Web3.to_checksum_address(target_token), abi=meta_abi)
                    target_sym = c_tgt.functions.symbol().call()
                except Exception:
                    pass

            final_sym = "BNT" if final_target_token.lower() == "0x1f573d6fb3f13d689ff844b4ce37794d79a7ff1c" else "FINAL"
            try:
                c_final = w3.eth.contract(address=Web3.to_checksum_address(final_target_token), abi=meta_abi)
                final_sym = c_final.functions.symbol().call()
            except Exception:
                pass

            print(f"    targetToken       : {target_token} ({target_sym})")
            print(f"    finalTargetToken  : {final_target_token} ({final_sym})")
            
            contexts[chain_name] = {
                "chain_id": chain_id,
                "vortex_address": vortex_addr.lower(),
                "target_token": target_token.lower(),
                "target_symbol": target_sym,
                "final_target_token": final_target_token.lower(),
                "final_target_symbol": final_sym
            }
        except Exception as e:
            print(f"    [-] Exception querying vortex context: {e}")

    out_path = os.path.join("data", "vortex_contexts.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(contexts, f, indent=2)

    print(f"\n[+] Saved on-chain Vortex contexts to {out_path}")

if __name__ == "__main__":
    query_contexts()
