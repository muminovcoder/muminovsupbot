import os
import asyncio
import aiosqlite
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramAPIError
from dotenv import load_dotenv

# 🌐 .env fayl yuklash
load_dotenv()

# 🔑 Token va xatolik tekshiruvi
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN topilmadi! .env fayliga qo'shing.")

# 📌 Sozlamalar
CHANNEL_USERNAME = "muminov_vlog"
CHANNEL_CHAT_ID = f"@{CHANNEL_USERNAME}"
CONTACT_URL = "https://t.me/Kmuminov"
PHONE_NUMBER = "+998 93 495 48 08"
CHAT_URL = "https://t.me/+eovmr7GVTjY2Nzcy"
DB_PATH = "posts.db"
USERS_DB_PATH = "numbers.db"

# 🇺🇿 O'zbekcha kun nomlari
DAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

# 🗃️ Postlar DB yaratish
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY,
                timestamp INTEGER NOT NULL
            )
        """)
        await db.commit()

# 👥 Foydalanuvchilar DB yaratish
async def init_users_db():
    async with aiosqlite.connect(USERS_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at INTEGER NOT NULL
            )
        """)
        await db.commit()

# ➕ Yangi foydalanuvchini qo'shish
async def add_user(user_id: int, first_name: str, username: str):
    joined_at = int(datetime.now(timezone.utc).timestamp())
    async with aiosqlite.connect(USERS_DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, first_name, username, joined_at) VALUES (?, ?, ?, ?)",
            (user_id, first_name, username, joined_at)
        )
        await db.commit()

# 📊 Foydalanuvchilar sonini olish
async def get_user_count() -> int:
    async with aiosqlite.connect(USERS_DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# 🧹 Eski postlarni o'chirish (bugungi 00:00 gacha)
async def clear_old_posts():
    now_utc = datetime.now(timezone.utc)
    today_00_uz_in_utc = now_utc.replace(hour=19, minute=0, second=0, microsecond=0)
    if now_utc.hour >= 19:
        today_00_uz_in_utc += timedelta(days=1)
    cutoff_timestamp = int(today_00_uz_in_utc.timestamp())

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM posts WHERE timestamp < ?", (cutoff_timestamp,))
        deleted = cursor.rowcount
        await db.commit()
    print(f"🧹 {deleted} ta eski post o'chirildi (timestamp < {cutoff_timestamp})")

# 💾 Yangi postni saqlash
async def save_post(post_id: int, timestamp: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO posts (post_id, timestamp) VALUES (?, ?)", (post_id, timestamp))
        await db.commit()

# 📅 Oxirgi post vaqtini olish (O'zbekiston vaqti)
async def get_last_post_info():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT post_id, timestamp FROM posts ORDER BY timestamp DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            post_id, ts = row
            post_time_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            post_time_uz = post_time_utc + timedelta(hours=5)
            day_name = DAYS_UZ[post_time_uz.weekday()]
            date_str = post_time_uz.strftime("%d.%m.%Y")
            time_str = post_time_uz.strftime("%H:%M")
            return {
                "post_id": post_id,
                "day_name": day_name,
                "date": date_str,
                "time": time_str,
                "timestamp": ts
            }

# 🎨 Inline tugmalar
def get_subscription_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
    ])

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kanal — Vloglar & Darslar", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton(text="💬 Chat — Guruhda suhbat", url=CHAT_URL)],
        [InlineKeyboardButton(text="🆕 Oxirgi yangiliklar", callback_data="last_posts")],
        [InlineKeyboardButton(text="📩 Murojaat qilish", url=CONTACT_URL)]
    ])

# ✅ Obuna holatini tekshirish
async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_CHAT_ID, user_id=user_id)
        return member.status in {"member", "administrator", "creator"}
    except TelegramAPIError as e:
        print(f"⚠️ Obuna tekshirishda xato: {e}")
        return False

# 📊 Kanal obunachilar sonini olish
async def get_channel_subscriber_count(bot: Bot) -> int:
    try:
        chat = await bot.get_chat(CHANNEL_CHAT_ID)
        return chat.subscribers_count if hasattr(chat, 'subscribers_count') else 0
    except TelegramAPIError as e:
        print(f"⚠️ Kanal obunachilar sonini olishda xato: {e}")
        return 0

# 🧠 Dispatcher
dp = Dispatcher()

# 📥 Yangi postni saqlash (kanal postlari)
@dp.channel_post()
async def handle_channel_post(message: Message):
    if message.chat.username and message.chat.username.lower() == CHANNEL_USERNAME.lower():
        await save_post(message.message_id, int(message.date.timestamp()))
        print(f"🆕 Yangi post saqlandi: ID={message.message_id} | Vaqt={message.date}")

# 🚪 /start
@dp.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = message.from_user
    await add_user(user.id, user.first_name or "", user.username or "")

    if not await check_subscription(bot, user.id):
        await message.answer(
            "🔐 <b>Majburiy obuna</b>\n\n"
            "Botdan to'liq foydalanish uchun quyidagi kanalga obuna bo'ling.\n\n"
            "📌 Obuna bo'ldingizmi? <b>'Obunani tekshirish'</b> tugmasini bosing.",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
        return

    first_name = user.first_name or "Do'stim"
    welcome = (
        f"✨ <b>Salom, {first_name}!</b>\n\n"
        "Siz <b>Muminov Vlog | ENGLISH</b> rasmiy botidasiz!\n\n"
        "📚 Ingliz tili darslari\n"
        "🎥 Shaxsiy vloglar\n"
        "💡 Foydali maslahatlar\n"
        "🆕 So'nggi yangiliklar\n\n"
        "<i>Quyidagi tugmalardan foydalaning:</i>"
    )
    await message.answer(welcome, parse_mode="HTML", reply_markup=get_main_keyboard())

# 🔍 Obuna tekshirish
@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery, bot: Bot):
    is_sub = await check_subscription(bot, callback.from_user.id)
    if is_sub:
        await callback.answer("✅ Muvaffaqiyatli tasdiqlandi!", show_alert=True)
        first_name = callback.from_user.first_name or "Do'stim"
        await callback.message.edit_text(
            f"✨ <b>Salom, {first_name}!</b>\n\n"
            "Endi barcha funksiyalardan foydalanishingiz mumkin.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    else:
        await callback.answer("❌ Hali kanalga obuna bo'lmagansiz!", show_alert=True)

# 🆕 Oxirgi postlar (faqat bugungi)
@dp.callback_query(lambda c: c.data == "last_posts")
async def show_last_posts(callback: CallbackQuery, bot: Bot):
    if not await check_subscription(bot, callback.from_user.id):
        await callback.answer("⚠️ Iltimos, avval kanalga obuna bo'ling!", show_alert=True)
        return

    posts = await get_recent_posts()
    if not posts:
        await callback.message.answer(
            "📭 Afsuski, bugun hali yangi yangiliklar yo'q.\n\n"
            "Tez orada yangi vloglar va darslar bilan qaytamiz!"
        )
        return

    text = "🆕 <b>Bugungi yangiliklar:</b>\n\n"
    for i, (post_id, date_str, time_str) in enumerate(posts, 1):
        url = f"https://t.me/{CHANNEL_USERNAME}/{post_id}"
        text += f"{i}. <a href='{url}'>Yangilik</a> — {date_str} • {time_str}\n"

    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

# 📅 Oxirgi 24 soatdagi (faqat bugungi) postlarni olish
async def get_recent_posts():
    now_utc = datetime.now(timezone.utc)
    start_of_today_uz_in_utc = now_utc.replace(hour=19, minute=0, second=0, microsecond=0)
    if now_utc.hour >= 19:
        start_of_today_uz_in_utc += timedelta(days=1)
    start_of_today_uz_in_utc -= timedelta(days=1)
    cutoff_timestamp = int(start_of_today_uz_in_utc.timestamp())

    posts = []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT post_id, timestamp FROM posts WHERE timestamp >= ? ORDER BY timestamp DESC",
            (cutoff_timestamp,)
        ) as cursor:
            async for row in cursor:
                post_id, ts = row
                post_time_uz = datetime.fromtimestamp(ts, tz=timezone.utc) + timedelta(hours=5)
                date_str = post_time_uz.strftime("%d.%m")
                time_str = post_time_uz.strftime("%H:%M")
                posts.append((post_id, date_str, time_str))
    return posts

# ℹ️ /help
@dp.message(Command("help"))
async def cmd_help(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("🔐 Iltimos, avval kanalga obuna bo'ling.", reply_markup=get_subscription_keyboard())
        return

    help_text = (
        "📘 <b>Muminov Vlog | ENGLISH — Yordam</b>\n\n"
        "Bu bot — <a href='https://t.me/muminov_vlog'>@muminov_vlog</a> kanalining "
        "rasmiy hamroh botidir.\n\n"
        "<b>Asosiy imkoniyatlar:</b>\n"
        "• 🎥 <b>Kanal</b> — Ingliz tili darslari, vloglar\n"
        "• 💬 <b>Chat</b> — Fikr almashish, savol berish\n"
        "• 🆕 <b>Oxirgi yangiliklar</b> — Bugungi postlar\n"
        "• 📩 <b>Murojaat</b> — Muallifga to'g'ridan-to'g'ri yozish\n\n"
        f"📞 <b>Telefon:</b> <code>{PHONE_NUMBER}</code>\n"
        f"👤 <b>Telegram:</b> <a href='{CONTACT_URL}'>@Kmuminov</a>"
    )
    await message.answer(help_text, parse_mode="HTML", disable_web_page_preview=True)

# 📊 /status — to'liq statistika
@dp.message(Command("status"))
async def cmd_status(message: Message, bot: Bot):
    bot_users = await get_user_count()
    channel_subs = await get_channel_subscriber_count(bot)
    last_post = await get_last_post_info()

    status_text = f"📊 <b>Statistika:</b>\n\n"
    status_text += f"🤖 Bot foydalanuvchilari: <b>{bot_users}</b>\n"
    if last_post:
        status_text += (
            f"\n🗓️ <b>Oxirgi post:</b>\n"
            f"• Kun: <b>{last_post['day_name']}</b>\n"
            f"• Sana: <b>{last_post['date']}</b>\n"
            f"• Vaqt: <b>{last_post['time']} (O'zbekiston)</b>\n"
        )
        post_url = f"https://t.me/{CHANNEL_USERNAME}/{last_post['post_id']}"
        status_text += f"• Havola: <a href='{post_url}'>Ko'rish</a>"
    else:
        status_text += "\n📥 Hali hech qanday post yo'q."

    await message.answer(status_text, parse_mode="HTML", disable_web_page_preview=True)

# 🕰️ Har kuni soat 00:00 (O'zbekiston vaqti) da tozalash
async def schedule_daily_cleanup():
    while True:
        now_uz = datetime.now(timezone(timedelta(hours=5)))
        next_midnight_uz = now_uz.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sleep_seconds = (next_midnight_uz - now_uz).total_seconds()
        await asyncio.sleep(sleep_seconds)
        await clear_old_posts()

# 🚀 Asosiy ishga tushirish
async def main():
    await init_db()
    await init_users_db()
    bot = Bot(token=BOT_TOKEN)

    asyncio.create_task(schedule_daily_cleanup())

    print("✅ Muminov Vlog | ENGLISH — Bot ishga tushdi (statistika va oxirgi post vaqti qo'shildi)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
