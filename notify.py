import os
import re
import html as html_lib
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


def get_gold_price():
    url = "https://www.talupa.com/gold/Thailand"

    res = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    res.raise_for_status()

    html = html_lib.unescape(res.text)

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    def find_price(k):
        pattern = rf"ราคาทองต่อกรัม\s*{k}\s*฿\s*([\d,]+\.\d+)"
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return f"฿ {match.group(1)}"

        return "ไม่พบ"

    return f"""📊 แจ้งเตือนราคาทองต่อกรัมประจำวัน

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


def push_line_message(text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

    if not LINE_USER_ID:
        raise RuntimeError("Missing LINE_USER_ID")

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
    message = get_gold_price()
    push_line_message(message)
