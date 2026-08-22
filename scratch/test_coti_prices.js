const { JsonRpcProvider } = require("ethers");
const { Toolkit } = require("@bancor/carbon-sdk/strategy-management");
const { initSyncedCache } = require("@bancor/carbon-sdk/chain-cache");
const { ContractsApi } = require("@bancor/carbon-sdk/contracts-api");

async function main() {
    const rpcUrl = "https://mainnet.coti.io/rpc";
    const controllerAddress = "0x59f21012B2E9BA67ce6a7605E74F945D0D4C84EA";
    
    const provider = new JsonRpcProvider(rpcUrl);
    const config = {
        carbonControllerAddress: controllerAddress,
        multiCallAddress: "0xcA11bde05977b3631167028862bE2a173976CA11",
    };
    
    const api = new ContractsApi(provider, config);
    const { cache, startDataSync } = initSyncedCache(api.reader);
    
    await startDataSync();
    
    const cachedPairs = cache.getCachedPairs(true);
    console.log("Cached Pairs with active strategies:");
    for (const p of cachedPairs) {
        console.log(`  - ${p[0]} / ${p[1]}`);
    }
}

main().catch(console.error);
