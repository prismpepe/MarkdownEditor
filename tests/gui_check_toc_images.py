"""画像の Base64 埋め込みと目次の作成を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_toc_images.py

確認ダイアログは、実際にボタンを押して進める。画像を選ぶ Windows のダイアログだけは、開くと止まるので、
選んだパスを返す関数に差し替える。設定の置き場所は一時フォルダーへ向ける。
"""
import base64
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

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'images'))
open(os.path.join(tmp, 'images', 'a.png'), 'wb').write(PNG)
open(os.path.join(tmp, 'picked.png'), 'wb').write(PNG + b'\x00')
big = os.urandom(3 * 1024 * 1024)
open(os.path.join(tmp, 'big.png'), 'wb').write(big)
DOC = ("# 題名\n\n## はじめに\n\n![図A](images/a.png)\n\n## 使い方\n\n### 手順\n\n"
       "<h2>HTML の見出し</h2>\n\n```\n# コードの中\n```\n\n本文の終わり\n")
doc = os.path.join(tmp, '手順書.md')
open(doc, 'w', encoding='utf-8', newline='\n').write(DOC)

api = mdeditor.Api(doc)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=860, x=20, y=20)
api._window = w
results = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def wait(code, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        if js(code):
            return True
        time.sleep(0.1)
    return bool(js(code))


def run(call):
    """画面の処理を始めて、確認ダイアログが出たら、その文面を返す（ダイアログは開いたまま）。"""
    js("window._done = false; %s.then(() => { window._done = true; })" % call)
    wait("document.getElementById('veil').classList.contains('show') || window._done", 20)
    return js("document.getElementById('veil').classList.contains('show') ? document.getElementById('dText').textContent : null")


def press(index_or_primary=None):
    js("(() => { const b = document.querySelectorAll('#dBtns button'); (document.querySelector('#dBtns button.primary') || b[0]).click(); })()"
       if index_or_primary is None else "document.querySelectorAll('#dBtns button')[%d].click()" % index_or_primary)
    wait("window._done", 30)


def text():
    return js("cm.getValue()")


def drive():
    time.sleep(8)
    js("openPath(%s)" % json.dumps(doc))
    wait("doc.path && cm.getValue().length > 0")
    time.sleep(1)
    check("文書が開いている", text(), DOC)
    check("ツールバーに「画像の挿入」と「目次」がある", js("[!!document.getElementById('fImage'), !!document.getElementById('fToc')]"), [True, True])

    # ---- 文書内の画像をすべて Base64 にする
    msg = run("embedAllImages()")
    check("確認ダイアログに、件数と画像名が出る", ('1 件の画像' in msg, 'a.png' in msg), (True, True))
    press(1)                                                    # 取り消し
    check("取り消すと、本文は変わらない", text(), DOC)
    run("embedAllImages()")
    press()
    t = text()
    check("参照形式になり、本文には Base64 が入らない", ('![図A][image1]' in t, '](data:' not in t), (True, True))
    check("文末に定義が入る", t.rstrip().split('\n')[-1].startswith('[image1]: data:image/png;base64,'), True)
    time.sleep(1.5)
    check("プレビューに画像が出る", js("document.querySelector('#preview img') && document.querySelector('#preview img').src.startsWith('data:image/png;base64,')"), True)
    js("cm.undo()")
    check("元に戻す（Ctrl+Z）1回で、変換前に戻る", text(), DOC)
    js("cm.redo()")

    # ---- ファイルへ戻す
    msg = run("embedBackToFiles()")
    check("戻す確認に、書き出すファイル名が出る", '手順書_001.png' in msg, True)
    press()
    t = text()
    check("相対パスの定義に戻る", '[image1]: images/手順書_001.png' in t and 'base64' not in t, True)
    check("画像ファイルが書き出される", open(os.path.join(tmp, 'images', '手順書_001.png'), 'rb').read(), PNG)
    js("cm.setValue(%s)" % json.dumps(DOC))

    # ---- 画像ファイルを選んで挿入（選ぶダイアログだけ差し替える）
    js("api.pick_image = () => Promise.resolve(%s)" % json.dumps(os.path.join(tmp, 'picked.png')))
    js("cm.setCursor({line: 0, ch: 0}); embedPickImage()")
    wait("cm.getValue().includes('[image1]: data:')", 10)
    t = text()
    check("カーソル位置に参照が入り、文末に定義が入る", (t.startswith('![picked][image1]# 題名'), t.rstrip().split('\n')[-1].startswith('[image1]: data:image/png;base64,')), (True, True))
    js("cm.setValue(%s)" % json.dumps(DOC))

    # ---- 画像を、パスで参照する書き方で挿入する（選択欄から）
    check("画像の挿入の選択肢", js("[...document.getElementById('fImage').options].map(o => o.textContent)"),
          ['画像の挿入…', '画像を選んで挿入（パスで参照）', '画像を選んで挿入（Base64 で埋め込み）', '文書内の画像をすべて Base64 に変換', 'Base64 の画像をファイルに戻す'])

    def pick(option):
        js("document.getElementById('fImage').value = %s; document.getElementById('fImage').dispatchEvent(new Event('change'))" % json.dumps(option))

    js("api.pick_image = (i, svg) => { window._svg = svg; return Promise.resolve(%s); }" % json.dumps(os.path.join(tmp, 'images', 'a.png')))
    js("cm.setValue(%s); cm.setCursor({line: 0, ch: 0})" % json.dumps("本文\n"))
    pick('ref')
    wait("cm.getValue().includes('![a](images/a.png)')", 10)
    check("パスで参照する書き方が、カーソルの位置に入る（相対パス）", js("cm.getValue()"), "![a](images/a.png)本文\n")
    check("パスで参照するときは、SVG も選べる", js("window._svg"), True)
    time.sleep(1.5)
    check("プレビューに画像が出る", js("!!document.querySelector('#preview img') && document.querySelector('#preview img').src.startsWith('data:image/png')"), True)
    js("cm.setValue('文字を選ぶ'); cm.setSelection({line: 0, ch: 0}, {line: 0, ch: 3})")
    pick('ref')
    wait("cm.getValue().includes('![文字を](')", 10)
    check("文字を選んでいれば、その文字が、画像の説明になる", js("cm.getValue()"), "![文字を](images/a.png)選ぶ")
    js("(() => { window._path = doc.path; doc.path = null; })()")
    js("cm.setValue(''); cm.setCursor({line: 0, ch: 0})")
    pick('ref')
    wait("cm.getValue().length > 0", 10)
    t = js("cm.getValue()")
    check("文書を保存していないときは、絶対パス（file:///）で入る", (t.startswith('![a](file:///'), t.endswith('/images/a.png)')), (True, True))
    js("doc.path = window._path")
    js("cm.undo()")
    js("cm.setValue(%s)" % json.dumps(DOC))

    # ---- 目次
    msg = run("tocDialog()")
    check("目次の確認ダイアログに、範囲の選択がある", js("[!!document.getElementById('tocMin'), !!document.getElementById('tocMax')]"), [True, True])
    js("document.getElementById('tocMax').value = '6'")
    js("cm.setCursor({line: 2, ch: 0})")
    press()
    t = text()
    check("印つきで目次が入る", ('<!-- toc -->' in t and '<!-- /toc -->' in t), True)
    check("コードブロックの中の # は入らない", 'コードの中' not in t.split('<!-- /toc -->')[0], True)
    check("HTML の見出しに id が付く", '<h2 id="html-の見出し">' in t, True)
    time.sleep(1.5)
    targets = js("[...document.querySelectorAll('#preview a[href^=\"#\"]')].map(a => decodeURIComponent(a.getAttribute('href').slice(1)))")
    check("目次のリンクが、プレビューに出る", len(targets) >= 5, True)
    check("目次のリンク先が、すべてプレビューに存在する（飛べる）",
          js("[...document.querySelectorAll('#preview a[href^=\"#\"]')].every(a => !!document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))))"), True)
    js("cm.undo()")
    check("元に戻す（Ctrl+Z）1回で、目次を入れる前に戻る", text(), DOC)
    js("cm.redo()")

    # ---- 更新
    js("cm.replaceRange('\\n## 追加した見出し\\n', {line: cm.lineCount() - 1, ch: 0})")
    run("tocDialog()")
    check("印があるときは「更新する」になる", js("document.querySelector('#dBtns button.primary').textContent"), '更新する')
    press()
    t = text()
    check("更新で、追加した見出しが目次に入る", '[追加した見出し]' in t, True)
    check("目次は1つだけ", t.count('<!-- toc -->'), 1)

    # ---- 大きな画像（3MB）でも、画面が固まらない
    js("cm.setValue(%s)" % json.dumps("# 大\n\n![大](big.png)\n"))
    t0 = time.time()
    run("embedAllImages()")
    press()
    check("3MB の画像を埋め込んでも、20秒以内に終わる", time.time() - t0 < 20, True)
    check("本文は短いまま（参照形式）", js("cm.getLine(2)"), '![大][image1]')
    t1 = time.time()
    js("cm.setCursor({line: 0, ch: 0}); cm.replaceSelection('x')")
    check("埋め込んだあとも、編集欄はすぐ応答する（2秒以内）", time.time() - t1 < 2, True)
    time.sleep(3)
    check("プレビューに大きな画像が出る", js("!!document.querySelector('#preview img') && document.querySelector('#preview img').src.length > 3000000"), True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
