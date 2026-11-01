"""ウィンドウへのファイル／フォルダーのドロップを受ける（ビューア・エディタ共通）。

- 開くのは「Markdown ファイル1つ」か「フォルダー1つ」だけ。ほかのファイル、複数のドロップは無視する。
- ドロップを受けないと、WebView2 がファイルをブラウザーで開こうとする。そのため、無視する場合も
  必ず既定の動作（ブラウザーの起動）を止める。
- ドラッグ中に絶え間なく出る dragover は、ここ（pywebview の DOM イベント）では受けない。1回ごとにイベント
  全体をシリアライズして Python へ送るため、実測で1回 0.1〜0.3 秒かかり、画面が固まってドロップが
  遅れた。dragover の既定の動作を止める処理は、画面側（ui.html）の素の JavaScript に置く。
- 実際のパスは、pywebview がドロップの直前にネイティブ側で拾った値（`pywebviewFullPath`）から得る。
"""
import json
import os

from webview.dom import DOMEventHandler


def dropped_paths(event):
    """ドロップのイベントから、ファイル・フォルダーの実パスを集める（取れなかったものは含めない）。"""
    try:
        files = event["dataTransfer"].get("files", [])
    except (KeyError, TypeError, AttributeError):
        return []
    return [f["pywebviewFullPath"] for f in files if isinstance(f, dict) and f.get("pywebviewFullPath")]


def classify(paths, is_markdown):
    """開く対象を決める。('folder', パス) / ('file', パス) / 無視するなら None。"""
    if len(paths) != 1:
        return None
    path = paths[0]
    if os.path.isdir(path):
        return ("folder", path)
    if os.path.isfile(path) and is_markdown(path):
        return ("file", path)
    return None


def install(window, is_markdown, notify=None):
    """document にドロップの受け口を付ける。notify(kind, path) は、開く対象が決まったときに呼ぶ。"""
    def on_drop(event):
        target = classify(dropped_paths(event), is_markdown)
        if target and notify:
            notify(*target)

    window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True, stop_propagation=True)


def open_in_window(window):
    """画面側の handleDrop(kind, path) を呼ぶ notify を返す。"""
    def notify(kind, path):
        window.evaluate_js("handleDrop(%s, %s)" % (json.dumps(kind), json.dumps(path)))
    return notify
