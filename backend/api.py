
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

app = Flask(__name__)
CORS(app) # Allow cross-origin requests from mobile

TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'tokens.json')
TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'tokens.json')
SIGNALS_FILE = os.path.join(os.path.dirname(__file__), "signals.json")
STATUS_FILE = os.path.join(os.path.dirname(__file__), "status.json")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NotifyInvest Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { margin-bottom: 20px; color: #1a1a1a; display: flex; align-items: center; justify-content: space-between; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }
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
        .tag { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 500; }
        .tag-buy { background: #e8f5e9; color: #2e7d32; }
        .tag-sell { background: #ffebee; color: #c62828; }
        .refresh-btn { background: #2196F3; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 0.9rem; }
        .refresh-btn:hover { background: #1976D2; }
        pre { background: #f8f9fa; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>
            <span>NotifyInvest Server</span>
            <div>
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
    </div>

    <script>
        function timeAgo(date) {
            const seconds = Math.floor((new Date() - date) / 1000);
            if (seconds < 60) return seconds + "s ago";
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return minutes + "m ago";
            const hours = Math.floor(minutes / 60);
            return hours + "h ago";
        }

        async function fetchData() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                // Update AI Status
                const status = data.status || {};
                const now = Math.floor(Date.now() / 1000);
                const lastUpdate = status.last_update || 0;
                const isOnline = (now - lastUpdate) < 120; // Consider offline if no update in 2 mins
                
                document.getElementById('status-dot').className = `status-indicator ${isOnline ? 'online' : 'offline'}`;
                document.getElementById('status-text').textContent = isOnline ? 'Online & Running' : 'Offline / Stalled';
                document.getElementById('last-update').textContent = status.last_update ? new Date(status.last_update * 1000).toLocaleString() : 'Never';
                document.getElementById('current-message').textContent = status.message || 'No status message';

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
                signalsTable.innerHTML = data.signals.slice(0, 10).map(s => {
                    const impact = s.body.split('\\n')[0].replace('Estimativa: ', '');
                    const reason = s.body.split('\\n')[1] || s.body;
                    const date = new Date(s.timestamp * 1000).toLocaleString();
                    const isBuy = s.title.includes('BUY');
                    
                    return `
                        <tr>
                            <td style="font-size: 0.85rem; color: #666;">${date}</td>
                            <td style="font-size: 0.9rem; font-weight: 500; color: #555;">${s.data && s.data.source_name ? s.data.source_name : '-'}</td>
                            <td style="font-weight: bold;">${s.title}</td>
                            <td><span class="tag ${isBuy ? 'tag-buy' : 'tag-sell'}">${impact}</span></td>
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
        
    # Python slices are robust, even if list is smaller than limit
    # Signals are appended (oldest first), we usually want newest first for API?
    # Sort Newest First to apply limit to recent items
    reversed_signals = list(reversed(signals))
    limited_signals = reversed_signals[:limit]
    
    # Restore chronological order (Oldest First) for the App
    final_signals = list(reversed(limited_signals))
    return jsonify(final_signals), 200

@app.route('/dashboard', methods=['GET'])
def dashboard():
    return DASHBOARD_HTML

@app.route('/tickers', methods=['GET'])
def view_tickers():
    try:
        from b3_tickers import B3_TICKERS
    except ImportError:
        B3_TICKERS = {}
        
    sorted_tickers = sorted(B3_TICKERS.items())
    
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
        
    return html % (len(B3_TICKERS), rows)

@app.route('/api/data', methods=['GET'])
def get_dashboard_data():
    # 1. Load Tokens
    tokens = load_tokens()
    
    # 2. Load Signals (Recents)
    signals = load_signals()
    signals.reverse() # Newest first
    
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
        "signals": signals[:50], # Send last 50 for dashboard
        "status": status
    })

if __name__ == '__main__':
    # Listen on all interfaces
    app.run(host='0.0.0.0', port=5000)
