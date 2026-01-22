
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import sys

# Setup logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app) # Allow cross-origin requests from mobile

TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'tokens.json')

def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return []
    try:
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

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
        tokens.append(token)
        save_tokens(tokens)
        logger.info(f"New token registered: {token}")
        return jsonify({"message": "Token registered successfully", "total_tokens": len(tokens)}), 201
    else:
        logger.info(f"Token already exists: {token}")
        return jsonify({"message": "Token already registered", "total_tokens": len(tokens)}), 200

if __name__ == '__main__':
    # Listen on all interfaces
    app.run(host='0.0.0.0', port=5000)
