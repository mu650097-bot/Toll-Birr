"""Promo posts for admin / manager / owner.

Flow (inside the bot):  Admin panel -> 📢 ማስታወቂያ  (or /promo)
  1. Staff sends ANY message: text, photo (+caption), video, GIF. Formatting, bold, emojis and custom
     emoji are preserved because the bot COPIES the message (copy_message) instead of rebuilding it.
  2. The bot shows an exact PREVIEW with the "🎮 አሁን ይጫወቱ" Mini App button.
  3. Staff taps ✅ ላክ  (all players) / 📣 ላክ + Channel / 🏷 Button text / ❌ ሰርዝ.
  4. Broadcast runs in the background, throttled (Telegram limit ~30 msg/s), and reports sent / blocked / failed.

Safety: banned and self-excluded players are never sent promos (responsible gambling).
The owner is notified when someone else sends a promo.
"""
import asyncio
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ChatType
from telegram.error import Forbidden, RetryAfter, TelegramError, BadRequest
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, MessageHandler, filters)

DEFAULT_BUTTON = "🎮 አሁን ይጫወቱ"
SEND_PER_SECOND = 20


def register_promo(app, *, is_staff, db, webapp_url, bot_username="", channel_id="", owner_id=0, admin_id=0, save_banner=None):
    """Registers handlers in group -1 so they run BEFORE the bot's old announcement handlers."""

    def staff_ok(uid):
        return bool(uid) and (is_staff(uid) or int(uid) == int(owner_id or 0))

    def play_markup(text, for_channel=False):
        if for_channel:
            if not bot_username:
                return None
            return InlineKeyboardMarkup([[InlineKeyboardButton(text, url=f"https://t.me/{bot_username}?startapp=promo")]])
        return InlineKeyboardMarkup([[InlineKeyboardButton(text, web_app=WebAppInfo(url=webapp_url))]])

    def recipients():
        conn = db(); cur = conn.cursor()
        cur.execute("SELECT user_id, banned, self_excluded_until FROM users")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ids = []
        for r in cur.fetchall():
            if r["banned"]:
                continue
            if r["self_excluded_until"] and str(r["self_excluded_until"]) > now:
                continue
            ids.append(int(r["user_id"]))
        conn.close()
        return ids

    def controls():
        rows = [[InlineKeyboardButton("✅ ለሁሉም ላክ", callback_data="promo_send")]]
        if channel_id:
            rows.append([InlineKeyboardButton("📣 ለሁሉም + Channel", callback_data="promo_send_ch")])
        rows.append([InlineKeyboardButton("🏷 Button ጽሁፍ ቀይር", callback_data="promo_btn"),
                     InlineKeyboardButton("❌ ሰርዝ", callback_data="promo_cancel")])
        return InlineKeyboardMarkup(rows)

    async def start_flow(update, context):
        uid = update.effective_user.id
        if not staff_ok(uid):
            return
        context.user_data.clear()
        context.user_data["waiting_admin_announcement"] = True
        text = ("📢 <b>ማስታወቂያ Post</b>\n\nText፣ 📸 Photo፣ 🎥 Video ወይም GIF ይላኩ (Caption ማከል ይችላሉ)።\n"
                "እኔ ትክክለኛውን Preview እና «አሁን ይጫወቱ» button አሳያለሁ፤ ከዚያ ያረጋግጡ።\n\n❌ ለመሰረዝ /cancel")
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
            raise ApplicationHandlerStop
        else:
            await update.message.reply_text(text, parse_mode="HTML")

    async def show_preview(context, chat_id):
        d = context.user_data.get("promo_draft")
        if not d:
            return
        await context.bot.copy_message(chat_id=chat_id, from_chat_id=d["chat_id"], message_id=d["message_id"],
                                       reply_markup=play_markup(d["button"]))
        n = len(recipients())
        await context.bot.send_message(chat_id=chat_id, parse_mode="HTML", reply_markup=controls(),
                                       text=f"👆 ተጠቃሚዎች የሚያዩት ይህን ነው።\n👥 የሚደርሳቸው: <b>{n}</b> ተጫዋቾች\n(የታገዱ እና Self-exclude ያደረጉ አይካተቱም)")

    async def capture(update, context):
        """Group -1: takes the staff member's next message while the promo flow is waiting."""
        msg = update.effective_message
        user = update.effective_user
        if not msg or not user or update.effective_chat.type != ChatType.PRIVATE:
            return
        ud = context.user_data
        if ud.get("promo_wait_button") and staff_ok(user.id) and msg.text and not msg.text.startswith("/"):
            ud.pop("promo_wait_button", None)
            ud["promo_draft"]["button"] = msg.text.strip()[:40] or DEFAULT_BUTTON
            await show_preview(context, update.effective_chat.id)
            raise ApplicationHandlerStop
        if not ud.get("waiting_admin_announcement") or not staff_ok(user.id):
            return
        if msg.text and msg.text.startswith("/"):
            return
        ud["waiting_admin_announcement"] = False
        ud["promo_draft"] = {"chat_id": msg.chat_id, "message_id": msg.message_id, "button": DEFAULT_BUTTON,
                             "photo": msg.photo[-1].file_id if msg.photo else None}
        await show_preview(context, update.effective_chat.id)
        raise ApplicationHandlerStop

    async def broadcast(app_, draft, ids, report_chat, with_channel, sender_id):
        bot = app_.bot
        sent = blocked = failed = 0
        markup = play_markup(draft["button"])
        delay = 1.0 / SEND_PER_SECOND
        for uid in ids:
            while True:
                try:
                    await bot.copy_message(chat_id=uid, from_chat_id=draft["chat_id"], message_id=draft["message_id"], reply_markup=markup)
                    sent += 1
                    break
                except RetryAfter as e:
                    await asyncio.sleep(float(e.retry_after) + 1)
                except Forbidden:
                    blocked += 1
                    break
                except (BadRequest, TelegramError) as e:
                    failed += 1
                    logging.warning("promo to %s failed: %s", uid, e)
                    break
            await asyncio.sleep(delay)
        ch_note = ""
        if with_channel and channel_id:
            try:
                await bot.copy_message(chat_id=channel_id, from_chat_id=draft["chat_id"], message_id=draft["message_id"],
                                       reply_markup=play_markup(draft["button"], for_channel=True))
                ch_note = "\n📣 Channel ላይ ተለጥፏል"
            except Exception as e:
                ch_note = f"\n⚠️ Channel post አልተሳካም: {e}"
        banner_note = ""
        if draft.get("photo") and save_banner:
            try:
                if await save_banner(app_, draft["photo"]):
                    banner_note = "\n🖼 App home ላይ banner ሆኖ ተለጥፏል"
            except Exception:
                pass
        report = (f"📢 ማስታወቂያ ተልኳል\n\n👥 ጠቅላላ: {len(ids)}\n✅ ደርሷል: {sent}\n🚫 Bot ያቆሙ: {blocked}\n❌ አልተሳካም: {failed}"
                  f"{ch_note}{banner_note}")
        await bot.send_message(chat_id=report_chat, text=report)
        if owner_id and int(owner_id) != int(sender_id):
            try:
                await bot.send_message(chat_id=owner_id, text=f"ℹ️ Staff {sender_id} ማስታወቂያ ልኳል — ደርሷል {sent}/{len(ids)}")
            except Exception:
                pass

    async def on_callback(update, context):
        q = update.callback_query
        uid = q.from_user.id
        if not staff_ok(uid):
            await q.answer()
            raise ApplicationHandlerStop
        data = q.data
        d = context.user_data.get("promo_draft")
        if data == "promo_cancel":
            context.user_data.pop("promo_draft", None); context.user_data.pop("promo_wait_button", None)
            await q.answer("ተሰርዟል")
            await q.edit_message_text("❌ ማስታወቂያው ተሰርዟል።")
        elif data == "promo_btn":
            if not d:
                await q.answer("Draft የለም", show_alert=True)
            else:
                context.user_data["promo_wait_button"] = True
                await q.answer()
                await context.bot.send_message(chat_id=q.message.chat_id, text="🏷 አዲስ የ Button ጽሁፍ ይጻፉ (ለምሳሌ: 🎰 777 ይጫወቱ)")
        elif data in ("promo_send", "promo_send_ch"):
            if not d:
                await q.answer("Draft የለም — እንደገና ይጀምሩ", show_alert=True)
            else:
                ids = recipients()
                context.user_data.pop("promo_draft", None)
                await q.answer("መላክ ተጀምሯል…")
                await q.edit_message_text(f"⏳ በመላክ ላይ… {len(ids)} ተጫዋቾች (ሲጨርስ ሪፖርት እልካለሁ)")
                context.application.create_task(broadcast(context.application, d, ids, q.message.chat_id, data == "promo_send_ch", uid))
        raise ApplicationHandlerStop

    app.add_handler(CommandHandler("promo", start_flow), group=-1)
    app.add_handler(CallbackQueryHandler(start_flow, pattern=r"^admin_announcement$"), group=-1)
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^promo_"), group=-1)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, capture), group=-1)
