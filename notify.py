import os
import re
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

    html = res.text

    def find_price(k):
        # หา pattern เช่น 24K ... ฿ 4,917.70
        pattern = rf"{k}\s*.*?฿\s*([\d,]+\.\d+)"
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)

        if match:
            return f"฿ {match.group(1)}"

        return "ไม่พบ"

    prices = {
        "24K": find_price("24K"),
        "22K": find_price("22K"),
        "21K": find_price("21K"),
        "20K": find_price("20K"),
        "18K": find_price("18K"),
        "14K": find_price("14K"),
        "10K": find_price("10K"),
        "9K": find_price("9K"),
    }

    return f"""📊 ราคาทองต่อกรัมวันนี้

24K: {prices["24K"]}
22K: {prices["22K"]}
21K: {prices["21K"]}
20K: {prices["20K"]}
18K: {prices["18K"]}
14K: {prices["14K"]}
10K: {prices["10K"]}
9K: {prices["9K"]}

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
