# bot.py
import os
import glob
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

# ---------- Load env ----------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
STOXEYE_URL = os.getenv("STOXEYE_URL", "https://your-stoxeye-site.example").strip()

# CSV_TARGET can be a folder OR a single file
CSV_TARGET = os.getenv("CSV_DIR", "sample_portfolios")
CSV_TARGET = (CSV_TARGET or "").strip().strip('"').strip("'")
CSV_TARGET = os.path.normpath(os.path.expanduser(CSV_TARGET))

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in .env with your BotFather token.")

WELCOME_TEXT = (
    "👋 Hey! Here’s the StoxEye link and test CSV files.\n\n"
    "Open StoxEye, upload a CSV, and play with the demo portfolio."
)

# ---------- File helpers ----------
def _list_from_dir(directory: str):
    """Find all csv/xlsx/xls inside a directory."""
    os.makedirs(directory, exist_ok=True)
    patterns = [
        os.path.join(directory, "*.csv"),
        os.path.join(directory, "*.CSV"),
        os.path.join(directory, "*.xlsx"),
        os.path.join(directory, "*.xls"),
    ]
    files = []
    for p in patterns:
        files.extend(glob.glob(p))
    return sorted(set(files), key=lambda p: p.lower())

def find_sources():
    """If CSV_TARGET is a file, return [that]; else list files in the folder."""
    if os.path.isfile(CSV_TARGET):
        return [CSV_TARGET]
    return _list_from_dir(CSV_TARGET)

def convert_excel_to_csv(excel_path: str) -> str:
    """Convert first sheet of Excel to a temp CSV and return that path."""
    df = pd.read_excel(excel_path, sheet_name=0)
    out_path = os.path.join(tempfile.gettempdir(), f"{Path(excel_path).stem}.csv")
    df.to_csv(out_path, index=False)
    return out_path

def prepare_files():
    """
    Return (pairs, temps)
    - pairs: list[(filepath, display_name)]
    - temps: list[temp files to delete]
    """
    src = find_sources()
    pairs, temps = [], []
    for p in src:
        lower = p.lower()
        if lower.endswith(".csv"):
            pairs.append((p, Path(p).name))
        elif lower.endswith((".xlsx", ".xls")):
            try:
                cp = convert_excel_to_csv(p)
                pairs.append((cp, f"{Path(p).stem}_converted.csv"))
                temps.append(cp)
            except Exception as e:
                print(f"[WARN] Excel->CSV failed for {p}: {e}")
                pairs.append((p, Path(p).name))
    return pairs, temps

def zip_pairs(pairs):
    """Create a ZIP containing all pairs; return zip path."""
    zip_path = os.path.join(tempfile.gettempdir(), "test_portfolios.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, name in pairs:
            if os.path.isfile(path):
                zf.write(path, arcname=name)
    return zip_path

# ---------- Telegram handlers ----------
async def _post_init(app: Application):
    # Ensure polling (no webhook) to avoid "Conflict: other getUpdates"
    await app.bot.delete_webhook(drop_pending_updates=True)

async def send_link(update: Update):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Open StoxEye", url=STOXEYE_URL)]])
    await update.message.reply_text(WELCOME_TEXT + f"\n\n🔗 {STOXEYE_URL}", reply_markup=kb)

async def send_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_link(update)
    pairs, temps = prepare_files()
    target_hint = CSV_TARGET if os.path.isfile(CSV_TARGET) else f"folder: {CSV_TARGET}"
    if not pairs:
        await update.message.reply_text(f"⚠️ No CSV/Excel files found at {target_hint}")
        return
    zip_path = zip_pairs(pairs)
    try:
        with open(zip_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="test_portfolios.zip",
                caption="📦 All sample portfolios (CSV). Import any one into StoxEye."
            )
    finally:
        try: os.remove(zip_path)
        except: pass
        for t in temps:
            try: os.remove(t)
            except: pass

async def send_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_link(update)
    pairs, temps = prepare_files()
    target_hint = CSV_TARGET if os.path.isfile(CSV_TARGET) else f"folder: {CSV_TARGET}"
    if not pairs:
        await update.message.reply_text(f"⚠️ No CSV/Excel files found at {target_hint}")
        return
    try:
        for path, name in pairs:
            with open(path, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=name, caption=f"📄 {name} — import into StoxEye."
                )
    finally:
        for t in temps:
            try: os.remove(t)
            except: pass

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_zip(update, context)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    if text == "hi":
        await send_zip(update, context)
    else:
        await update.message.reply_text(
            "Say 'hi' or use /start for link + ZIP.\n"
            "Commands: /zip (one ZIP) · /files (send individually)"
        )

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("zip", send_zip))
    app.add_handler(CommandHandler("files", send_files))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
