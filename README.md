# 🔄 FlipToEnglish

**Turn your daily Ukrainian news scrolling into an English learning opportunity.**

FlipToEnglish is a Telegram bot that takes news from popular Ukrainian channels, translates them into English at your level, and delivers them to you — just like a regular news feed, but in English.

## ✨ Features

- **Real-time news** from 9 Ukrainian Telegram channels
- **3 English difficulty levels** — Beginner, Intermediate, Advanced
- **Difficult words highlighted** — tap to see the Ukrainian translation
- **Smart duplicate detection** — no repeated news in your feed
- **Full media support** — photos, videos, documents come through intact
- **Personalized settings** — choose your channels and level per user

## 🏗️ Architecture

The system has 3 independent components running simultaneously:

| Component         | Description                                              |
|-------------------|----------------------------------------------------------|
| `collector.py`    | Monitors Ukrainian Telegram channels and saves new posts |
| `translator.py`   | Translates news into 3 English levels using Claude AI    |
| `bot.py`          | Delivers translated news to users at their chosen level  |

> For a detailed architecture overview and database schema, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/your-username/FlipToEnglish.git
cd FlipToEnglish

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and fill in your real keys
```

## 🔑 Getting API Keys

| Key                | Where to get it                                                       |
|--------------------|-----------------------------------------------------------------------|
| `BOT_TOKEN`        | Talk to [@BotFather](https://t.me/BotFather) on Telegram              |
| `API_ID` & `API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps)              |
| `ANTHROPIC_API_KEY`| [console.anthropic.com](https://console.anthropic.com)                |

## 🏃 Running

You need **3 terminal windows** running at the same time:

```bash
# Terminal 1 — Collector (fetches news from Telegram channels)
python collector.py

# Terminal 2 — Translator (translates news via Claude AI)
python translator.py

# Terminal 3 — Bot (serves translated news to users)
python bot.py
```

> **Note:** On first run, `collector.py` will ask for your Telegram phone number and a verification code to authenticate via Telethon. After that, the session file keeps you logged in.

## 📡 Supported Channels

The bot currently monitors these Ukrainian news channels:

- [@truexanewsua](https://t.me/truexanewsua)
- [@vanek_nikolaev](https://t.me/vanek_nikolaev)
- [@u_now](https://t.me/u_now)
- [@insiderUKR](https://t.me/insiderUKR)
- [@Tsaplienko](https://t.me/Tsaplienko)
- [@Ukraine_365News](https://t.me/Ukraine_365News)
- [@uniannet](https://t.me/uniannet)
- [@TCH_channel](https://t.me/TCH_channel)
- [@suspilnenews](https://t.me/suspilnenews)

## 🤝 Contributing

Pull requests are welcome! Feel free to open issues for bugs or feature requests.

## 📝 License

This project is licensed under the [MIT License](LICENSE).
