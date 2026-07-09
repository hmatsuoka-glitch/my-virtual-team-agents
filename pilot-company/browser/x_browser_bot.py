#!/usr/bin/env python3
"""X（旧Twitter）をログイン済みChromeで直接操作するローカルボット。

X API移行までの暫定運用（2026-07-08 HARU指示）。**ローカルMacで実行する**。

2つの接続モード:
  - CDPモード（推奨）: あなたが普段使っているChromeを --remote-debugging-port 付きで起動し、
      そこへ後から接続する。ログイン作業が不要で、本物のブラウザなのでbot検出されにくい。
      環境変数 X_BOT_CDP に接続先（例 http://localhost:9222）を設定すると有効になる。
  - プロファイルモード（フォールバック）: 専用プロファイルを自動化ブラウザで開く。
      ※Xはこの方式のログインを弾くことがある（bot検出）。CDPモードが使えない時のみ。

サブコマンド:
    login             プロファイルモード用の初回ログイン（CDPモードでは不要）
    post [--dry-run]  tasks/x_queue/ の最も古いドラフトを1本投稿する
    metrics           投稿済みポストの表示数等を取得し ledger/x_metrics.csv を更新する

安全装置: 日次上限2件 / 人間らしい入力速度 / 起動時ランダム待機 / 失敗時スクショ＋キュー保持
必要: python3 -m venv ~/.x-bot-venv && ~/.x-bot-venv/bin/pip install playwright
      && ~/.x-bot-venv/bin/python -m playwright install chromium
"""
import csv
import datetime
import os
import pathlib
import random
import re
import sys
import time
import unicodedata

PILOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = PILOT / "tasks" / "x_queue"
POSTED = QUEUE / "posted"
POST_LOG = PILOT / "logs" / "x_posts.csv"
METRICS = PILOT / "ledger" / "x_metrics.csv"
ERR_DIR = PILOT / "browser" / "logs"
PROFILE = pathlib.Path.home() / ".x-bot-profile"
CDP = os.environ.get("X_BOT_CDP", "").strip()  # 例: http://127.0.0.1:9222
# localhost はIPv6(::1)に解決され接続失敗することがあるためIPv4に正規化
CDP = CDP.replace("localhost", "127.0.0.1")
DAILY_CAP = 2


def weighted_length(text):
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in text)


def today_post_count():
    if not POST_LOG.exists():
        return 0
    today = datetime.date.today().isoformat()
    with open(POST_LOG, newline="", encoding="utf-8") as f:
        return sum(1 for row in csv.reader(f) if row and row[0].startswith(today))


def get_context(p):
    """接続モードに応じて (context, cleanup関数) を返す。

    CDPモード: 既存Chromeに接続し既存コンテキストを使う。cleanupはページを閉じるだけ
              （ユーザーのChrome本体は閉じない）。
    プロファイルモード: 専用プロファイルで永続コンテキストを開き、cleanupで閉じる。
    """
    if CDP:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        return ctx, (lambda: browser.close())
    ctx = p.chromium.launch_persistent_context(
        str(PROFILE), headless=False,
        viewport={"width": 1280, "height": 900}, locale="ja-JP",
    )
    return ctx, (lambda: ctx.close())


def new_page(ctx):
    # CDPモードで既存タブがあれば再利用、なければ新規
    if CDP and ctx.pages:
        return ctx.pages[0]
    return ctx.new_page()


def save_error(page, tag):
    ERR_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        page.screenshot(path=str(ERR_DIR / f"{tag}-{ts}.png"))
    except Exception:
        pass


def cmd_login():
    if CDP:
        print("CDPモードではlogin不要です。普段のChromeでXにログイン済みであることを確認してください。")
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, locale="ja-JP")
        page = ctx.new_page()
        page.goto("https://x.com/login")
        print("ブラウザでXにログインしてください。完了したらこのターミナルで Enter を押してください。")
        input()
        ctx.close()
    print("ログイン情報をプロファイルに保存しました:", PROFILE)


def cmd_post(dry_run=False):
    from playwright.sync_api import sync_playwright

    if today_post_count() >= DAILY_CAP:
        print(f"本日の投稿上限（{DAILY_CAP}件）に達しています")
        return
    drafts = sorted(QUEUE.glob("*.txt"))
    if not drafts:
        print("投稿予約キュー (tasks/x_queue/) は空です")
        return
    draft = drafts[0]
    text = draft.read_text(encoding="utf-8").strip()
    if not text or weighted_length(text) > 280:
        sys.exit(f"error: {draft.name} が空か文字数超過です。修正が必要（キューに残します）")

    if not dry_run:
        time.sleep(random.uniform(0, 120))  # 定時実行の規則性を崩す

    with sync_playwright() as p:
        ctx, cleanup = get_context(p)
        page = new_page(ctx)
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
            box = page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=30000)
            box.click()
            for ch in text:
                page.keyboard.type(ch, delay=random.uniform(30, 90))
            time.sleep(random.uniform(1.0, 3.0))
            if dry_run:
                print("[dry-run] 入力まで確認しました。投稿はしていません")
                save_error(page, "dryrun")
                cleanup()
                return
            page.click('[data-testid="tweetButton"]')

            tweet_url = ""
            try:
                a = page.wait_for_selector('[data-testid="toast"] a[href*="/status/"]', timeout=15000)
                tweet_url = "https://x.com" + a.get_attribute("href")
            except Exception:
                try:
                    page.click('[data-testid="AppTabBar_Profile_Link"]')
                    a = page.wait_for_selector('article a[href*="/status/"]', timeout=15000)
                    tweet_url = "https://x.com" + a.get_attribute("href")
                except Exception:
                    pass
            m = re.search(r"/status/(\d+)", tweet_url or "")
            tweet_id = m.group(1) if m else f"unknown-{int(time.time())}"

            POST_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(POST_LOG, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    datetime.datetime.now().isoformat(timespec="seconds"),
                    tweet_id, str(draft.relative_to(PILOT)), text[:50].replace("\n", " "),
                ])
            POSTED.mkdir(parents=True, exist_ok=True)
            draft.rename(POSTED / draft.name)
            print(f"posted: {tweet_url or tweet_id}")
        except Exception as e:
            save_error(page, "post-fail")
            sys.exit(f"error: 投稿に失敗しました（キューに残します）: {e}")
        finally:
            cleanup()


NUM = r"([\d,\.]+(?:万)?)"
PATTERNS = {
    "replies": [NUM + r"\s*件の返信", NUM + r"\s+repl"],
    "retweets": [NUM + r"\s*件のリポスト", NUM + r"\s+repost"],
    "likes": [NUM + r"\s*件のいいね", NUM + r"\s+like"],
    "bookmarks": [NUM + r"\s*件のブックマーク", NUM + r"\s+bookmark"],
    "impressions": [NUM + r"\s*件の表示", NUM + r"\s+view"],
}


def parse_count(label, key):
    for pat in PATTERNS[key]:
        m = re.search(pat, label, re.IGNORECASE)
        if m:
            v = m.group(1).replace(",", "")
            return int(float(v[:-1]) * 10000) if v.endswith("万") else int(float(v))
    return 0


def cmd_metrics():
    from playwright.sync_api import sync_playwright

    if not POST_LOG.exists():
        print("投稿ログがまだありません")
        return
    with open(POST_LOG, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.reader(f) if len(r) >= 2 and r[1].isdigit()]
    targets = rows[-20:]
    if not targets:
        print("取得対象の投稿IDがありません")
        return

    fetched_at = datetime.datetime.now().isoformat(timespec="seconds")
    results = []
    with sync_playwright() as p:
        ctx, cleanup = get_context(p)
        page = new_page(ctx)
        for posted_at, tweet_id, *_ in targets:
            url = f"https://x.com/i/status/{tweet_id}"
            try:
                page.goto(url, wait_until="domcontentloaded")
                grp = page.wait_for_selector('article div[role="group"][aria-label]', timeout=20000)
                label = grp.get_attribute("aria-label") or ""
                results.append([
                    tweet_id, posted_at,
                    parse_count(label, "impressions"), parse_count(label, "likes"),
                    parse_count(label, "retweets"), parse_count(label, "replies"),
                    0, parse_count(label, "bookmarks"), fetched_at, url,
                ])
                time.sleep(random.uniform(3, 8))
            except Exception:
                save_error(page, f"metrics-{tweet_id}")
                continue
        cleanup()

    if not results:
        sys.exit("error: 成果データを1件も取得できませんでした（スクリーンショット参照）")
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tweet_id", "posted_at", "impressions", "likes", "retweets",
                    "replies", "quotes", "bookmarks", "fetched_at", "url"])
        w.writerows(results)
    print(f"updated: {METRICS}（{len(results)}件）")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("login", "post", "metrics"):
        sys.exit(__doc__)
    if args[0] == "login":
        cmd_login()
    elif args[0] == "post":
        cmd_post(dry_run="--dry-run" in args)
    else:
        cmd_metrics()
