#!/usr/bin/env python3
"""
Evernote (.enex) to Notion 匯入工具

用法:
    # 匯入到 Notion Database
    python evernote_to_notion.py --enex 筆記.enex --token TOKEN --database DATABASE_ID

    # 匯入到某個 Notion 頁面底下
    python evernote_to_notion.py --enex 筆記.enex --token TOKEN --page PAGE_ID

    # 儲存附圖到本機 images/ 目錄
    python evernote_to_notion.py --enex 筆記.enex --token TOKEN --page PAGE_ID --save-images

取得 Notion Integration Token:
    https://www.notion.so/my-integrations

取得 Database/Page ID:
    從 Notion 頁面 URL 中取得，例如:
    https://notion.so/workspace/abc123def456... → ID 為 abc123def456...
"""

import argparse
import base64
import hashlib
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
    from notion_client import Client
    from notion_client.errors import APIResponseError
except ImportError:
    print("缺少依賴套件，請執行:\n  pip install -r requirements.txt")
    sys.exit(1)

MAX_TEXT_LEN = 2000   # Notion rich text 單一元素長度限制
RATE_DELAY = 0.35     # ~3 req/s，低於 Notion API 限制


# ── Rich text / block 建構函式 ─────────────────────────────────────────────────

def _truncate(text: str) -> str:
    return text[:MAX_TEXT_LEN] if len(text) > MAX_TEXT_LEN else text


def make_text(content: str, ann: dict | None = None, url: str | None = None) -> dict:
    obj: dict[str, Any] = {
        "type": "text",
        "text": {"content": _truncate(content)},
        "annotations": {
            "bold": False, "italic": False, "underline": False,
            "strikethrough": False, "code": False, "color": "default",
            **(ann or {}),
        },
    }
    if url:
        obj["text"]["link"] = {"url": url}
    return obj


def make_block(btype: str, rich_text: list, extra: dict | None = None) -> dict:
    return {"object": "block", "type": btype, btype: {"rich_text": rich_text, **(extra or {})}}


def divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def code_block(text: str, lang: str = "plain text") -> dict:
    return {"object": "block", "type": "code",
            "code": {"rich_text": [make_text(text)], "language": lang}}


# ── ENML → Notion blocks 轉換 ──────────────────────────────────────────────────

BLOCK_TAGS = frozenset({
    "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "hr", "table", "br", "en-note",
})


def extract_rich_text(element, ann: dict | None = None) -> list:
    """遞迴提取 HTML 元素中的 inline 富文字。"""
    if ann is None:
        ann = {}

    if isinstance(element, NavigableString):
        text = str(element)
        if text and text != "\n":
            return [make_text(text, ann)]
        return []

    tag = (element.name or "").lower()
    new_ann = dict(ann)

    if tag in ("b", "strong"):
        new_ann["bold"] = True
    elif tag in ("i", "em"):
        new_ann["italic"] = True
    elif tag == "u":
        new_ann["underline"] = True
    elif tag in ("s", "strike", "del"):
        new_ann["strikethrough"] = True
    elif tag == "code":
        new_ann["code"] = True

    if tag == "a":
        href = element.get("href", "") or ""
        text = element.get_text()
        if text:
            return [make_text(text, new_ann, href or None)]
        return []

    if tag == "br":
        return [make_text("\n", ann)]

    if tag in ("en-todo", "en-media"):
        return []

    result = []
    for child in element.children:
        result.extend(extract_rich_text(child, new_ann))
    return result


def element_to_blocks(element) -> list:
    """將 HTML 元素轉換為 Notion block 列表。"""
    if isinstance(element, NavigableString):
        text = str(element).strip()
        if text:
            return [make_block("paragraph", [make_text(text)])]
        return []

    tag = (element.name or "").lower()

    # ── 段落 / div ─────────────────────────────────────────────────────────────
    if tag in ("div", "p"):
        # 有 en-todo 子元素 → to_do block
        todo = element.find("en-todo")
        if todo:
            checked = (todo.get("checked") or "false").lower() == "true"
            todo.extract()
            return [make_block("to_do", extract_rich_text(element), {"checked": checked})]

        # 含 block-level 子元素 → 展開
        has_block_child = any(
            not isinstance(c, NavigableString) and (c.name or "").lower() in BLOCK_TAGS
            for c in element.children
        )
        if has_block_child:
            blocks = []
            for child in element.children:
                blocks.extend(element_to_blocks(child))
            return blocks

        rich_text = extract_rich_text(element)
        return [make_block("paragraph", rich_text if rich_text else [make_text("")])]

    # ── 標題 ───────────────────────────────────────────────────────────────────
    if tag == "h1":
        return [make_block("heading_1", extract_rich_text(element))]
    if tag == "h2":
        return [make_block("heading_2", extract_rich_text(element))]
    if tag in ("h3", "h4", "h5", "h6"):
        return [make_block("heading_3", extract_rich_text(element))]

    # ── 清單 ───────────────────────────────────────────────────────────────────
    if tag == "ul":
        blocks = []
        for li in element.find_all("li", recursive=False):
            todo = li.find("en-todo")
            if todo:
                checked = (todo.get("checked") or "false").lower() == "true"
                todo.extract()
                blocks.append(make_block("to_do", extract_rich_text(li), {"checked": checked}))
            else:
                blocks.append(make_block("bulleted_list_item", extract_rich_text(li)))
        return blocks

    if tag == "ol":
        return [
            make_block("numbered_list_item", extract_rich_text(li))
            for li in element.find_all("li", recursive=False)
        ]

    if tag == "li":
        todo = element.find("en-todo")
        if todo:
            checked = (todo.get("checked") or "false").lower() == "true"
            todo.extract()
            return [make_block("to_do", extract_rich_text(element), {"checked": checked})]
        return [make_block("bulleted_list_item", extract_rich_text(element))]

    # ── 其他 block 類型 ────────────────────────────────────────────────────────
    if tag == "blockquote":
        return [make_block("quote", extract_rich_text(element))]

    if tag in ("pre", "code"):
        # 嘗試偵測語言（class="language-python" 等）
        lang = "plain text"
        cls = " ".join(element.get("class") or [])
        if "python" in cls:
            lang = "python"
        elif "javascript" in cls or "js" in cls:
            lang = "javascript"
        elif "typescript" in cls or "ts" in cls:
            lang = "typescript"
        elif "java" in cls:
            lang = "java"
        elif "bash" in cls or "shell" in cls:
            lang = "bash"
        elif "sql" in cls:
            lang = "sql"
        return [code_block(element.get_text(), lang)]

    if tag == "hr":
        return [divider_block()]

    if tag == "br":
        return []

    if tag == "table":
        rows = []
        for tr in element.find_all("tr"):
            cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        if rows:
            return [code_block("\n".join(rows))]
        return []

    if tag == "en-media":
        media_type = element.get("type") or ""
        return [{"_en_media": True, "hash": element.get("hash") or "", "mime": media_type}]

    if tag == "en-note":
        blocks = []
        for child in element.children:
            blocks.extend(element_to_blocks(child))
        return blocks

    # 其餘 inline / 未知標籤 → 嘗試當段落
    rich_text = extract_rich_text(element)
    if rich_text:
        return [make_block("paragraph", rich_text)]
    return []


def enml_to_blocks(enml_content: str, resources: dict) -> list:
    """將 ENML 字串轉換為 Notion blocks，並處理媒體附件。"""
    soup = BeautifulSoup(enml_content, "lxml")
    en_note = soup.find("en-note") or soup

    raw_blocks = []
    for child in en_note.children:
        raw_blocks.extend(element_to_blocks(child))

    blocks = []
    for b in raw_blocks:
        if b.get("_en_media"):
            h = b["hash"]
            if h in resources:
                res = resources[h]
                blocks.append(make_block("paragraph", [make_text(f"[附件: {res['filename']}]")]))
                if res.get("saved_path"):
                    blocks.append(make_block("paragraph", [make_text(f"  → 已儲存: {res['saved_path']}")]))
            else:
                blocks.append(make_block("paragraph", [make_text(f"[附件]")]))
            continue
        blocks.append(b)

    # 移除首尾空段落
    def is_empty(b: dict) -> bool:
        if b.get("type") != "paragraph":
            return False
        rt = b.get("paragraph", {}).get("rich_text", [])
        return not any(t.get("text", {}).get("content", "").strip() for t in rt)

    while blocks and is_empty(blocks[0]):
        blocks.pop(0)
    while blocks and is_empty(blocks[-1]):
        blocks.pop()

    return blocks


# ── .enex 解析 ─────────────────────────────────────────────────────────────────

def parse_en_date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        dt = datetime.strptime(s.strip(), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def parse_resources(note_elem: ET.Element, save_images: bool, output_dir: str) -> dict:
    resources = {}
    for res in note_elem.findall("resource"):
        data_elem = res.find("data")
        mime_elem = res.find("mime")
        if data_elem is None or not data_elem.text:
            continue

        raw = base64.b64decode(data_elem.text.strip())
        md5 = hashlib.md5(raw).hexdigest()
        mime = (mime_elem.text or "application/octet-stream").strip()

        # 取原始檔名
        fn_elem = res.find(".//file-name") or res.find(".//resource-attributes/file-name")
        filename = fn_elem.text.strip() if fn_elem is not None and fn_elem.text else f"{md5}"

        saved_path = None
        if save_images and mime.startswith("image/"):
            ext = mime.split("/")[-1].split("+")[0]  # image/png → png
            os.makedirs(output_dir, exist_ok=True)
            saved_path = os.path.join(output_dir, f"{md5}.{ext}")
            with open(saved_path, "wb") as f:
                f.write(raw)

        resources[md5] = {"data": raw, "mime": mime, "filename": filename, "saved_path": saved_path}
    return resources


def parse_enex(filepath: str, save_images: bool = False, images_dir: str = "images") -> list[dict]:
    tree = ET.parse(filepath)
    root = tree.getroot()

    notes = []
    for note_elem in root.findall("note"):
        note: dict[str, Any] = {}

        title_elem = note_elem.find("title")
        note["title"] = (title_elem.text or "Untitled").strip() if title_elem is not None else "Untitled"

        content_elem = note_elem.find("content")
        note["content"] = content_elem.text or "" if content_elem is not None else ""

        note["tags"] = [t.text.strip() for t in note_elem.findall("tag") if t.text]

        note["created"] = parse_en_date((note_elem.findtext("created") or "").strip())
        note["updated"] = parse_en_date((note_elem.findtext("updated") or "").strip())

        # 筆記本名稱（若有）
        nb_elem = note_elem.find(".//note-attributes/notebook")
        note["notebook"] = nb_elem.text.strip() if nb_elem is not None and nb_elem.text else None

        note["resources"] = parse_resources(note_elem, save_images, images_dir)

        notes.append(note)

    return notes


# ── Notion 匯入 ────────────────────────────────────────────────────────────────

def build_properties(note: dict, parent_type: str) -> dict:
    title_value = [{"type": "text", "text": {"content": _truncate(note["title"])}}]
    if parent_type == "database_id":
        return {"Name": {"title": title_value}}
    return {"title": {"title": title_value}}


def import_note(notion: Client, note: dict, parent: dict) -> str:
    blocks = enml_to_blocks(note["content"], note["resources"])

    properties = build_properties(note, parent.get("type", "page_id"))
    page = notion.pages.create(parent=parent, properties=properties)
    page_id = page["id"]
    time.sleep(RATE_DELAY)

    # 分批 append blocks（最多 100 個/次）
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i + 100]
        try:
            notion.blocks.children.append(block_id=page_id, children=chunk)
        except APIResponseError as e:
            print(f"  ⚠ 部分內容略過: {e.message}")
        time.sleep(RATE_DELAY)

    return page_id


def run(args: argparse.Namespace) -> None:
    if not os.path.isfile(args.enex):
        print(f"找不到檔案: {args.enex}")
        sys.exit(1)

    print(f"解析 {args.enex} …")
    notes = parse_enex(args.enex, save_images=args.save_images, images_dir=args.images_dir)
    print(f"共 {len(notes)} 則筆記\n")

    notion = Client(auth=args.token)

    # 確認 token 有效
    try:
        notion.users.me()
    except APIResponseError as e:
        print(f"Notion API 驗證失敗: {e.message}")
        sys.exit(1)

    if args.database:
        parent = {"type": "database_id", "database_id": args.database}
    else:
        parent = {"type": "page_id", "page_id": args.page}

    ok = 0
    fail = 0
    for i, note in enumerate(notes, 1):
        title_display = note["title"][:50] + "…" if len(note["title"]) > 50 else note["title"]
        print(f"[{i}/{len(notes)}] {title_display}", end=" … ", flush=True)
        try:
            page_id = import_note(notion, note, parent)
            print(f"✓ {page_id}")
            ok += 1
        except APIResponseError as e:
            print(f"✗ {e.message}")
            fail += 1
        except Exception as e:
            print(f"✗ {e}")
            fail += 1

    print(f"\n完成！成功: {ok}，失敗: {fail}")
    if args.save_images:
        count = sum(
            1 for n in notes for r in n["resources"].values() if r.get("saved_path")
        )
        if count:
            print(f"已儲存 {count} 張圖片到 {args.images_dir}/")
            print("請手動將圖片上傳後，在 Notion 頁面中替換 [附件] 佔位符。")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="將 Evernote .enex 匯出檔匯入 Notion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--enex", required=True, help=".enex 檔案路徑")
    parser.add_argument("--token", required=True, help="Notion Integration Token")

    dest = parser.add_mutually_exclusive_group(required=True)
    dest.add_argument("--database", help="目標 Notion Database ID")
    dest.add_argument("--page", help="目標 Notion 父頁面 ID")

    parser.add_argument("--save-images", action="store_true",
                        help="將嵌入圖片儲存到本機目錄")
    parser.add_argument("--images-dir", default="images",
                        help="儲存圖片的目錄（預設: images）")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
