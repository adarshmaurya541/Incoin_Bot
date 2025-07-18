from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from config import OWNER_ID, MONGO_URI, MONGO_DB_NAME
import asyncio
from pyrogram.enums import ParseMode

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]
started_users = db["started_users"]

last_broadcast_msg = {
    "cancel": False,
    "message_id_map": {},
    "target_message": None,
    "confirmation_received": False,
    "users": [],
    "message": None,
    "confirmation_msg": None
}

async def get_users():
    return list(started_users.distinct("user_id"))

def setup_broadcast_handlers(app):

    async def send_msg(user_id, message):
        try:
            sent = await app.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.id
            )
            return sent.message_id
        except Exception:
            return None

    async def send_broadcast_confirmation(app, message, users, confirm_buttons):
        countdown = 60
        confirmation_msg = await message.reply(
            f"📣 **Broadcast Confirmation**\n\n"
            f"Do you want to send this message to all users?\n\n"
            f"👥 Users to send: `{len(users)}`\n⏳ Time left: `{countdown}` seconds",
            reply_markup=confirm_buttons,
            parse_mode=ParseMode.MARKDOWN
        )

        last_broadcast_msg.update({
            "confirmation_received": False,
            "confirmation_msg": confirmation_msg,
            "users": users,
            "message": message,
            "cancel": False
        })

        for seconds_left in range(countdown - 1, -1, -1):
            await asyncio.sleep(1)
            if last_broadcast_msg.get("confirmation_received", False) or last_broadcast_msg.get("cancel", False):
                return confirmation_msg
            try:
                await confirmation_msg.edit_text(
                    f"📣 **Broadcast Confirmation**\n\n"
                    f"Do you want to send this message to all users?\n\n"
                    f"👥 Users to send: `{len(users)}`\n⏳ Time left: `{seconds_left}` seconds",
                    reply_markup=confirm_buttons,
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                break

        if not last_broadcast_msg.get("confirmation_received", False):
            try:
                await confirmation_msg.edit(
                    "❌ **Broadcast cancelled due to timeout.**",
                    reply_markup=None
                )
            except:
                pass
        return confirmation_msg

    @app.on_message(filters.command("gcast") & filters.user(OWNER_ID))
    async def gcast_command(_, message: Message):
        if not message.reply_to_message:
            return await message.reply_text("⚠️ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ɪᴛ.")

        users = await get_users()
        if not users:
            return await message.reply("😕 ɴᴏ ᴜsᴇʀs ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ.")

        confirm_buttons = InlineKeyboardMarkup([[ 
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_broadcast"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
        ]])

        await send_broadcast_confirmation(app, message, users, confirm_buttons)

    @app.on_callback_query(filters.regex("confirm_broadcast"))
    async def confirm_broadcast_handler(_, query: CallbackQuery):
        if query.from_user.id != OWNER_ID:
            return await query.answer("❌ Not allowed!", show_alert=True)

        if last_broadcast_msg.get("confirmation_received"):
            return await query.answer("✅ Already confirmed.")

        last_broadcast_msg["confirmation_received"] = True
        await query.message.edit("📢 **Broadcast initiated...**", reply_markup=None)

        await broadcast_handler(
            app,
            last_broadcast_msg["message"],
            last_broadcast_msg["users"],
            last_broadcast_msg["confirmation_msg"]
        )

    async def broadcast_handler(app, message, users, confirmation_msg):
        cancel_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 ᴄᴀɴᴄᴇʟ ʙʀᴏᴀᴅᴄᴀsᴛ", callback_data="cancel_broadcast")]
        ])
        status_msg = await confirmation_msg.reply(
            f"📤 ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ...\n\n✅ 0/{len(users)} sᴇɴᴛ | ❌ 0 ғᴀɪʟᴇᴅ",
            reply_markup=cancel_btn
        )

        done, failed = 0, 0
        last_broadcast_msg["cancel"] = False
        last_broadcast_msg["message_id_map"] = {}
        last_broadcast_msg["target_message"] = message.reply_to_message

        for idx, user_id in enumerate(users, 1):
            if last_broadcast_msg.get("cancel", False):
                break

            msg_id = await send_msg(user_id, message.reply_to_message)
            if msg_id:
                done += 1
                last_broadcast_msg["message_id_map"][user_id] = msg_id
            else:
                failed += 1

            if idx % 10 == 0 or idx == len(users):
                try:
                    await status_msg.edit_text(
                        f"📤 ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ...\n\n✅ {done}/{len(users)} sᴇɴᴛ | ❌ {failed} ғᴀɪʟᴇᴅ",
                        reply_markup=cancel_btn
                    )
                except:
                    pass
            await asyncio.sleep(0.1)

        if last_broadcast_msg.get("cancel", False):
            await status_msg.edit_text(
                f"🔴 ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ!\n\n✅ {done} sᴇɴᴛ | ❌ {failed} ғᴀɪʟᴇᴅ"
            )
        else:
            await status_msg.edit_text(
                f"✅ **ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ**\n\n📨 `{done}` sᴇɴᴛ\n⚠️ `{failed}` ғᴀɪʟᴇᴅ",
                parse_mode=ParseMode.MARKDOWN
            )
        last_broadcast_msg["cancel"] = False

    @app.on_message(filters.command("delete_gcast") & filters.user(OWNER_ID))
    async def delete_gcast(_, message: Message):
        msg_map = last_broadcast_msg.get("message_id_map", {})
        if not msg_map:
            return await message.reply("ℹ️ ɴᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ʜɪsᴛᴏʀʏ ғᴏᴜɴᴅ.")

        confirm_btns = InlineKeyboardMarkup([[ 
            InlineKeyboardButton("✅ Confirm Delete", callback_data="confirm_delete"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete")
        ]])
        prompt = await message.reply(
            f"⚠️ Do you want to delete the last broadcast from `{len(msg_map)}` users?\n"
            "This will remove the message from their chats.\n⏳ Auto-cancels in 60 seconds.",
            reply_markup=confirm_btns,
            parse_mode=ParseMode.MARKDOWN
        )

        try:
            cbq = await app.listen(message.chat.id)
            if cbq.from_user.id != OWNER_ID:
                return await cbq.answer("❌ Not allowed.", show_alert=True)
        except asyncio.TimeoutError:
            return await prompt.edit("❌ **Delete operation timed out.**", reply_markup=None)

        if cbq.data == "cancel_delete":
            return await cbq.message.edit("❌ **Deletion cancelled.**", reply_markup=None)

        deleted, failed = 0, 0
        for user_id, msg_id in msg_map.items():
            try:
                await app.delete_messages(user_id, msg_id)
                deleted += 1
            except Exception:
                failed += 1

        await cbq.message.edit(
            f"🗑️ **Broadcast Deletion Completed**\n\n"
            f"✅ `{deleted}` deleted\n❌ `{failed}` failed",
            parse_mode=ParseMode.MARKDOWN
        )
        last_broadcast_msg["message_id_map"] = {}

    @app.on_callback_query(filters.regex("cancel_broadcast"))
    async def cancel_callback(_, query: CallbackQuery):
        if query.from_user.id != OWNER_ID:
            return await query.answer("❌ ʏᴏᴜ'ʀᴇ ɴᴏᴛ ᴀʟʟᴏᴡᴇᴅ ᴛᴏ ᴄᴀɴᴄᴇʟ ᴛʜɪs!", show_alert=True)

        last_broadcast_msg["cancel"] = True
        try:
            await query.message.edit("🔴 **Broadcast cancelled.**", reply_markup=None)
        except:
            pass
