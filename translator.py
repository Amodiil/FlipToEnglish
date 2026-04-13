"""
translator.py — reads untranslated news from the database and uses the
Claude API to produce three English translations (beginner, intermediate,
advanced) plus word lists with Ukrainian translations for each level.
Runs as a standalone process alongside collector.py and bot.py.

Usage:
    python translator.py
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Support both spellings of the key name
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTROPIC_API_KEY")
DB_PATH = "fliptoenglish.db"
POLL_INTERVAL = 10   # seconds between polls when no work is found
BATCH_DELAY = 2      # seconds between items in a batch to stay within rate limits
BATCH_SIZE = 5       # items to fetch per poll cycle

# Similarity threshold for marking translated news as duplicate
TRANSLATION_SIMILARITY = 0.60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Database ──────────────────────────────────────────────────────────────────

def migrate_db():
    """Add translation and word-list columns to news table if they don't exist yet."""
    with sqlite3.connect(DB_PATH) as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(news)").fetchall()]
        if not cols:
            return
        for col_name, col_def in [
            ("translation_beginner",     "TEXT"),
            ("translation_intermediate", "TEXT"),
            ("translation_advanced",     "TEXT"),
            ("is_translated",            "INTEGER NOT NULL DEFAULT 0"),
            ("word_list_beginner",       "TEXT"),
            ("word_list_intermediate",   "TEXT"),
            ("word_list_advanced",       "TEXT"),
        ]:
            if col_name not in cols:
                con.execute(f"ALTER TABLE news ADD COLUMN {col_name} {col_def}")
        con.commit()


def fetch_untranslated(limit: int = BATCH_SIZE) -> list:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT id, original_text FROM news
               WHERE is_translated = 0
                 AND is_duplicate  = 0
                 AND original_text != ''
               ORDER BY id ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return rows


def save_translations(
    news_id: int,
    beginner: str,
    intermediate: str,
    advanced: str,
    words_beginner: dict,
    words_intermediate: dict,
    words_advanced: dict,
    is_duplicate: bool = False,
):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """UPDATE news
               SET translation_beginner     = ?,
                   translation_intermediate = ?,
                   translation_advanced     = ?,
                   word_list_beginner       = ?,
                   word_list_intermediate   = ?,
                   word_list_advanced       = ?,
                   is_translated            = 1,
                   is_duplicate             = ?
               WHERE id = ?""",
            (
                beginner, intermediate, advanced,
                json.dumps(words_beginner, ensure_ascii=False),
                json.dumps(words_intermediate, ensure_ascii=False),
                json.dumps(words_advanced, ensure_ascii=False),
                int(is_duplicate),
                news_id,
            ),
        )
        con.commit()


def mark_failed(news_id: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE news SET is_translated = 1 WHERE id = ?", (news_id,))
        con.commit()


def check_translation_duplicate(news_id: int, translated_text: str) -> bool:
    if not translated_text or len(translated_text) < 30:
        return False
    compare = translated_text[:500]
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=24)
    ).isoformat(timespec="seconds")
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT translation_intermediate FROM news
               WHERE is_translated = 1
                 AND is_duplicate  = 0
                 AND id != ?
                 AND created_at >= ?
               ORDER BY id DESC
               LIMIT 150""",
            (news_id, cutoff),
        ).fetchall()
    for (existing,) in rows:
        if not existing:
            continue
        if SequenceMatcher(None, compare, existing[:500]).ratio() >= TRANSLATION_SIMILARITY:
            return True
    return False


# ── Translation quality ──────────────────────────────────────────────────────

def clean_translation(text: str) -> str:
    """Remove formatting artifacts from translated text."""
    if not text:
        return text

    # Remove triple+ underscores
    text = re.sub(r"_{3,}", "", text)

    # Remove double underscores
    text = re.sub(r"__", "", text)

    # Remove underscored whitespace: "_ " or " _"
    text = re.sub(r"_\s", " ", text)
    text = re.sub(r"\s_", " ", text)

    # Remove underscores wrapping only punctuation / non-letter chars
    text = re.sub(r"_([^a-zA-Z_]*?)_", r"\1", text)

    # Limit _underlined_ phrases to max 2 words
    def limit_phrase_length(m):
        inner = m.group(1).strip()
        words = inner.split()
        if len(words) > 2:
            return inner  # drop markers, keep text
        return f"_{inner}_"

    text = re.sub(r"_([^_]+)_", limit_phrase_length, text)

    # Remove orphaned underscores (not part of a _word_ pair)
    # First, temporarily protect valid _word_ pairs
    protected = {}
    counter = [0]

    def protect(m):
        key = f"\x00PROT{counter[0]}\x00"
        protected[key] = m.group(0)
        counter[0] += 1
        return key

    text = re.sub(r"_(\S+?)_", protect, text)
    # Now remove any remaining lone underscores
    text = text.replace("_", "")
    # Restore protected pairs
    for key, val in protected.items():
        text = text.replace(key, val)

    # Strip leaked HTML tags
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)

    # Strip leaked markdown bold/italic markers
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)

    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)

    return text.strip()


def validate_translation(text: str) -> bool:
    """Return True if the translation looks valid, False if it seems broken."""
    if not text or len(text.strip()) < 5:
        return False

    # Reject if HTML tags leaked in
    if re.search(r"<[a-zA-Z/][^>]{0,50}>", text):
        return False

    # Reject if too many underscores remain (broken formatting)
    underscore_count = text.count("_")
    if underscore_count > 0:
        # Count proper _word_ pairs
        pairs = len(re.findall(r"_\S+?_", text))
        orphaned = underscore_count - pairs * 2
        if orphaned > 3:
            return False

    # Reject if too much Cyrillic (translation should be English)
    cyrillic = len(re.findall(r"[\u0400-\u04FF]", text))
    latin = len(re.findall(r"[a-zA-Z]", text))
    if latin > 0 and cyrillic / max(latin, 1) > 0.3:
        return False
    if latin == 0 and cyrillic > 10:
        return False

    return True


# ── Translation ───────────────────────────────────────────────────────────────

TRANSLATION_PROMPT = """\
Translate the following Ukrainian news text into English at three different levels.

Return ONLY a JSON object with exactly these six keys:

- "beginner": very simple words, short sentences, basic grammar. Wrap words that \
may be new or difficult for a beginner in underscores, like _word_.
- "intermediate": natural everyday English. Wrap only harder vocabulary words in \
underscores, like _word_.
- "advanced": professional English newspaper style. No underscores or markup at all.
- "words_beginner": JSON object mapping every underscored word from the beginner \
translation to its Ukrainian translation. Include ALL unfamiliar words — beginners \
need the most help. Example: {{"announced": "оголосив", "agreement": "угода"}}.
- "words_intermediate": JSON object mapping only the underscored words from the \
intermediate translation to their Ukrainian translations. Fewer words than beginner.
- "words_advanced": JSON object mapping only very technical or specialised terms \
from the advanced translation to their Ukrainian translations. Usually empty {{}}.

IMPORTANT formatting rules for underscores:
- Only underline SINGLE words or TWO-WORD phrases, never longer.
- Do NOT put underscores around punctuation, spaces, or non-English characters.
- Do NOT use double underscores (__).
- The advanced translation must have NO underscores at all.

Ukrainian text:
{text}

Return only the JSON object, no other text."""


def translate_with_claude(client: anthropic.Anthropic, text: str) -> dict:
    """Call Claude and return a dict with all six translation keys."""
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[
            {"role": "user", "content": TRANSLATION_PROMPT.format(text=text)},
        ],
    )
    raw = message.content[0].text.strip()

    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) >= 2 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    if not ANTHROPIC_API_KEY:
        raise SystemExit(
            "No Anthropic API key found in .env.\n"
            "Add ANTHROPIC_API_KEY=<your-key> (or ANTROPIC_API_KEY) to .env."
        )

    migrate_db()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    log.info("Translator started. Polling for untranslated news every %ds.", POLL_INTERVAL)

    while True:
        rows = fetch_untranslated()
        if not rows:
            time.sleep(POLL_INTERVAL)
            continue

        for news_id, text in rows:
            log.info("Translating news #%d  (%.60s…)", news_id, text)

            attempts = 0
            max_attempts = 2

            while attempts < max_attempts:
                attempts += 1
                try:
                    result = translate_with_claude(client, text)

                    beginner     = result.get("beginner", "")
                    intermediate = result.get("intermediate", "")
                    advanced     = result.get("advanced", "")
                    words_beg    = result.get("words_beginner", {})
                    words_int    = result.get("words_intermediate", {})
                    words_adv    = result.get("words_advanced", {})

                    if not isinstance(words_beg, dict):
                        words_beg = {}
                    if not isinstance(words_int, dict):
                        words_int = {}
                    if not isinstance(words_adv, dict):
                        words_adv = {}

                    # Clean up underscore formatting artifacts
                    beginner     = clean_translation(beginner)
                    intermediate = clean_translation(intermediate)
                    advanced     = clean_translation(advanced)

                    # Ensure advanced has NO underscore markers at all
                    advanced = advanced.replace("_", "")

                    # Validate quality
                    all_valid = (
                        validate_translation(beginner)
                        and validate_translation(intermediate)
                        and validate_translation(advanced)
                    )

                    if not all_valid and attempts < max_attempts:
                        log.warning(
                            "Translation validation failed for news #%d (attempt %d/%d), retrying…",
                            news_id, attempts, max_attempts,
                        )
                        time.sleep(1)
                        continue

                    if not all_valid:
                        log.warning(
                            "Translation still invalid after %d attempts for news #%d, saving anyway",
                            max_attempts, news_id,
                        )

                    # Check for semantic duplicate
                    is_dup = check_translation_duplicate(news_id, intermediate or beginner)
                    if is_dup:
                        log.info("News #%d flagged as duplicate after translation", news_id)

                    save_translations(
                        news_id, beginner, intermediate, advanced,
                        words_beg, words_int, words_adv,
                        is_duplicate=is_dup,
                    )
                    log.info("Translated news #%d (dup=%s)", news_id, is_dup)
                    break  # success

                except Exception as exc:
                    if attempts < max_attempts:
                        log.warning(
                            "Translation attempt %d failed for news #%d: %s — retrying",
                            attempts, news_id, exc,
                        )
                        time.sleep(1)
                    else:
                        log.error("Failed to translate news #%d: %s", news_id, exc)
                        mark_failed(news_id)

            time.sleep(BATCH_DELAY)


if __name__ == "__main__":
    run()
