# Sub-proyek: Explorer (Carbon Vortex Log & Token Explorer)

Sub-proyek **Explorer** bertugas melakukan pemindaian (scanning) log transaksi on-chain sejak **Contract Creation Block** untuk menarik data event `TradedToken` (Topic1) dan `PriceUpdated` (Topic3/Topic2 Controller), melakukan pengayaan metadata token, serta membuat dashboard visualisasi statis per chain.

---

## 📁 Struktur Direktori `explorer/`

```
explorer/
├── scanners/            # Skrip scanning log on-chain sejak contract creation
│   ├── scan_etherscan_v2_logs.py           # Multi-chain scanner via Etherscan v2 API
│   ├── scan_vortex_multi_chain.py          # Scanner multi-chain dengan chunking otomatis
│   ├── scan_celo_tokens_fast.py            # Fast RPC scanner untuk Celo
│   ├── scan_celo_tokens_fast_v2.py         # Fast RPC scanner v2 untuk Celo
│   ├── scan_and_enrich_sei_celo_tokens.py  # Log scanner & metadata enricher untuk Sei & Celo
│   ├── fetch_controller_topic3_addresses.py# Mengambil address dari log Controller PriceUpdated
│   ├── fetch_vortex_eth_topic1_addresses.py# Mengambil address dari log Vortex TradedToken
│   ├── find_contract_deploy_block.py       # Menentukan block terkecil (Contract Creation Block)
│   └── scan_vortex_logs.py                 # Single-chain vortex scanner
├── analyzers/           # Skrip analisis data, pengayaan metadata, & konsolidasi DB
│   ├── analyze_total_volume.py             # Menghitung total akumulasi volume & fee per token
│   ├── analyze_vortex_trades.py            # Analisa mendalam histori perdagangan Vortex
│   ├── enrich_token_metadata.py            # Melengkapi symbol & decimals token via RPC/Coingecko
│   ├── consolidate_tokens_to_db.py         # Sinkronisasi log token ke SQLite (token_registry)
│   ├── insert_missing_controller_tokens.py # Sinkronisasi token Controller ke registry DB
│   ├── insert_missing_topic1_tokens.py     # Sinkronisasi token Topic1 ke registry DB
│   ├── compare_topic1_with_db.py           # Perbandingan token hasil scan vs database
│   ├── inspect_celo_tokens_db.py           # Inspeksi status token Celo di DB
│   ├── inspect_sei_celo_tokens.py          # Inspeksi status token Sei/Celo
│   ├── query_vortex_context.py             # Query data konteks Vortex
│   ├── check_chain_tokens_db.py            # Pemeriksaan kecocokan token_registry per chain
│   ├── cleanup_db_duplicates.py            # Pembersihan duplikat data registry
│   └── import_logs_to_db_snapshots.py      # Impor log historis ke tabel snapshots
├── dashboards/          # Generator & file dashboard HTML statis
│   ├── generate_all_dashboards.py          # Generator otomatis semua dashboard HTML
│   ├── generate_dashboard.py               # Template generator dashboard HTML
│   ├── vortex_eth_dashboard.html           # Dashboard statis Ethereum Mainnet
│   ├── vortex_celo_dashboard.html          # Dashboard statis Celo Mainnet
│   └── vortex_sei_dashboard.html           # Dashboard statis Sei Mainnet
└── utils/               # Skrip pengujian RPC & API Etherscan
    ├── check_celo_etherscan_api.py         # Tes konektivitas API Celo Etherscan
    ├── test_celo_fast_rpc.py               # Tes kecepatan RPC Celo
    └── test_etherscan_v2_celo.py           # Tes endpoint Etherscan v2 Celo
```

---

## 🚀 Panduan Penggunaan Sub-proyek

### 1. Pindai Log On-Chain sejak Contract Creation Block
Untuk memindai event `PriceUpdated` & `TradedToken` dari block pertama kontrak dibuat:
```bash
python explorer/scanners/scan_etherscan_v2_logs.py
```

### 2. Analisis & Pengayaan Metadata Token
Untuk melengkapi symbol, decimals, dan total akumulasi volume token:
```bash
python explorer/analyzers/enrich_token_metadata.py
python explorer/analyzers/analyze_total_volume.py
```

### 3. Konsolidasi Data Token ke Database (`token_registry`)
Untuk memasukkan hasil pemindaian log ke database SQLite:
```bash
python explorer/analyzers/consolidate_tokens_to_db.py
```

### 4. Generate Dashboard Statis Per Chain
Untuk memperbarui file HTML dashboard statis (`vortex_eth_dashboard.html`, dll.):
```bash
python explorer/dashboards/generate_all_dashboards.py
```
