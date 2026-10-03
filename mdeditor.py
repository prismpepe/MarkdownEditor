"""Markdown エディタ（Windows）。左で書き、右でリアルタイムにプレビューする。

使い方:
    MarkdownEditor.exe [ファイル.md | フォルダー]
    MarkdownEditor.exe --register     エクスプローラーの「プログラムから開く」に登録
    MarkdownEditor.exe --unregister   登録を解除

描画は Edge の WebView2。プレビューの HTML は編集中の文書から作るので信頼しない。
埋め込み HTML は sanitize.py で許可したタグだけ残す（スクリプトは動かさない）。
文書の読み書き（文字コード・改行・競合・バックアップ）は filemodel.py に分けてある。
"""
import base64
import gzip
import ctypes
import json
import mimetypes
import os
import re
import sys
import threading
import webbrowser

import clipboard
import dialogs
import filemodel
import printing
from sanitize import sanitize

APP_NAME = "Markdown エディタ"
MD_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd")
PROG_ID = "MarkdownEditor.File"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
MAX_FILES = 5000
MAX_INLINE_IMAGE = 20 * 1024 * 1024
# ブロック要素のうち、プレビューと編集の位置合わせに使うもの
LINE_TOKENS = {"paragraph_open", "heading_open", "bullet_list_open", "ordered_list_open",
               "list_item_open", "blockquote_open", "table_open", "tr_open", "hr"}


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def data_dir():
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "MarkdownEditor")


def settings_path():
    return os.path.join(data_dir(), "settings.json")


def backup_root():
    return os.path.join(data_dir(), "backup")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def is_markdown(path):
    return path.lower().endswith(MD_EXTENSIONS)


def list_markdown(folder):
    """フォルダー以下の Markdown を相対パスで返す（サブフォルダーも含む）。"""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if is_markdown(name):
                rel = os.path.relpath(os.path.join(root, name), folder)
                found.append(rel.replace("\\", "/"))
                if len(found) >= MAX_FILES:
                    return found
    return found


def inline_image(src, base):
    """相対パスの画像は data URI にして埋め込む（読み込み元を持たない画面のため）。"""
    if not src or src.startswith(("http://", "https://", "data:")) or not base:
        return src
    from urllib.parse import unquote
    path = unquote(src.split("#")[0].split("?")[0])
    if path.startswith("file:///"):
        path = path[8:]
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    try:
        if os.path.getsize(path) > MAX_INLINE_IMAGE:
            return src
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return src
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return f"data:{mime};base64,{data}"


def make_renderer():
    from markdown_it import MarkdownIt
    from markdown_it.common.utils import escapeHtml
    from mdit_py_plugins.anchors import anchors_plugin
    from mdit_py_plugins.tasklists import tasklists_plugin

    md = MarkdownIt("commonmark", {"html": True})
    md.enable(["table", "strikethrough"])
    md.use(tasklists_plugin)
    md.use(anchors_plugin, min_level=1, max_level=6)

    def add_lines(state):
        for tok in state.tokens:
            if tok.map and tok.type in LINE_TOKENS:
                tok.attrSet("data-line", str(tok.map[0]))

    md.core.ruler.push("source_lines", add_lines)

    def image(self, tokens, idx, options, env):
        tok = tokens[idx]
        tok.attrSet("src", inline_image(tok.attrGet("src") or "", env.get("base", "")))
        tok.attrSet("alt", self.renderInlineAsText(tok.children, options, env))
        return self.renderToken(tokens, idx, options, env)

    default_fence = md.renderer.fence

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        line = tok.map[0] if tok.map else 0
        if tok.info.strip().split(" ")[0].lower() == "mermaid":
            return (f'<pre class="mermaid-src" data-line="{line}"><code>'
                    + escapeHtml(tok.content) + "</code></pre>")
        out = default_fence(tokens, idx, options, env)
        return out.replace("<pre", f'<pre data-line="{line}"', 1)

    md.add_render_rule("image", image)
    md.add_render_rule("fence", fence)
    return md


class Api:
    def __init__(self, start_path):
        self._window = None
        self._md = make_renderer()
        self._mermaid = None
        self._start_path = start_path
        self._dirty = False
        self._closing = False

    # --- 起動 ---------------------------------------------------------------
    def get_initial(self):
        settings = load_settings()
        start = self._start_path
        result = {"folder": None, "file": None, "error": None,
                  "prefs": settings.get("prefs", {}),
                  "encodings": list(filemodel.ENCODINGS),
                  "newlines": list(filemodel.NEWLINES),
                  "default_encoding": filemodel.DEFAULT_ENCODING,
                  "default_newline": filemodel.DEFAULT_NEWLINE}
        last = settings.get("last_folder")
        if start:
            if os.path.isdir(start):
                result["folder"] = start
            elif os.path.isfile(start):
                result["file"] = start
                result["folder"] = os.path.dirname(start)
            else:
                result["error"] = f"見つかりません: {start}"
        elif last and os.path.isdir(last):
            result["folder"] = last
        return result

    def set_prefs(self, prefs):
        settings = load_settings()
        settings["prefs"] = {**settings.get("prefs", {}), **prefs}
        save_settings(settings)

    # --- フォルダー・一覧 ----------------------------------------------------
    def _initial_dir(self, initial):
        if initial and os.path.isdir(initial):
            return initial
        last = load_settings().get("last_folder")
        return last if last and os.path.isdir(last) else os.getcwd()

    def pick_folder(self, initial=None):
        return dialogs.pick_folder(self._initial_dir(initial))

    def pick_file(self, initial=None):
        return dialogs.pick_file(self._initial_dir(initial))

    def pick_save(self, initial_dir=None, name="無題.md"):
        return dialogs.pick_save(self._initial_dir(initial_dir), name)

    def list_files(self, folder):
        if not os.path.isdir(folder):
            return {"error": f"フォルダーが見つかりません: {folder}", "files": []}
        settings = load_settings()
        settings["last_folder"] = folder
        save_settings(settings)
        return {"error": None, "files": list_markdown(folder)}

    # --- 文書 ---------------------------------------------------------------
    def read_file(self, path):
        try:
            return {"error": None, "doc": filemodel.read_document(path)}
        except OSError as e:
            return {"error": f"開けません: {e}"}

    def check_changed(self, path):
        """読み込んだあとにファイルが変わったかを確かめるための、現在のスタンプ。"""
        try:
            return {"state": "exists", "stamp": filemodel.stamp_of(path)}
        except OSError:
            return {"state": "missing", "stamp": None}

    def save(self, path, text, encoding, newline, stamp):
        """stamp が None なら競合を確かめずに上書きする（利用者が上書きを選んだとき）。"""
        try:
            new_stamp = filemodel.write_document(
                path, text, encoding, newline, expected_stamp=stamp,
                backup_root=backup_root())
        except filemodel.Conflict:
            return {"ok": False, "kind": "conflict"}
        except filemodel.EncodingFailure as e:
            return {"ok": False, "kind": "encoding", "encoding": e.encoding,
                    "chars": e.chars}
        except OSError as e:
            return {"ok": False, "kind": "error", "message": str(e)}
        return {"ok": True, "stamp": new_stamp}

    def render(self, text, path=None):
        base = os.path.dirname(path) if path else ""
        html = self._md.render(text, {"base": base})
        return sanitize(html, lambda src: inline_image(src, base))

    def resolve_link(self, current, href):
        """文書内の相対リンクを開く先に解決する。Markdown 以外は開かない。"""
        from urllib.parse import unquote
        target = unquote(href.split("#")[0])
        if not target or not current:
            return None
        path = os.path.normpath(os.path.join(os.path.dirname(current), target))
        return path if os.path.isfile(path) and is_markdown(path) else None

    # --- Mermaid の追加アイコン（Architecture Diagram の `logos:slack-icon` など）---------
    def list_icon_packs(self):
        folder = resource_path(os.path.join("vendor", "icons"))
        try:
            return sorted(n[:-8] for n in os.listdir(folder) if n.endswith(".json.gz"))
        except OSError:
            return []

    def get_icon_pack(self, name):
        """アイコン集（iconify の JSON）を返す。図でそのアイコンが要るときだけ画面が取りに来る。"""
        if not re.fullmatch(r"[a-z0-9-]+", name or ""):
            return None
        path = os.path.join(resource_path(os.path.join("vendor", "icons")), name + ".json.gz")
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def get_mermaid(self):
        """Mermaid 本体。図があるときだけ画面が取りに来る（3.5MB あるため）。"""
        if self._mermaid is None:
            with open(resource_path("vendor/mermaid.min.js"), encoding="utf-8") as f:
                self._mermaid = f.read()
        return self._mermaid

    def open_external(self, url):
        if url.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(url)

    # --- 印刷・PDF ----------------------------------------------------------
    def get_print_prefs(self):
        return load_settings().get("print", {})

    def set_print_prefs(self, prefs):
        settings = load_settings()
        settings["print"] = prefs
        save_settings(settings)

    def print_printers(self):
        try:
            return printing.list_printers()
        except Exception:
            return {"printers": [], "default": ""}

    def print_check_ranges(self, text, total):
        try:
            return {"ok": True, "ranges": printing.parse_ranges(text, total or None)}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def _print_call(self, fn):
        try:
            return {"ok": True, **(fn() or {})}
        except printing.PrintError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:                      # 画面へは文言で返す（原因が分かるように）
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def print_count(self, opts):
        return self._print_call(lambda: {"pages": printing.count_pages(self._window, opts)})

    def print_preview(self, opts, ranges):
        return self._print_call(lambda: printing.preview_pdf(
            self._window, opts, printing.parse_ranges(ranges)) and None)

    def print_save_pdf(self, opts, ranges, path):
        return self._print_call(lambda: printing.save_pdf(
            self._window, opts, printing.parse_ranges(ranges), path) and None)

    def print_send(self, opts, ranges):
        return self._print_call(lambda: printing.send_to_printer(
            self._window, opts, printing.parse_ranges(ranges)) and None)

    def pick_pdf_path(self, name, initial_dir=None):
        return dialogs.pick_save(self._initial_dir(initial_dir), name, "pdf")

    # --- クリップボード -----------------------------------------------------
    def clipboard_get(self):
        return clipboard.get_text()

    def clipboard_set(self, text):
        return clipboard.set_text(text)

    # --- ウィンドウ ---------------------------------------------------------
    def set_title(self, title):
        try:
            self._window.set_title(title)
        except Exception:
            pass

    def set_dirty(self, dirty):
        self._dirty = bool(dirty)

    def close_now(self):
        """画面で保存・破棄が済んだあとに閉じる。"""
        self._closing = True
        self._dirty = False
        self._window.destroy()

    def on_closing(self):
        """未保存があれば閉じずに、画面へ確認を出させる（False で閉じるのを止める）。"""
        if self._closing or not self._dirty:
            return True
        # closing は画面のスレッド上で呼ばれるので、画面への問い合わせは別スレッドで行う
        threading.Thread(
            target=lambda: self._window.evaluate_js("requestClose()"),
            daemon=True).start()
        return False


def build_html():
    """画面を組み立てる。部品は文字列として埋め込む（読み込み元を持たない画面のため）。"""
    def read(name):
        with open(resource_path(os.path.join("vendor", name)), encoding="utf-8") as f:
            return f.read()

    with open(resource_path("ui.html"), encoding="utf-8") as f:
        html = f.read()
    css = "\n".join(read(n) for n in ("codemirror.css", "dialog.css"))
    js = "\n".join(read(n) for n in (
        "codemirror.js", "meta.js", "xml.js", "markdown.js", "overlay.js",
        "dialog.js", "jump-to-line.js",
        "continuelist.js", "active-line.js", "placeholder.js"))
    with open(resource_path("format.js"), encoding="utf-8") as f:
        fmt = f.read()
    with open(resource_path("find.js"), encoding="utf-8") as f:
        find = f.read()
    with open(resource_path("print.js"), encoding="utf-8") as f:
        print_js = f.read()
    return (html.replace("/*VENDOR_CSS*/", css)
                .replace("/*FORMAT_JS*/", fmt)
                .replace("/*FIND_JS*/", find)
                .replace("/*PRINT_JS*/", print_js)
                .replace("/*VENDOR_JS*/", js.replace("</script", "<\\/script")))


# --- エクスプローラー連携 ----------------------------------------------------
def message(text, title=APP_NAME):
    ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)


def register_association():
    import winreg
    if not getattr(sys, "frozen", False):
        message("exe 版から実行してください。")
        return
    exe = sys.executable
    base = r"Software\Classes"

    def put(key, value, name=""):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    put(rf"{base}\{PROG_ID}", "Markdown 文書")
    put(rf"{base}\{PROG_ID}\DefaultIcon", f'"{exe}",0')
    put(rf"{base}\{PROG_ID}\shell\open", "Markdown エディタで開く")
    put(rf"{base}\{PROG_ID}\shell\open\command", f'"{exe}" "%1"')
    for ext in (".md", ".markdown"):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              rf"{base}\{ext}\OpenWithProgids") as k:
            winreg.SetValueEx(k, PROG_ID, 0, winreg.REG_NONE, b"")
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    message("登録しました。\n\nMarkdown ファイルを右クリック →「プログラムから開く」→"
            "「別のプログラムを選択」で「Markdown エディタで開く」を選び、"
            "「常に使う」を押すと、ダブルクリックで開けます。")


def unregister_association():
    import winreg

    def delete_tree(root, sub):
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_ALL_ACCESS) as k:
                while True:
                    try:
                        child = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    delete_tree(root, rf"{sub}\{child}")
            winreg.DeleteKey(root, sub)
        except OSError:
            pass

    base = r"Software\Classes"
    delete_tree(winreg.HKEY_CURRENT_USER, rf"{base}\{PROG_ID}")
    for ext in (".md", ".markdown"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                rf"{base}\{ext}\OpenWithProgids", 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, PROG_ID)
        except OSError:
            pass
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    message("登録を解除しました。")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--register":
        register_association()
        return
    if args and args[0] == "--unregister":
        unregister_association()
        return

    import webview
    start = os.path.abspath(args[0]) if args else None
    api = Api(start)
    window = webview.create_window(
        APP_NAME, html=build_html(), js_api=api,
        width=1400, height=860, min_size=(800, 480))
    api._window = window
    window.events.closing += api.on_closing
    webview.start()


if __name__ == "__main__":
    main()
