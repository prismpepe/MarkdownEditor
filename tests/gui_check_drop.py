"""ウィンドウへのドロップ（Markdown ファイル1つ／フォルダー1つ）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_drop.py

エクスプローラーからの本物のドロップは再現できないので、pywebview がネイティブ側で拾うパスの記録
（_dnd_state）を直接書き込み、画面にはドロップのイベントを送る。確かめるのは「イベント → 実パスの
取得 → 対象の判定 → 画面の処理」の経路。設定の置き場所は一時フォルダーへ向ける。
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor
from webview.dom import _dnd_state

tmp = tempfile.mkdtemp()
dir_a = os.path.join(tmp, '資料 A')
dir_b = os.path.join(tmp, 'B')
os.makedirs(dir_a)
os.makedirs(dir_b)
doc_a = os.path.join(dir_a, '最初.md')
doc_b = os.path.join(dir_b, '別.md')
txt_b = os.path.join(dir_b, 'メモ.txt')
TEXT_B = '# 別のフォルダーの文書\n'
open(doc_a, 'w', encoding='utf-8', newline='\n').write('# 最初の文書\n')
open(doc_b, 'w', encoding='utf-8', newline='\n').write(TEXT_B)
open(txt_b, 'w', encoding='utf-8').write('text')

api = mdeditor.Api(doc_a)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=860, x=20, y=20)
api._window = w
results = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def drop(*paths, target="document.body"):
    """ネイティブ側が拾うパスの記録を用意し、ドロップのイベントを送る。返り値: 既定の動作を止めたか"""
    for p in paths:
        _dnd_state['paths'].append((os.path.basename(p), p))
    names = json.dumps([os.path.basename(p) for p in paths])
    prevented = js("""(() => {
        const dt = new DataTransfer();
        for (const n of %s) dt.items.add(new File(['混入する中身'], n));
        const e = new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true });
        %s.dispatchEvent(e);
        return e.defaultPrevented; })()""" % (names, target))
    time.sleep(2.5)
    return prevented


def cur_path():
    return js("doc.path")


def folder():
    return js("document.getElementById('folder').textContent")


def drive():
    time.sleep(8)
    mdeditor._install_drop(w)
    time.sleep(2)
    # 疑似のファイルは、実ファイルを渡すネイティブ呼び出しに通せないので、この呼び出しだけ空にする（本物のドロップでは使われる）
    js("chrome.webview.postMessageWithAdditionalObjects = () => {}")
    check("最初のファイルが開いている", cur_path(), doc_a)

    over = js("""(() => { const e = new DragEvent('dragover', { bubbles: true, cancelable: true });
        document.body.dispatchEvent(e); return e.defaultPrevented; })()""")
    check("ドラッグ中、既定の動作（ブラウザーで開く）を止める", over, True)

    # 編集欄の上にドロップしても、ファイルの中身（疑似ファイルの「混入する中身」）は挿入されない
    check("編集欄へのドロップ: 既定の動作を止める", drop(doc_b, target="document.querySelector('.CodeMirror-scroll')"), True)
    check("Markdown ファイルをドロップすると、それが開く", cur_path(), doc_b)
    check("編集欄には、開いたファイルの中身だけが入る（ドロップの中身は挿入されない）", js("cm.getValue()"), TEXT_B)
    check("そのファイルのフォルダーの一覧になる", folder(), dir_b)

    check("Markdown 以外のファイルは、既定の動作を止めたうえで無視する", drop(txt_b), True)
    check("Markdown 以外は開かない（表示はそのまま）", (cur_path(), js("cm.getValue()")), (doc_b, TEXT_B))

    drop(doc_a, doc_b)
    check("複数ファイルのドロップは無視する", cur_path(), doc_b)

    drop(dir_a)
    check("フォルダーをドロップすると、そのフォルダーの一覧になる", folder(), dir_a)
    check("フォルダーを変えたので、開いていた文書は閉じて空白になる", (cur_path(), js("cm.getValue()")), (None, ''))

    drop(doc_b)
    check("続けてファイルをドロップしても開ける", cur_path(), doc_b)

    print("RESULT", sum(results), "/", len(results), flush=True)
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
