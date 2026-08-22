const { JsonRpcProvider, WebSocketProvider, getAddress } = require("ethers");
const { Toolkit } = require("@bancor/carbon-sdk/strategy-management");
const { initSyncedCache } = require("@bancor/carbon-sdk/chain-cache");
const { ContractsApi } = require("@bancor/carbon-sdk/contracts-api");

async function main() {
    const args = process.argv.slice(2);
    if (args.length < 4) {
        console.error("Usage: node get_carbon_prices.js <rpcUrl> <controllerAddress> <stablecoinsJson> <tokensJson>");
        process.exit(1);
    }
    
    const rpcUrl = args[0];
    const controllerAddress = getAddress(args[1]);
    const stablecoins = JSON.parse(args[2]).map(s => [getAddress(s[0]), s[1]]);
    const tokens = JSON.parse(args[3]).map(t => [getAddress(t[0]), t[1], t[2]]);
    
    const provider = rpcUrl.startsWith("ws")
        ? new WebSocketProvider(rpcUrl)
        : new JsonRpcProvider(rpcUrl);
    const config = {
        carbonControllerAddress: controllerAddress,
        multiCallAddress: "0xcA11bde05977b3631167028862bE2a173976CA11",
    };
    
    const api = new ContractsApi(provider, config);
    const { cache, startDataSync } = initSyncedCache(api.reader);
    
    const carbonSDK = new Toolkit(
        api,
        cache,
        (address) => {
            const addrLower = address.toLowerCase();
            const t = tokens.find(tk => tk[0].toLowerCase() === addrLower);
            if (t) return t[2];
            const s = stablecoins.find(st => st[0].toLowerCase() === addrLower);
            if (s) return s[1];
            if (addrLower === "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee") return 18;
            return 18;
        }
    );
    
    // Start data sync and wait for it to complete initial sync
    await startDataSync();
    
    const prices = {};
    
    // Initialize stablecoin prices to 1.0 USD
    for (const [addr, dec] of stablecoins) {
        prices[addr] = 1.0;
    }
    
    const nativeAddr = getAddress("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee");
    
    // Helper function to get rate between two tokens using getTradeData
    async function getRate(src, tgt, decimals) {
        try {
            const amount = decimals >= 3 ? "0.001" : "1";
            const data = await carbonSDK.getTradeData(src, tgt, amount, false);
            if (data && data.effectiveRate && data.effectiveRate !== "0") {
                return parseFloat(data.effectiveRate);
            }
        } catch (e) {
            // Silence expected insufficient liquidity errors
        }
        return null;
    }
    
    // 1. Resolve Native Token price first if it's not already in prices
    if (!prices[nativeAddr]) {
        for (const [stableAddr, stableDec] of stablecoins) {
            let rate = await getRate(nativeAddr, stableAddr, 18);
            if (rate === null) {
                const reverseRate = await getRate(stableAddr, nativeAddr, stableDec);
                if (reverseRate !== null && reverseRate !== 0) {
                    rate = 1 / reverseRate;
                }
            }
            if (rate !== null) {
                prices[nativeAddr] = rate; // since stablecoin is 1.0 USD
                break;
            }
        }
    }
    
    // 2. Resolve target tokens prices
    for (const [tAddr, symbol, tDec] of tokens) {
        if (prices[tAddr]) continue;
        
        // Try directly against stablecoins
        let resolved = false;
        for (const [stableAddr, stableDec] of stablecoins) {
            let rate = await getRate(tAddr, stableAddr, tDec);
            if (rate === null) {
                const reverseRate = await getRate(stableAddr, tAddr, stableDec);
                if (reverseRate !== null && reverseRate !== 0) {
                    rate = 1 / reverseRate;
                }
            }
            if (rate !== null) {
                prices[tAddr] = rate;
                resolved = true;
                break;
            }
        }
        
        // If not resolved, try against native token (like ETH)
        if (!resolved && prices[nativeAddr]) {
            let rate = await getRate(tAddr, nativeAddr, tDec);
            if (rate === null) {
                const reverseRate = await getRate(nativeAddr, tAddr, 18);
                if (reverseRate !== null && reverseRate !== 0) {
                    rate = 1 / reverseRate;
                }
            }
            if (rate !== null) {
                prices[tAddr] = rate * prices[nativeAddr];
                resolved = true;
            }
        }
    }
    
    // Format output exactly like estimate_carbon_prices in Python:
    const market = {};
    for (const [tAddr, symbol, tDec] of tokens) {
        if (prices[tAddr] !== undefined) {
            market[tAddr.toLowerCase()] = {
                price_usd: prices[tAddr],
                liquidity_usd: 100000.0,
                is_carbon_native: true
            };
        }
    }
    
    console.log(JSON.stringify(market));
    process.exit(0);
}

main().catch(err => {
    console.error(err.message || err);
    process.exit(1);
});
