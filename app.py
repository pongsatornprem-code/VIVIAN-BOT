import os, anthropic
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

app = Flask(__name__)
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])
line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """คุณคือเลขาส่วนตัวที่ฉลาดและเป็นมิตร
หน้าที่:
- ตอบคำถามทั่วไปอย่างกระชับ ใช้ภาษาไทย
- ถ้ามีเอกสารหรือข้อความยาวส่งมา ให้สรุปเป็นข้อๆ
- ให้คำแนะนำที่เป็นประโยชน์ ตรงประเด็น"""

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_msg = event.message.text
    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )
    reply_text = response.content[0].text
    with ApiClient(line_config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.reply_message(ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        ))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
