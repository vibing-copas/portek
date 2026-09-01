#!/usr/bin/env python3
import os
import json

CHAINS = {
    "ethereum": {
        "name": "Ethereum Mainnet",
        "chain_id": 1,
        "contract": "0xD053Dcd7037AF7204cecE544Ea9F227824d79801",
        "explorer_tx": "https://etherscan.io/tx/",
        "explorer_addr": "https://etherscan.io/address/",
        "totals_file": os.path.join("data", "vortex_eth_trade_totals.json"),
        "output_html": "vortex_eth_dashboard.html"
    },
    "sei": {
        "name": "Sei Network",
        "chain_id": 1329,
        "contract": "0x5715203B16F15d7349Cb1E3537365E9664EAf933",
        "explorer_tx": "https://seitrace.com/tx/",
        "explorer_addr": "https://seitrace.com/address/",
        "totals_file": os.path.join("data", "vortex_sei_trade_totals.json"),
        "output_html": "vortex_sei_dashboard.html"
    },
    "celo": {
        "name": "Celo Mainnet",
        "chain_id": 42220,
        "contract": "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857",
        "explorer_tx": "https://celoscan.io/tx/",
        "explorer_addr": "https://celoscan.io/address/",
        "totals_file": os.path.join("data", "vortex_celo_trade_totals.json"),
        "output_html": "vortex_celo_dashboard.html"
    }
}

def generate_chain_html(chain_key, cfg):
    totals_data = []
    if os.path.exists(cfg["totals_file"]):
        with open(cfg["totals_file"], "r", encoding="utf-8") as f:
            totals_data = json.load(f)

    json_embedded = json.dumps(totals_data)
    total_events = sum(t.get("trade_count", 0) for t in totals_data)
    l1_count = len([t for t in totals_data if t.get("level") == 1])
    l2_count = sum(t.get("trade_count", 0) for t in totals_data if t.get("level") == 2)
    native_sym = "SEI" if chain_key == "sei" else ("CELO" if chain_key == "celo" else "ETH")
    final_sym = "BNT" if chain_key == "ethereum" else "WETH"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vortex {cfg['name']} - Trade Analytics Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #090c15;
            --card-bg: rgba(17, 24, 39, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-hover: rgba(30, 41, 64, 0.85);
            --primary: #6366f1;
            --primary-glow: rgba(99, 102, 241, 0.35);
            --accent: #10b981;
            --accent-glow: rgba(16, 185, 129, 0.35);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 85% 80%, rgba(16, 185, 129, 0.08) 0%, transparent 40%);
            background-attachment: fixed;
            padding-bottom: 60px;
        }}
        .navbar {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 20px 40px; background: rgba(9, 12, 21, 0.85);
            backdrop-filter: blur(16px); border-bottom: 1px solid var(--card-border);
            position: sticky; top: 0; z-index: 100;
        }}
        .brand {{ display: flex; align-items: center; gap: 14px; }}
        .brand-icon {{
            width: 42px; height: 42px; border-radius: 12px;
            background: linear-gradient(135deg, #6366f1, #10b981);
            display: flex; align-items: center; justify-content: center;
            font-weight: 700; font-size: 20px; box-shadow: 0 0 20px var(--primary-glow);
        }}
        .brand-title {{
            font-size: 22px; font-weight: 700; letter-spacing: -0.5px;
            background: linear-gradient(to right, #ffffff, #9ca3af);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .chain-nav {{ display: flex; gap: 8px; }}
        .chain-nav a {{
            padding: 6px 14px; border-radius: 20px; text-decoration: none;
            font-size: 13px; font-weight: 600; transition: all 0.2s ease;
            background: rgba(255, 255, 255, 0.05); color: var(--text-muted);
            border: 1px solid var(--card-border);
        }}
        .chain-nav a.active, .chain-nav a:hover {{
            background: rgba(99, 102, 241, 0.2); color: #818cf8; border-color: rgba(99, 102, 241, 0.4);
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 30px 20px; }}
        .meta-banner {{
            background: var(--card-bg); border: 1px solid var(--card-border);
            backdrop-filter: blur(12px); border-radius: 16px; padding: 20px 24px;
            margin-bottom: 30px; display: flex; flex-wrap: wrap; gap: 24px;
            justify-content: space-between; align-items: center;
        }}
        .meta-item {{ display: flex; flex-direction: column; gap: 4px; }}
        .meta-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; }}
        .meta-val {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; color: #e5e7eb; background: rgba(255, 255, 255, 0.05); padding: 4px 10px; border-radius: 6px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 35px; }}
        .stat-card {{ background: var(--card-bg); border: 1px solid var(--card-border); backdrop-filter: blur(12px); border-radius: 20px; padding: 24px; position: relative; overflow: hidden; }}
        .stat-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--primary), var(--accent)); }}
        .stat-title {{ font-size: 14px; color: var(--text-muted); margin-bottom: 10px; font-weight: 500; }}
        .stat-value {{ font-size: 30px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px; }}
        .stat-sub {{ font-size: 13px; color: var(--accent); margin-top: 8px; }}
        .controls-bar {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 24px; }}
        .search-box {{ position: relative; flex: 1; min-width: 280px; max-width: 420px; }}
        .search-input {{ width: 100%; padding: 13px 18px 13px 44px; border-radius: 12px; background: rgba(17, 24, 39, 0.8); border: 1px solid var(--card-border); color: var(--text-main); font-family: inherit; font-size: 15px; outline: none; }}
        .search-icon {{ position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }}
        .control-group {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
        .select-sort {{ padding: 10px 14px; border-radius: 10px; background: rgba(17, 24, 39, 0.9); border: 1px solid var(--card-border); color: var(--text-main); font-family: inherit; font-size: 14px; outline: none; }}
        .btn-filter {{ padding: 10px 16px; border-radius: 10px; background: rgba(17, 24, 39, 0.8); border: 1px solid var(--card-border); color: var(--text-muted); font-family: inherit; font-size: 14px; cursor: pointer; }}
        .btn-filter.active {{ background: var(--primary); color: #ffffff; border-color: var(--primary); }}
        .table-card {{ background: var(--card-bg); border: 1px solid var(--card-border); backdrop-filter: blur(12px); border-radius: 20px; overflow: hidden; }}
        .table-responsive {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{ background: rgba(12, 17, 28, 0.9); padding: 16px 20px; font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; border-bottom: 1px solid var(--card-border); }}
        td {{ padding: 16px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); font-size: 15px; vertical-align: middle; }}
        tr.clickable-row {{ cursor: pointer; }}
        tr.clickable-row:hover td {{ background: var(--card-hover); }}
        .token-cell {{ display: flex; align-items: center; gap: 12px; }}
        .token-avatar {{ width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, #4f46e5, #06b6d4); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 13px; color: #fff; }}
        .token-symbol {{ font-weight: 600; color: #ffffff; font-size: 16px; }}
        .level-badge {{ display: inline-flex; padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
        .level-1 {{ background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); }}
        .level-2 {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
        .btn-copy {{ background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.1); color: var(--text-muted); border-radius: 6px; padding: 4px 8px; font-size: 11px; cursor: pointer; }}
        .btn-view-trades {{ background: linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(16, 185, 129, 0.35)); border: 1px solid rgba(99, 102, 241, 0.6); color: #ffffff; padding: 8px 16px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; }}
        .link-etherscan {{ color: #818cf8; text-decoration: none; font-weight: 500; }}
        .link-etherscan:hover {{ color: #c7d2fe; text-decoration: underline; }}
        .amount-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 15px; color: #ffffff; }}
        .usd-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 16px; color: #10b981; }}
        .source-paid-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 15px; color: #818cf8; }}
        .progress-bar-bg {{ width: 100%; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; margin-top: 6px; overflow: hidden; }}
        .progress-bar-fill {{ height: 100%; background: linear-gradient(90deg, #6366f1, #10b981); border-radius: 3px; }}
        
        #trade-modal-overlay {{
            position: fixed !important; top: 0 !important; left: 0 !important;
            width: 100vw !important; height: 100vh !important;
            background: rgba(0, 0, 0, 0.88) !important; backdrop-filter: blur(16px) !important;
            z-index: 999999 !important; display: none; justify-content: center; align-items: center; padding: 20px;
        }}
        .modal-card {{ background: #0f172a; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 24px; width: 100%; max-width: 1150px; max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; }}
        .modal-header {{ padding: 24px 30px; border-bottom: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.98); }}
        .modal-title {{ font-size: 22px; font-weight: 700; color: #ffffff; }}
        .btn-close {{ background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.2); color: #ffffff; width: 42px; height: 42px; border-radius: 50%; font-size: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
        .modal-body {{ padding: 24px 30px; overflow-y: auto; flex: 1; }}
        .trade-detail-summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; background: rgba(30, 41, 59, 0.6); padding: 18px 24px; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 24px; }}
        .detail-item {{ display: flex; flex-direction: column; gap: 4px; }}
        .detail-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; }}
        .detail-val {{ font-size: 16px; font-weight: 600; color: #ffffff; font-family: 'JetBrains Mono', monospace; }}
    </style>
</head>
<body>

    <div class="navbar">
        <div class="brand">
            <div class="brand-icon">{cfg['name'][0]}</div>
            <div class="brand-title">Carbon Vortex - {cfg['name']}</div>
        </div>
        <div class="chain-nav">
            <a href="vortex_eth_dashboard.html" class="{'active' if chain_key=='ethereum' else ''}">Ethereum</a>
            <a href="vortex_sei_dashboard.html" class="{'active' if chain_key=='sei' else ''}">SEI</a>
            <a href="vortex_celo_dashboard.html" class="{'active' if chain_key=='celo' else ''}">CELO</a>
        </div>
    </div>

    <div class="container">

        <div class="meta-banner">
            <div class="meta-item">
                <span class="meta-label">Contract Address</span>
                <span class="meta-val"><a href="{cfg['explorer_addr']}{cfg['contract']}" target="_blank" class="link-etherscan">{cfg['contract']}</a></span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Chain ID</span>
                <span class="meta-val">{cfg['chain_id']}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Topic0 Event Filter</span>
                <span class="meta-val">0x16ddee9b3f1b2e6f797172fe2cd10a214e749294...</span>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-title">Total Log Events</div>
                <div class="stat-value">{total_events:,}</div>
                <div class="stat-sub">⚡ Scanned from Creation Block</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Unique Tokens Traded</div>
                <div class="stat-value">{len(totals_data)}</div>
                <div class="stat-sub">💎 Decoded from topic2</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Level 1 (Token → {native_sym})</div>
                <div class="stat-value">{l1_count} Tokens</div>
                <div class="stat-sub">Fee Tokens → {native_sym} (target)</div>
            </div>
            <div class="stat-card">
                <div class="stat-title">Level 2 ({native_sym} → {final_sym})</div>
                <div class="stat-value">{l2_count} Trades</div>
                <div class="stat-sub">{native_sym} → {final_sym} (final target)</div>
            </div>
        </div>

        <div class="controls-bar">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="search-input" class="search-input" placeholder="Search token symbol or address...">
            </div>
            
            <div class="control-group">
                <span class="control-label">Sort by:</span>
                <select id="select-sort" class="select-sort" onchange="handleSortChange(this.value)">
                    <option value="usd-desc" selected>Total Volume USD ($) (High → Low)</option>
                    <option value="price-desc">Avg Unit Price (High → Low)</option>
                    <option value="amount-desc">Total Target Released (High → Low)</option>
                    <option value="source-desc">Total Source Paid (High → Low)</option>
                    <option value="trades-desc">Trade Count (High → Low)</option>
                    <option value="level-desc">Trade Level (Level 2 → Level 1)</option>
                    <option value="symbol-asc">Token Symbol (A → Z)</option>
                </select>

                <div style="display: flex; gap: 6px; margin-left: 10px;">
                    <button class="btn-filter active" onclick="setFilter('all', this)">All Tokens ({len(totals_data)})</button>
                    <button class="btn-filter" onclick="setFilter('l1', this)">Level 1 ({native_sym})</button>
                    <button class="btn-filter" onclick="setFilter('l2', this)">Level 2 ({final_sym})</button>
                </div>
            </div>
        </div>

        <div class="table-card">
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th style="width: 50px;">#</th>
                            <th>Token</th>
                            <th>Level & Pair</th>
                            <th>Contract Address</th>
                            <th style="text-align: center;">Trade History</th>
                            <th style="text-align: right;">Total Source Paid</th>
                            <th style="text-align: right;">Total Target Amount</th>
                            <th style="text-align: right;">Total Volume ($)</th>
                        </tr>
                    </thead>
                    <tbody id="table-body"></tbody>
                </table>
                <div id="no-results" style="display: none; padding: 40px; text-align: center; color: var(--text-muted);">
                    No tokens found matching search.
                </div>
            </div>
        </div>

    </div>

    <div id="trade-modal-overlay">
        <div class="modal-card">
            <div class="modal-header">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div id="modal-token-avatar" class="token-avatar">#</div>
                    <div>
                        <div class="modal-title" id="modal-title">Token Trade History</div>
                        <div id="modal-subtitle" style="font-size: 13px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">0x...</div>
                    </div>
                </div>
                <button class="btn-close" onclick="closeModal()">✕</button>
            </div>
            
            <div class="modal-body">
                <div class="trade-detail-summary">
                    <div class="detail-item"><span class="detail-label">Trade Level Rule</span><span class="detail-val" id="modal-level-val">-</span></div>
                    <div class="detail-item"><span class="detail-label">Total Volume ($ USD)</span><span class="detail-val" id="modal-usd-val" style="color: #10b981;">-</span></div>
                    <div class="detail-item"><span class="detail-label">Total Target Released</span><span class="detail-val" id="modal-total-amt">-</span></div>
                    <div class="detail-item"><span class="detail-label">Total Source Paid</span><span class="detail-val" id="modal-total-source" style="color: #818cf8;">-</span></div>
                    <div class="detail-item"><span class="detail-label">Total Trades Executed</span><span class="detail-val" id="modal-trade-cnt" style="color: #fbbf24;">-</span></div>
                </div>

                <h4 style="margin-bottom: 16px; font-weight: 600; color: #e2e8f0;">Individual TokenTraded Event Logs</h4>

                <div class="table-responsive" style="border-radius: 14px; border: 1px solid var(--card-border);">
                    <table>
                        <thead>
                            <tr>
                                <th>Timestamp</th>
                                <th>Block</th>
                                <th>Tx Hash (Click to Open)</th>
                                <th>Caller Address</th>
                                <th style="text-align: right;">Target Released</th>
                                <th style="text-align: right;">Source Paid</th>
                                <th style="text-align: right;">Est Value ($)</th>
                            </tr>
                        </thead>
                        <tbody id="modal-trade-tbody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        const rawData = {json_embedded};
        const EXPLORER_TX = "{cfg['explorer_tx']}";
        const EXPLORER_ADDR = "{cfg['explorer_addr']}";
        const NATIVE_SYM = "{native_sym}";
        const FINAL_SYM = "{final_sym}";
        
        let currentFilter = 'all';
        let currentSort = 'usd-desc';
        let searchQuery = '';

        const maxVolumeUsd = rawData.length > 0 ? Math.max(...rawData.map(r => r.volume_usd || 0)) : 1;

        function sortData(data) {{
            return data.sort((a, b) => {{
                if (currentSort === 'usd-desc') return (b.volume_usd || 0) - (a.volume_usd || 0);
                if (currentSort === 'price-desc') return b.avg_unit_price - a.avg_unit_price;
                if (currentSort === 'amount-desc') return b.total_amount - a.total_amount;
                if (currentSort === 'source-desc') return b.total_source_amount - a.total_source_amount;
                if (currentSort === 'trades-desc') return b.trade_count - a.trade_count;
                if (currentSort === 'level-desc') return b.level - a.level;
                if (currentSort === 'symbol-asc') return a.symbol.localeCompare(b.symbol);
                return 0;
            }});
        }}

        function renderTable() {{
            const tbody = document.getElementById('table-body');
            const noResults = document.getElementById('no-results');
            tbody.innerHTML = '';

            let filtered = rawData.filter(item => {{
                const matchesSearch = item.symbol.toLowerCase().includes(searchQuery) || item.address.toLowerCase().includes(searchQuery);
                if (!matchesSearch) return false;
                if (currentFilter === 'l1') return item.level === 1;
                if (currentFilter === 'l2') return item.level === 2;
                return true;
            }});

            filtered = sortData(filtered);
            if (filtered.length === 0) {{ noResults.style.display = 'block'; return; }} else {{ noResults.style.display = 'none'; }}

            filtered.forEach((item, index) => {{
                const tr = document.createElement('tr');
                tr.className = 'clickable-row';
                const shortAddr = item.address.substring(0, 8) + '...' + item.address.substring(34);
                const addrExplorerUrl = EXPLORER_ADDR + item.address;
                
                const formattedTargetAmount = item.total_amount.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 4}});
                const formattedSourcePaid = item.total_source_amount.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 6}});
                const formattedUsd = '$' + (item.volume_usd || 0).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                const pct = Math.min(100, Math.max(3, ((item.volume_usd || 0) / maxVolumeUsd) * 100));
                const symbolInitial = item.symbol.startsWith('0x') ? '#' : item.symbol.substring(0, 2).toUpperCase();

                const levelBadgeClass = item.level === 2 ? 'level-2' : 'level-1';
                const levelText = item.level === 2 ? 'Level 2: ' + NATIVE_SYM + ' → ' + FINAL_SYM : 'Level 1: ' + item.symbol + ' → ' + NATIVE_SYM;

                tr.innerHTML = `
                    <td style="color: var(--text-muted); font-weight: 500;">${{index + 1}}</td>
                    <td><div class="token-cell"><div class="token-avatar">${{symbolInitial}}</div><div><div class="token-symbol">${{item.symbol}}</div></div></div></td>
                    <td><span class="level-badge ${{levelBadgeClass}}">${{levelText}}</span></td>
                    <td>
                        <div class="address-cell">
                            <a href="${{addrExplorerUrl}}" target="_blank" class="link-etherscan" onclick="event.stopPropagation();">${{shortAddr}} ↗</a>
                            <button class="btn-copy">Copy</button>
                        </div>
                    </td>
                    <td style="text-align: center;"><button class="btn-view-trades">📊 View ${{item.trade_count}} Trades</button></td>
                    <td style="text-align: right;"><div class="source-paid-val">${{formattedSourcePaid}} ${{item.source_symbol}}</div></td>
                    <td style="text-align: right;"><div class="amount-val">${{formattedTargetAmount}} ${{item.symbol}}</div></td>
                    <td style="text-align: right;"><div class="usd-val">${{formattedUsd}}</div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${{pct}}%;"></div></div></td>
                `;

                const copyBtn = tr.querySelector('.btn-copy');
                if (copyBtn) copyBtn.addEventListener('click', (e) => {{ e.stopPropagation(); copyToClipboard(item.address, copyBtn); }});
                const viewBtn = tr.querySelector('.btn-view-trades');
                if (viewBtn) viewBtn.addEventListener('click', (e) => {{ e.stopPropagation(); openTradeModal(item); }});
                tr.addEventListener('click', (e) => {{ if (e.target.tagName === 'A' || e.target.classList.contains('btn-copy')) return; openTradeModal(item); }});

                tbody.appendChild(tr);
            }});
        }}

        function setFilter(filterType, btnEl) {{
            currentFilter = filterType;
            document.querySelectorAll('.btn-filter').forEach(btn => btn.classList.remove('active'));
            btnEl.classList.add('active');
            renderTable();
        }}

        function handleSortChange(sortVal) {{ currentSort = sortVal; renderTable(); }}
        document.getElementById('search-input').addEventListener('input', (e) => {{ searchQuery = e.target.value.toLowerCase().trim(); renderTable(); }});

        function copyToClipboard(text, btn) {{
            navigator.clipboard.writeText(text).then(() => {{
                const orig = btn.innerText; btn.innerText = 'Copied!';
                setTimeout(() => {{ btn.innerText = orig; }}, 1500);
            }});
        }}

        function setElText(id, val) {{ const el = document.getElementById(id); if (el) el.innerText = val; }}

        function openTradeModal(item) {{
            const overlay = document.getElementById('trade-modal-overlay');
            if (!overlay) return;
            setElText('modal-token-avatar', item.symbol.startsWith('0x') ? '#' : item.symbol.substring(0, 2).toUpperCase());
            setElText('modal-title', item.symbol + ' Trade History');
            setElText('modal-subtitle', item.address);
            setElText('modal-level-val', item.level === 2 ? 'Level 2 (' + NATIVE_SYM + ' → ' + FINAL_SYM + ' Burn/Swap)' : 'Level 1 (' + item.symbol + ' → ' + NATIVE_SYM + ' Target)');
            setElText('modal-usd-val', '$' + (item.volume_usd || 0).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}));
            setElText('modal-total-amt', item.total_amount.toLocaleString(undefined, {{maximumFractionDigits: 4}}) + ' ' + item.symbol);
            setElText('modal-total-source', item.total_source_amount.toLocaleString(undefined, {{maximumFractionDigits: 6}}) + ' ' + item.source_symbol);
            setElText('modal-trade-cnt', item.trade_count + ' Events');

            const tbody = document.getElementById('modal-trade-tbody');
            if (tbody) {{
                tbody.innerHTML = '';
                (item.trades || []).forEach(tr => {{
                    const row = document.createElement('tr');
                    const txShort = tr.tx_hash ? tr.tx_hash.substring(0, 10) + '...' + tr.tx_hash.substring(54) : 'N/A';
                    const txExplorerUrl = tr.tx_hash ? EXPLORER_TX + tr.tx_hash : '#';
                    const callerShort = tr.caller ? tr.caller.substring(0, 8) + '...' + tr.caller.substring(34) : 'N/A';
                    const callerExplorerUrl = tr.caller ? EXPLORER_ADDR + tr.caller : '#';

                    row.innerHTML = `
                        <td style="font-size: 13px; color: var(--text-muted);">${{tr.timestamp}}</td>
                        <td style="font-family: 'JetBrains Mono', monospace; font-size: 13px;">${{tr.block_number}}</td>
                        <td>
                            <a href="${{txExplorerUrl}}" target="_blank" class="link-etherscan" style="font-family: 'JetBrains Mono', monospace; font-size: 13px;">
                                ${{txShort}} ↗
                            </a>
                        </td>
                        <td>
                            <a href="${{callerExplorerUrl}}" target="_blank" style="font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--text-muted); text-decoration: none;">
                                ${{callerShort}} ↗
                            </a>
                        </td>
                        <td style="text-align: right; font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #10b981;">${{tr.target_formatted.toLocaleString(undefined, {{maximumFractionDigits: 4}})}} ${{item.symbol}}</td>
                        <td style="text-align: right; font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #818cf8;">${{tr.source_formatted.toLocaleString(undefined, {{maximumFractionDigits: 6}})}} ${{tr.source_symbol}}</td>
                        <td style="text-align: right; font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #34d399;">$${{(tr.usd_value || 0).toLocaleString(undefined, {{maximumFractionDigits: 2}})}}</td>
                    `;
                    tbody.appendChild(row);
                }});
            }}
            overlay.style.setProperty('display', 'flex', 'important');
            overlay.style.setProperty('opacity', '1', 'important');
        }}

        function closeModal() {{
            const overlay = document.getElementById('trade-modal-overlay');
            if (overlay) overlay.style.setProperty('display', 'none', 'important');
        }}

        document.getElementById('trade-modal-overlay').addEventListener('click', (e) => {{ if (e.target.id === 'trade-modal-overlay') closeModal(); }});
        document.addEventListener('keydown', (e) => {{ if (e.key === 'Escape') closeModal(); }});

        renderTable();
    </script>
</body>
</html>
"""
    with open(cfg["output_html"], "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[+] Generated {cfg['name']} Dashboard HTML: {cfg['output_html']}")

def main():
    for chain_key, cfg in CHAINS.items():
        generate_chain_html(chain_key, cfg)

if __name__ == "__main__":
    main()
