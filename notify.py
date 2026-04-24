import os
import requests
from bs4 import BeautifulSoup

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)


LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")


def get_gold_price_from_talupa():
    url = "https://www.talupa.com/gold/Thailand"

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text("\n", strip=True)

        # ดึงแบบกว้างก่อน เพื่อเช็คว่าเว็บตอบข้อมูลกลับมาจริง
        lines = [line for line in text.split("\n") if "บาท" in line or "ทอง" in line]

        if lines:
            return "\n".join(lines[:10])

        return "ดึงข้อมูลจาก Talupa ได้ แต่ยังอ่านราคาทองไม่เจอ"

    except Exception as e:
        return f"ดึงราคาทองจาก Talupa ไม่สำเร็จ: {e}"


def push_line_message(text):
    config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

    with ApiClient(config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.push_message(
            PushMessageRequest(
                to=LINE_USER_ID,
                messages=[
                    TextMessage(text=text)
                ]
            )
        )


if __name__ == "__main__":
    gold_data = get_gold_price_from_talupa()

    message = f"""สรุปราคาทองประจำวัน

{gold_data}

ที่มา: Talupa
"""

    push_line_message(message)
