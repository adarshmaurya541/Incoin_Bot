from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from config import OWNER_ID, MONGO_URI, MONGO_DB_NAME
from pymongo import MongoClient
import asyncio

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
started_users = db["started_users"]
logged_in_users = db["logged_in_users"]

ITEMS_PER_PAGE = 6

def register_data_commands(app):

    @app.on_message(filters.command("stats"))
    async def stats_command(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return await message.reply("🚫 This command is only for the bot owner.")

        started_count = started_users.count_documents({})
        logged_in_count = logged_in_users.count_documents({"status": "active"})

        text = f"""
📊 <b>Bot Usage Stats</b>

👤 Total Started Users: <code>{started_count}</code>
🔐 Total Logged In Users: <code>{logged_in_count}</code>
"""
        buttons = [[InlineKeyboardButton("📋 Get Data", callback_data="details:loggedin:1")]]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)

    @app.on_callback_query(filters.regex(r"^details:(loggedin|started):\d+$"))
    async def details_paged(client, query: CallbackQuery):
        if query.from_user.id != OWNER_ID:
            return await query.answer("🚫 Only owner can access this!", show_alert=True)

        _, mode, page = query.data.split(":")
        page = int(page)

        if mode == "loggedin":
            users = list(logged_in_users.find({"status": "active"}))
            title = "🔐 Logged In Users"
        else:
            users = list(started_users.find({}))
            title = "🟢 Started Users"

        total = len(users)
        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        paged = users[start:end]

        if not paged:
            return await query.answer("No more records.", show_alert=True)

        text = f"<b>{title}</b> (Page {page}/{(total-1)//ITEMS_PER_PAGE + 1})\n\n"
        for idx, u in enumerate(paged, start=start + 1):
            text += (
                f"{idx}. 👤 <b>Name:</b> {u.get('name','N/A')}\n"
                f"🔗 <b>Username:</b> @{u.get('username','N/A')}\n"
                f"🆔 <b>User ID:</b> <code>{u.get('user_id')}</code>\n\n"
            )

        nav_buttons = []
        if start > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"details:{mode}:{page-1}"))
        if end < total:
            nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"details:{mode}:{page+1}"))

        # Wrap nav_buttons correctly
        reply_markup = InlineKeyboardMarkup([nav_buttons]) if nav_buttons else None

        await query.message.edit_text(text.strip(), parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    @app.on_message(filters.command("details"))
    async def details_command(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return await message.reply("🚫 This command is only for the bot owner.")

        buttons = [
            [
                InlineKeyboardButton("🔐 Logged In", callback_data="details:loggedin:1"),
                InlineKeyboardButton("🟢 Started", callback_data="details:started:1")
            ]
        ]
        await message.reply_text("Select which list to view:", reply_markup=InlineKeyboardMarkup(buttons))

    @app.on_message(filters.command("get"))
    async def get_command(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return await message.reply("🚫 This command is only for the bot owner.")
        try:
            response = await client.ask(
                message.chat.id,
                "✏️ Enter the User ID whose detail you want:",
                filters=filters.text,
                timeout=30
            )
            user_id = int(response.text.strip())  # throws if invalid

            u = started_users.find_one({"user_id": user_id})
            login = logged_in_users.find_one({"user_id": user_id})

            if not u:
                return await response.reply("⚠️ User not found in the database.")

            details = (
                f"🧾 <b>User Details</b>\n\n"
                f"👤 <b>Name:</b> {u.get('name','N/A')}\n"
                f"🔗 <b>Username:</b> @{u.get('username','N/A')}\n"
                f"🆔 <b>User ID:</b> <code>{u.get('user_id')}</code>\n"
                f"📅 <b>Start Time:</b> <code>{u.get('start_time')}</code>\n"
                f"✅ <b>Status:</b> {login.get('status','inactive') if login else 'inactive'}"
            )
            await response.reply(details, parse_mode=ParseMode.HTML)

        except ValueError:
            await response.reply("❌ Invalid user ID. Please enter a number.")
        except asyncio.TimeoutError:
            await message.reply("⏰ Timeout! You didn't send a User ID in time.")
