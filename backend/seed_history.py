import json
import time
import os
import json
import time
import os
import uuid

SIGNALS_FILE = os.path.join(os.path.dirname(__file__), "signals.json")

dummy_data = [
    {
        "id": str(uuid.uuid4()),
        "title": "PETR4: BUY",
        "body": "Estimativa: +2%\nPetrobras announce new oil discovery in pre-salt layer.",
        "data": {"url": "https://example.com/petr4"},
        "timestamp": time.time() - 3600
    },
    {
        "id": str(uuid.uuid4()),
        "title": "VALE3: HOLD",
        "body": "Estimativa: 0%\nIron ore prices stabilize after recent drop.",
        "data": {"url": "https://example.com/vale3"},
        "timestamp": time.time() - 1800
    },
    {
        "id": str(uuid.uuid4()),
        "title": "ITUB4: BUY",
        "body": "Estimativa: +1.5%\nItaú reports strong Q3 earnings beating expectations.",
        "data": {"url": "https://example.com/itub4"},
        "timestamp": time.time() - 900
    }
]

def seed():
    print(f"Seeding {SIGNALS_FILE} with {len(dummy_data)} items...")
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(dummy_data, f, indent=2)
    print("Done! Restart the API to serve these signals.")

if __name__ == "__main__":
    seed()
