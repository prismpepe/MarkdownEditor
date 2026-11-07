"""検査（lint）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_lint.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。
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

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=900, x=20, y=20)
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
        time.sleep(.2)
    return bool(js(code))


def set_text(text):
    js("cm.setValue(%s)" % json.dumps(text))


def rows():
    return js("[...document.querySelectorAll('#lintList .lrow')].map(r => r.querySelector('.rid').textContent + '@' + r.dataset.line)")


def drive():
    time.sleep(8)
    wait("document.getElementById('lintBtn') && lint.rules.length > 0")
    check("規則の一覧を Python から受け取る（24 規則）", js("lint.rules.length"), 24)
    check("一覧は、はじめは閉じている", js("document.getElementById('lintPanel').hidden"), True)
    check("空の文書は「問題なし」", wait("document.getElementById('lintBtn').textContent.includes('問題なし')"), True)

    # 自動検査（編集のあと少し待つと現れる）
    set_text("# 題名\n\n### 飛んだ見出し\n\n#見出しでない\n")
    check("自動検査: 編集のあと、状態表示欄に件数が出る",
          wait("document.getElementById('lintBtn').textContent.includes('⚠')"), True)
    check("件数は ⚠ 2 件（MD001・MD018）", js("document.getElementById('lintBtn').querySelector('.w').textContent.trim()"), '⚠ 2')
    check("行番号の横の印が、2 行に付く", js("document.querySelectorAll('.lint-mark').length"), 2)
    check("印は警告の色", js("document.querySelectorAll('.lint-mark.warning').length"), 2)
    check("印にカーソルを置くと、規則と内容が出る", js("document.querySelector('.lint-mark').title.startsWith('MD001 ')"), True)

    # 一覧
    js("document.getElementById('lintBtn').click()")
    check("状態表示欄のボタンで、一覧が開く", js("document.getElementById('lintPanel').hidden"), False)
    check("一覧の行（行番号は 0 から）", rows(), ['MD001@2', 'MD018@4'])
    check("見出し（件数）", js("document.getElementById('lintCount').textContent"), '警告 2 件 / 情報 0 件')
    check("一覧の開閉が、設定に残る", js("prefs.lint.open"), True)
    js("document.querySelectorAll('#lintList .lrow')[1].click()")
    check("行をクリックすると、その行へ移る", js("cm.getCursor().line"), 4)
    check("編集欄に焦点が移る", js("cm.hasFocus()"), True)

    # 自動検査を切る
    js("document.getElementById('lintRules').click()")
    check("「ルール…」で、ダイアログが開く", js("!document.getElementById('lveil').hidden"), True)
    check("規則の欄が 24 件", js("document.querySelectorAll('#lRules .lr').length"), 24)
    check("既定で切っている規則（MD010・MD026・MD040・MD045）は、チェックが外れている",
          js("[...document.querySelectorAll('#lRules .lr')].filter(d => !d.querySelector('input').checked).map(d => d.querySelector('.id').textContent)"),
          ['MD010', 'MD026', 'MD040', 'MD045'])
    check("ダイアログが開いている間は、Ctrl+N を受けない",
          (js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'n', ctrlKey: true, bubbles: true, cancelable: true}))"), time.sleep(.3), js("cm.getValue().startsWith('# 題名')"))[2], True)
    # MD001 のチェックを外す
    js("[...document.querySelectorAll('#lRules .lr')].find(d => d.querySelector('.id').textContent === 'MD001').querySelector('input').click()")
    check("規則を止めると、その指摘が消える", wait("document.querySelectorAll('#lintList .lrow').length === 1"), True)
    check("止めた規則が、設定に残る", js("prefs.lint.disabled.includes('MD001')"), True)
    # MD040 を有効にする
    set_text("```\nコード\n```\n")
    js("[...document.querySelectorAll('#lRules .lr')].find(d => d.querySelector('.id').textContent === 'MD040').querySelector('input').click()")
    check("既定で切っていた規則を入れると、指摘が出る", wait("document.querySelectorAll('#lintList .lrow').length === 1 && document.querySelector('#lintList .rid').textContent === 'MD040'"), True)
    js("document.getElementById('lDefault').click()")
    check("「既定に戻す」で、MD001 が有効、MD040 が無効に戻る",
          js("[lint.rules.length, lintPref().disabled.includes('MD001'), lintPref().disabled.includes('MD040')]"), [24, False, True])
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
    check("Esc でダイアログが閉じる", js("document.getElementById('lveil').hidden"), True)

    # 自動検査を切ると、編集しても更新されない
    js("document.getElementById('lintRules').click()")
    js("document.getElementById('lAuto').click()")
    js("document.getElementById('lClose').click()")
    check("自動検査を切った設定が残る", js("prefs.lint.auto"), False)
    set_text("# a\n\n### b\n")
    time.sleep(1.4)
    check("自動検査が切れていると、編集しても一覧は変わらない（古いと知らせる）",
          js("[document.getElementById('lintCount').textContent.includes('編集しました'), document.querySelectorAll('#lintList .lrow').length]"), [True, 0])
    js("document.getElementById('lintNow').click()")
    check("「いま検査する」で更新される", wait("document.querySelectorAll('#lintList .lrow').length === 1"), True)
    js("document.getElementById('lintRules').click()")
    js("document.getElementById('lAuto').click()")
    js("document.getElementById('lClose').click()")

    # 数式・図の誤りは、描いた結果から集める
    set_text("# 数式\n\n$$\n\\frac{\n$$\n\n文中の $\\unknowncommand$ です。\n")
    check("数式の誤り（X009）が、一覧に出る",
          wait("[...document.querySelectorAll('#lintList .rid')].filter(r => r.textContent === 'X009').length === 2", 25), True)
    check("数式の誤りの行は、その数式の行", js("[...new Set([...document.querySelectorAll('#lintList .lrow')].filter(r => r.querySelector('.rid').textContent === 'X009').map(r => r.dataset.line))].sort().join()"), '2,6')
    set_text("# 図\n\n```mermaid\ngraph TD\n  A --> \n  B[[[\n```\n")
    check("図の誤り（X010）が、一覧に出る",
          wait("[...document.querySelectorAll('#lintList .rid')].some(r => r.textContent === 'X010')", 40), True)

    # 保存先が分かる文書では、ファイルの有無を調べる
    set_text("![ない](nothing_here.png)\n\n[ない](nothing_here.pdf)\n")
    js("doc.path = %s" % json.dumps(os.path.join(tempfile.gettempdir(), 'lint_doc.md')))
    js("runLint()")
    check("画像とリンクのファイルが無いと指摘する（X001・X002）",
          wait("[...document.querySelectorAll('#lintList .rid')].map(r => r.textContent).sort().join() === 'X001,X002'"), True)

    # 大きな文書は省く
    js("doc.path = null")
    set_text("a\n" * 10)
    js("document.getElementById('lintBtn').click()")
    check("一覧を閉じられる", js("document.getElementById('lintPanel').hidden"), True)
    check("閉じた状態が、設定に残る", js("prefs.lint.open"), False)

    # 編集で行がずれても、印は行についていく
    set_text("#見出しでない\n\n本文\n")
    wait("document.querySelectorAll('.lint-mark').length === 1")
    js("cm.replaceRange('先頭に1行\\n\\n', {line: 0, ch: 0})")
    check("先頭に行を足すと、印も下の行へ動く", js("(() => { const i = cm.lineInfo(2); return !!(i.gutterMarkers && i.gutterMarkers['lint-gutter']) })()"), True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
