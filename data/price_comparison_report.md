# Price Feed Layers Comparison Report
Comparison of **Case 1 (2-layer: DexScreener + Carbon)** and **Case 2 (3-layer: DIA API + DexScreener + Carbon)**.
## 1. Performance and Resolution Summary
| Metric | Case 1 (2-Layer) | Case 2 (3-Layer) | Difference |
|---|---|---|---|
| **Execution Time** | 18.84 seconds | 47.59 seconds | +28.75 seconds | 
| **Total Tokens Checked** | 37 | 37 | - |
| **Resolved successfully** | 37 | 37 | +0 |
| **- From DIA API** | - | 26 | +26 |
| **- From DexScreener** | 34 | 8 | -26 |
| **- From Carbon Strategy** | 3 | 3 | +0 |
| **Failed / Unresolved** | 0 | 0 | +0 |

## 2. Price Differences (Side-by-Side)
Listing tokens resolved by both price feeds to check for price deviations.
| Chain | Symbol | Address | Case 1 Price (USD) | Case 2 Price (USD) | Source (C1 / C2) | Diff ($) | Diff (%) |
|---|---|---|---|---|---|---|---|
| Ethereum | BNT | `0x1F573D6Fb3F13d689FF844B4cE37794d79a7FF1C` | $0.322300 | $0.319600 | DexScreener / DIA API | -0.002700 | -0.84% |
| Ethereum | sUSDS | `0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD` | $1.099000 | $1.107323 | DexScreener / DIA API | +0.008323 | +0.76% |
| Ethereum | sfrxUSD | `0xcf62F905562626CfcDD2261162a51fd02Fc9c5b6` | $1.200000 | $1.206936 | DexScreener / DIA API | +0.006936 | +0.58% |
| Ethereum | USDT | `0xdAC17F958D2ee523a2206206994597C13D831ec7` | $0.999900 | $0.994326 | DexScreener / DIA API | -0.005574 | -0.56% |
| Ethereum | ARB | `0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1` | $0.096090 | $0.095634 | DexScreener / DIA API | -0.000456 | -0.47% |
| Ethereum | XAUt | `0x68749665FF8D2d112Fa859AA293F07A622782F38` | $4,593.400000 | $4,573.262190 | DexScreener / DIA API | -20.137810 | -0.44% |
| Ethereum | MATIC | `0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0` | $0.102800 | $0.103205 | DexScreener / DIA API | +0.000405 | +0.39% |
| Ethereum | PEPE | `0x6982508145454Ce325dDbE47a25d4ec3d2311933` | $0.000004 | $0.000004 | DexScreener / DIA API | -0.000000 | -0.31% |
| Ethereum | BIFI | `0xB1F1ee126e9c96231Cc3d3fAD7C08b4cf873b1f1` | $47.840000 | $47.985658 | DexScreener / DIA API | +0.145658 | +0.30% |
| Ethereum | COTI | `0xDDB3422497E61e13543BeA06989C0789117555c5` | $0.012190 | $0.012158 | DexScreener / DIA API | -0.000032 | -0.26% |
| Ethereum | ANDY | `0x68BbEd6A47194EFf1CF514B50Ea91895597fc91E` | $0.000009 | $0.000009 | DexScreener / DIA API | -0.000000 | -0.26% |
| Ethereum | CRV | `0xD533a949740bb3306d119CC777fa900bA034cd52` | $0.318800 | $0.318155 | DexScreener / DIA API | -0.000645 | -0.20% |
| Ethereum | GUSD | `0x056Fd409E1d7A124BD7017459dFEa2F387b6d5Cd` | $1.002500 | $1.000827 | DexScreener / DIA API | -0.001673 | -0.17% |
| Ethereum | SHIB | `0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE` | $0.000005 | $0.000005 | DexScreener / DIA API | -0.000000 | -0.16% |
| Ethereum | DAI | `0x6B175474E89094C44Da98b954EedeAC495271d0F` | $1.000130 | $0.998882 | DexScreener / DIA API | -0.001248 | -0.12% |
| Ethereum | USDC | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` | $1.000035 | $0.998868 | DexScreener / DIA API | -0.001167 | -0.12% |
| Ethereum | UNI | `0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984` | $4.056000 | $4.051312 | DexScreener / DIA API | -0.004688 | -0.12% |
| Ethereum | USDS | `0xdC035D45d973E3EC169d2276DDab16f1e407384F` | $1.000035 | $0.998888 | DexScreener / DIA API | -0.001147 | -0.11% |
| Ethereum | RAIL | `0xe76C6c83af64e4C60245D8C7dE953DF673a7A33D` | $2.100000 | $2.098070 | DexScreener / DIA API | -0.001930 | -0.09% |
| Ethereum | AAVE | `0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9` | $122.280000 | $122.392258 | DexScreener / DIA API | +0.112258 | +0.09% |
| Ethereum | LINK | `0x514910771AF9Ca656af840dff83E8264EcF986CA` | $11.140000 | $11.132723 | DexScreener / DIA API | -0.007277 | -0.07% |
| Ethereum | wstETH | `0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0` | $2,950.200000 | $2,948.417714 | DexScreener / DIA API | -1.782286 | -0.06% |
| Ethereum | PAXG | `0x45804880De22913dAFE09f4980848ECE6EcbAf78` | $4,586.960000 | $4,586.057644 | DexScreener / DIA API | -0.902356 | -0.02% |
| Ethereum | WBTC | `0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599` | $76,045.180000 | $76,055.266518 | DexScreener / DIA API | +10.086518 | +0.01% |
| Ethereum | LDO | `0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32` | $0.349700 | $0.349724 | DexScreener / DIA API | +0.000024 | +0.01% |
| Ethereum | ETH | `0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE` | $2,373.600000 | $2,373.657711 | DexScreener / DIA API | +0.057711 | +0.00% |
| Ethereum | RTB | `0x055999B83f9cADE9E3988A0f34Ef72817566800D` | $0.001000 | $0.001000 | Carbon Strategy / Carbon Strategy | +0.000000 | +0.00% |
| Ethereum | BZZ | `0x19062190B1925b5b6689D7073fDfC8c2976EF8Cb` | $0.041020 | $0.041020 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | vBNT | `0x48Fb253446873234F2fEBbF9BdeAA72d9d387f94` | $0.219000 | $0.219000 | Carbon Strategy / Carbon Strategy | +0.000000 | +0.00% |
| Ethereum | LVVA | `0x6243558a24CC6116aBE751f27E6d7Ede50ABFC76` | $0.000334 | $0.000334 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | WINGS | `0x667088b212ce3d06a1b553a7221E1fD19000d9aF` | $0.000163 | $0.000163 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | GET | `0x8a854288a5976036A725879164Ca3e91d30c6A1B` | $0.070850 | $0.070850 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | LF | `0x957c7fA189a408E78543113412f6Ae1a9b4022C4` | $0.000034 | $0.000034 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | gCOTI | `0xAf2CA40d3fc4459436D11B94d21FA4b8A89fB51d` | $0.000654 | $0.000654 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | VAIX | `0xB7b37b81d4497AB317fc9d4A370CF243043d6bBe` | $0.001110 | $0.001110 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | sfrxETH | `0xac3E018457B222d93114458476f3E3416Abbe38F` | $2,834.900000 | $2,834.900000 | DexScreener / DexScreener | +0.000000 | +0.00% |
| Ethereum | GVNR | `0xfc60fc0145D7330e5abcFc52AF7B043a1cE18e7d` | $0.786506 | $0.786506 | Carbon Strategy / Carbon Strategy | +0.000000 | +0.00% |
