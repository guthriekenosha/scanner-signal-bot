# 📊 Breakout Signal Scanner

This is a mobile-friendly Streamlit dashboard for tracking breakout, pullback, and momentum signals in crypto tokens. It reads from `signal_log.csv` and displays live analytics using the Blofin API.

## 🚀 Features
- 📈 Live price % and candle snapshots
- 🧠 Signal confidence and aging logic
- 🟢 Confirmation vs 🟡 Anticipation breakout tagging
- 🔄 Auto-refreshing and mobile layout
- ⚡ Top signals by symbol and RSI alerts

## 📱 Mobile Access
Open in any browser or "Add to Home Screen" to use as a PWA.

## 🔧 Run Locally

```bash
pip install -r requirements.txt
streamlit run gui_dashboard.py