#!/usr/bin/env python3
"""投稿済みXポストの成果データ（インプレッション・いいね等）を取得する。標準ライブラリのみで動作。

使い方:
    python3 fetch_x_metrics.py

動作:
    - pilot-company/logs/x_posts.csv に記録された投稿ID（直近100件）の public_metrics を
      X API から取得し、pilot-company/ledger/x_metrics.csv を最新値で書き換える
    - 週次会議・日報がこのCSVを分析の一次データとして使う

必要な環境変数:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
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
import urllib.error
import urllib.parse
import urllib.request

BASE = pathlib.Path(__file__).resolve().parent.parent
POST_LOG = BASE / "logs" / "x_posts.csv"
OUT = BASE / "ledger" / "x_metrics.csv"
API_URL = "https://api.x.com/2/tweets"


def percent(s):
    return urllib.parse.quote(str(s), safe="~")


def oauth1_header(method, url, query, ck, cs, at, ats):
    oauth = {
        "oauth_consumer_key": ck,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": at,
        "oauth_version": "1.0",
    }
    all_params = {**query, **oauth}
    param_str = "&".join(f"{percent(k)}={percent(v)}" for k, v in sorted(all_params.items()))
    base = "&".join([method.upper(), percent(url), percent(param_str)])
    key = f"{percent(cs)}&{percent(ats)}".encode()
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key, base.encode(), hashlib.sha1).digest()
    ).decode()
    return "OAuth " + ", ".join(f'{percent(k)}="{percent(v)}"' for k, v in sorted(oauth.items()))


def main():
    if not POST_LOG.exists():
        print("投稿ログ (logs/x_posts.csv) がまだありません。取得対象なし")
        return

    keys = [os.environ.get(k) for k in
            ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")]
    if not all(keys):
        sys.exit("error: X APIキーが未設定のため成果データを取得できません")

    with open(POST_LOG, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if len(r) >= 2]
    ids = [r[1] for r in rows][-100:]  # APIの1リクエスト上限=100件
    if not ids:
        print("投稿ログに有効なIDがありません")
        return

    query = {"ids": ",".join(ids),
             "tweet.fields": "public_metrics,created_at"}
    url = API_URL + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={
        "Authorization": oauth1_header("GET", API_URL, query, *keys),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.load(res)
    except urllib.error.HTTPError as e:
        sys.exit(f"error: X API {e.code}: {e.read().decode(errors='replace')}")

    fetched_at = datetime.datetime.now().isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tweet_id", "posted_at", "impressions", "likes", "retweets",
                    "replies", "quotes", "bookmarks", "fetched_at", "url"])
        for t in data.get("data", []):
            m = t.get("public_metrics", {})
            w.writerow([
                t["id"], t.get("created_at", ""),
                m.get("impression_count", 0), m.get("like_count", 0),
                m.get("retweet_count", 0), m.get("reply_count", 0),
                m.get("quote_count", 0), m.get("bookmark_count", 0),
                fetched_at, f"https://x.com/i/status/{t['id']}",
            ])
    print(f"updated: {OUT}（{len(data.get('data', []))}件）")


if __name__ == "__main__":
    main()
