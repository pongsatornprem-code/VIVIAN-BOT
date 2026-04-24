import os
import json
import traceback
from datetime import datetime

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

if not LINE_CHANNEL_SECRET:
    raise RuntimeError("Missing LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

if not ANTHROPIC_API_KEY:
    raise RuntimeError("Missing ANTHROPIC_API_KEY")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = "คุณคือเลขาส่วนตัว ตอบภาษาไทย กระชับ ชัดเจน"


# =========================
# GOOGLE SHEET FUNCTION
# =========================
def save_note_to_sheet(text):
    print("👉 START save_note_to_sheet")

    if not GOOGLE_SHEET_ID:
        raise RuntimeError("Missing GOOGLE_SHEET_ID")

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")

    service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes
    )

    client = gspread.authorize(creds)

    print("👉 Open sheet")
    sheet = client.open_by_key(GOOGLE_SHEET_ID)

    print("👉 Open worksheet: Notes")
    worksheet = sheet.worksheet("Notes")  # ต้องชื่อ Notes เท่านั้น

    print("👉 Append row")
    worksheet.append_row([
        text,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ])

    print("✅ SAVE SUCCESS")


# =========================
# CLAUDE
# =========================
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


# =========================
# ROUTES
# =========================
@app.route("/", methods=["GET"])
def home():
    return "Bot running", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    print("BODY:", body)

    if not signature:
        abort(400)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception:
        traceback.print_exc()
        return "ERROR", 500

    return "OK", 200


# =========================
# LINE HANDLER
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()

    print("USER_ID:", event.source.user_id)
    print("MESSAGE:", user_msg)

    try:
        # 🔥 ดู USER ID
        if user_msg == "userid":
            reply_text = f"USER_ID:\n{event.source.user_id}"

        # 🔥 บันทึกลง Google Sheet
        elif "จด" in user_msg:
            save_note_to_sheet(user_msg)
            reply_text = "บันทึกลง Google Sheet เรียบร้อยครับ"

        # 🔥 ปกติใช้ AI
        else:
            reply_text = ask_claude(user_msg)

    except Exception:
        traceback.print_exc()
        reply_text = "❌ บันทึกไม่สำเร็จ หรือระบบมีปัญหา"

    with ApiClient(line_config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
