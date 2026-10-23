
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys
import time
from push import send_push_notification

# Setup logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import RSS_FEEDS for /sources endpoint
try:
    from feeds import RSS_FEEDS
except ImportError:
    from backend.feeds import RSS_FEEDS

try:
    from evaluator import load_evaluations, evaluate_all_signals, parse_signal_record
except ImportError:
    from backend.evaluator import load_evaluations, evaluate_all_signals, parse_signal_record

app = Flask(__name__)
CORS(app) # Allow cross-origin requests from mobile

TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'tokens.json')
SIGNALS_FILE = os.path.join(os.path.dirname(__file__), "signals.json")
STATUS_FILE = os.path.join(os.path.dirname(__file__), "status.json")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NotifyInvest Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { margin-bottom: 20px; color: #1a1a1a; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .card h2 { margin-top: 0; font-size: 1.2rem; color: #666; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 10px; }
        .stat { font-size: 2rem; font-weight: bold; color: #2196F3; }
        .status-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .online { background-color: #4CAF50; box-shadow: 0 0 8px rgba(76, 175, 80, 0.4); }
        .offline { background-color: #F44336; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #eee; }
        th { color: #888; font-weight: 500; font-size: 0.9rem; }
        tr:last-child td { border-bottom: none; }
        .tag { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 500; display: inline-block; }
        .tag-buy { background: #e8f5e9; color: #2e7d32; }
        .tag-sell { background: #ffebee; color: #c62828; }
        .refresh-btn { background: #2196F3; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.9rem; font-weight: 500; }
        .refresh-btn:hover { background: #1976D2; }
        pre { background: #f8f9fa; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>
            <span>NotifyInvest Server</span>
            <div>
                <a href="/evaluations" class="refresh-btn" style="text-decoration: none; background: #2E7D32; margin-right: 10px;">📊 Relatório de Assertividade</a>
                <a href="/tickers" class="refresh-btn" style="text-decoration: none; background: #607D8B; margin-right: 10px;">View Tickers</a>
                <button class="refresh-btn" onclick="fetchData()">Refresh</button>
            </div>
        </h1>
        
        <div class="grid">
            <!-- AI Status -->
            <div class="card">
                <h2>🤖 AI Monitor Status</h2>
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <span id="status-dot" class="status-indicator offline"></span>
                    <span id="status-text" style="font-weight: 500; font-size: 1.1rem;">Waiting...</span>
                </div>
                <div>
                    <div style="font-size: 0.9rem; color: #666;">Last Activity:</div>
                    <div id="last-update" style="font-family: monospace; margin-top: 4px;">-</div>
                </div>
                <div style="margin-top: 15px;">
                    <div style="font-size: 0.9rem; color: #666;">Current Action:</div>
                    <pre id="current-message" style="margin-top: 4px; color: #333;">-</pre>
                </div>
            </div>

            <!-- Accuracy Summary Card -->
            <div class="card">
                <h2>🎯 Assertividade dos Alertas</h2>
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <div>
                        <div style="font-size: 0.8rem; color: #666;">Taxa Consolidada (≥70% Meta)</div>
                        <div class="stat" id="eval-winrate" style="color: #2E7D32;">-%</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.8rem; color: #666;">Nota Geral IA</div>
                        <div class="stat" id="eval-score" style="color: #1565C0;">-/100</div>
                    </div>
                </div>
                <div style="margin-top: 12px; font-size: 0.85rem; color: #555; display: flex; justify-content: space-between;">
                    <span>⏱️ Tempo Médio Consol.: <strong id="eval-avg-time">-</strong></span>
                    <a href="/evaluations" style="color: #2196F3; text-decoration: none; font-weight: 600;">Ver Auditoria →</a>
                </div>
            </div>

            <!-- Tokens -->
            <div class="card">
                <h2>📱 Connected Devices</h2>
                <div class="stat" id="token-count">0</div>
                <div style="margin-top: 10px; max-height: 150px; overflow-y: auto;">
                    <table id="token-table">
                        <!-- Tokens here -->
                    </table>
                </div>
            </div>
            
            <!-- RSS Feeds -->
            <div class="card">
                <h2>📡 Active Feeds</h2>
                <div class="stat" id="rss-count">0</div>
                <div style="margin-top: 10px; max-height: 150px; overflow-y: auto;">
                    <table id="rss-table">
                        <!-- Feeds populate here -->
                    </table>
                </div>
            </div>
        </div>

        <!-- Signals History -->
        <div class="card">
            <h2>📡 Recent Signals</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Source</th>
                            <th>Signal</th>
                            <th>Impact</th>
                            <th>Avaliação / Status</th>
                            <th>Reason</th>
                        </tr>
                    </thead>
                    <tbody id="signals-table">
                        <!-- Signals here -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        async function fetchData() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                // Update AI Status
                const status = data.status || {};
                const now = Math.floor(Date.now() / 1000);
                const lastUpdate = status.last_update || 0;
                const isOnline = (now - lastUpdate) < 120;
                
                document.getElementById('status-dot').className = `status-indicator ${isOnline ? 'online' : 'offline'}`;
                document.getElementById('status-text').textContent = isOnline ? 'Online & Running' : 'Offline / Stalled';
                document.getElementById('last-update').textContent = status.last_update ? new Date(status.last_update * 1000).toLocaleString() : 'Never';
                document.getElementById('current-message').textContent = status.message || 'No status message';

                // Update Evaluation Summary
                const summary = data.evaluation_summary || {};
                document.getElementById('eval-winrate').textContent = (summary.win_rate_strict_pct !== undefined ? summary.win_rate_strict_pct : 0) + '%';
                document.getElementById('eval-score').textContent = (summary.avg_scores && summary.avg_scores.overall ? summary.avg_scores.overall : 0) + '/100';
                document.getElementById('eval-avg-time').textContent = summary.avg_trading_time_to_consolidate_str || '-';

                // Update Tokens
                const tokenKeys = Object.keys(data.tokens || {});
                document.getElementById('token-count').textContent = tokenKeys.length;
                const tokenTable = document.getElementById('token-table');
                tokenTable.innerHTML = tokenKeys.map(t => `
                    <tr>
                        <td style="font-family: monospace; font-size: 0.8rem;">
                            ${t.substring(0, 20)}...
                        </td>
                    </tr>
                `).join('');

                // Update Signals
                const signalsTable = document.getElementById('signals-table');
                signalsTable.innerHTML = data.signals.slice(0, 12).map(s => {
                    const impact = s.body.split('\\n')[0].replace('Estimativa: ', '');
                    const reason = s.body.split('\\n')[1] || s.body;
                    const date = new Date(s.timestamp * 1000).toLocaleString();
                    const isBuy = s.title.includes('BUY');
                    const ev = s.evaluation || {};
                    const badge = ev.status_badge || '⏳ Pendente';
                    const scoreTxt = ev.scores && ev.scores.overall ? ` (${ev.scores.overall}/100)` : '';
                    
                    return `
                        <tr>
                            <td style="font-size: 0.85rem; color: #666;">${date}</td>
                            <td style="font-size: 0.9rem; font-weight: 500; color: #555;">${s.data && s.data.source_name ? s.data.source_name : '-'}</td>
                            <td style="font-weight: bold;">${s.title}</td>
                            <td><span class="tag ${isBuy ? 'tag-buy' : 'tag-sell'}">${impact}</span></td>
                            <td style="font-size: 0.85rem; font-weight: 600;">${badge}${scoreTxt}</td>
                            <td style="font-size: 0.9rem;">${reason.substring(0, 80)}${reason.length > 80 ? '...' : ''}</td>
                        </tr>
                    `;
                }).join('');

                // Update RSS Sources
                const rssFeeds = status.rss_feeds || [];
                document.getElementById('rss-count').textContent = status.rss_source_count || 0;
                
                const rssTable = document.getElementById('rss-table');
                if (rssFeeds.length > 0) {
                     rssTable.innerHTML = rssFeeds.map(f => {
                        const typeColor = f.type === 'FATOS' ? '#e3f2fd' : (f.type === 'INTERPRETACAO' ? '#fff3e0' : '#fce4ec');
                        const textColor = f.type === 'FATOS' ? '#1565c0' : (f.type === 'INTERPRETACAO' ? '#e65100' : '#c2185b');
                        
                        return `
                        <tr>
                            <td style="font-size: 0.85rem; color: #555;">${f.url}</td>
                            <td style="width: 100px; text-align: right;">
                                <span style="background: ${typeColor}; color: ${textColor}; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold;">
                                    ${f.type}
                                </span>
                            </td>
                        </tr>
                    `}).join('');
                } else {
                     rssTable.innerHTML = '<tr><td>No feeds found</td></tr>';
                }

            } catch (e) {
                console.error("Failed to fetch data", e);
            }
        }

        // Initial load
        fetchData();
        // Poll every 5 seconds
        setInterval(fetchData, 5000);
    </script>
</body>
</html>
"""

def load_signals():
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return {}
    try:
        with open(TOKENS_FILE, 'r') as f:
            data = json.load(f)
                # Migration: if list, convert to dict
            if isinstance(data, list):
                new_data = {}
                for t in data:
                    new_data[t] = {"min_buy": 0, "min_sell": 0, "whitelist": [], "blacklist": []}
                return new_data
            
            # Ensure new fields exist for existing dict entries
            for t, prefs in data.items():
                if "whitelist" not in prefs: prefs["whitelist"] = []
                if "blacklist" not in prefs: prefs["blacklist"] = []
                if "source_whitelist" not in prefs: prefs["source_whitelist"] = []
            return data
    except:
        return {}

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "online", "service": "NotifyInvest API"}), 200

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    token = data.get('token')
    
    if not token or not token.startswith('ExponentPushToken'):
        return jsonify({"error": "Invalid token"}), 400
        
    tokens = load_tokens()
    
    if token not in tokens:
        tokens[token] = {"min_buy": 0, "min_sell": 0, "whitelist": [], "blacklist": [], "source_whitelist": []}
        save_tokens(tokens)
        logger.info(f"New token registered: {token}")
        return jsonify({"message": "Token registered successfully", "total_tokens": len(tokens)}), 201
    else:
        logger.info(f"Token already exists: {token}")
        return jsonify({"message": "Token already registered", "total_tokens": len(tokens)}), 200

@app.route('/debug/test', methods=['POST'])
def debug_test():
    """Manual trigger for testing notification delivery and DB storage."""
    try:
        from push import send_push_notification
        import uuid
        import time
        
        # 1. Load Tokens
        tokens = load_tokens()
        results = {}
        
        # 2. Create Signal Data
        title = "DEBUG: SERVER TEST"
        body = "Teste manual disparado do endpoint /debug/test."
        data = {"url": "https://google.com", "source_name": "Debug System"}
        
        # 3. Save to DB (Status/Signals)
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, 'r') as f:
                signals = json.load(f)
        else:
            signals = []
            
        new_signal = {
            "id": str(uuid.uuid4()),
            "title": title,
            "body": body,
            "data": data,
            "timestamp": time.time()
        }
        signals.append(new_signal)
        # Keep last 1000
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(signals[-1000:], f)
            
        # 4. Broadcast
        for token in tokens.keys():
            try:
                send_push_notification(token, title, body, data)
                results[token] = "Success"
            except Exception as e:
                results[token] = str(e)
                
        return jsonify({
            "status": "completed",
            "db_updated": True,
            "signal_id": new_signal['id'],
            "delivery_results": results
        }), 200
    except Exception as e:
        logger.error(f"Debug test failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    tokens = load_tokens()
    
    if request.method == 'GET':
        token = request.args.get('token')
        if not token or token not in tokens:
            return jsonify({"error": "Token not found"}), 404
        return jsonify(tokens[token]), 200
    
    if request.method == 'POST':
        data = request.json
        token = data.get('token')
        if not token or token not in tokens:
            return jsonify({"error": "Token not found"}), 404
            
        settings = tokens[token]
        # Update fields if provided
        if 'min_buy' in data: settings['min_buy'] = int(data['min_buy'])
        if 'min_sell' in data: settings['min_sell'] = int(data['min_sell'])
        if 'whitelist' in data: settings['whitelist'] = data['whitelist'] # Expecting list of strings
        if 'blacklist' in data: settings['blacklist'] = data['blacklist'] # Expecting list of strings
        if 'source_whitelist' in data: settings['source_whitelist'] = data['source_whitelist'] # Expecting list of strings
        
        tokens[token] = settings
        save_tokens(tokens)
        return jsonify({"message": "Preferences saved", "settings": settings}), 200

@app.route('/sources', methods=['GET'])
def get_sources():
    # Return unique source names
    sources = list(set([f.get('name', 'Unknown') for f in RSS_FEEDS]))
    sources.sort()
    return jsonify(sources), 200

def attach_evaluations(signals_list):
    """Attaches evaluation data to each signal dict if available."""
    store = load_evaluations()
    evals = store.get("evaluations", {})
    # If evaluations store is empty and we have signals, trigger an initial non-blocking evaluation
    if not evals and signals_list:
        try:
            store = evaluate_all_signals(force_recalculate=False, max_signals_to_eval=25)
            evals = store.get("evaluations", {})
        except Exception as e:
            logger.warning(f"Initial evaluation run failed: {e}")

    enriched = []
    for s in signals_list:
        s_copy = dict(s)
        sig_id = s_copy.get("id")
        if not sig_id:
            parsed = parse_signal_record(s_copy)
            sig_id = parsed["id"] if parsed else None
        if sig_id and sig_id in evals:
            s_copy["evaluation"] = evals[sig_id]
        enriched.append(s_copy)
    return enriched, store.get("summary", {})


@app.route('/signals', methods=['GET'])
def get_signals():
    signals = load_signals()
    
    # 1. Search Filter
    query = request.args.get('search', '').lower()
    if query:
        signals = [s for s in signals if query in s['title'].lower() or query in s['body'].lower()]
        
    # 2. Limit (Default 50, Max 1000)
    try:
        limit = int(request.args.get('limit', 50))
    except:
        limit = 50
        
    # Sort Newest First to apply limit to recent items
    reversed_signals = list(reversed(signals))
    limited_signals = reversed_signals[:limit]
    
    # Restore chronological order (Oldest First) for the App
    final_signals = list(reversed(limited_signals))
    final_signals, _ = attach_evaluations(final_signals)
    return jsonify(final_signals), 200

@app.route('/dashboard', methods=['GET'])
def dashboard():
    return DASHBOARD_HTML

EVALUATIONS_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NotifyInvest - Auditoria de Assertividade</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #222; }
        .container { max-width: 1280px; margin: 0 auto; }
        .top-bar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
        h1 { margin: 0; font-size: 1.65rem; color: #1a1a1a; }
        .subtitle { color: #666; font-size: 0.92rem; margin-top: 4px; }
        .btn { background: #2196F3; color: white; border: none; padding: 9px 16px; border-radius: 8px; cursor: pointer; font-size: 0.9rem; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
        .btn:hover { background: #1976D2; }
        .btn-secondary { background: #546E7A; }
        .btn-secondary:hover { background: #455A64; }
        .btn-green { background: #2E7D32; }
        .btn-green:hover { background: #1B5E20; }
        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .card { background: white; padding: 18px 20px; border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
        .kpi-label { font-size: 0.82rem; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; }
        .kpi-val { font-size: 1.9rem; font-weight: 800; margin-top: 6px; color: #1a1a1a; }
        .kpi-sub { font-size: 0.8rem; color: #777; margin-top: 4px; }
        .pillars-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 20px; }
        .pillar-box { background: #fff; padding: 14px 18px; border-radius: 10px; border-left: 5px solid #2196F3; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
        .pillar-title { font-size: 0.85rem; color: #555; font-weight: 600; display: flex; justify-content: space-between; }
        .pillar-score { font-size: 1.4rem; font-weight: bold; margin-top: 4px; }
        .progress-bg { height: 6px; background: #e0e0e0; border-radius: 3px; margin-top: 8px; overflow: hidden; }
        .progress-fill { height: 100%; border-radius: 3px; }
        .filters-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; justify-content: space-between; margin-bottom: 16px; background: white; padding: 14px 18px; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
        .filter-pills { display: flex; gap: 8px; flex-wrap: wrap; }
        .pill { padding: 6px 13px; border-radius: 20px; border: 1px solid #d0d7de; background: #fff; cursor: pointer; font-size: 0.84rem; font-weight: 600; color: #444; }
        .pill.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
        .search-input { padding: 8px 12px; border-radius: 8px; border: 1px solid #ccc; font-size: 0.9rem; min-width: 220px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 12px 10px; border-bottom: 1px solid #eee; font-size: 0.88rem; vertical-align: top; }
        th { color: #666; font-weight: 600; background: #fafafa; position: sticky; top: 0; }
        tr.eval-row:hover { background: #f8fbff; cursor: pointer; }
        .badge { padding: 4px 9px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; display: inline-block; white-space: nowrap; }
        .b-consolidated { background: #e8f5e9; color: #1b5e20; border: 1px solid #a5d6a7; }
        .b-partial { background: #e3f2fd; color: #0d47a1; border: 1px solid #90caf9; }
        .b-reversed { background: #ffebee; color: #b71c1c; border: 1px solid #ef9a9a; }
        .b-expired { background: #f5f5f5; color: #616161; border: 1px solid #e0e0e0; }
        .b-tracking { background: #fff8e1; color: #e65100; border: 1px solid #ffe082; }
        .sig-buy { color: #2e7d32; font-weight: 800; }
        .sig-sell { color: #c62828; font-weight: 800; }
        .score-chip { font-weight: 700; padding: 2px 7px; border-radius: 5px; font-size: 0.8rem; }
        .details-row { display: none; background: #fafcff; }
        .details-box { padding: 14px 18px; border-left: 4px solid #2196F3; margin: 4px 0; border-radius: 6px; }
        .checkpoints { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
        .cp-item { background: #fff; border: 1px solid #e0e0e0; padding: 6px 10px; border-radius: 6px; font-size: 0.8rem; }
        .methodology { background: #e8f4fd; border-left: 4px solid #1976D2; padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; font-size: 0.85rem; color: #1e3a5f; line-height: 1.45; }
    </style>
</head>
<body>
    <div class="container">
        <div class="top-bar">
            <div>
                <h1>📊 Auditoria de Assertividade & Consolidação (B3)</h1>
                <div class="subtitle">Avaliação automática de Signal, Sentiment, Impact e Reason confrontando alertas com cotações reais da B3 e notícias posteriores</div>
            </div>
            <div style="display: flex; gap: 10px;">
                <a href="/dashboard" class="btn btn-secondary">← Voltar ao Dashboard</a>
                <button id="run-btn" class="btn btn-green" onclick="triggerEvaluation()">🔄 Reavaliar Agora</button>
            </div>
        </div>

        <div class="methodology">
            <strong>📐 Critério de Consolidação e Janela de Observação:</strong>
            Cada alerta é acompanhado na B3 (candles de 15 min) por até <strong>3 pregões completos (~21h de pregão / até 5 dias corridos)</strong>.
            Considera-se <strong>✅ Consolidado</strong> no exato momento em que a ação atinge <strong>≥ 70% a 100% da variação estimada no Impact</strong> na direção do sinal (registrando o tempo exato de pregão).
            Se o ativo for fortemente na direção oposta (≥ 100% do impacto estimado contra o sinal), recebe o alerta de <strong>🚨 Direção Contrária (Stop)</strong>.
        </div>

        <!-- Global KPIs -->
        <div class="kpi-grid">
            <div class="card">
                <div class="kpi-label">Taxa de Consolidação (≥70% Meta)</div>
                <div class="kpi-val" id="kpi-strict" style="color: #2E7D32;">-%</div>
                <div class="kpi-sub" id="kpi-strict-sub">0 consolidados de 0 finalizados</div>
            </div>
            <div class="card">
                <div class="kpi-label">Acerto Direcional (Consol. + Parcial)</div>
                <div class="kpi-val" id="kpi-dir" style="color: #1565C0;">-%</div>
                <div class="kpi-sub" id="kpi-dir-sub">Foram na direção correta do sinal</div>
            </div>
            <div class="card">
                <div class="kpi-label">Tempo Médio até Consolidar</div>
                <div class="kpi-val" id="kpi-time" style="color: #6A1B9A;">-</div>
                <div class="kpi-sub">Horas/minutos efetivos de pregão na B3</div>
            </div>
            <div class="card">
                <div class="kpi-label">Direção Contrária / Stop</div>
                <div class="kpi-val" id="kpi-rev" style="color: #C62828;">0</div>
                <div class="kpi-sub" id="kpi-tracking-sub">0 em observação no momento</div>
            </div>
        </div>

        <!-- 4 Pillars Accuracy Scores -->
        <div class="pillars-grid">
            <div class="pillar-box" style="border-left-color: #2E7D32;">
                <div class="pillar-title"><span>1. Grau de Acerto: SIGNAL (BUY/SELL)</span></div>
                <div class="pillar-score" id="score-signal">-/100</div>
                <div class="progress-bg"><div id="bar-signal" class="progress-fill" style="width:0%; background:#2E7D32;"></div></div>
            </div>
            <div class="pillar-box" style="border-left-color: #1565C0;">
                <div class="pillar-title"><span>2. Grau de Acerto: IMPACT (% Estimado)</span></div>
                <div class="pillar-score" id="score-impact">-/100</div>
                <div class="progress-bg"><div id="bar-impact" class="progress-fill" style="width:0%; background:#1565C0;"></div></div>
            </div>
            <div class="pillar-box" style="border-left-color: #EF6C00;">
                <div class="pillar-title"><span>3. Grau de Acerto: SENTIMENT</span></div>
                <div class="pillar-score" id="score-sentiment">-/100</div>
                <div class="progress-bg"><div id="bar-sentiment" class="progress-fill" style="width:0%; background:#EF6C00;"></div></div>
            </div>
            <div class="pillar-box" style="border-left-color: #6A1B9A;">
                <div class="pillar-title"><span>4. Grau de Acerto: REASON (Tese IA)</span></div>
                <div class="pillar-score" id="score-reason">-/100</div>
                <div class="progress-bg"><div id="bar-reason" class="progress-fill" style="width:0%; background:#6A1B9A;"></div></div>
            </div>
        </div>

        <!-- Filters -->
        <div class="filters-bar">
            <div class="filter-pills">
                <button class="pill active" onclick="setStatusFilter('ALL', this)">Todos</button>
                <button class="pill" onclick="setStatusFilter('CONSOLIDATED', this)">✅ Consolidados</button>
                <button class="pill" onclick="setStatusFilter('PARTIAL', this)">☑️ Parciais</button>
                <button class="pill" onclick="setStatusFilter('REVERSED', this)">🚨 Direção Contrária</button>
                <button class="pill" onclick="setStatusFilter('EXPIRED_MISSED', this)">❌ Não Consolidados</button>
                <button class="pill" onclick="setStatusFilter('TRACKING', this)">⏳ Em Observação</button>
            </div>
            <input type="text" id="ticker-search" class="search-input" placeholder="🔎 Filtrar ticker ou motivo..." oninput="renderTable()">
        </div>

        <!-- Detailed Table -->
        <div class="card" style="padding: 0; overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>Data do Alerta</th>
                        <th>Ativo / Sinal</th>
                        <th>Impacto Previsto (Alvo ≥70%)</th>
                        <th>Cotação (Entrada → Pico / Atual)</th>
                        <th>Status de Consolidação</th>
                        <th>Tempo p/ Consolidar</th>
                        <th>Notas (Sig / Imp / Sent / Reas)</th>
                        <th>Nota Geral</th>
                    </tr>
                </thead>
                <tbody id="eval-tbody">
                    <tr><td colspan="8" style="text-align:center; padding: 30px; color:#888;">Carregando avaliações...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let allEvaluations = [];
        let currentFilter = 'ALL';

        function badgeClass(status) {
            if (status === 'CONSOLIDATED') return 'b-consolidated';
            if (status === 'PARTIAL') return 'b-partial';
            if (status === 'REVERSED' || status === 'TRACKING_ADVERSE') return 'b-reversed';
            if (status === 'EXPIRED_MISSED') return 'b-expired';
            return 'b-tracking';
        }

        function setStatusFilter(filter, btn) {
            currentFilter = filter;
            document.querySelectorAll('.pill').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');
            renderTable();
        }

        function toggleDetails(idx) {
            const row = document.getElementById('details-' + idx);
            if (!row) return;
            row.style.display = (row.style.display === 'table-row') ? 'none' : 'table-row';
        }

        async function loadEvaluations() {
            try {
                const res = await fetch('/api/evaluations');
                const data = await res.json();
                const s = data.summary || {};

                document.getElementById('kpi-strict').textContent = (s.win_rate_strict_pct !== undefined ? s.win_rate_strict_pct : 0) + '%';
                document.getElementById('kpi-strict-sub').textContent = `${s.consolidated_count || 0} consolidados de ${s.resolved_signals || s.total_signals || 0} avaliados`;
                document.getElementById('kpi-dir').textContent = (s.win_rate_directional_pct !== undefined ? s.win_rate_directional_pct : 0) + '%';
                document.getElementById('kpi-dir-sub').textContent = `${(s.consolidated_count || 0) + (s.partial_count || 0)} a favor vs ${s.reversed_count || 0} contra`;
                document.getElementById('kpi-time').textContent = s.avg_trading_time_to_consolidate_str || '-';
                document.getElementById('kpi-rev').textContent = s.reversed_count || 0;
                document.getElementById('kpi-tracking-sub').textContent = `${s.tracking_count || 0} em observação no pregão`;

                const scores = s.avg_scores || {};
                ['signal', 'impact', 'sentiment', 'reason'].forEach(k => {
                    const val = scores[k] !== undefined ? scores[k] : 0;
                    document.getElementById('score-' + k).textContent = val + '/100';
                    document.getElementById('bar-' + k).style.width = val + '%';
                });

                allEvaluations = data.items || [];
                renderTable();
            } catch (e) {
                console.error("Failed to load evaluations:", e);
            }
        }

        function renderTable() {
            const tbody = document.getElementById('eval-tbody');
            const q = (document.getElementById('ticker-search').value || '').toLowerCase();

            const filtered = allEvaluations.filter(item => {
                if (currentFilter !== 'ALL') {
                    if (currentFilter === 'TRACKING') {
                        if (item.status !== 'TRACKING' && item.status !== 'TRACKING_ADVERSE') return false;
                    } else if (item.status !== currentFilter) {
                        return false;
                    }
                }
                if (q) {
                    const hay = `${item.ticker || ''} ${item.reason || ''} ${item.verdict || ''} ${item.source_name || ''}`.toLowerCase();
                    if (!hay.includes(q)) return false;
                }
                return true;
            });

            if (filtered.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding: 30px; color:#888;">Nenhum alerta encontrado para este filtro.</td></tr>';
                return;
            }

            tbody.innerHTML = filtered.map((ev, idx) => {
                const dateStr = new Date((ev.alert_timestamp || 0) * 1000).toLocaleString();
                const isBuy = ev.signal === 'BUY';
                const entryP = ev.entry_price ? `R$ ${ev.entry_price.toFixed(2)}` : '-';
                const latestP = ev.latest_price ? `R$ ${ev.latest_price.toFixed(2)}` : '-';
                const maxFav = ev.max_favorable_pct !== undefined ? `${ev.max_favorable_pct >= 0 ? '+' : ''}${ev.max_favorable_pct.toFixed(2)}%` : '-';
                const latestPct = ev.latest_change_pct !== undefined ? `${ev.latest_change_pct >= 0 ? '+' : ''}${ev.latest_change_pct.toFixed(2)}%` : '-';
                const sc = ev.scores || {signal: 0, impact: 0, sentiment: 0, reason: 0, overall: 0};
                const timeCons = ev.consolidated ? `<strong>${ev.trading_time_to_consolidate_str}</strong> <span style="color:#777;font-size:0.78rem;">(pregão)<br>${ev.elapsed_time_to_consolidate_str} corridos</span>` : `<span style="color:#888;">Obs: ${ev.trading_duration_observed_str || '0min'}</span>`;

                const cp = ev.checkpoints || {};
                const newsHtml = (ev.subsequent_news && ev.subsequent_news.length > 0)
                    ? ev.subsequent_news.map(n => `<li><a href="${n.url}" target="_blank" style="color:#1565C0;">${n.title}</a> <span style="color:#777;">(${n.source})</span></li>`).join('')
                    : '<li style="color:#777;">Nenhuma notícia posterior capturada ainda.</li>';

                return `
                    <tr class="eval-row" onclick="toggleDetails(${idx})">
                        <td style="color:#555; font-size:0.82rem;">${dateStr}<br><span style="color:#888;">${ev.source_name || ''}</span></td>
                        <td>
                            <strong style="font-size:1rem;">${ev.ticker}</strong>
                            <span class="${isBuy ? 'sig-buy' : 'sig-sell'}">${ev.signal}</span>
                            <div style="font-size:0.75rem; color:#777;">Sent: ${ev.sentiment || '-'}</div>
                        </td>
                        <td>
                            <strong>${ev.impact_str}</strong>
                            <div style="font-size:0.78rem; color:#666;">Meta ≥70%: <strong>${ev.target_threshold_pct || 0}%</strong></div>
                        </td>
                        <td>
                            <div>Entrada: <strong>${entryP}</strong> → Atual: <strong>${latestP}</strong> (${latestPct})</div>
                            <div style="font-size:0.78rem; color:#2e7d32;">Pico a favor: <strong>${maxFav}</strong> | Drawdown máx: <span style="color:#c62828;">${ev.max_adverse_pct || 0}%</span></div>
                        </td>
                        <td><span class="badge ${badgeClass(ev.status)}">${ev.status_badge || ev.status}</span></td>
                        <td>${timeCons}</td>
                        <td style="font-family: monospace; font-size:0.82rem;">
                            Sig: <b>${sc.signal}</b> | Imp: <b>${sc.impact}</b><br>
                            Sent: <b>${sc.sentiment}</b> | Reas: <b>${sc.reason}</b>
                        </td>
                        <td>
                            <span class="score-chip" style="background:${sc.overall >= 70 ? '#e8f5e9' : (sc.overall >= 45 ? '#fff8e1' : '#ffebee')}; color:${sc.overall >= 70 ? '#1b5e20' : (sc.overall >= 45 ? '#e65100' : '#b71c1c')};">
                                ${sc.overall}/100
                            </span>
                            <div style="font-size:0.72rem; color:#2196F3; margin-top:4px;">▼ Detalhes</div>
                        </td>
                    </tr>
                    <tr id="details-${idx}" class="details-row">
                        <td colspan="8">
                            <div class="details-box">
                                <div style="margin-bottom:8px;"><strong>📝 Motivo Original (Reason):</strong> ${ev.reason || '-'}</div>
                                <div style="margin-bottom:8px;"><strong>🤖 Veredito da Auditoria (Pós-Alerta):</strong> ${ev.verdict || '-'}</div>
                                <div class="checkpoints">
                                    <div class="cp-item">⏱️ <strong>+1h pregão:</strong> ${cp['1h'] !== null && cp['1h'] !== undefined ? cp['1h'] + '%' : 'Aguardando'}</div>
                                    <div class="cp-item">⏱️ <strong>+4h pregão:</strong> ${cp['4h'] !== null && cp['4h'] !== undefined ? cp['4h'] + '%' : 'Aguardando'}</div>
                                    <div class="cp-item">📅 <strong>D+1 (1 pregão):</strong> ${cp['1d'] !== null && cp['1d'] !== undefined ? cp['1d'] + '%' : 'Aguardando'}</div>
                                    <div class="cp-item">📅 <strong>D+3 (3 pregões):</strong> ${cp['3d'] !== null && cp['3d'] !== undefined ? cp['3d'] + '%' : 'Aguardando'}</div>
                                </div>
                                <div style="margin-top:10px;">
                                    <strong>📰 Notícias Posteriores sobre ${ev.ticker}:</strong>
                                    <ul style="margin: 6px 0 0 18px; padding:0; font-size:0.83rem;">${newsHtml}</ul>
                                </div>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        async function triggerEvaluation() {
            const btn = document.getElementById('run-btn');
            btn.disabled = true;
            btn.textContent = '⏳ Avaliando B3 e Notícias...';
            try {
                await fetch('/api/evaluations/run', { method: 'POST' });
                await loadEvaluations();
            } catch (e) {
                console.error(e);
            } finally {
                btn.disabled = false;
                btn.textContent = '🔄 Reavaliar Agora';
            }
        }

        loadEvaluations();
        setInterval(loadEvaluations, 15000);
    </script>
</body>
</html>
"""

@app.route('/evaluations', methods=['GET'])
def evaluations_page():
    return EVALUATIONS_HTML

@app.route('/api/evaluations', methods=['GET'])
def api_get_evaluations():
    store = load_evaluations()
    evals_dict = store.get("evaluations", {})
    if not evals_dict:
        store = evaluate_all_signals(force_recalculate=False, max_signals_to_eval=50)
        evals_dict = store.get("evaluations", {})

    items = list(evals_dict.values())
    items.sort(key=lambda x: x.get("alert_timestamp", 0), reverse=True)
    return jsonify({
        "summary": store.get("summary", {}),
        "last_run": store.get("last_run", 0),
        "items": items
    }), 200

@app.route('/api/evaluations/run', methods=['POST'])
def api_run_evaluations():
    force = False
    if request.is_json and request.json:
        force = bool(request.json.get("force", True))
    else:
        force = True
    store = evaluate_all_signals(force_recalculate=force, max_signals_to_eval=50)
    return jsonify({
        "status": "ok",
        "summary": store.get("summary", {}),
        "evaluated_count": len(store.get("evaluations", {}))
    }), 200

@app.route('/tickers', methods=['GET'])
def view_tickers():
    import traceback
    
    B3_TICKERS = {}
    error_details = ""
    
    try:
        try:
            from b3_tickers import B3_TICKERS
        except ImportError:
            # Fallback for when running from root dir
            from backend.b3_tickers import B3_TICKERS
            
    except Exception as e:
        error_details = f"Import Error: {str(e)}<br><pre>{traceback.format_exc()}</pre>"
        B3_TICKERS = {}
        
    sorted_tickers = sorted(B3_TICKERS.items()) if B3_TICKERS else []
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NotifyInvest - B3 Tickers</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #333; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            h1 { margin-bottom: 20px; text-align: center; color: #1a1a1a; }
            .error-box { background: #ffebee; color: #c62828; padding: 15px; border-radius: 8px; margin-bottom: 20px; overflow-x: auto; }
            .search-box { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 20px; font-size: 1rem; box-sizing: border-box; }
            table { width: 100%; border-collapse: collapse; }
            th, td { text-align: left; padding: 12px; border-bottom: 1px solid #eee; }
            th { background: #f8f9fa; position: sticky; top: 0; }
            tr:hover { background: #f5f5f5; }
            .count { text-align: center; color: #666; margin-bottom: 20px; }
            .back-btn { display: inline-block; margin-bottom: 20px; color: #2196F3; text-decoration: none; font-weight: 500; }
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/dashboard" class="back-btn">← Back to Dashboard</a>
            <h1>B3 Ticker Database</h1>
            
            %s
            
            <div class="count">Tracking <strong>%d</strong> companies</div>
            
            <input type="text" id="search" class="search-box" placeholder="Search ticker or name..." onkeyup="filterTable()">
            
            <table id="tickerTable">
                <thead>
                    <tr>
                        <th>Company / Key</th>
                        <th>Ticker</th>
                    </tr>
                </thead>
                <tbody>
                    %s
                </tbody>
            </table>
        </div>

        <script>
            function filterTable() {
                const input = document.getElementById('search');
                const filter = input.value.toUpperCase();
                const table = document.getElementById('tickerTable');
                const tr = table.getElementsByTagName('tr');

                for (let i = 1; i < tr.length; i++) {
                    const tds = tr[i].getElementsByTagName('td');
                    let show = false;
                    for (let j = 0; j < tds.length; j++) {
                        if (tds[j].textContent.toUpperCase().indexOf(filter) > -1) {
                            show = true;
                            break;
                        }
                    }
                    tr[i].style.display = show ? '' : 'none';
                }
            }
        </script>
    </body>
    </html>
    """
    
    rows = ""
    for key, value in sorted_tickers:
        rows += f"<tr><td>{key}</td><td><strong>{value}</strong></td></tr>"
    
    error_html = f'<div class="error-box"><strong>System Error:</strong><br>{error_details}</div>' if error_details else ""
        
    # Use replace to avoid conflict with CSS % 
    return html.replace("%s", error_html, 1).replace("%d", str(len(B3_TICKERS))).replace("%s", rows)

@app.route('/api/data', methods=['GET'])
def get_dashboard_data():
    # 1. Load Tokens
    tokens = load_tokens()
    
    # 2. Load Signals (Recents) & Attach Evaluations
    signals = load_signals()
    signals.reverse() # Newest first
    recent_signals, eval_summary = attach_evaluations(signals[:50])
    
    # 3. Load Monitor Status
    status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                status = json.load(f)
        except:
            status = {"message": "Error reading status file"}
            
    return jsonify({
        "tokens": tokens,
        "signals": recent_signals, # Send last 50 for dashboard with evaluation status
        "evaluation_summary": eval_summary,
        "status": status
    })

if __name__ == '__main__':
    # Listen on all interfaces
    app.run(host='0.0.0.0', port=5000)
