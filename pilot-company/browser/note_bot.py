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
SEL_EYECATCH_SAVE = ['button:text-is("保存")', 'button:has-text("この画像を使用")',
                     'button:text-is("適用")', 'button:text-is("完了")']
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


def _caret_block_rect(page):
    """現在のキャレットがあるブロック要素の中心座標を返す（トリプルクリック用）。"""
    try:
        return page.evaluate(
            """() => {
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return null;
                let node = sel.anchorNode;
                if (node && node.nodeType === 3) node = node.parentElement;
                while (node && node.nodeType === 1 &&
                       getComputedStyle(node).display === 'inline')
                    node = node.parentElement;
                if (!node || node.nodeType !== 1) return null;
                const r = node.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) return null;
                return {x: r.left + r.width / 2, y: r.top + r.height / 2};
            }"""
        )
    except Exception:
        return None


def _click_heading_button(page):
    for sel in ('button:text-is("見出し")', 'button:has-text("見出し")',
                '[aria-label="見出し"]', '[aria-label*="見出し"]'):
        try:
            page.click(sel, timeout=1500)
            return True
        except Exception:
            pass
    return False


def apply_heading(page, n_chars=0):
    """直前に入力した見出し行を note の『見出し』整形に変える。
    noteのバブルツールバーは*マウス選択*でしか出ない（キーボード選択では出ない）ため、
    トリプルクリックで見出し行を丸ごと選択してからツールバーの『見出し』を押す。"""
    kb = page.keyboard
    # 1) 本命: マウスのトリプルクリックで行選択 → バブルメニューの『見出し』
    try:
        rect = _caret_block_rect(page)
        if rect:
            page.mouse.click(rect["x"], rect["y"], click_count=3)
            time.sleep(0.6)
            if _click_heading_button(page):
                time.sleep(0.3)
                kb.press("End")  # 選択解除・行末へ
                return True
    except Exception:
        pass
    # 2) フォールバック: キーボードで文字数ぶん選択（従来手法）
    try:
        if n_chars <= 0:
            return False
        for _ in range(n_chars):
            kb.press("Shift+ArrowLeft")
        time.sleep(0.4)
        if _click_heading_button(page):
            time.sleep(0.3)
            kb.press("ArrowRight")
            return True
        kb.press("ArrowRight")  # 選択解除・行末へ
    except Exception:
        try:
            kb.press("ArrowRight")
        except Exception:
            pass
    return False


# ---- 本文を note の見出し・段落に整形して入力（bannersがあれば見出し前に画像挿入） ----
def enter_body(page, md, banners=None):
    banners = banners or {}
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
        if hm:  # 見出し: （バナー対象なら画像挿入→）文字入力→選択→note『見出し』ボタンで整形
            htxt = hm.group(2).strip()
            if htxt in banners:
                # 挿入前に選択状態を必ず解除（前の見出しのバブル選択が残ると崩れるため）
                _dismiss_popups(page)
                _focus_editor_end(page)
                kb.press("Enter")  # 画像用の新規空行
                ok = insert_image(page, banners[htxt])  # 離脱防止の途中バナー
                print(f"[info] バナー挿入 {'OK' if ok else 'NG'}: {htxt[:16]}")
                _focus_editor_end(page)  # バナー挿入後、末尾にキャレットを戻す
            kb.type(htxt, delay=8)
            time.sleep(0.3)
            hok = apply_heading(page, len(htxt))
            print(f"[info] 見出し整形 {'OK' if hok else 'NG'}: {htxt[:16]}")
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


def gen_banner(p, text):
    """セクション区切り用のスリムなバナー画像を生成（離脱防止の途中画像）。"""
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-zぁ-んァ-ン一-龠]+", "_", text)[:20] or "banner"
    out = GEN_DIR / f"banner_{safe}.png"
    disp = text if len(text) <= 30 else text[:29] + "…"
    html = (
        '<!doctype html><meta charset="utf-8"><style>'
        'html,body{margin:0;width:1280px;height:420px;background:#1B3A5B;overflow:hidden;'
        "font-family:'Hiragino Kaku Gothic ProN','Hiragino Sans','Noto Sans JP',sans-serif}"
        '.w{width:1280px;height:420px;box-sizing:border-box;padding:0 96px;display:flex;'
        'flex-direction:column;justify-content:center}'
        '.tag{color:#F5C518;font-size:26px;font-weight:800;letter-spacing:6px;margin-bottom:22px}'
        '.ttl{color:#fff;font-size:52px;font-weight:800;line-height:1.3}'
        '.u{width:96px;height:8px;background:#F5C518;border-radius:4px;margin-top:28px}'
        '</style><div class="w"><div class="tag">POINT</div><div class="ttl">' + disp +
        '</div><div class="u"></div></div>'
    )
    b = p.chromium.launch(headless=True)
    try:
        pg = b.new_page(viewport={"width": 1280, "height": 420}, device_scale_factor=2)
        pg.set_content(html, wait_until="load")
        time.sleep(0.4)
        pg.screenshot(path=str(out))
    finally:
        b.close()
    return out


def _editor_img_count(page):
    """エディタ領域内の画像数を返す（挿入成否の判定用）。取得失敗は -1。"""
    try:
        return page.evaluate(
            "() => (document.querySelector('.ProseMirror') || document.body)"
            ".querySelectorAll('img').length"
        )
    except Exception:
        return -1


def _dismiss_popups(page):
    """開いているメニュー/ダイアログを Escape で閉じる（フォーカスを壊さない安全策）。"""
    for _ in range(2):
        try:
            page.keyboard.press("Escape")
            time.sleep(0.3)
        except Exception:
            pass


def _focus_editor_end(page):
    """本文エディタ末尾にキャレットを戻す（バナー挿入後に見出し入力を確実にするため）。"""
    try:
        page.evaluate(
            """() => {
                const pm = document.querySelector('.ProseMirror');
                if (!pm) return;
                pm.focus();
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(pm);
                range.collapse(false);
                sel.removeAllRanges();
                sel.addRange(range);
            }"""
        )
        time.sleep(0.2)
    except Exception:
        pass


def _open_inline_image_uploader(page):
    """本文中画像用: 行左の『＋（メニューを開く）』→ メニュー内の『画像』。
    file input が出たら True。見つからなければメニュー項目をログして False。"""
    try:
        page.click('[aria-label="メニューを開く"]', timeout=2500)
        time.sleep(0.9)
    except Exception:
        return False
    for isel in ('[aria-label="画像"]', '[aria-label*="画像"]',
                 '[role="menuitem"]:has-text("画像")', 'button:has-text("画像")',
                 'li:has-text("画像")', 'text=画像'):
        try:
            page.click(isel, timeout=1200)
            time.sleep(0.9)
            if page.locator('input[type="file"]').count() > 0:
                return True
        except Exception:
            pass
    try:
        items = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'[role=\"menuitem\"],[role=\"menu\"] button,[role=\"menu\"] li,button,li'))"
            ".filter(b => b.offsetParent)"
            ".map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())"
            ".filter(Boolean).slice(0, 30)"
        )
        print(f"[warn] ＋メニューに画像項目が見つからず。可視項目: {items}")
    except Exception:
        pass
    return False


def insert_image(page, img_path, inline=True):
    """画像を挿入。inline=True は本文中バナー（＋メニュー→画像数の増加で判定）、
    inline=False はヘッダー(アイキャッチ)（画像を追加→位置調整ダイアログの保存で判定）。
    UIが別物なので開き方も成功判定も分ける。失敗しても Escape で閉じて後続を壊さない。"""
    before = _editor_img_count(page)
    try:
        if inline:
            if not _open_inline_image_uploader(page):
                print("[warn] 本文バナーの画像UIを開けず（スキップ）")
                _dismiss_popups(page)
                return False
        else:
            # アイキャッチ: 常設『画像を追加』→（あれば）アップロード
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
        time.sleep(3)  # アップロード＆位置調整ダイアログを待つ

        if inline:
            # 本文中: 多くはアップロード完了で自動挿入される。画像数の増加で判定。
            # ※Enter連打は本文（選択中テキスト）を壊すため絶対にしない。
            for _ in range(8):  # 最大~8秒、アップロード完了を待つ
                time.sleep(1.0)
                if before >= 0 and _editor_img_count(page) > before:
                    return True
            # まだ増えないなら保存ダイアログがある可能性 → 保存ボタンだけ1回試す
            for meth in ("role", "textis"):
                try:
                    if meth == "role":
                        page.get_by_role("button", name="保存", exact=True).click(timeout=1500)
                    else:
                        page.click('button:text-is("保存")', timeout=1200)
                except Exception:
                    pass
            time.sleep(1.5)
            if before >= 0 and _editor_img_count(page) > before:
                return True
            try:
                btns = page.evaluate(
                    "() => Array.from(document.querySelectorAll('button'))"
                    ".filter(b => b.offsetParent)"
                    ".map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())"
                    ".filter(Boolean).slice(0, 24)"
                )
                print(f"[warn] 本文バナーを確定できず。可視ボタン: {btns}")
            except Exception:
                pass
            save_error(page, "banner-save-fail")
            _dismiss_popups(page)
            return before >= 0 and _editor_img_count(page) > before

        # アイキャッチ: 位置調整ダイアログの「保存」を押し、ダイアログが閉じたら成功
        saved = False
        for meth in ("role", "textis", "enter"):
            try:
                if meth == "role":
                    page.get_by_role("button", name="保存", exact=True).click(timeout=3000)
                elif meth == "textis":
                    page.click('button:text-is("保存")', timeout=2500)
                else:
                    page.keyboard.press("Enter")
            except Exception:
                pass
            time.sleep(2)
            try:
                if page.locator('button:has-text("キャンセル")').count() == 0:
                    saved = True
                    break
            except Exception:
                pass
        if not saved:
            save_error(page, "eyecatch-save-fail")
            _dismiss_popups(page)
            return False
        try:
            page.keyboard.press("End")
            page.keyboard.press("Enter")
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[warn] insert_image 例外({'inline' if inline else 'eyecatch'}): {e}")
        save_error(page, "img-insert-fail")
        _dismiss_popups(page)
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

        # 離脱防止の途中バナー: 番号付きセクション見出し（「1. …」等）の先頭3つに自動生成
        banners = {}
        if len(body) >= 1500:
            picked = 0
            for ln in body.splitlines():
                m = re.match(r"^#{2,6}\s+(\d+[.．].*)", ln.strip())
                if m and picked < 3:
                    htxt = m.group(1).strip()
                    try:
                        banners[htxt] = gen_banner(p, htxt)
                        picked += 1
                    except Exception as e:
                        print(f"[warn] バナー生成失敗: {e}")
        print(f"[info] セクションバナー生成: {len(banners)}枚 / 本文{len(body)}字")

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
                eyecatch_ok = insert_image(page, eyecatch, inline=False)
            body_in = body
            if visibility == "paid":
                marker = meta.get("paywall_marker", "")
                if marker and marker in body:
                    body_in = body.split(marker, 1)[0] + \
                        "\n\n（※ここから先は有料。価格" + meta.get("price", "") + \
                        "円と有料ラインは人間が設定して公開）"
            enter_body(page, body_in, banners)
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
