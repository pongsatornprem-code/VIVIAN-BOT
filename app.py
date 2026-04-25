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

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")

handler = WebhookHandler(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """
คุณคือเลขาส่วนตัวของเจ้าของแบรนด์จิวเวลรี่ VIVIAN.GEMS
ตอบภาษาไทย กระชับ ชัดเจน เป็นมืออาชีพ
ช่วยจัดการลูกค้า งาน follow-up งานผลิต และการคำนวณต้นทุนทอง
"""


def thai_now():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")


def thai_today():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d")


def thai_now_minute():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M")


def get_sheet():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID)


def is_allowed(user_id):
    if user_id == ADMIN_USER_ID:
        return True

    sheet = get_sheet()
    ws = sheet.worksheet("Users")
    rows = ws.get_all_records()

    for row in rows:
        if row.get("UserID") == user_id:
            return row.get("Status") == "approved"

    ws.append_row([user_id, "user", "pending"])
    return False


def save_note(text):
    ws = get_sheet().worksheet("Notes")
    ws.append_row([text, thai_now()])


def get_notes(limit=5):
    ws = get_sheet().worksheet("Notes")
    rows = ws.get_all_values()

    if len(rows) <= 1:
        return "ยังไม่มีบันทึกครับ"

    latest = rows[1:][-limit:]
    reply = "📒 บันทึกล่าสุด\n\n"

    for row in latest:
        note = row[0] if len(row) > 0 else "-"
        time = row[1] if len(row) > 1 else "-"
        reply += f"- {note}\n  เวลา: {time}\n"

    return reply


def add_task(msg):
    # ตัวอย่าง: งาน โทรหาลูกค้าคุณแพร 2026-04-30 14:00
    match = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", msg)

    if match:
        due = match.group(0)
        task = msg.replace("งาน", "", 1).replace(due, "").strip()
    else:
        due = thai_today() + " 09:00"
        task = msg.replace("งาน", "", 1).strip()

    ws = get_sheet().worksheet("Tasks")
    ws.append_row([task, due, "pending", thai_now()])

    return f"""เพิ่มงานเรียบร้อยครับ

งาน: {task}
เวลาเตือน: {due}
"""


def today_tasks():
    ws = get_sheet().worksheet("Tasks")
    rows = ws.get_all_records()
    today = thai_today()

    tasks = [
        row for row in rows
        if str(row.get("DueDateTime", "")).startswith(today)
        and str(row.get("Status", "")).lower() != "done"
    ]

    if not tasks:
        return "วันนี้ยังไม่มีงานค้างครับ"

    reply = f"✅ งานวันนี้ ({today})\n\n"
    for i, row in enumerate(tasks, 1):
        reply += f"{i}. {row.get('Task')} | {row.get('DueDateTime')}\n"

    return reply


def add_customer(msg):
    # ตัวอย่าง:
    # ลูกค้า คุณแพร สนใจแหวนหยก งบ30000 follow2026-04-30 18:00

    name_match = re.search(r"ลูกค้า\s+(\S+)", msg)
    budget_match = re.search(r"งบ\s*([\d,]+)", msg)
    follow_match = re.search(r"follow\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", msg)

    name = name_match.group(1) if name_match else "-"
    budget = budget_match.group(1) if budget_match else "-"
    follow_time = follow_match.group(1) if follow_match else "-"

    interest = msg
    interest = interest.replace("ลูกค้า", "", 1)
    interest = interest.replace(name, "", 1)
    interest = re.sub(r"งบ\s*[\d,]+", "", interest)
    interest = re.sub(r"follow\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", "", interest)
    interest = interest.strip()

    ws = get_sheet().worksheet("Customers")
    ws.append_row([
        name,
        interest,
        budget,
        "new",
        follow_time,
        msg,
        thai_now()
    ])

    return f"""บันทึกลูกค้าเรียบร้อยครับ

ชื่อ: {name}
สนใจ: {interest}
งบ: {budget}
Follow-up: {follow_time}
"""


def search_customer(keyword):
    ws = get_sheet().worksheet("Customers")
    rows = ws.get_all_records()

    found = []
    for row in rows:
        text = " ".join(str(v) for v in row.values())
        if keyword in text:
            found.append(row)

    if not found:
        return f"ไม่พบข้อมูลลูกค้า: {keyword}"

    reply = f"🔎 ผลค้นหา: {keyword}\n\n"
    for row in found[-5:]:
        reply += f"""ชื่อ: {row.get("Name")}
สนใจ: {row.get("Interest")}
งบ: {row.get("Budget")}
สถานะ: {row.get("Status")}
Follow-up: {row.get("FollowUpDateTime")}

"""

    return reply


def follow_today():
    ws = get_sheet().worksheet("Customers")
    rows = ws.get_all_records()
    today = thai_today()

    found = [
        row for row in rows
        if str(row.get("FollowUpDateTime", "")).startswith(today)
    ]

    if not found:
        return "วันนี้ยังไม่มีลูกค้าที่ต้อง follow-up ครับ"

    reply = f"🔔 Follow-up วันนี้ ({today})\n\n"
    for row in found:
        reply += f"- {row.get('Name')} | {row.get('Interest')} | งบ {row.get('Budget')} | {row.get('FollowUpDateTime')}\n"

    return reply


def get_gold_text():
    url = "https://www.talupa.com/gold/Thailand"

    res = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    res.raise_for_status()

    raw = html_lib.unescape(res.text)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text)

    def find_price(k):
        pattern = rf"ราคาทองต่อกรัม\s*{k}\s*฿\s*([\d,]+\.\d+)"
        match = re.search(pattern, text, re.IGNORECASE)
        return f"฿ {match.group(1)}" if match else "ไม่พบ"

    return f"""📊 ราคาทองต่อกรัมล่าสุด
เวลาไทย: {thai_now()}

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


def get_gold_number(karat):
    gold_text = get_gold_text()
    match = re.search(rf"{karat}K:\s*฿\s*([\d,]+\.\d+)", gold_text)

    if not match:
        return None

    return float(match.group(1).replace(",", ""))


def calculate_cost(msg):
    # ตัวอย่าง: คำนวณ 18K 3.2g ค่าแรง 6500 margin 40

    karat_match = re.search(r"(\d{1,2})K", msg, re.IGNORECASE)
    gram_match = re.search(r"([\d.]+)\s*g", msg, re.IGNORECASE)
    labor_match = re.search(r"ค่าแรง\s*([\d,]+)", msg)
    margin_match = re.search(r"margin\s*([\d.]+)", msg, re.IGNORECASE)

    if not karat_match or not gram_match:
        return "พิมพ์แบบนี้ครับ:\nคำนวณ 18K 3.2g ค่าแรง 6500 margin 40"

    karat = karat_match.group(1)
    gram = float(gram_match.group(1))
    labor = float(labor_match.group(1).replace(",", "")) if labor_match else 0
    margin = float(margin_match.group(1)) if margin_match else 40

    price_per_gram = get_gold_number(karat)

    if not price_per_gram:
        return f"ไม่พบราคาทอง {karat}K ครับ"

    gold_cost = price_per_gram * gram
    total_cost = gold_cost + labor
    sell_price = total_cost / (1 - margin / 100)

    return f"""💰 คำนวณต้นทุน

ทอง: {karat}K
น้ำหนัก: {gram}g
ราคาทอง/กรัม: ฿ {price_per_gram:,.2f}

ต้นทุนทอง: ฿ {gold_cost:,.2f}
ค่าแรง: ฿ {labor:,.2f}
ต้นทุนรวม: ฿ {total_cost:,.2f}

ราคาขายแนะนำ margin {margin}%:
฿ {sell_price:,.2f}
"""


def ask_ai(msg):
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": msg}
        ]
    )
    return response.content[0].text


@app.route("/", methods=["GET"])
def home():
    return "VIVIAN Operation Bot running", 200


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
    msg = event.message.text.strip()
    user_id = event.source.user_id

    try:
        if msg.lower() == "userid":
            reply = user_id

        elif msg == "env":
            reply = f"""ENV CHECK

GOOGLE_SHEET_ID: {bool(GOOGLE_SHEET_ID)}
GOOGLE_SERVICE_ACCOUNT_JSON: {bool(GOOGLE_SERVICE_ACCOUNT_JSON)}
ADMIN_USER_ID: {bool(ADMIN_USER_ID)}
เวลาไทย: {thai_now()}
"""

        elif not is_allowed(user_id):
            reply = f"""บัญชีนี้ยังไม่มีสิทธิ์ใช้งานครับ

UserID:
{user_id}

ให้แอดมินเพิ่มใน Google Sheet tab Users
และตั้ง Status เป็น approved
"""

        elif msg == "help":
            reply = """คำสั่งที่ใช้ได้

userid
env

ราคาทอง
จด ...
ดูบันทึก

งาน โทรหาลูกค้า 2026-04-30 14:00
งานวันนี้

ลูกค้า คุณแพร สนใจแหวนหยก งบ30000 follow2026-04-30 18:00
หา คุณแพร
follow วันนี้

คำนวณ 18K 3.2g ค่าแรง 6500 margin 40
"""

        elif "ราคาทอง" in msg:
            reply = get_gold_text()

        elif msg.startswith("จด") or msg.startswith("บันทึก"):
            save_note(msg)
            reply = f"บันทึกเรียบร้อยครับ\nเวลาไทย: {thai_now()}"

        elif msg.startswith("ดูบันทึก"):
            reply = get_notes()

        elif msg.startswith("งาน "):
            reply = add_task(msg)

        elif msg == "งานวันนี้":
            reply = today_tasks()

        elif msg.startswith("ลูกค้า"):
            reply = add_customer(msg)

        elif msg.startswith("หา "):
            keyword = msg.replace("หา", "", 1).strip()
            reply = search_customer(keyword)

        elif msg == "follow วันนี้":
            reply = follow_today()

        elif msg.startswith("คำนวณ"):
            reply = calculate_cost(msg)

        else:
            reply = ask_ai(msg)

    except Exception as e:
        reply = f"❌ ERROR:\n{type(e).__name__}\n{str(e)}"

    with ApiClient(line_config) as api_client:
        line_bot = MessagingApi(api_client)
        line_bot.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply)]
            )
        )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000))
    )
