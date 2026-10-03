"""Mermaid の Architecture Diagram で、追加アイコン（logos）が描かれることを画面で確かめる。

    .venv\\Scripts\\python tests\\gui_check_icons.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。
"""
import gzip
import json
import os
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor

# 同梱のアイコン集から、図で使うアイコンの描画データの一部を取り出しておく（描かれたかの目印にする）
pack = json.loads(gzip.open(os.path.join('vendor', 'icons', 'logos.json.gz'), 'rt', encoding='utf-8').read())


def marker(name):
    """図形の座標データの一部（ID を含まないので、描画時に書き換わらない）。"""
    m = re.search(r'd="([^"]{40,})"', pack['icons'][name]['body'])
    return m.group(1)[:40]


DIAGRAM = """architecture-beta
    group storage(logos:aws)[Storage]
    service slack(logos:slack-icon)[Slack]
    service lambda(logos:aws-lambda)[Lambda] in storage
    service bucket(logos:aws-s3)[Bucket] in storage
    service db(database)[DB]
    slack:R -- L:lambda
    lambda:R -- L:bucket
    bucket:B -- T:db
"""
UNKNOWN = """architecture-beta
    service a(nosuchpack:foo)[A]
    service b(server)[B]
    a:R -- L:b
"""

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1200, height=800, x=20, y=20)
api._window = w
results = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def wait(code, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        v = js(code)
        if v:
            return v
        time.sleep(.4)
    return js(code)


def drive():
    time.sleep(8)
    js("cm.setValue(%s)" % json.dumps("```mermaid\n" + DIAGRAM + "```\n"))
    wait("document.querySelectorAll('#preview .diagram svg').length >= 1")
    time.sleep(1.5)
    svg = js("document.querySelector('#preview .diagram') ? document.querySelector('#preview .diagram').innerHTML : ''") or ''
    check("図が描かれる（エラー表示ではない）", (bool(svg), js("document.querySelectorAll('#preview .diagram-error').length")), (True, 0))
    for name in ('slack-icon', 'aws-lambda', 'aws-s3'):
        check(f"追加アイコン logos:{name} が描かれる", marker(name) in svg, True)
    check("標準のアイコン（database）も描かれる", 'database' in svg.lower() or svg.count('<g') > 5, True)

    # 登録していないアイコン集は、エラーにせず代わりの印で描かれる
    js("cm.setValue(%s)" % json.dumps("```mermaid\n" + UNKNOWN + "```\n"))
    wait("document.querySelectorAll('#preview .diagram svg, #preview .diagram-error').length >= 1")
    time.sleep(1.5)
    check("未登録のアイコン集でも図は描かれる（落ちない）",
          (js("document.querySelectorAll('#preview .diagram svg').length >= 1"), js("document.querySelectorAll('#preview .diagram-error').length")), (True, 0))

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
