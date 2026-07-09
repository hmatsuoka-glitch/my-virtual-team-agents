#!/usr/bin/env python3
"""X（旧Twitter）をログイン済みChromeプロファイルで直接操作するローカルボット。

X API移行までの暫定運用（2026-07-08 HARU指示）。クラウドRoutinesではなく
**ローカルMacで launchd から実行する**（セットアップは同フォルダの README.md 参照）。

サブコマンド:
    login             初回のみ。ブラウザが開くので手動でXにログインし、ウィンドウを閉じる
    post [--dry-run]  tasks/x_queue/ の最も古いドラフトを1本投稿する（--dry-run は入力まで行い投稿しない）
    metrics           投稿済みポストの表示数・いいね等を取得し ledger/x_metrics.csv を更新する

安全装置:
    - 日次投稿上限2件（logs/x_posts.csv で API方式と共有カウント）
    - 人間らしい入力速度（1文字30〜90ms）と起動時のランダム待機（0〜120秒）
    - 失敗時: スクリーンショットを browser/logs/ に保存して終了。キューは消さない（次回再試行）

必要: pip3 install playwright && python3 -m playwright install chromium
"""
import csv
import datetime
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
DAILY_CAP = 2


def weighted_length(text):
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in text)


def today_post_count():
    if not POST_LOG.exists():
        return 0
    today = datetime.date.today().isoformat()
    with open(POST_LOG, newline="", encoding="utf-8") as f:
        return sum(1 for row in csv.reader(f) if row and row[0].startswith(today))


def launch(p, headless=False):
    return p.chromium.launch_persistent_context(
        str(PROFILE), headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="ja-JP",
    )


def save_error(page, tag):
    ERR_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        page.screenshot(path=str(ERR_DIR / f"{tag}-{ts}.png"))
    except Exception:
        pass


def cmd_login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = launch(p, headless=False)
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

    # 定時実行の機械的な規則性を崩す（人間らしさ）
    if not dry_run:
        time.sleep(random.uniform(0, 120))

    with sync_playwright() as p:
        ctx = launch(p)
        page = ctx.new_page()
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
            box = page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=30000)
            box.click()
            for ch in text:
                page.keyboard.type(ch, delay=random.uniform(30, 90))
            time.sleep(random.uniform(1.0, 3.0))
            if dry_run:
                print("[dry-run] 入力まで確認しました。投稿はしていません")
                save_error(page, "dryrun")  # 確認用スクリーンショット
                ctx.close()
                return
            page.click('[data-testid="tweetButton"]')

            # 投稿URLの取得: 成功トースト内のリンク → 失敗時は自分のプロフィール最新ポスト
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
            ctx.close()


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
        ctx = launch(p)
        page = ctx.new_page()
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
        ctx.close()

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
