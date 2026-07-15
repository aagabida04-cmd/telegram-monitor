 """
مانیتور روزانه کانال‌های عمومی تلگرام برای اخبار استخدامی
-------------------------------------------------------------
از صفحه‌ی پیش‌نمایش عمومی تلگرام (t.me/s/...) استفاده می‌کند که بدون
لاگین قابل خواندن است. نیازی به Playwright یا حساب تلگرام شما نیست.

هر روز از طریق GitHub Actions اجرا می‌شود و نتیجه را با همان ربات
تلگرامی قبلی به شما اطلاع می‌دهد.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# تنظیمات
# ---------------------------------------------------------------------------

TELEGRAM_CHANNELS = [
    "azmoonestekhdami04",
]

# کانال‌های عمومی ایتا (بدون نیاز به لاگین) — فقط یوزرنیم، بدون eitaa.com/
EITAA_CHANNELS = [
    "azmonaslah1404",
]

KEYWORDS = [
    "بانک",
    "پالایشگاه",
    "شیراز",
    "شیراز ناحیه ۱",
    "شیراز ناحیه۱",
    "شیراز ناحیه یک",
]

STATE_FILE = Path("seen_messages.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


# ---------------------------------------------------------------------------
# کمکی‌ها
# ---------------------------------------------------------------------------

def load_seen() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen: dict) -> None:
    STATE_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  توکن ربات یا chat id تنظیم نشده؛ پیام فقط چاپ می‌شود:")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    if not resp.ok:
        print(f"❌ ارسال تلگرام ناموفق بود: {resp.status_code} {resp.text}", file=sys.stderr)


def text_matches(message_text: str) -> bool:
    return any(kw in message_text for kw in KEYWORDS)


# ---------------------------------------------------------------------------
# اسکرپینگ
# ---------------------------------------------------------------------------

def fetch_telegram_messages(channel_username: str):
    """پیام‌های صفحه پیش‌نمایش عمومی تلگرام را می‌خواند: لیستی از (message_id, text)."""
    url = f"https://t.me/s/{channel_username}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for wrap in soup.select("div.tgme_widget_message"):
        msg_id = wrap.get("data-post", "")  # مثل "channelname/123"
        text_el = wrap.select_one(".tgme_widget_message_text")
        text = text_el.get_text(separator="\n").strip() if text_el else ""
        if msg_id and text:
            results.append((msg_id, text))
    return results


def fetch_eitaa_messages(channel_username: str):
    """
    پیام‌های صفحه پیش‌نمایش عمومی ایتا را می‌خواند: لیستی از (message_id, text).

    ⚠️ نکته: ساختار HTML این صفحه حدسی است (شبیه تلگرام) و ممکن است بعد از
    اولین اجرای واقعی نیاز به اصلاح داشته باشد.
    """
    url = f"https://eitaa.com/{channel_username}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    # تلاش با چند سلکتور احتمالی مختلف (ایتا از کد مشابه تلگرام استفاده می‌کند)
    candidates = soup.select("div.etme_widget_message, div.text_content, div[id^='message']")
    if not candidates:
        candidates = soup.select("div.tgme_widget_message")  # fallback

    for i, wrap in enumerate(candidates):
        msg_id = wrap.get("id") or wrap.get("data-post") or f"{channel_username}-{i}"
        text = wrap.get_text(separator="\n").strip()
        if text:
            results.append((str(msg_id), text))
    return results


def collect_matches(channel_label: str, messages, seen: dict, key: str):
    channel_seen = set(seen.get(key, []))
    matches = []
    for msg_id, text in messages:
        if msg_id in channel_seen:
            continue
        channel_seen.add(msg_id)
        if text_matches(text):
            matches.append((channel_label, text))
    seen[key] = list(channel_seen)[-300:]
    return matches


def run():
    seen = load_seen()
    new_matches = []

    for channel in TELEGRAM_CHANNELS:
        print(f"🔎 [تلگرام] در حال بررسی کانال: {channel}")
        try:
            messages = fetch_telegram_messages(channel)
        except Exception as e:
            print(f"❌ خطا در خواندن کانال تلگرام {channel}: {e}", file=sys.stderr)
            continue
        new_matches += collect_matches(f"تلگرام: {channel}", messages, seen, f"tg:{channel}")

    for channel in EITAA_CHANNELS:
        print(f"🔎 [ایتا] در حال بررسی کانال: {channel}")
        try:
            messages = fetch_eitaa_messages(channel)
        except Exception as e:
            print(f"❌ خطا در خواندن کانال ایتا {channel}: {e}", file=sys.stderr)
            continue
        new_matches += collect_matches(f"ایتا: {channel}", messages, seen, f"eitaa:{channel}")

    save_seen(seen)

    if new_matches:
        for channel, text in new_matches:
            msg = f"📢 خبر استخدامی جدید در کانال «{channel}»:\n\n{text}"
            send_telegram(msg)
        print(f"✅ {len(new_matches)} پیام مچ پیدا و ارسال شد.")
    else:
        print("ℹ️ هیچ پیام جدید مرتبطی پیدا نشد.")


if __name__ == "__main__":
    run()
   results = []
    for wrap in soup.select("div.tgme_widget_message"):
        msg_id = wrap.get("data-post", "")
        text_el = wrap.select_one(".tgme_widget_message_text")
        text = text_el.get_text(separator="\n").strip() if text_el else ""
        if msg_id and text:
            results.append((msg_id, text))
    return results


def run():
    seen = load_seen()
    new_matches = []

    for channel in CHANNELS:
        print(f"🔎 در حال بررسی کانال: {channel}")
        try:
            messages = fetch_channel_messages(channel)
        except Exception as e:
            print(f"❌ خطا در خواندن کانال {channel}: {e}", file=sys.stderr)
            continue

        channel_seen = set(seen.get(channel, []))
        for msg_id, text in messages:
            if msg_id in channel_seen:
                continue
            channel_seen.add(msg_id)
            if text_matches(text):
                new_matches.append((channel, text))

        seen[channel] = list(channel_seen)[-300:]

    save_seen(seen)

    if new_matches:
        for channel, text in new_matches:
            msg = f"📢 خبر استخدامی جدید در کانال «{channel}»:\n\n{text}"
            send_telegram(msg)
        print(f"✅ {len(new_matches)} پیام مچ پیدا و ارسال شد.")
    else:
        print("ℹ️ هیچ پیام جدید مرتبطی پیدا نشد.")


if __name__ == "__main__":
    run()
