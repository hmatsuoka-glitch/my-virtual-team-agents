#!/usr/bin/env python3
"""note をログイン済みChrome(CDP)で自動投稿するローカルボット。X bot と同じCDP方式。

note公式APIが無いためブラウザ操作で自動化（2026-07-10 HARU指示）。ローカルMacで実行。
整形（見出し・改行）＋アイキャッチ画像の自動生成・設定に対応（2026-07-10 改善）。

前提: start_chrome_cdp.sh の CDP Chrome（ポート9222・~/.x-bot-chrome）で note にログイン済み。
      環境変数 X_BOT_CDP=http://127.0.0.1:9222 を設定して実行。

キュー: pilot-company/tasks/note_queue/*.md（frontmatter付き）
  ---
  title: 記事タイトル
  visibility: free        # free=自動公開 / paid=下書き＋人間承認
  eyecatch: auto          # auto=タイトルからブランド画像を自動生成 / none / <画像パス>
  eyecatch_sub: 建設業・小さな会社の採用ノート   # アイキャッチ副題（任意）
  tags: 建設業, 採用
  ---
  （本文markdown。# 見出しはnote見出しに変換。空行で段落）

サブコマンド:
  login              専用Chromeを note ログインページへ（手動ログイン用）
  draft [--dry-run]  最古の記事を下書き保存
  publish [--dry-run] free=公開 / paid=下書き。--dry-run は公開直前で停止
"""
import csv
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
GEN_DIR = PILOT / "brand" / "eyecatch"
CDP = os.environ.get("X_BOT_CDP", "").strip().replace("localhost", "127.0.0.1")

NEW_URL = "https://note.com/notes/new"
SEL_TITLE = ['textarea[placeholder="記事タイトル"]', 'textarea[placeholder*="タイトル"]',
             '[placeholder="記事タイトル"]', 'textarea[aria-label*="タイトル"]',
             '[contenteditable="true"][aria-label*="タイトル"]', 'h1[contenteditable="true"]',
             'textarea']
SEL_BODY = ['div[contenteditable="true"][role="textbox"]', '.ProseMirror',
            'div[contenteditable="true"]:not([aria-label*="タイトル"])',
            'div[contenteditable="true"]']
SEL_EYECATCH_BTN = ['[aria-label="画像を追加"]', '[aria-label*="画像"]']
SEL_EYECATCH_UPLOAD = ['button:has-text("画像をアップロード")', 'button:has-text("アップロード")',
                       'text=画像をアップロード']
SEL_EYECATCH_SAVE = ['button:has-text("保存")', 'button:has-text("適用")', 'button:has-text("完了")',
                     'button:has-text("この画像を使用")']
SEL_PUBLISH_NEXT = ['button:has-text("公開に進む")', 'button:has-text("公開設定")', 'button:has-text("次へ")']
SEL_PUBLISH_DO = ['button:has-text("投稿する")', 'button:has-text("公開する")', 'button:has-text("公開")']


def parse_article(path):
    text = path.read_text(encoding="utf-8")
    meta = {"visibility": "free", "tags": "", "eyecatch": "auto"}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return meta, body.strip()


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
            return page.wait_for_selector(sel, timeout=max(2000, timeout // len(selectors)))
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


# ---- アイキャッチ画像の自動生成（ヘッドレスChromeでHTML→PNG。ブランド濃紺×安全イエロー） ----
def gen_eyecatch(p, title, sub):
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-zぁ-んァ-ン一-龠]+", "_", title)[:24] or "eyecatch"
    out = GEN_DIR / f"{safe}.png"
    disp = title if len(title) <= 34 else title[:33] + "…"
    html = (
        '<!doctype html><meta charset="utf-8"><style>'
        'html,body{margin:0;width:1280px;height:670px;background:#1B3A5B;overflow:hidden;'
        "font-family:'Hiragino Kaku Gothic ProN','Hiragino Sans','Noto Sans JP',sans-serif}"
        '.w{width:1280px;height:670px;box-sizing:border-box;padding:90px 96px;display:flex;'
        'flex-direction:column;justify-content:center}'
        '.tag{color:#F5C518;font-size:30px;font-weight:700;letter-spacing:4px;margin-bottom:26px}'
        '.ttl{color:#fff;font-size:62px;font-weight:800;line-height:1.35}'
        '.u{width:120px;height:8px;background:#F5C518;border-radius:4px;margin-top:34px}'
        '</style><div class="w"><div class="tag">' + (sub or "現場の採用ノート") +
        '</div><div class="ttl">' + disp + '</div><div class="u"></div></div>'
    )
    b = p.chromium.launch(headless=True)
    try:
        pg = b.new_page(viewport={"width": 1280, "height": 670}, device_scale_factor=2)
        pg.set_content(html, wait_until="load")
        time.sleep(0.5)
        pg.screenshot(path=str(out))
    finally:
        b.close()
    return out


def apply_heading(page, n_chars):
    """直前に入力した見出し行（n_chars文字）だけを選択し、noteの『見出し』ボタンで整形。
    Home/End は文書全体を選ぶ挙動があり本文を壊すため、Shift+←を文字数ぶん送って厳密に選択する。"""
    if n_chars <= 0:
        return False
    kb = page.keyboard
    try:
        for _ in range(n_chars):
            kb.press("Shift+ArrowLeft")
        time.sleep(0.5)
        page.click('button:text-is("見出し")', timeout=2500)
        time.sleep(0.3)
        kb.press("ArrowRight")  # 選択解除・行末へ
        return True
    except Exception:
        try:
            kb.press("ArrowRight")
        except Exception:
            pass
        return False


# ---- 本文を note の見出し・段落に整形して入力 ----
def enter_body(page, md):
    kb = page.keyboard
    lines = md.splitlines()
    # 先頭の H1（タイトル重複）は除去
    while lines and (not lines[0].strip() or re.match(r"^#\s+", lines[0])):
        if re.match(r"^#\s+", lines[0]):
            lines.pop(0)
            break
        lines.pop(0)
    # 空行で段落ブロックへ分割
    blocks, cur = [], []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                blocks.append(cur); cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)

    first = True
    for blk in blocks:
        if not first:
            kb.press("Enter")
        head = blk[0]
        hm = re.match(r"^(#{2,6})\s+(.*)", head)
        if hm:  # 見出し: 文字を入力→その文字数だけ選択→note『見出し』ボタンで整形
            htxt = hm.group(2).strip()
            kb.type(htxt, delay=8)
            time.sleep(0.2)
            apply_heading(page, len(htxt))
        elif re.match(r"^\s*---\s*$", head):  # 区切り線
            kb.type("---")
        elif re.match(r"^\s*[・\-*]\s+", head):  # 箇条書き
            for i, li in enumerate(blk):
                if i:
                    kb.press("Enter")
                kb.type("- " + re.sub(r"^\s*[・\-*]\s+", "", li).strip(), delay=8)
        else:  # 段落: 強調記号を除いて高速入力
            para = " ".join(x.strip() for x in blk)
            para = re.sub(r"\*\*(.+?)\*\*", r"\1", para)
            para = re.sub(r"`(.+?)`", r"\1", para)
            para = re.sub(r"^\s*>\s?", "", para)
            kb.insert_text(para)
        first = False
    kb.press("Enter")


def try_set_eyecatch(page, img_path):
    """本文先頭に画像（アイキャッチ）を挿入。カーソルは本文にある前提。失敗しても記事作成は続行。"""
    try:
        btn = find(page, SEL_EYECATCH_BTN, timeout=8000)
        btn.click()
        time.sleep(1.5)
        try:
            up = find(page, SEL_EYECATCH_UPLOAD, timeout=3000)
            up.click()
            time.sleep(1)
        except Exception:
            pass
        fi = page.wait_for_selector('input[type="file"]', timeout=6000, state="attached")
        fi.set_input_files(str(img_path))
        time.sleep(3)
        try:
            sv = find(page, SEL_EYECATCH_SAVE, timeout=5000)
            sv.click()
            time.sleep(2)
        except Exception:
            pass
        try:
            page.keyboard.press("End")   # 画像の後ろへカーソルを移す
            page.keyboard.press("Enter")
        except Exception:
            pass
        return True
    except Exception:
        save_error(page, "eyecatch-fail")
        return False


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
    force_draft = (mode == "draft") or (visibility == "paid")

    with sync_playwright() as p:
        # アイキャッチを先に生成（自動）
        eyecatch = None
        ec = meta.get("eyecatch", "auto")
        if ec and ec != "none":
            try:
                if ec == "auto":
                    eyecatch = gen_eyecatch(p, title, meta.get("eyecatch_sub", ""))
                else:
                    cand = (PILOT / ec) if not os.path.isabs(ec) else pathlib.Path(ec)
                    eyecatch = cand if cand.exists() else None
            except Exception:
                eyecatch = None

        browser, page = get_page(p)
        try:
            page.goto(NEW_URL, wait_until="domcontentloaded")
            time.sleep(random.uniform(2, 4))
            if "login" in page.url or "signup" in page.url:
                save_error(page, "not-logged-in")
                sys.exit("error: この専用Chromeが note に未ログインです。"
                         "`note_bot.py login` でログインしてから再実行してください。\n"
                         f"  現在のURL: {page.url}")

            # タイトル
            try:
                t = find(page, SEL_TITLE)
            except Exception:
                save_error(page, "no-title")
                sys.exit(f"error: タイトル入力欄が見つかりません。browser/logs のスクショと共有:\n"
                         f"  URL: {page.url}\n  ページ名: {page.title()}")
            t.click()
            page.keyboard.type(title, delay=random.uniform(20, 45))
            time.sleep(1)

            # 本文エリアにカーソルを置き、まず先頭にアイキャッチ画像を挿入 → その後に本文
            b = find(page, SEL_BODY)
            b.click()
            time.sleep(0.5)
            eyecatch_ok = False
            if eyecatch:
                eyecatch_ok = try_set_eyecatch(page, eyecatch)
            body_in = body
            if visibility == "paid":
                marker = meta.get("paywall_marker", "")
                if marker and marker in body:
                    body_in = body.split(marker, 1)[0] + \
                        "\n\n（※ここから先は有料。価格" + meta.get("price", "") + \
                        "円と有料ラインは人間が設定して公開）"
            enter_body(page, body_in)
            time.sleep(random.uniform(1.5, 3))

            if dry_run:
                save_error(page, "dryrun")
                print(f"[dry-run] 入力完了（公開せず）。visibility={visibility} / "
                      f"アイキャッチ={'設定OK' if eyecatch_ok else ('生成のみ:' + str(eyecatch) if eyecatch else '無し')}")
                print(f"  スクショ: {ERR_DIR}")
                return

            if force_draft:
                time.sleep(3)
                _record(art, title, "draft", visibility)
                reason = "paid(販売開始は人間承認)" if visibility == "paid" else "draftモード"
                print(f"下書き保存しました（{reason}）: {title}")
                return

            nxt = find(page, SEL_PUBLISH_NEXT, timeout=20000)
            nxt.click()
            time.sleep(random.uniform(2, 4))
            do = find(page, SEL_PUBLISH_DO, timeout=20000)
            do.click()
            time.sleep(random.uniform(3, 6))

            _record(art, title, "published-free", visibility, page.url)
            POSTED.mkdir(parents=True, exist_ok=True)
            art.rename(POSTED / art.name)
            print(f"公開しました（無料記事・アイキャッチ{'あり' if eyecatch_ok else 'なし'}）: {page.url}")
        except Exception as e:
            save_error(page, "fail")
            sys.exit(f"error: note操作に失敗（キューは保持）: {e}\n  スクショ: {ERR_DIR}")
        finally:
            try:
                browser.close()
            except Exception:
                pass


def _record(art, title, status, visibility, url=""):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            status, visibility, str(art.relative_to(PILOT)), title[:60], url,
        ])


def cmd_inspect():
    """note新規記事エディタのボタン一覧と、文字選択時に出るツールバーを吸い出す診断。"""
    from playwright.sync_api import sync_playwright
    out = []

    def dump_buttons(page):
        res = []
        for b in page.query_selector_all('button, [role="button"], a[role="button"], label'):
            try:
                if not b.is_visible():
                    continue
                txt = (b.inner_text() or "").strip().replace("\n", " ")[:28]
                al = (b.get_attribute("aria-label") or "")[:28]
                if txt or al:
                    res.append(f"text='{txt}' aria='{al}'")
            except Exception:
                pass
        return res

    with sync_playwright() as p:
        browser, page = get_page(p)
        try:
            page.goto(NEW_URL, wait_until="domcontentloaded")
            time.sleep(3)
            if "login" in page.url:
                sys.exit("未ログインです。note_bot.py login でログインしてください")
            out.append("=== URL === " + page.url)
            out.append("\n=== 初期ボタン（この中に『見出し画像』系があるはず） ===")
            before = dump_buttons(page)
            out += before
            # 本文に文字を入れて選択 → バブルツールバーを出す
            try:
                b = find(page, SEL_BODY)
                b.click()
                page.keyboard.type("見出しテスト行", delay=20)
                time.sleep(0.5)
                page.keyboard.press("Home")
                page.keyboard.down("Shift"); page.keyboard.press("End"); page.keyboard.up("Shift")
                time.sleep(1.2)
                out.append("\n=== 文字選択後に増えたボタン（この中に『見出し』整形があるはず） ===")
                after = dump_buttons(page)
                for x in after:
                    if x not in before:
                        out.append(x)
            except Exception as e:
                out.append("選択ツールバー取得失敗: " + str(e))
            ERR_DIR.mkdir(parents=True, exist_ok=True)
            path = ERR_DIR / "note_inspect.txt"
            path.write_text("\n".join(out), encoding="utf-8")
            print("診断結果を保存しました。次のファイルの中身を共有してください:")
            print("  " + str(path))
        finally:
            try:
                browser.close()
            except Exception:
                pass


def cmd_login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = get_page(p)
        try:
            page.goto("https://note.com/login")
            try:
                page.bring_to_front()
            except Exception:
                pass
            print("開いた専用Chromeで note にログインしてください。完了したら Enter を押してください。")
            input()
            print("OK。ログイン状態は専用プロファイルに保持されます。")
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("login", "inspect", "draft", "publish"):
        sys.exit(__doc__)
    if args[0] == "login":
        cmd_login()
    elif args[0] == "inspect":
        cmd_inspect()
    else:
        run(args[0], dry_run="--dry-run" in args)
