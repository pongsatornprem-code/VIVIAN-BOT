import os
import json
import re
import html as html_lib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import anthropic
import gspread

from flask import Flask, request, abort
from google.oauth2.service_account import Credentials

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError


app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = "คุณคือเลขาส่วนตัว ตอบภาษาไทย กระชับ ชัดเจน"


def thai_now():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S TH")


def get_gold_price():
    url = "https://www.talupa.com/gold/Thailand"

    res = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )

    raw_html = html_lib.unescape(res.text)
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = re.sub(r"\s+", " ", text)

    def find_price(k):
        pattern = rf"ราคาทองต่อกรัม\s*{k}\s*฿\s*([\d,]+\.\d+)"
        match = re.search(pattern, text, re.IGNORECASE)
        return f"฿ {match.group(1)}" if match else "ไม่พบ"

    return f"""📊 ราคาทองต่อกรัมล่าสุด
เวลาอัปเดต: {thai_now()}

24K: {find_price("24K")}
22K: {find_price("22K")}
21K: {find_price("21K")}
20K: {find_price("20K")}
18K: {find_price("18K")}
14K: {find_price("14K")}
10K: {find_price("10K")}
9K: {find_price("9K")}

อ้างอิง: Talupa
{url}
"""


def save_note_to_sheet(text):
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("Missing GOOGLE_SHEET_ID")

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")

    service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.worksheet("Notes")

    worksheet.append_row([
        text,
        thai_now()
    ])


def ask_claude(user_msg):
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_msg}
        ]
    )
    return response.content[0].text


@app.route("/", methods=["GET"])
def home():
    return "Bot running", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()

    try:
        if user_msg == "env":
            reply_text = f"""ENV CHECK
GOOGLE_SHEET_ID: {bool(GOOGLE_SHEET_ID)}
JSON: {bool(GOOGLE_SERVICE_ACCOUNT_JSON)}
เวลาไทย: {thai_now()}
"""

        elif user_msg.lower() == "userid":
            reply_text = event.source.user_id

        elif "ราคาทอง" in user_msg:
            reply_text = get_gold_price()

        elif "จด" in user_msg or "บันทึก" in user_msg:
            save_note_to_sheet(user_msg)
            reply_text = f"บันทึกเรียบร้อยครับ\nเวลาไทย: {thai_now()}"

        else:
            reply_text = ask_claude(user_msg)

    except Exception as e:
        reply_text = f"❌ ERROR:\n{type(e).__name__}\n{str(e)}"

    with ApiClient(line_config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
