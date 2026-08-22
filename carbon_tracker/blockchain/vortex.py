from web3 import Web3

def context(vortex):
    return {
        "target_token": Web3.to_checksum_address(vortex.functions.targetToken().call()),
        "final_target_token": Web3.to_checksum_address(vortex.functions.finalTargetToken().call()),
        "price_decay_half_life": int(vortex.functions.priceDecayHalfLife().call()),
        "target_price_decay_half_life": int(vortex.functions.targetTokenPriceDecayHalfLife().call()),
        "target_price_decay_half_life_on_reset": int(vortex.functions.targetTokenPriceDecayHalfLifeOnReset().call()),
        "rewards_ppm": int(vortex.functions.rewardsPPM().call()),
    }

def classify(token, ctx):
    token = Web3.to_checksum_address(token)
    if token.lower() == ctx["final_target_token"].lower():
        return {"level": None, "source": None, "target": None, "tradable": False, "reason": "finalTargetToken"}
    if token.lower() == ctx["target_token"].lower():
        return {"level": 2, "source": ctx["final_target_token"], "target": ctx["target_token"], "tradable": True, "reason": "targetToken"}
    return {"level": 1, "source": ctx["target_token"], "target": token, "tradable": True, "reason": "feeToken"}
