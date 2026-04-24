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


SYSTEM_PROMPT = """คุณคือเลขาส่วนตัวของเจ้าของแบรนด์จิวเวลรี่ VIVIAN.GEMS

หน้าที่:
- ตอบภาษาไทย กระชับ ชัดเจน
- ช่วยจัดระบบงาน ออเดอร์ ลูกค้า คอนเทนต์ การผลิต และนัดหมาย
- ถ้าผู้ใช้สั่งงาน ให้แปลงเป็น action ที่ทำต่อได้
- ถ้าข้อมูลไม่ครบ ให้ถามกลับเฉพาะจุดที่จำเป็น
- น้ำเสียงมืออาชีพ เป็นกันเอง เหมือนเลขาส่วนตัว
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

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes
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
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": user_msg
            }
        ]
    )

    return response.content[0].text


# =========================
# ROUTES
# =========================

@app.route("/", methods=["GET"])
def home():
    return "VIVIAN Secretary Bot is running", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

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
# LINE MESSAGE HANDLER
# =========================

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text.strip()

    print("USER_ID:", event.source.user_id)
    print("USER_MSG:", user_msg)

    try:
        if user_msg.startswith("จด") or "จดไว้" in user_msg or "บันทึก" in user_msg:
            save_note_to_sheet(user_msg)
            reply_text = "บันทึกเรียบร้อยครับ"

        else:
            reply_text = ask_claude(user_msg)

    except Exception:
        traceback.print_exc()
        reply_text = "ขออภัยครับ ระบบเลขามีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้ง"

    try:
        with ApiClient(line_config) as api_client:
            line_bot = MessagingApi(api_client)
            line_bot.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(text=reply_text)
                    ]
                )
            )

    except Exception:
        traceback.print_exc()


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
