# 📋 NewsLingo — Project vision and roadmap

## 🌍 The big picture

NewsLingo started as a personal experiment: I wanted to learn English by reading my favorite Ukrainian news channels in English. But the concept goes far beyond that.

**The vision:** A universal Telegram bot that works for any language pair and any country. Imagine:

- A Spanish speaker learning French by reading French news channels — translated to their level
- A Japanese speaker learning English through their favorite tech channels
- A German speaker learning Portuguese through Brazilian news

The core idea is simple: **people already scroll through content every day. Let's turn that habit into a learning opportunity.** No textbooks, no homework, no pressure — just your regular feed, but in the language you're learning.

## 🎯 What makes this different

Most language learning apps force you to learn with artificial content: made-up dialogues, textbook exercises, gamified drills. NewsLingo takes a different approach:

- **Real content** — actual news from channels you already follow
- **Your interests** — you choose what to read, so you're always engaged
- **Passive learning** — no extra effort, just read your feed as usual
- **Leveled translation** — the same news adapted to your exact level
- **Context learning** — learn words in real-world context, not isolated flashcards

## 🗺️ Roadmap

### ✅ Phase 1 — Proof of concept (DONE)
- Bot works with Ukrainian → English
- 9 source channels
- 3 difficulty levels
- Basic duplicate detection
- Cloud deployment

### 🔨 Phase 2 — Improve quality (CURRENT)
- [ ] Better translation quality and consistency
- [ ] Smarter duplicate detection (semantic similarity, not just text matching)
- [ ] Fix media handling (albums, videos, documents)
- [ ] Cleaner UI/UX in the bot
- [ ] Better word highlighting (only truly difficult words, not random ones)
- [ ] Stable performance under load

### 🚀 Phase 3 — Learning features
- [ ] Tap any highlighted word to see translation instantly
- [ ] Daily vocabulary summary — words you learned today
- [ ] Vocabulary quiz based on words from the news you read
- [ ] Progress tracking — how many words you've learned, how many news you've read
- [ ] Spaced repetition for vocabulary review
- [ ] Grammar tips based on patterns in the news

### 🌍 Phase 4 — Multi-language support
- [ ] Support any language pair (not just Ukrainian → English)
- [ ] User can input any public Telegram channel as a source
- [ ] Auto-detect source language
- [ ] Let users choose target language and level
- [ ] Language-specific difficulty calibration

### 💡 Phase 5 — Smart features
- [ ] AI-powered content summary (TLDR for each news item)
- [ ] Topic-based filtering (politics, tech, sports, culture)
- [ ] Reading time estimates
- [ ] Pronunciation audio for highlighted words
- [ ] Community features — share interesting translations, discuss news
- [ ] Analytics dashboard — what topics help you learn faster

### 📈 Phase 6 — Scale
- [ ] Multiple bot instances for different language markets
- [ ] Web version alongside Telegram
- [ ] API for third-party integrations
- [ ] Support for other platforms (WhatsApp, Discord)

## 🛠️ Tech stack

| Component | Technology |
|-----------|-----------|
| Bot framework | python-telegram-bot |
| Channel monitoring | Telethon |
| AI translation | Anthropic Claude API |
| Database | SQLite (will migrate to PostgreSQL at scale) |
| Hosting | DigitalOcean |
| Language | Python 3.14 |

## 🤝 How to contribute

### I'm looking for help with

- **Python developers** — improve the core bot, collector, and translator
- **AI/NLP specialists** — better translation quality, smarter duplicate detection, word difficulty estimation
- **UI/UX designers** — make the bot interface cleaner and more intuitive
- **Language teachers** — help design effective learning features
- **Testers** — use the bot and report bugs, suggest improvements
- **Translators** — help adapt the system for other language pairs

### How to get started

1. Fork the repo
2. Check the [Issues](../../issues) tab for open tasks
3. Pick something interesting and comment that you're working on it
4. Submit a Pull Request when ready
5. Or just open an Issue with your idea!

### Code structure

```
NewsLingo/
├── bot.py              # Telegram bot — user interface and news delivery
├── collector.py        # Channel monitor — collects news in real-time
├── translator.py       # AI translator — translates to 3 levels
├── requirements.txt    # Python dependencies
├── .env.example        # Template for API keys
├── README.md           # Project overview
├── PROJECT.md          # This file — vision and roadmap
└── docs/
    └── ARCHITECTURE.md # Technical architecture details
```

## 💬 Try it & Contact

**Try the bot:** [@NewsLingoUKRBot](https://t.me/NewsLingoUKRBot) — press Start, pick your level, and read Ukrainian news in English.

Have questions or ideas? Open an Issue or reach out. This project is in its early days and every contribution matters.

---

*This project started from a simple need: I wanted to learn English without it feeling like homework. If you're learning any language and this idea resonates with you — let's build it together.*
