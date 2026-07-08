#!/usr/bin/env python3
"""X (旧Twitter) への自動投稿スクリプト。標準ライブラリのみで動作する。

使い方:
    python3 post_to_x.py <投稿本文のテキストファイル>

必要な環境変数（X Developer Portal で発行し、実行環境に設定する）:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

安全装置:
    - 1日の投稿上限: 2件（環境変数 X_DAILY_CAP で変更可）。超過時はエラー終了
    - 文字数超過時はエラー終了（AIが本文を短縮して再実行する）
    - 成功した投稿は pilot-company/logs/x_posts.csv に全件記録される
"""
import base64
import csv
import datetime
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.x.com/2/tweets"
LOG = pathlib.Path(__file__).resolve().parent.parent / "logs" / "x_posts.csv"


def percent(s):
    return urllib.parse.quote(str(s), safe="~")


def oauth1_header(method, url, ck, cs, at, ats):
    params = {
        "oauth_consumer_key": ck,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": at,
        "oauth_version": "1.0",
    }
    param_str = "&".join(f"{percent(k)}={percent(v)}" for k, v in sorted(params.items()))
    base = "&".join([method.upper(), percent(url), percent(param_str)])
    key = f"{percent(cs)}&{percent(ats)}".encode()
    params["oauth_signature"] = base64.b64encode(
        hmac.new(key, base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(f'{percent(k)}="{percent(v)}"' for k, v in sorted(params.items()))


def weighted_length(text):
    # Xの文字数カウント近似: 全角=2, 半角=1 の重み付きで上限280
    # (URLの一律23換算までは再現しないため、URLを含む場合は実際より厳しめに出る)
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in text)


def today_post_count():
    if not LOG.exists():
        return 0
    today = datetime.date.today().isoformat()
    with open(LOG, newline="", encoding="utf-8") as f:
        return sum(1 for row in csv.reader(f) if row and row[0].startswith(today))


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: post_to_x.py <text-file>")
    text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    if not text:
        sys.exit("error: 本文が空です")
    wlen = weighted_length(text)
    if wlen > 280:
        sys.exit(f"error: 本文が長すぎます（重み付き{wlen}/280）。短縮して再実行してください")

    cap = int(os.environ.get("X_DAILY_CAP", "2"))
    if today_post_count() >= cap:
        sys.exit(f"error: 本日の投稿上限（{cap}件）に達しています。明日以降に回してください")

    keys = [os.environ.get(k) for k in
            ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")]
    if not all(keys):
        sys.exit("error: X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET が未設定です。"
                 "自動投稿は無効のため、従来通り承認待ちキューに積んでください")

    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Authorization": oauth1_header("POST", API_URL, *keys),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.load(res)
    except urllib.error.HTTPError as e:
        sys.exit(f"error: X API {e.code}: {e.read().decode(errors='replace')}")

    tweet_id = data["data"]["id"]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            tweet_id, sys.argv[1], text[:50].replace("\n", " "),
        ])
    print(f"posted: https://x.com/i/status/{tweet_id}")


if __name__ == "__main__":
    main()
