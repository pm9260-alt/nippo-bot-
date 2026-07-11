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


# Renderのヘルスチェック＆UptimeRobotのping先
@app.route("/", methods=["GET"])
def health():
    return "OK", 200


# LINEからのメッセージ・友だち追加はここに届く
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

        # ① 友だち追加された瞬間 → 使い方を送る
        if etype == "follow":
            reply(reply_token, usage_text())
            continue

        # ② テキスト以外（スタンプ・画像など）は無視
        if etype != "message" or event["message"].get("type") != "text":
            continue

        text = event["message"]["text"]

        # ③「使い方」「ヘルプ」なら、いつでも使い方を再表示
        if re.search(r"使い方|ヘルプ|help", text, re.IGNORECASE):
            reply(reply_token, usage_text())
            continue

        # ④ 数字を3つ抜き出して日報にする
        nums = re.findall(r"\d+", text)
        if len(nums) < 3:
            reply(reply_token, "数字を3つ送ってください。\n例）12 5 8\n\n（「使い方」と送ると説明を表示します）")
        else:
            reply(reply_token, build_report(nums[0], nums[1], nums[2]))

    return "OK", 200


# 友だち追加時などに送る使い方メッセージ
def usage_text():
    sample = build_report("12", "5", "8")
    return (
        "追加ありがとうございます！\n"
        "このアカウントは、数字を3つ送るだけで日報を作ります。\n\n"
        "左から UberEats → RocketNow → menu の順です。\n\n"
        "▼ こう送ると（スペースでも改行でもOK）\n"
        "12 5 8\n\n"
        "▼ こう返します\n"
        f"{sample}\n\n"
        "・日付と曜日は自動で入ります\n"
        "・生地数は空欄なので、あとから手書きで記入してください\n"
        "・説明をもう一度見たいときは「使い方」と送ってください"
    )


# 日報の文章を組み立てる
def build_report(uber, rocket, menu):
    now = datetime.now(JST)
    week = WEEK[now.weekday()]
    return (
        f"{now.month}月{now.day}日({week})\n"
        f"生地数 : \n"
        f"UberEats : {uber}\n"
        f"RocketNow : {rocket}\n"
        f"menu : {menu}"
    )


# LINEに返信する
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
