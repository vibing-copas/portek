from ..blockchain.erc20 import metadata
from .math import human, unit_price, discount, eta_days


def execute_row(vortex, w3, token, market):
    meta = metadata(w3, token)
    available = int(vortex.functions.availableTokens(token).call())
    ppm = int(vortex.functions.rewardsPPM().call())
    reward_raw = available * ppm // 1_000_000
    p = market.get(token.lower(), {}).get("price_usd")
    return {
        "token": token, "symbol": meta["symbol"], "available_raw": available,
        "available": human(available, meta["decimals"]), "ppm": ppm,
        "reward": human(reward_raw, meta["decimals"]),
        "reward_usd": None if p is None else human(reward_raw, meta["decimals"]) * p,
        "market_usd": p,
        "size_usd": None if p is None else human(available, meta["decimals"]) * p,
    }


def execute_row_multicall(token, meta, available, ppm, market):
    reward_raw = available * ppm // 1_000_000
    p = market.get(token.lower(), {}).get("price_usd")
    return {
        "token": token, "symbol": meta["symbol"], "available_raw": available,
        "available": human(available, meta["decimals"]), "ppm": ppm,
        "reward": human(reward_raw, meta["decimals"]),
        "reward_usd": None if p is None else human(reward_raw, meta["decimals"]) * p,
        "market_usd": p,
        "size_usd": None if p is None else human(available, meta["decimals"]) * p,
    }


def trade_row(vortex, w3, token, ctx, market):
    c = __import__("web3").Web3.to_checksum_address(token)
    cls = __import__("carbon_tracker.blockchain.vortex", fromlist=["classify"]).classify(c, ctx)
    meta = metadata(w3, c)
    base = {"token": c, "symbol": meta["symbol"], "level": cls["level"], "status": "OK", "reason": "", "available": 0}
    if not cls["tradable"]:
        base.update(status="SKIP", reason="finalTargetToken")
        return base
    if not vortex.functions.tradingEnabled(c).call():
        base.update(status="SKIP", reason="tradingDisabled")
        return base
    available = int(vortex.functions.amountAvailableForTrading(c).call())
    base["available"] = human(available, meta["decimals"])
    base["available_raw"] = available
    if available <= 0:
        base.update(status="SKIP", reason="noInventory")
        return base
    try:
        required_source = int(vortex.functions.expectedTradeInput(c, available).call())
    except Exception as exc:
        base.update(status="SKIP", reason=f"quoteError:{type(exc).__name__}")
        return base

    source_meta = metadata(w3, cls["source"])
    target_meta = metadata(w3, cls["target"])
    auction_unit = unit_price(required_source, available, source_meta["decimals"], target_meta["decimals"])
    source_market = market.get(cls["source"].lower(), {}).get("price_usd")
    target_market = market.get(cls["target"].lower(), {}).get("price_usd")
    auction_usd = None if source_market is None else auction_unit * source_market
    target_usd = target_market
    disc = discount(auction_usd, target_usd)
    premium_pct = None
    if auction_usd is not None and target_usd is not None and target_usd > 0:
        premium_pct = (auction_usd / target_usd - 1) * 100
    market_rate = None
    if source_market is not None and source_market > 0 and target_market is not None:
        market_rate = target_market / source_market
    market_value = None if target_usd is None else human(available, target_meta["decimals"]) * target_usd
    cost_usd = None if source_market is None else human(required_source, source_meta["decimals"]) * source_market
    profit = None if market_value is None or cost_usd is None else market_value - cost_usd
    half = ctx["target_price_decay_half_life"] if cls["level"] == 2 else ctx["price_decay_half_life"]
    eta = eta_days(auction_usd, target_usd, half)
    base.update(
        status="OK", pair=f"{source_meta['symbol']} -> {target_meta['symbol']}",
        source_symbol=source_meta["symbol"], target_symbol=target_meta["symbol"],
        source_address=cls["source"], target_address=cls["target"],
        required_source=human(required_source, source_meta["decimals"]),
        required_source_raw=str(required_source), auction_unit=auction_unit,
        market_rate=market_rate, premium_pct=premium_pct,
        auction_usd=auction_usd, market_usd=target_usd, discount_pct=disc,
        market_value_usd=market_value, cost_usd=cost_usd, estimated_profit_usd=profit,
        eta_days=eta, half_life_seconds=half,
        target_decay_half_life_on_reset_seconds=ctx["target_price_decay_half_life_on_reset"],
    )
    return base


def trade_row_multicall(token, meta, source_meta, target_meta, cls, t_data, ctx, market):
    base = {"token": token, "symbol": meta["symbol"], "level": cls["level"], "status": t_data["quote_status"], "reason": t_data.get("quote_reason", ""), "available": 0}
    if t_data["quote_status"] == "SKIP":
        return base
        
    available = t_data["available_trade_raw"]
    required_source = t_data["required_source_raw"]
    
    base["available"] = human(available, meta["decimals"])
    base["available_raw"] = available
    
    auction_unit = unit_price(required_source, available, source_meta["decimals"], target_meta["decimals"])
    source_market = market.get(cls["source"].lower(), {}).get("price_usd")
    target_market = market.get(cls["target"].lower(), {}).get("price_usd")
    auction_usd = None if source_market is None else auction_unit * source_market
    target_usd = target_market
    disc = discount(auction_usd, target_usd)
    
    premium_pct = None
    if auction_usd is not None and target_usd is not None and target_usd > 0:
        premium_pct = (auction_usd / target_usd - 1) * 100
        
    market_rate = None
    if source_market is not None and source_market > 0 and target_market is not None:
        market_rate = target_market / source_market
        
    market_value = None if target_usd is None else human(available, target_meta["decimals"]) * target_usd
    cost_usd = None if source_market is None else human(required_source, source_meta["decimals"]) * source_market
    profit = None if market_value is None or cost_usd is None else market_value - cost_usd
    half = ctx["target_price_decay_half_life"] if cls["level"] == 2 else ctx["price_decay_half_life"]
    eta = eta_days(auction_usd, target_usd, half)
    
    base.update(
        status="OK", pair=f"{source_meta['symbol']} -> {target_meta['symbol']}",
        source_symbol=source_meta["symbol"], target_symbol=target_meta["symbol"],
        source_address=cls["source"], target_address=cls["target"],
        required_source=human(required_source, source_meta["decimals"]),
        required_source_raw=str(required_source), auction_unit=auction_unit,
        market_rate=market_rate, premium_pct=premium_pct,
        auction_usd=auction_usd, market_usd=target_usd, discount_pct=disc,
        market_value_usd=market_value, cost_usd=cost_usd, estimated_profit_usd=profit,
        eta_days=eta, half_life_seconds=half,
        target_decay_half_life_on_reset_seconds=ctx["target_price_decay_half_life_on_reset"],
    )
    return base
