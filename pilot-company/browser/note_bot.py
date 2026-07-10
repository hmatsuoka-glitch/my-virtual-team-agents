#!/usr/bin/env python3
"""note をログイン済みChrome(CDP)で自動投稿するローカルボット。X bot と同じCDP方式。

X API移行と同様、note公式APIが無いためブラウザ操作で自動化する（2026-07-10 HARU指示・
「NoteもX同様に自動投稿まで」）。**ローカルMacで launchd から実行**。

前提:
  - X bot と同じ CDP Chrome（start_chrome_cdp.sh・ポート9222・プロファイル ~/.x-bot-chrome）を使う
  - その Chrome で **note にもログイン済み**であること（初回のみ手動ログイン）
  - 環境変数 X_BOT_CDP=http://127.0.0.1:9222 を設定して実行

キュー: pilot-company/tasks/note_queue/*.md（frontmatter付き）
  ---
  title: 記事タイトル
  visibility: free        # free=自動公開 / paid=下書き保存し人間が価格設定して公開
  price: 980              # paid のとき
  paywall_marker: <<PAYWALL>>   # paid のとき、本文中のこの行以降が有料
  tags: 建設業, 採用
  ---
  （本文markdown）

サブコマンド:
  draft   [--dry-run]  最古の記事を「下書き保存」する（最も安全）
  publish [--dry-run]  最古の記事を処理する（free=公開 / paid=下書き＋人間へ）
  --dry-run は公開直前で止め、スクリーンショットを残す

安全装置: 1回1本 / 失敗時スクショ(browser/logs) ＋ キュー保持 / 対外公開は free のみ自動
必要: ~/.x-bot-venv の playwright
"""
import datetime
import os
import pathlib
import random
import re
import sys
import time

PILOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = PILOT / "tasks" / "note_queue"
POSTED = QUEUE / "posted"
LOG = PILOT / "logs" / "note_posts.csv"
ERR_DIR = PILOT / "browser" / "logs"
CDP = os.environ.get("X_BOT_CDP", "").strip().replace("localhost", "127.0.0.1")

# note のセレクタ（実機で調整が必要な場合あり。壊れたら browser/logs のスクショで確認）
NEW_URL = "https://note.com/notes/new"
SEL_TITLE = ['textarea[placeholder*="タイトル"]', '[placeholder="記事タイトル"]',
             'textarea[aria-label*="タイトル"]']
SEL_BODY = ['div[contenteditable="true"][role="textbox"]', '.ProseMirror',
            'div[contenteditable="true"]']
SEL_PUBLISH_NEXT = ['button:has-text("公開に進む")', 'button:has-text("公開設定")',
                    'button:has-text("次へ")']
SEL_PUBLISH_DO = ['button:has-text("投稿する")', 'button:has-text("公開する")',
                  'button:has-text("公開")']


def parse_article(path):
    text = path.read_text(encoding="utf-8")
    meta = {"visibility": "free", "tags": ""}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return meta, body.strip()


def clean_for_note(md):
    """markdown を note 貼り付け用のプレーンテキストへ。見出し記号や強調記号を除去し段落を保つ。"""
    out = []
    for line in md.splitlines():
        s = line.rstrip()
        if re.match(r"^\s*---\s*$", s):
            out.append("")
            continue
        s = re.sub(r"^\s*#{1,6}\s+", "", s)        # 見出し記号を除去（テキストは残す）
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)     # **bold** → text
        s = re.sub(r"`(.+?)`", r"\1", s)           # `code` → text
        s = re.sub(r"^\s*>\s?", "", s)             # 引用記号除去
        s = re.sub(r"^\s*[-*]\s+", "・", s)         # 箇条書き → ・
        out.append(s)
    txt = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def save_error(page, tag):
    ERR_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        page.screenshot(path=str(ERR_DIR / f"note-{tag}-{ts}.png"))
    except Exception:
        pass


def find(page, selectors, timeout=15000):
    last = None
    for sel in selectors:
        try:
            return page.wait_for_selector(sel, timeout=timeout // len(selectors) + 1500)
        except Exception as e:
            last = e
    raise last or RuntimeError("selector not found")


def get_page(p):
    if not CDP:
        sys.exit("error: X_BOT_CDP 未設定。start_chrome_cdp.sh でChromeを起動し環境変数を設定してください")
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return browser, page


def run(mode, dry_run=False):
    from playwright.sync_api import sync_playwright

    arts = sorted(QUEUE.glob("*.md"))
    if not arts:
        print("note投稿キュー (tasks/note_queue/) は空です")
        return
    art = arts[0]
    meta, body = parse_article(art)
    title = meta.get("title", art.stem)
    visibility = meta.get("visibility", "free").lower()

    # paid は「販売開始」に当たるため自動公開しない（下書き止まり＋人間へ）
    force_draft = (mode == "draft") or (visibility == "paid")

    with sync_playwright() as p:
        browser, page = get_page(p)
        try:
            page.goto(NEW_URL, wait_until="domcontentloaded")
            time.sleep(random.uniform(2, 4))

            # タイトル
            t = find(page, SEL_TITLE)
            t.click()
            page.keyboard.type(title, delay=random.uniform(20, 50))
            time.sleep(1)

            # 本文（有料は無料部のみ本文へ。有料部は人間が設定するため注記）
            note_body = clean_for_note(body)
            if visibility == "paid":
                marker = meta.get("paywall_marker", "")
                if marker and marker in body:
                    free_part = clean_for_note(body.split(marker, 1)[0])
                    note_body = free_part + "\n\n（※ここから先は有料。価格" + \
                        meta.get("price", "") + "円と有料ラインは人間が設定して公開）"
            b = find(page, SEL_BODY)
            b.click()
            page.keyboard.insert_text(note_body)
            time.sleep(random.uniform(1.5, 3))

            if dry_run:
                save_error(page, "dryrun")
                print(f"[dry-run] タイトル・本文を入力しました（公開せず）。visibility={visibility}")
                print(f"  スクショ: {ERR_DIR}")
                return

            # note は下書き自動保存。draft モード/paid はここで終了（人間が確認・公開）
            if force_draft:
                time.sleep(3)  # 自動保存待ち
                _record(art, title, "draft", visibility)
                reason = "paid(販売開始は人間承認)" if visibility == "paid" else "draftモード"
                print(f"下書き保存しました（{reason}）: {title}")
                print("  → note で内容確認し、必要なら価格・有料ラインを設定して公開してください")
                return

            # free の自動公開
            nxt = find(page, SEL_PUBLISH_NEXT, timeout=20000)
            nxt.click()
            time.sleep(random.uniform(2, 4))
            # タグ入力は任意（失敗しても続行）
            do = find(page, SEL_PUBLISH_DO, timeout=20000)
            do.click()
            time.sleep(random.uniform(3, 6))

            url = page.url
            _record(art, title, "published-free", visibility, url)
            POSTED.mkdir(parents=True, exist_ok=True)
            art.rename(POSTED / art.name)
            print(f"公開しました（無料記事）: {url}")
        except Exception as e:
            save_error(page, "fail")
            sys.exit(f"error: note操作に失敗（キューは保持）: {e}\n  スクショ: {ERR_DIR}")
        finally:
            try:
                browser.close()
            except Exception:
                pass


def _record(art, title, status, visibility, url=""):
    import csv
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            status, visibility, str(art.relative_to(PILOT)), title[:60], url,
        ])


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("draft", "publish"):
        sys.exit(__doc__)
    run(args[0], dry_run="--dry-run" in args)
