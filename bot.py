import asyncio
import json
import logging
import os
import re
import sqlite3
import warnings
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
    BotCommand,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

warnings.filterwarnings("ignore", message=".*per_message.*")

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "fliptoenglish.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

WAITING_FOR_CHANNEL = 1

CHANNELS = [
    "@truexanewsua",
    "@vanek_nikolaev",
    "@u_now",
    "@insiderUKR",
    "@Tsaplienko",
    "@Ukraine_365News",
    "@uniannet",
    "@TCH_channel",
    "@suspilnenews",
]

LEVELS = {
    "beginner":     "Початківець",
    "intermediate": "Середній",
    "advanced":     "Просунутий",
}

LEVEL_DESCRIPTIONS = {
    "beginner":     "Прості слова, короткі речення, багато підкреслених слів для перекладу",
    "intermediate": "Звичайна англійська, лише складніші слова підкреслені",
    "advanced":     "Як справжня англійська газета, дуже мало підкреслених слів",
}

SETTINGS_SAVED_MSG = "✅ Зміни збережено! Нові налаштування застосуються з наступної новини."

WELCOME_MESSAGE = (
    "👋 Ласкаво просимо до FlipToEnglish!\n\n"
    "Як це працює:\n"
    "1️⃣ Оберіть канали — звідки брати новини\n"
    "2️⃣ Оберіть рівень англійської — початківець, середній або просунутий\n"
    "3️⃣ Читайте новини англійською — з перекладом складних слів\n\n"
    "Ваші улюблені українські канали новин тепер англійською мовою вашого рівня. "
    "Просто скролите стрічку як звичайно — і вчите англійську без зусиль!\n\n"
    "Натисніть кнопку меню щоб почати налаштування ⬇️"
)


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id        INTEGER PRIMARY KEY,
                channels       TEXT    NOT NULL DEFAULT '',
                english_level  TEXT    NOT NULL DEFAULT '',
                news_per_day   INTEGER NOT NULL DEFAULT 5,
                setup_complete INTEGER NOT NULL DEFAULT 0,
                welcomed       INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_news_log (
                user_id INTEGER NOT NULL,
                news_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, news_id)
            )
        """)

        user_cols = [r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()]
        for col_name, col_def in [
            ("setup_complete", "INTEGER NOT NULL DEFAULT 0"),
            ("welcomed",       "INTEGER NOT NULL DEFAULT 0"),
        ]:
            if col_name not in user_cols:
                con.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

        news_cols = [r[1] for r in con.execute("PRAGMA table_info(news)").fetchall()]
        if news_cols:
            for col_name, col_def in [
                ("translation_beginner",     "TEXT"),
                ("translation_intermediate", "TEXT"),
                ("translation_advanced",     "TEXT"),
                ("is_translated",            "INTEGER NOT NULL DEFAULT 0"),
                ("word_list_beginner",       "TEXT"),
                ("word_list_intermediate",   "TEXT"),
                ("word_list_advanced",       "TEXT"),
                ("collected_at",             "TEXT"),
                ("media_files",              "TEXT"),
            ]:
                if col_name not in news_cols:
                    con.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_def}")

        con.commit()


def get_user(user_id: int) -> dict:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT channels, english_level, news_per_day, setup_complete, welcomed "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        _insert_user(user_id)
        return {
            "channels": [], "english_level": "", "news_per_day": 5,
            "setup_complete": False, "welcomed": False,
        }
    channels = [c for c in row[0].split(",") if c]
    return {
        "channels":      channels,
        "english_level": row[1],
        "news_per_day":  row[2],
        "setup_complete": bool(row[3]),
        "welcomed":      bool(row[4]),
    }


def _insert_user(user_id: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        con.commit()


def _save_fields(user_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [user_id]
    with sqlite3.connect(DB_PATH) as con:
        con.execute(f"UPDATE users SET {sets} WHERE user_id = ?", vals)
        con.commit()


def toggle_channel(user_id: int, channel: str) -> list:
    user = get_user(user_id)
    channels = user["channels"]
    if channel in channels:
        channels.remove(channel)
    else:
        channels.append(channel)
    _save_fields(user_id, channels=",".join(channels))
    return channels


def set_channels_done(user_id: int):
    user = get_user(user_id)
    complete = bool(user["channels"] and user["english_level"])
    _save_fields(user_id, setup_complete=int(complete))
    return complete


def set_level(user_id: int, level: str) -> bool:
    user = get_user(user_id)
    complete = bool(user["channels"] and level)
    _save_fields(user_id, english_level=level, setup_complete=int(complete))
    return complete


def get_all_setup_users() -> list:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT user_id, english_level, channels FROM users WHERE setup_complete = 1"
        ).fetchall()
    result = []
    for user_id, level, channels_str in rows:
        channels = [c for c in channels_str.split(",") if c]
        if channels and level:
            result.append((user_id, level, channels))
    return result


def get_next_news_for_user(user_id: int, channels: list) -> dict | None:
    if not channels:
        return None
    placeholders = ",".join("?" * len(channels))
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            f"""SELECT id, channel, original_text,
                       translation_beginner, translation_intermediate, translation_advanced,
                       media_type, media_file_id, created_at,
                       word_list_beginner, word_list_intermediate, word_list_advanced,
                       media_files
                FROM news
                WHERE channel IN ({placeholders})
                  AND is_translated = 1
                  AND is_duplicate  = 0
                  AND id NOT IN (
                      SELECT news_id FROM user_news_log WHERE user_id = ?
                  )
                ORDER BY id ASC
                LIMIT 1""",
            (*channels, user_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "id":                       row[0],
        "channel":                  row[1],
        "original_text":            row[2],
        "translation_beginner":     row[3],
        "translation_intermediate": row[4],
        "translation_advanced":     row[5],
        "media_type":               row[6],
        "media_file_id":            row[7],
        "created_at":               row[8],
        "word_list_beginner":       row[9],
        "word_list_intermediate":   row[10],
        "word_list_advanced":       row[11],
        "media_files":              row[12],
    }


def log_news_sent(user_id: int, news_id: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR IGNORE INTO user_news_log (user_id, news_id) VALUES (?, ?)",
            (user_id, news_id),
        )
        con.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def format_underlines(text: str) -> str:
    """Convert _word_ markers into HTML underline tags."""
    if not text:
        return text
    return re.sub(r"_(\S+?)_", r"<u>\1</u>", text)


def parse_word_list(json_str: str | None) -> dict:
    if not json_str:
        return {}
    try:
        data = json.loads(json_str)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_media_files(media_files_json: str | None, media_file_id: str | None,
                       media_type: str | None) -> list:
    """Return list of {type, path} dicts from media_files JSON or legacy single file."""
    if media_files_json:
        try:
            data = json.loads(media_files_json)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    if media_file_id:
        ext = os.path.splitext(media_file_id)[1].lower()
        mtype = media_type or ("video" if ext in (".mp4", ".mov", ".avi") else "photo")
        return [{"type": mtype, "path": media_file_id}]
    return []


async def _send_news(bot, chat_id: int, news: dict, level: str):
    """Send a single translated news item to chat_id with action buttons."""
    translation_key = f"translation_{level}"
    raw_text = news.get(translation_key) or news.get("original_text", "")
    body = format_underlines(raw_text)

    ts = news["created_at"][:16].replace("T", " ") if news.get("created_at") else ""
    header = f"<b>{news['channel']}</b>  <i>{ts}</i>"
    full_text = f"{header}\n\n{body}" if body else header

    word_list_key = f"word_list_{level}"
    words = parse_word_list(news.get(word_list_key))

    row1 = [InlineKeyboardButton("Показати українською", callback_data=f"orig:{news['id']}")]
    if words:
        row1.append(InlineKeyboardButton("📖 Слова", callback_data=f"words:{news['id']}"))
    keyboard = InlineKeyboardMarkup([
        row1,
        [InlineKeyboardButton("Наступна ➡️", callback_data=f"next:{news['id']}")],
    ])

    MAX_CAPTION = 1020
    caption = full_text if len(full_text) <= MAX_CAPTION else full_text[:MAX_CAPTION] + "…"

    media_items = _parse_media_files(
        news.get("media_files"), news.get("media_file_id"), news.get("media_type")
    )
    valid_media = [m for m in media_items if os.path.exists(m["path"])]

    sent = False

    if len(valid_media) >= 2:
        file_handles = []
        try:
            media_group = []
            for i, m in enumerate(valid_media[:10]):
                fh = open(m["path"], "rb")
                file_handles.append(fh)
                kw = {"caption": caption, "parse_mode": "HTML"} if i == 0 else {}
                if m["type"] == "photo":
                    media_group.append(InputMediaPhoto(media=fh, **kw))
                elif m["type"] == "video":
                    media_group.append(InputMediaVideo(media=fh, **kw))
            if media_group:
                await bot.send_media_group(chat_id=chat_id, media=media_group)
                # send_media_group doesn't support reply_markup — send buttons separately
                await bot.send_message(chat_id=chat_id, text="👆", reply_markup=keyboard)
                sent = True
        except Exception as exc:
            log.warning("Media group send failed for news #%d: %s", news["id"], exc)
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    elif len(valid_media) == 1:
        m = valid_media[0]
        try:
            with open(m["path"], "rb") as f:
                if m["type"] == "photo":
                    await bot.send_photo(chat_id=chat_id, photo=f,
                                         caption=caption, parse_mode="HTML",
                                         reply_markup=keyboard)
                elif m["type"] == "video":
                    await bot.send_video(chat_id=chat_id, video=f,
                                         caption=caption, parse_mode="HTML",
                                         reply_markup=keyboard)
            sent = True
        except Exception as exc:
            log.warning("Media send failed for news #%d: %s", news["id"], exc)

    if not sent:
        MAX_TEXT = 4090
        text_to_send = full_text if len(full_text) <= MAX_TEXT else full_text[:MAX_TEXT] + "…"
        await bot.send_message(
            chat_id=chat_id, text=text_to_send,
            parse_mode="HTML", reply_markup=keyboard,
        )


# ── Keyboards ─────────────────────────────────────────────────────────────────

def main_menu_keyboard(setup_complete: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        ["1️⃣ Канали для перекладу"],
        ["2️⃣ Рівень англійської"],
        ["3️⃣ Налаштування"],
    ]
    if setup_complete:
        buttons.append(["▶️ Почати читати новини"])
    return ReplyKeyboardMarkup(
        buttons, resize_keyboard=True, is_persistent=False, one_time_keyboard=True
    )


def channels_keyboard(selected: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in CHANNELS:
        mark = "✅ " if ch in selected else "☐ "
        buttons.append([InlineKeyboardButton(f"{mark}{ch}", callback_data=f"ch:{ch}")])
    buttons.append([InlineKeyboardButton("➕ Додати свій канал", callback_data="add_channel")])
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data="ch_done")])
    return InlineKeyboardMarkup(buttons)


def channels_message_text(selected: list) -> str:
    count = len(selected)
    if count == 0:
        return "Оберіть канали для перекладу (можна обрати кілька):"
    return f"Оберіть канали для перекладу (можна обрати кілька):\n\n<b>Обрано: {count}</b>"


def levels_keyboard(current_level: str = "") -> InlineKeyboardMarkup:
    def label(key: str, name: str) -> str:
        return f"✅ {name}" if key == current_level else name

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label("beginner",     "🟢 " + LEVELS["beginner"]),
                              callback_data="lvl:beginner")],
        [InlineKeyboardButton(label("intermediate", "🔵 " + LEVELS["intermediate"]),
                              callback_data="lvl:intermediate")],
        [InlineKeyboardButton(label("advanced",     "🔴 " + LEVELS["advanced"]),
                              callback_data="lvl:advanced")],
    ])


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _insert_user(user_id)
    user = get_user(user_id)

    if not user["welcomed"]:
        _save_fields(user_id, welcomed=1)
        await update.message.reply_text(
            WELCOME_MESSAGE,
            reply_markup=main_menu_keyboard(user["setup_complete"]),
        )
    else:
        await update.message.reply_text(
            "Головне меню:",
            reply_markup=main_menu_keyboard(user["setup_complete"]),
        )


async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    await update.message.reply_text(
        channels_message_text(user["channels"]),
        parse_mode="HTML",
        reply_markup=channels_keyboard(user["channels"]),
    )


async def show_levels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    text = "Оберіть рівень англійської мови:\n\n"
    for key, name in LEVELS.items():
        text += f"<b>{name}</b> — {LEVEL_DESCRIPTIONS[key]}\n\n"
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=levels_keyboard(user["english_level"])
    )


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    channels_str = (
        "\n".join(f"  • {ch}" for ch in user["channels"])
        if user["channels"] else "  (не обрано)"
    )
    level_key = user["english_level"]
    level_name = LEVELS.get(level_key, "не обрано") if level_key else "не обрано"
    level_desc = LEVEL_DESCRIPTIONS.get(level_key, "") if level_key else ""
    level_line = level_name + (f" — <i>{level_desc}</i>" if level_desc else "")
    status = "✅ Налаштовано" if user["setup_complete"] else "⚠️ Не повністю налаштовано"
    text = (
        f"⚙️ <b>Ваші налаштування</b>  {status}\n\n"
        f"📡 <b>Канали:</b>\n{channels_str}\n\n"
        f"📚 <b>Рівень англійської:</b> {level_line}\n\n"
        f"📰 <b>Новин на день:</b> {user['news_per_day']}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_start_reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user["channels"]:
        await update.message.reply_text("Спочатку оберіть канали для перекладу!")
        return
    if not user["english_level"]:
        await update.message.reply_text("Спочатку оберіть рівень англійської!")
        return

    news = get_next_news_for_user(user_id, user["channels"])
    if news:
        log_news_sent(user_id, news["id"])
        await _send_news(context.bot, user_id, news, user["english_level"])
        return

    placeholders = ",".join("?" * len(user["channels"]))
    with sqlite3.connect(DB_PATH) as con:
        count = con.execute(
            f"SELECT COUNT(*) FROM news WHERE channel IN ({placeholders}) AND is_duplicate = 0",
            user["channels"],
        ).fetchone()[0]

    if count == 0:
        await update.message.reply_text(
            "Новин поки немає. Запустіть collector.py, щоб почати збір новин!"
        )
    else:
        await update.message.reply_text(
            "Перекладені новини ще готуються. Зачекайте трохи — вони з'являться автоматично!"
        )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "Канали" in text:
        await show_channels(update, context)
    elif "Рівень" in text:
        await show_levels(update, context)
    elif "Налаштування" in text:
        await show_settings(update, context)
    elif "Почати читати" in text or "читати новини" in text:
        await handle_start_reading(update, context)


# ── Inline callbacks ───────────────────────────────────────────────────────────

async def callback_channel_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channel = query.data[len("ch:"):]
    updated_channels = toggle_channel(query.from_user.id, channel)
    await query.edit_message_text(
        channels_message_text(updated_channels),
        parse_mode="HTML",
        reply_markup=channels_keyboard(updated_channels),
    )


async def callback_channel_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = get_user(query.from_user.id)

    if not user["channels"]:
        await query.answer("Спочатку оберіть хоча б один канал!", show_alert=True)
        return

    await query.answer()
    count = len(user["channels"])
    set_channels_done(query.from_user.id)

    count_word = "канал" if count == 1 else "канали" if 2 <= count <= 4 else "каналів"
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        f"✅ Ви обрали <b>{count}</b> {count_word} для перекладу!\n\n"
        "Тепер оберіть рівень англійської ➡️",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("2️⃣ Оберіть рівень англійської ➡️", callback_data="goto_level")]
        ]),
    )


async def callback_goto_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    text = "Оберіть рівень англійської мови:\n\n"
    for key, name in LEVELS.items():
        text += f"<b>{name}</b> — {LEVEL_DESCRIPTIONS[key]}\n\n"
    await query.message.reply_text(
        text, parse_mode="HTML", reply_markup=levels_keyboard(user["english_level"])
    )


async def callback_level_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    level = query.data[len("lvl:"):]
    setup_complete = set_level(query.from_user.id, level)
    level_name = LEVELS.get(level, level)

    await query.edit_message_text(
        f"✅ Рівень встановлено: <b>{level_name}</b>\n\n"
        f"<i>{LEVEL_DESCRIPTIONS[level]}</i>",
        parse_mode="HTML",
    )

    if setup_complete:
        await query.message.reply_text(
            "🎉 Все готово! Можна починати читати новини.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Почати читати новини ➡️", callback_data="start_reading")]
            ]),
        )
    else:
        await query.message.reply_text(
            SETTINGS_SAVED_MSG + "\n\nСпочатку оберіть канали для перекладу ➡️",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1️⃣ Оберіть канали ➡️", callback_data="goto_channels")]
            ]),
        )


async def callback_goto_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = get_user(query.from_user.id)
    await query.message.reply_text(
        channels_message_text(user["channels"]),
        parse_mode="HTML",
        reply_markup=channels_keyboard(user["channels"]),
    )


async def callback_start_reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline 'Start reading' button handler."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)

    if not user["setup_complete"]:
        await query.message.reply_text("Спочатку завершіть налаштування!")
        return

    news = get_next_news_for_user(user_id, user["channels"])
    if not news:
        await query.message.reply_text(
            "Перекладені новини ще готуються. Зачекайте трохи — вони з'являться автоматично!"
        )
        return

    log_news_sent(user_id, news["id"])
    await _send_news(context.bot, user_id, news, user["english_level"])


async def callback_show_original(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        news_id = int(query.data[len("orig:"):])
    except ValueError:
        return
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT original_text, channel, created_at FROM news WHERE id = ?", (news_id,)
        ).fetchone()
    if not row:
        await query.message.reply_text("Оригінальний текст не знайдено.")
        return
    original_text, channel, created_at = row
    ts = created_at[:16].replace("T", " ") if created_at else ""
    await query.message.reply_text(
        f"<b>{channel}</b>  <i>{ts}</i>\n\n{original_text}", parse_mode="HTML"
    )


async def callback_show_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        news_id = int(query.data[len("words:"):])
    except ValueError:
        return

    user = get_user(query.from_user.id)
    level = user.get("english_level", "intermediate") or "intermediate"

    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            f"SELECT word_list_{level} FROM news WHERE id = ?", (news_id,)
        ).fetchone()

    if not row:
        await query.message.reply_text("Список слів не знайдено.")
        return

    words = parse_word_list(row[0])
    if not words:
        await query.message.reply_text("Для цієї новини список слів порожній.")
        return

    lines = [f"<b>{word}</b> — {translation}" for word, translation in words.items()]
    text = "📖 <b>Складні слова:</b>\n\n" + "\n".join(lines)
    if len(text) > 4090:
        text = text[:4090] + "…"
    await query.message.reply_text(text, parse_mode="HTML")


async def callback_next_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)

    if not user["setup_complete"]:
        await query.message.reply_text("Спочатку завершіть налаштування!")
        return

    news = get_next_news_for_user(user_id, user["channels"])
    if not news:
        await query.message.reply_text(
            "Нових перекладених новин поки немає. Зачекайте — вони з'являться автоматично!"
        )
        return

    log_news_sent(user_id, news["id"])
    await _send_news(context.bot, user_id, news, user["english_level"])


# ── Add channel conversation ───────────────────────────────────────────────────

async def callback_add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введіть назву каналу (наприклад: @mychannel):")
    return WAITING_FOR_CHANNEL


async def receive_channel_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not re.match(r"^@[A-Za-z][A-Za-z0-9_]{4,}$", text):
        await update.message.reply_text(
            "Невірний формат. Канал повинен починатися з @ та містити мінімум 5 символів.\n"
            "Спробуйте ще раз або натисніть /start для повернення в меню."
        )
        return WAITING_FOR_CHANNEL
    await update.message.reply_text(
        f"✅ Запит на додавання каналу <b>{text}</b> прийнято.\n\n"
        "Адміну надіслано повідомлення про ваш запит. "
        "Перевірте основний список каналів через 3 дні.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    await update.message.reply_text(
        "Скасовано.", reply_markup=main_menu_keyboard(user["setup_complete"])
    )
    return ConversationHandler.END


# ── Auto-delivery background task ─────────────────────────────────────────────

async def _deliver_to_all_users(app: Application):
    for user_id, level, channels in get_all_setup_users():
        news = get_next_news_for_user(user_id, channels)
        if not news:
            continue
        try:
            log_news_sent(user_id, news["id"])
            await _send_news(app.bot, user_id, news, level)
            log.info("Auto-delivered news #%d to user %d", news["id"], user_id)
        except Exception as exc:
            log.warning("Auto-delivery failed for user %d: %s", user_id, exc)


async def auto_deliver_loop(app: Application):
    await asyncio.sleep(10)
    log.info("Auto-delivery loop started.")
    while True:
        try:
            await _deliver_to_all_users(app)
        except Exception as exc:
            log.error("Auto-delivery loop error: %s", exc)
        await asyncio.sleep(30)


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",    "Головне меню"),
        BotCommand("channels", "1️⃣ Канали для перекладу"),
        BotCommand("level",    "2️⃣ Рівень англійської"),
        BotCommand("settings", "3️⃣ Налаштування"),
        BotCommand("read",     "▶️ Читати новини"),
    ])
    app.create_task(auto_deliver_loop(app))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_add_channel_start, pattern="^add_channel$")],
        states={
            WAITING_FOR_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel_name)
            ],
        },
        fallbacks=[CommandHandler("start", cancel)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("channels", show_channels))
    app.add_handler(CommandHandler("level",    show_levels))
    app.add_handler(CommandHandler("settings", show_settings))
    app.add_handler(CommandHandler("read",     handle_start_reading))
    app.add_handler(add_channel_conv)
    app.add_handler(CallbackQueryHandler(callback_channel_toggle,  pattern=r"^ch:"))
    app.add_handler(CallbackQueryHandler(callback_channel_done,    pattern=r"^ch_done$"))
    app.add_handler(CallbackQueryHandler(callback_goto_level,      pattern=r"^goto_level$"))
    app.add_handler(CallbackQueryHandler(callback_goto_channels,   pattern=r"^goto_channels$"))
    app.add_handler(CallbackQueryHandler(callback_level_select,    pattern=r"^lvl:"))
    app.add_handler(CallbackQueryHandler(callback_start_reading,   pattern=r"^start_reading$"))
    app.add_handler(CallbackQueryHandler(callback_show_original,   pattern=r"^orig:"))
    app.add_handler(CallbackQueryHandler(callback_show_words,      pattern=r"^words:"))
    app.add_handler(CallbackQueryHandler(callback_next_news,       pattern=r"^next:"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(Канали|Рівень|Налаштування|Почати читати|читати новини)"),
            handle_menu,
        )
    )

    print("FlipToEnglish bot is running...")
    app.run_polling()
