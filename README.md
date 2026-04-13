# 🔄 NewsLingo

**Turn your daily news scrolling into a language learning opportunity.**

## 💡 The idea

I was trying to learn English and realized something simple: the best way to learn a language is to consume content you already enjoy — but in the language you're learning.

I spend a lot of time scrolling Telegram news channels. What if those same channels could be translated into English, at my level? Not textbook English — real news I actually care about, delivered just like a regular Telegram feed.

That's how NewsLingo was born.

## 🧪 Current status: Testing the concept

This is an early-stage experiment. Right now, the bot works specifically for Ukrainian Telegram channels translated into English at 3 difficulty levels. But the vision is much bigger (see [PROJECT.md](PROJECT.md)).

### What works today

- Real-time news collection from 9 Ukrainian Telegram channels
- AI-powered translation into 3 English levels:
  - 🟢 **Beginner** — simple words, short sentences, many highlighted words
  - 🔵 **Intermediate** — natural English, only harder words highlighted
  - 🔴 **Advanced** — like a real English newspaper
- Difficult words highlighted — tap to see translation
- Smart duplicate detection across channels
- Full media support (photos, videos, documents)
- Personal settings (choose channels, level, preferences)
- Runs 24/7 on a cloud server

## 🏗️ Architecture

The system has 3 components running simultaneously:

```
Ukrainian Telegram Channels
        ↓
  collector.py — monitors channels, saves new posts in real-time
        ↓
  translator.py — translates each post into 3 English levels using Claude AI
        ↓
  bot.py — delivers translated news to each user at their chosen level
```

## 💬 Try it

The bot is live — search for **@NewsLingoUKRBot** on Telegram or open [t.me/NewsLingoUKRBot](https://t.me/NewsLingoUKRBot), press **Start**, and pick your English level.

## 🚀 Quick start (self-hosting)

> Want to run your own instance? Follow the steps below.
> Or just use the hosted bot: [@NewsLingoUKRBot](https://t.me/NewsLingoUKRBot)

1. Clone the repo: `git clone https://github.com/YOUR_USERNAME/NewsLingo.git`
2. Copy `.env.example` to `.env` and fill in your API keys
3. Install dependencies: `pip install -r requirements.txt`
4. Run all 3 components in separate terminals:

```bash
python collector.py    # collects news from channels
python translator.py   # translates news into 3 levels
python bot.py          # serves the Telegram bot
```

## 🔑 Getting API keys

| Key | Where to get it |
|-----|----------------|
| Telegram Bot Token | Talk to [@BotFather](https://t.me/BotFather) on Telegram |
| Telegram API ID & Hash | [my.telegram.org/apps](https://my.telegram.org/apps) |
| Anthropic API Key | [console.anthropic.com](https://console.anthropic.com) |

## 🤝 Contributing

This project is in its early testing phase and I'm looking for help! See [PROJECT.md](PROJECT.md) for the full vision and roadmap.

Whether you're a developer, designer, language teacher, or just someone learning a language — your ideas and contributions are welcome. Feel free to:

- Open an **Issue** with ideas or bug reports
- Submit a **Pull Request** with improvements
- Share your feedback on the concept

## 📝 License

MIT — use it, fork it, build on it.
