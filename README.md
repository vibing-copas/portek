# Carbon Vortex Tracker V1

Read-only daily scanner for CarbonVortex. No private key and no transaction signing.

## What it does

- Discovers fee tokens from `CarbonController.TokensTraded` logs.
- Correctly derives the fee-token denomination from `byTargetAmount`:
  - `false` => fee is taken from `sourceToken`.
  - `true` => fee is taken from `targetToken`.
- Reads `targetToken` and `finalTargetToken` from CarbonVortex.
- Classifies trade opportunities:
  - `token == finalTargetToken`: skip trade.
  - `token == targetToken`: Level 2, targetToken -> finalTargetToken.
  - otherwise: Level 1, feeToken -> targetToken.
- Execute scan: `availableTokens`, `rewardsPPM`, estimated reward USD.
- Trade scan: `tradingEnabled`, `amountAvailableForTrading`, full-inventory `expectedTradeInput`; failed quotes are skipped.
- Computes auction unit price, USD auction price, market USD price, discount, full-inventory theoretical P/L, and simple decay ETA.
- Uses DexScreener token endpoint in batches of up to 30 addresses.
- Saves daily snapshots to SQLite and renders a Streamlit dashboard with Level 2 above Level 1.

## Important contract fact

Carbon's `TokensTraded` event says `tradingFeeAmount` is the fee earned by Carbon. The verified controller source shows the fee is accumulated in `sourceToken` when the trade is by source amount (`byTargetAmount == false`), and in `targetToken` when the trade is by target amount (`byTargetAmount == true`).

## Ethereum deployment

Carbon docs list:
- CarbonController: `0xC537e898CD774e2dCBa3B14Ea6f34C93d5eA45e1`
- CarbonVortex: `0xD053Dcd7037AF7204cecE544Ea9F227824d79801`

These are in `config.yaml`.

## Setup

1. Python 3.11+ recommended.
2. `python -m venv .venv`
3. Activate the venv.
4. `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and put your RPC URL there.
6. Set `START_BLOCK` to the CarbonController deployment block, or a safe historical block. If you leave it at 0, the scanner uses the configured lookback.
7. Run one scan:
   `python -m carbon_tracker.daily_scan`
8. Open dashboard:
   `streamlit run carbon_tracker/ui/dashboard.py`

## Daily run

Use cron/Task Scheduler, or the included `scripts/run_daily.py`. The scanner is intentionally read-only.

## Notes

- ERC-20 metadata is read by `symbol/name/decimals`. Native ETH uses Carbon's standard `0xEeeee...` pseudo-address and is mapped to WETH only for market-price lookup.
- Full-inventory quoting can revert because `expectedTradeInput` returns `uint128`. That is treated as a failed quote and skipped exactly as requested.
- The simple ETA assumes the current auction continues decaying exponentially without a reset before equality. It is an estimate, not a guarantee.
- Gas is not subtracted in V1; transaction signing/auto-execution is intentionally out of scope.
