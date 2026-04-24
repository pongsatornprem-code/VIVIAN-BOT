import os
import json
import re
import html as html_lib
import traceback
from datetime import datetime

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

# =========================
# ENV
# =========================
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = "คุณคือเลขาส่วนตัว ตอบภาษาไทย กระชับ ชัดเจน"


# =========================
# GOLD PRICE
# =========================
def get_gold_price():
    url = "https://www.talupa.com/gold/Thailand"

    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    raw_html = html_lib.unescape(res.text)

    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = re.sub(r"\s+", " ", text)

    def find_price(k):
        pattern = rf"ราคาทองต่อกรัม\s*{k}\s*฿\s*([\d,]+\.\d+)"
        match = re.search(pattern, text, re.IGNORECASE)
        return f"฿ {match.group(1)}" if match else "ไม่พบ"

    return f"""📊 ราคาทองล่าสุด

24K: {find_price("24K")}
22K: {find_price("22K")}
18K: {find_price("18K")}
14K: {find_price("14K")}
10K: {find_price("10K")}
"""


# =========================
# GOOGLE SHEET
# =========================
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
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ])


# =========================
# CLAUDE
# =========================
def ask_claude(user_msg):
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )
    return response.content[0].text


# =========================
# ROUTE
# =========================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


# =========================
# LINE
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()

    try:
        # 🔥 เช็ค ENV
        if user_msg == "env":
            reply_text = f"""
GOOGLE_SHEET_ID: {bool(GOOGLE_SHEET_ID)}
JSON: {bool(GOOGLE_SERVICE_ACCOUNT_JSON)}
"""

        elif user_msg == "userid":
            reply_text = event.source.user_id

        elif "ราคาทอง" in user_msg:
            reply_text = get_gold_price()

        elif "จด" in user_msg:
            save_note_to_sheet(user_msg)
            reply_text = "บันทึกเรียบร้อย"

        else:
            reply_text = ask_claude(user_msg)

    except Exception as e:
        reply_text = f"❌ ERROR:\n{type(e).__name__}\n{str(e)}"

    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
