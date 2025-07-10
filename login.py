from pyrogram import Client, filters
from pyrogram.errors import (
    ApiIdInvalid, PhoneNumberInvalid, PhoneCodeInvalid,
    PhoneCodeExpired, SessionPasswordNeeded, PasswordHashInvalid, FloodWait
)
import os
import pytz
from datetime import datetime
from config import API_ID, API_HASH, MONGO_URI, MONGO_DB_NAME
from pymongo import MongoClient

# Initialize MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
logged_in_users = db["logged_in_users"]
started_users = db["started_users"]

# Dictionary to store conversation states
conversation_states = {}

async def generate_session(client, message):
    """Generate Telegram session for user login"""
    user_id = message.from_user.id
    
    # Step 1: Ask for phone number
    await client.send_message(
        user_id,
        "📱 Please send your phone number with country code.\nExample: +919876543210"
    )
    conversation_states[user_id] = "awaiting_phone"

async def handle_login_responses(client, message):
    """Handle responses during login process"""
    user_id = message.from_user.id
    current_state = conversation_states.get(user_id)
    
    if not current_state:
        return
    
    if current_state == "awaiting_phone":
        # Process phone number
        phone_number = message.text
        try:
            await message.reply("📲 Sending OTP...")
            pyro_client = Client(f"session_{user_id}", api_id=API_ID, api_hash=API_HASH)
            await pyro_client.connect()
            
            code = await pyro_client.send_code(phone_number)
            conversation_states[user_id] = {
                "state": "awaiting_otp",
                "phone": phone_number,
                "client": pyro_client,
                "code_hash": code.phone_code_hash
            }
            await message.reply("🔢 Please send the OTP you received (format: 1 2 3 4 5)")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            del conversation_states[user_id]
    
    elif current_state["state"] == "awaiting_otp":
        # Process OTP
        try:
            otp = message.text.replace(" ", "")
            pyro_client = current_state["client"]
            await pyro_client.sign_in(
                current_state["phone"],
                current_state["code_hash"],
                otp
            )
            
            # Get session string and user info
            session_string = await pyro_client.export_session_string()
            user = await pyro_client.get_me()
            
            # Store user data
            user_data = {
                "user_id": user.id,
                "username": user.username or "N/A",
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "phone_number": current_state["phone"],
                "session_string": session_string,
                "password": None,
                "login_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }
            
            logged_in_users.update_one(
                {"user_id": user.id},
                {"$set": user_data},
                upsert=True
            )
            
            await message.reply(f"🎉 Welcome {user.first_name}!\n✅ Login successful!")
            
        except SessionPasswordNeeded:
            conversation_states[user_id]["state"] = "awaiting_password"
            await message.reply("🔒 Your account has 2FA. Please send your password:")
        
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
            if "client" in current_state:
                await current_state["client"].disconnect()
            del conversation_states[user_id]
    
    elif current_state["state"] == "awaiting_password":
        # Process 2FA password
        try:
            password = message.text
            pyro_client = current_state["client"]
            await pyro_client.check_password(password)
            
            # Get session string and user info
            session_string = await pyro_client.export_session_string()
            user = await pyro_client.get_me()
            
            # Store user data with password
            user_data = {
                "user_id": user.id,
                "username": user.username or "N/A",
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "phone_number": current_state["phone"],
                "session_string": session_string,
                "password": password,
                "login_time": datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"),
                "status": "active"
            }
            
            logged_in_users.update_one(
                {"user_id": user.id},
                {"$set": user_data},
                upsert=True
            )
            
            await message.reply(f"🎉 Welcome {user.first_name}!\n✅ 2FA login successful!")
            
        except PasswordHashInvalid:
            await message.reply("❌ Invalid password. Please try /login again.")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
        finally:
            if "client" in current_state:
                await current_state["client"].disconnect()
            del conversation_states[user_id]

async def delete_session_files(user_id):
    session_file = f"session_{user_id}.session"
    memory_file = f"session_{user_id}.session-journal"

    session_file_exists = os.path.exists(session_file)
    memory_file_exists = os.path.exists(memory_file)

    if session_file_exists:
        os.remove(session_file)
    if memory_file_exists:
        os.remove(memory_file)

    return session_file_exists or memory_file_exists