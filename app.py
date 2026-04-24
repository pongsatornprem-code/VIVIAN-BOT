import os
import traceback
import anthropic

from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError


app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

if not LINE_CHANNEL_SECRET:
    raise RuntimeError("Missing LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

if not ANTHROPIC_API_KEY:
    raise RuntimeError("Missing ANTHROPIC_API_KEY")

print("ANTHROPIC KEY START:", ANTHROPIC_API_KEY[:7])

handler = WebhookHandler(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """คุณคือเลขาส่วนตัวที่ฉลาดและเป็นมิตร
หน้าที่:
- ตอบคำถามทั่วไปอย่างกระชับ ใช้ภาษาไทย
- ถ้ามีเอกสารหรือข้อความยาวส่งมา ให้สรุปเป็นข้อๆ
- ให้คำแนะนำที่เป็นประโยชน์ ตรงประเด็น"""


@app.route("/", methods=["GET"])
def home():
    return "LINE Claude Bot is running", 200


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


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    print("USER_ID:", event.source.user_id)
    user_msg = event.message.text

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_msg}
            ]
        )

        reply_text = response.content[0].text

    except Exception:
        traceback.print_exc()
        reply_text = "ขออภัยครับ ตอนนี้ระบบ AI มีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้ง"

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


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
