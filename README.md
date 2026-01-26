# NotifyInvest

NotifyInvest is a holistic investment alert system that uses Generative AI (Gemma 27b via Gemini API) to monitor the Brazilian Stock Market (B3). It scrapes RSS feeds, analyzes news sentiment/impact, and sends push notifications to a React Native mobile app.

## 🚀 Server Dashboard

**URL:** [http://144.22.206.150:5000/dashboard](http://144.22.206.150:5000/dashboard)

The dashboard provides real-time monitoring of the backend:

- **AI Monitor Status**: Checks if the news scanning loop is active.
- **Connected Devices**: Lists all mobile devices registered for push notifications.
- **Recent Signals**: A history of the last 50 generated signals with their AI reasoning.

## 📱 Mobile App (Android)

The app receives push notifications and synchronizes with the server's history database to ensure no alerts are missed, even if the device was offline.

- **Search**: Search for ticker symbols (e.g., `PETR4`) to filter history.
- **Sync**: Pull-to-refresh to update the list.
- **Deep Links**: Tapping a notification opens the related news URL.

## 🛠 Deployment Status

**Server (OCI Oracle Cloud)**:

- **IP**: `144.22.206.150`
- **Services**: `notifyinvest` (Backend Monitor), `notifyinvest-api` (Flask API)
- **Path**: `/home/opc/notifyinvest`

**Architecture**:

1. **Monitor (`monitor.py`)**: Runs independently, polls RSS, calls Gemini API, saves to `signals.json`, sends Push via Expo.
2. **API (`api.py`)**: Flask server exposing `/signals`, `/register`, and `/dashboard`. Serves `signals.json` to the app.
