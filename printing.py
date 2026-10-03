"""印刷と PDF 出力（Edge WebView2 の機能を使う）。ビューアとエディタで同じものを使う。

画面の文書を、印刷用の見た目（画面の部品を隠した本文だけ）で出力する。見た目は画面側の
`@media print` が決め、ここは出力の設定（用紙・余白・倍率・ページ範囲・プリンター）を渡す。

WebView2 は画面のスレッドからしか触れないため、呼び出しは画面スレッドへ渡し、完了の待ち合わせは
呼び出し元のスレッドで行う（画面スレッドで待つと、出力の完了を処理できず固まる）。
"""
import os
import re
import tempfile
import time

INCH_PER_MM = 1 / 25.4
# 用紙の大きさ（縦向きのときの 幅, 高さ。単位はインチ）
PAPERS = {
    "A4": (210 * INCH_PER_MM, 297 * INCH_PER_MM),
    "A3": (297 * INCH_PER_MM, 420 * INCH_PER_MM),
    "B5": (182 * INCH_PER_MM, 257 * INCH_PER_MM),       # JIS B5
    "B4": (257 * INCH_PER_MM, 364 * INCH_PER_MM),       # JIS B4
    "Letter": (8.5, 11.0),
}
# 余白（mm）
MARGINS = {"標準": 15, "狭い": 8, "広い": 25, "なし": 0}
TIMEOUT = 180


class PrintError(Exception):
    """利用者に伝える文言を持つ失敗。"""


# ---- ページ範囲 ---------------------------------------------------------------
def parse_ranges(text, total=None):
    """「1-3,5」「全角の１ー３、５」「5-」などを、WebView2 に渡せる形に直す。

    空なら "" （全ページ）。誤りは ValueError（利用者に見せる文言）。
    total を渡すと、ページ数を超える指定も誤りにする。
    """
    t = (text or "").translate(str.maketrans("０１２３４５６７８９，、－ー～〜−", "0123456789,,-----"))
    t = re.sub(r"\s+", "", t)
    if not t:
        return ""
    parts = []
    for item in t.split(","):
        if not item:
            raise ValueError("カンマの前後に数字がありません")
        m = re.fullmatch(r"(\d+)(?:(-)(\d*))?", item)
        if not m:
            raise ValueError(f"「{item}」は指定できません（例: 1-3,5）")
        start = int(m.group(1))
        if m.group(2):
            if m.group(3):
                end = int(m.group(3))
            elif total:
                end = total                                  # 「5-」は最後まで
            else:
                raise ValueError("「5-」の形はページ数が分かってから使えます")
        else:
            end = start
        if start < 1:
            raise ValueError("ページは1から数えます")
        if end < start:
            raise ValueError(f"「{item}」は逆順です")
        if total and (start > total or end > total):
            raise ValueError(f"全 {total} ページを超えています")
        parts.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(parts)


def count_pdf_pages(data):
    """Chromium が書いた PDF のページ数。"""
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", data))


# ---- WebView2 の呼び出し -----------------------------------------------------
def _core(window):
    return window.native.browser.webview.CoreWebView2


def _on_ui(window, fn):
    """fn を画面スレッドで実行して結果を返す。"""
    from System import Action
    box = {}

    def run():
        try:
            box["v"] = fn()
        except BaseException as e:               # noqa: BLE001  画面スレッドの例外は呼び出し元へ運ぶ
            box["e"] = e

    window.native.Invoke(Action(run))
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _wait(task):
    deadline = time.time() + TIMEOUT
    while not task.IsCompleted:
        if time.time() > deadline:
            raise PrintError("時間内に終わりませんでした")
        time.sleep(0.05)
    if task.IsFaulted:
        inner = task.Exception.InnerException if task.Exception is not None else None
        raise PrintError(str(inner or task.Exception))
    if task.IsCanceled:
        raise PrintError("取り消されました")
    return task.Result


def _settings(window, o, ranges, for_print=False):
    import Microsoft.Web.WebView2.Core as C
    s = _core(window).Environment.CreatePrintSettings()
    width, height = PAPERS.get(o.get("paper"), PAPERS["A4"])
    landscape = bool(o.get("landscape"))
    s.Orientation = C.CoreWebView2PrintOrientation.Landscape if landscape else C.CoreWebView2PrintOrientation.Portrait
    s.PageWidth, s.PageHeight = width, height        # 縦向きの寸法を渡す（向きの指定で縦横が入れ替わる）
    margin = MARGINS.get(o.get("margin"), MARGINS["標準"]) * INCH_PER_MM
    s.MarginTop = s.MarginBottom = s.MarginLeft = s.MarginRight = margin
    s.ScaleFactor = max(0.1, min(2.0, float(o.get("scale") or 1.0)))
    s.ShouldPrintBackgrounds = bool(o.get("backgrounds"))
    s.ShouldPrintHeaderAndFooter = bool(o.get("header_footer"))
    s.HeaderTitle = o.get("title") or ""
    s.FooterUri = o.get("uri") or ""
    if ranges:
        s.PageRanges = ranges
    if for_print:
        if o.get("printer"):
            s.PrinterName = o["printer"]
        s.Copies = max(1, min(99, int(o.get("copies") or 1)))
        s.ColorMode = (C.CoreWebView2PrintColorMode.Grayscale if o.get("mono")
                       else C.CoreWebView2PrintColorMode.Color)
    return s


def _to_pdf(window, o, ranges, path):
    def start():
        return _core(window).PrintToPdfAsync(path, _settings(window, o, ranges))

    ok = _wait(_on_ui(window, start))
    if not ok or not os.path.exists(path):
        raise PrintError("PDF を作れませんでした")


# ---- 画面から呼ばれる操作 ----------------------------------------------------
def list_printers():
    import clr
    clr.AddReference("System.Drawing")
    from System.Drawing.Printing import PrinterSettings
    names = [str(n) for n in PrinterSettings.InstalledPrinters]
    default = str(PrinterSettings().PrinterName) if names else ""
    return {"printers": names, "default": default}


def count_pages(window, o):
    """この設定で印刷したときの全ページ数。"""
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="mdprint_")
    os.close(fd)
    try:
        _to_pdf(window, o, "", path)
        with open(path, "rb") as f:
            return count_pdf_pages(f.read())
    finally:
        _remove(path)


def save_pdf(window, o, ranges, path):
    _to_pdf(window, o, ranges, path)
    return path


def preview_pdf(window, o, ranges):
    """一時 PDF を作り、既定の PDF 表示アプリで開く（印刷の仕上がり確認用）。"""
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="mdpreview_")
    os.close(fd)
    _to_pdf(window, o, ranges, path)
    os.startfile(path)                       # 開いたあとに消すと表示できないので、一時フォルダーに残す
    return path


def send_to_printer(window, o, ranges):
    import Microsoft.Web.WebView2.Core as C

    def start():
        return _core(window).PrintAsync(_settings(window, o, ranges, for_print=True))

    status = _wait(_on_ui(window, start))
    if status == C.CoreWebView2PrintStatus.Succeeded:
        return True
    if status == C.CoreWebView2PrintStatus.PrinterUnavailable:
        raise PrintError("プリンターを使えません（電源・接続・プリンターの選択を確認してください）")
    raise PrintError("印刷されませんでした（プリンター側の画面で取り消したときも、この表示になります）")


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
