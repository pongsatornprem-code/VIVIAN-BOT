import os
import requests

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
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()

        text = response.text

        return f"ดึงข้อมูล Talupa ได้แล้วครับ\n\nความยาวข้อมูล: {len(text)} ตัวอักษร\n\nเช็กราคาได้ที่:\n{url}"

    except Exception as e:
        return f"ดึงราคาทองจาก Talupa ไม่สำเร็จ: {e}"


def push_line_message(text):
    config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

    with ApiClient(config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.push_message(
            PushMessageRequest(
                to=LINE_USER_ID,
                messages=[TextMessage(text=text)]
            )
        )


if __name__ == "__main__":
    gold_data = get_gold_price_from_talupa()

    message = f"""แจ้งเตือนราคาทองประจำวัน

{gold_data}
"""

    push_line_message(message)
