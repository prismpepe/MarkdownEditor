"""画面の設定（フォント・表示倍率・ウィンドウの位置と大きさ）の検査と、システムのフォント一覧。

設定ファイル（settings.json）は手で書き換えられることもあるので、読むときも書くときも、
ここで型と範囲を確かめてから使う。範囲を外れたものは、その項目だけ「既定」に戻す。
"""
import os
import re

# 部品ごとの文字サイズ(px)の範囲。None は「大きさは指定しない」（見出しは本文に対する比率で決まる）
FONT_PARTS = {"ui": (8, 40), "editor": (8, 60), "body": (8, 60), "head": None, "code": (8, 60), "diagram": (8, 60)}
HEAD_LEVELS = ("h1", "h2", "h3", "h4")
HEAD_SIZE = (8, 120)
ZOOM_MIN, ZOOM_MAX = 0.1, 5.0
WINDOW_MIN = (640, 400)
WINDOW_MAX = (10000, 10000)

_BAD_CHARS = re.compile(r"[\"'`;{}<>\\\r\n\t]")     # CSS を壊す文字は、フォント名から取り除く


def clean_family(value):
    """フォント名（1つだけ）。使えない文字を取り除く。空は「既定」。
    昔の設定ファイルにカンマ区切りの複数指定があったときは、最初の1つだけを使う。"""
    if not isinstance(value, str):
        return ""
    for part in value.split(","):
        name = _BAD_CHARS.sub("", part).strip()
        if name:
            return name[:100]
    return ""


def clean_size(value, lo, hi):
    """文字サイズ(px)。範囲外・数でないものは 0（= 既定）。"""
    if isinstance(value, bool):
        return 0
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return 0
    return n if lo <= n <= hi else 0


def clean_fonts(value):
    out = {}
    if not isinstance(value, dict):
        return out
    for part, limits in FONT_PARTS.items():
        item = value.get(part)
        if not isinstance(item, dict):
            continue
        entry = {"family": clean_family(item.get("family"))}
        if limits:
            entry["size"] = clean_size(item.get("size"), *limits)
        if part == "head":                  # 見出しは H1〜H4 の大きさを、それぞれ設定できる
            raw = item.get("sizes")
            sizes = {}
            if isinstance(raw, dict):
                for level in HEAD_LEVELS:
                    n = clean_size(raw.get(level), *HEAD_SIZE)
                    if n:
                        sizes[level] = n
            entry["sizes"] = sizes
        out[part] = entry
    return out


def clean_zoom(value):
    if not isinstance(value, dict):
        return None
    try:
        z = float(value.get("value"))
    except (TypeError, ValueError):
        return None
    if z != z or not (ZOOM_MIN <= z <= ZOOM_MAX):       # z != z は NaN
        return None
    return {"value": round(z, 2), "fit": bool(value.get("fit"))}


def clean_toc(value):
    """目次の指定（含める見出しの範囲と、「目次」という見出しを除くか）。"""
    if not isinstance(value, dict):
        return None
    lo, hi = value.get("min"), value.get("max")
    for n in (lo, hi):
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 6:
            return None
    if lo > hi:
        return None
    return {"min": lo, "max": hi, "skip": bool(value.get("skip"))}


def clean_prefs(patch):
    """画面から受け取った設定のうち、正しいものだけを返す（書き込んでよい項目に限る）。"""
    out = {}
    if not isinstance(patch, dict):
        return out
    if "fonts" in patch:
        out["fonts"] = clean_fonts(patch["fonts"])
    if "zoom" in patch:
        zoom = clean_zoom(patch["zoom"])
        if zoom:
            out["zoom"] = zoom
    if "side_hidden" in patch:
        out["side_hidden"] = bool(patch["side_hidden"])
    if "toc" in patch:
        toc = clean_toc(patch["toc"])
        if toc:
            out["toc"] = toc
    return out


VIEWS = ("triple", "split", "edit", "preview")      # 3画面・2画面・編集のみ・プレビューのみ
SPLIT_RANGE = (5, 95)


def clean_layout(patch):
    """編集画面の配置（表示モード・分割位置）。旧版の editorSize（編集欄の文字サイズ）も読めるようにする。"""
    out = {}
    if not isinstance(patch, dict):
        return out
    if patch.get("view") in VIEWS:
        out["view"] = patch["view"]
    if patch.get("layout_v") == 2 and not isinstance(patch.get("layout_v"), bool):
        out["layout_v"] = 2                  # 表示モードを新しい4つにしたあとの設定、という印（旧版の設定と区別する）
    s = patch.get("split")
    if not isinstance(s, bool) and isinstance(s, (int, float)) and s == s \
            and SPLIT_RANGE[0] <= s <= SPLIT_RANGE[1]:
        out["split"] = int(round(s))
    n = clean_size(patch.get("editorSize"), *FONT_PARTS["editor"])
    if n:
        out["editorSize"] = n
    return out


def clean_window(value):
    """保存してあるウィンドウの位置・大きさ。使える項目だけ返す。"""
    out = {}
    if not isinstance(value, dict):
        return out

    def integer(key, lo, hi):
        v = value.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            return None
        v = int(v)
        return v if lo <= v <= hi else None

    w = integer("width", WINDOW_MIN[0], WINDOW_MAX[0])
    h = integer("height", WINDOW_MIN[1], WINDOW_MAX[1])
    if w is not None and h is not None:
        out["width"], out["height"] = w, h
    x, y = integer("x", -32000, 32000), integer("y", -32000, 32000)
    if x is not None and y is not None:
        out["x"], out["y"] = x, y
    if value.get("maximized") is True:
        out["maximized"] = True
    return out


def virtual_screen():
    """すべてのモニターを含む範囲 (左, 上, 幅, 高さ)。分からなければ None。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        u = ctypes.windll.user32
        return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
                u.GetSystemMetrics(78), u.GetSystemMetrics(79))
    except Exception:
        return None


def place_visible(geo, screen, need_w=120, need_h=60):
    """保存した位置のウィンドウが、いまの画面の中に十分見えるか。
    モニターを外したあとなどに、画面の外へ出てしまうのを防ぐ。"""
    if "x" not in geo or "y" not in geo or screen is None:
        return False
    sl, st, sw, sh = screen
    w, h = geo.get("width", 1200), geo.get("height", 800)
    left, top = max(geo["x"], sl), max(geo["y"], st)
    right, bottom = min(geo["x"] + w, sl + sw), min(geo["y"] + h, st + sh)
    return right - left >= min(need_w, w) and bottom - top >= min(need_h, h)


def list_system_fonts():
    """インストールされているフォントの名前（重複なし）。取れなければ空。"""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class LOGFONTW(ctypes.Structure):
            _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG),
                        ("lfEscapement", wintypes.LONG), ("lfOrientation", wintypes.LONG),
                        ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                        ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE),
                        ("lfCharSet", wintypes.BYTE), ("lfOutPrecision", wintypes.BYTE),
                        ("lfClipPrecision", wintypes.BYTE), ("lfQuality", wintypes.BYTE),
                        ("lfPitchAndFamily", wintypes.BYTE), ("lfFaceName", wintypes.WCHAR * 32)]

        names = set()
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(LOGFONTW),
                                           ctypes.c_void_p, wintypes.DWORD, wintypes.LPARAM)

        def callback(lf, _metrics, _type, _lparam):
            name = lf.contents.lfFaceName
            if name and not name.startswith("@"):        # @ は縦書き用の別名
                names.add(name)
            return 1

        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        user32.GetDC.restype = ctypes.c_void_p
        user32.GetDC.argtypes = [ctypes.c_void_p]
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        gdi32.EnumFontFamiliesExW.argtypes = [ctypes.c_void_p, ctypes.POINTER(LOGFONTW),
                                              callback_type, wintypes.LPARAM, wintypes.DWORD]
        query = LOGFONTW()
        query.lfCharSet = 1                              # DEFAULT_CHARSET: すべての文字セット
        hdc = user32.GetDC(None)
        try:
            cb = callback_type(callback)                 # 参照を保って、列挙の間に消えないようにする
            gdi32.EnumFontFamiliesExW(hdc, ctypes.byref(query), cb, 0, 0)
        finally:
            user32.ReleaseDC(None, hdc)
        return sorted(names, key=str.casefold)
    except Exception:
        return []
