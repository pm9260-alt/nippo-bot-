import os
import re
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, request, abort

app = Flask(__name__)

# Renderの環境変数から読み込む（コードに直書きしない）
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

JST = timezone(timedelta(hours=9))
WEEK = ["月", "火", "水", "木", "金", "土", "日"]  # 月曜=0

# ユーザーごとの「今日の日報」を一時的に覚えておく（メモリ上）
records = {}


@app.route("/", methods=["GET"])
def health():
    return "OK", 200


@app.route("/callback", methods=["POST"])
def callback():
    # 署名検証（LINE以外からの偽リクエストを弾く）
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()
    mac = hmac.new(CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, base64.b64encode(mac).decode("utf-8")):
        abort(400)

    for event in json.loads(body).get("events", []):
        etype = event.get("type")
        reply_token = event.get("replyToken")

        # 友だち追加 → 使い方を送る
        if etype == "follow":
            reply(reply_token, usage_text())
            continue

        # テキスト以外（スタンプ・画像など）は無視
        if etype != "message" or event["message"].get("type") != "text":
            continue

        user_id = event.get("source", {}).get("userId", "default")
        text = event["message"]["text"].strip()
        handle_text(reply_token, user_id, text)

    return "OK", 200


def handle_text(reply_token, user_id, text):
    # 使い方
    if re.search(r"使い方|ヘルプ|help", text, re.IGNORECASE):
        reply(reply_token, usage_text())
        return

    rec = today_record(user_id)

    # リセット（今日の分を消す）
    if re.search(r"リセット|クリア|reset", text, re.IGNORECASE):
        rec.update(kiji="", uber="", rocket="", menu="")
        reply(reply_token, "今日の日報をリセットしました。\n\n" + build_report(rec))
        return

    nums = re.findall(r"\d+", text)

    # リッチメニュー「生地数」など、数字が無いときは入力を促す
    if "生地数" in text and not nums:
        reply(reply_token, "生地数を数字で送ってください。\n例）40")
        return

    if len(nums) == 4:
        # 生地数 → UberEats → RocketNow → menu の順
        rec["kiji"], rec["uber"], rec["rocket"], rec["menu"] = nums
    elif len(nums) == 3:
        # UberEats → RocketNow → menu（生地数は前の値を維持）
        rec["uber"], rec["rocket"], rec["menu"] = nums
    elif len(nums) == 1:
        # 数字1つ = 生地数
        rec["kiji"] = nums[0]
    else:
        reply(
            reply_token,
            "数字の送り方\n"
            "・4つ → 生地数 / UberEats / RocketNow / menu\n"
            "・3つ → UberEats / RocketNow / menu\n"
            "・1つ → 生地数だけ\n\n"
            "例）40 12 5 8",
        )
        return

    reply(reply_token, build_report(rec))


def today_record(user_id):
    today = datetime.now(JST).strftime("%Y-%m-%d")
    rec = records.get(user_id)
    if rec is None or rec.get("date") != today:
        rec = {"date": today, "kiji": "", "uber": "", "rocket": "", "menu": ""}
        records[user_id] = rec
    return rec


def build_report(rec):
    now = datetime.now(JST)
    week = WEEK[now.weekday()]
    return (
        f"{now.month}月{now.day}日({week})\n"
        f"生地数 : {rec['kiji']}\n"
        f"UberEats : {rec['uber']}\n"
        f"RocketNow : {rec['rocket']}\n"
        f"menu : {rec['menu']}"
    )


def usage_text():
    now = datetime.now(JST)
    week = WEEK[now.weekday()]
    sample = (
        f"{now.month}月{now.day}日({week})\n"
        f"生地数 : 40\n"
        f"UberEats : 12\n"
        f"RocketNow : 5\n"
        f"menu : 8"
    )
    return (
        "追加ありがとうございます！\n"
        "数字を送るだけで日報を作ります。\n\n"
        "▼ スペースでも改行でもOK\n"
        "・4つの数字を入れると
        "生地数→UberEats→RocketNow→menu の順\n"
        "　例）40 12 5 8\n"
        "▼ こう返します\n"
        f"{sample}\n\n"
        "・日付と曜日は自動です\n"
        "・同じ日なら、生地数を後から足しても前の数字は残ります\n"
        "・「リセット」で今日の分を消せます\n"
        "・「使い方」で説明を再表示します"
    )


def reply(reply_token, text):
    if not reply_token:
        return
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        },
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
