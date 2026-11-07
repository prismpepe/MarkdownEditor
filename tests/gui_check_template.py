"""テンプレートから新規作成を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_template.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。エクスプローラーは、実際には開かない。
"""
import datetime
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
os.startfile = lambda p: None                      # 「テンプレートの場所を開く」で、エクスプローラーを開かない
import webview
import mdeditor

api = mdeditor.Api(None)
os.makedirs(api.template_folder())
open(os.path.join(api.template_folder(), '週報.md'), 'w', encoding='utf-8').write("# {{週}}週報\n\n担当: {{担当:山田}}\n作成: {{日付}}\n")
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


def open_dialog():
    js("document.getElementById('bTemplate').click()")
    wait("!document.getElementById('mveil').hidden && document.getElementById('mList').value")
    time.sleep(.5)


def key(code, key_, target="document"):
    js("%s.dispatchEvent(new KeyboardEvent('keydown', {key: %s, bubbles: true, cancelable: true}))" % (target, json.dumps(key_)))


def drive():
    time.sleep(8)
    today = datetime.date.today().strftime('%Y-%m-%d')

    check("ツールバーに「テンプレート」ボタンがあり、新規の隣", js("document.getElementById('bNew').nextElementSibling.id"), 'bTemplate')
    check("ダイアログは、はじめは閉じている", js("document.getElementById('mveil').hidden"), True)

    open_dialog()
    check("ダイアログが開く", js("!document.getElementById('mveil').hidden"), True)
    check("一覧: 組み込み 4 つと、自分のテンプレート 1 つ",
          js("[...document.querySelectorAll('#mList optgroup')].map(g => g.label + ':' + [...g.querySelectorAll('option')].map(o => o.textContent).join('/'))"),
          ['組み込み:議事録/リリースノート/日報・メモ/README のひな形', '自分のテンプレート:週報'])
    check("先頭のテンプレート（議事録）が選ばれ、入力欄が出る",
          js("[document.getElementById('mList').selectedOptions[0].textContent, [...document.querySelectorAll('#mFields input')].map(i => i.dataset.name)]"),
          ['議事録', ['会議名', '開始時刻', '場所', '出席者', '記録者']])
    check("既定値（開始時刻: 10:00）が、入力欄に入る", js("document.getElementById('mf_開始時刻').value"), '10:00')
    check("プレビューに、日付が自動で入る（欄の記法は、日付には残らない）", js("document.getElementById('mPrev').textContent.includes('日時: %s（')" % today), True)
    check("入力していない欄は、空で出る", js("document.getElementById('mPrev').textContent.startsWith('#  議事録')"), True)

    # 入力すると、プレビューが変わる
    js("(() => { const i = document.getElementById('mf_会議名'); i.value = '理事会'; i.dispatchEvent(new Event('input')); })()")
    ok = wait("document.getElementById('mPrev').textContent.startsWith('# 理事会 議事録')")
    check("入力すると、プレビューに反映される", ok, True)
    check("作る前に、欄の記法（{{）が、プレビューに残らない", js("document.getElementById('mPrev').textContent.includes('{{')"), False)

    # 作成: 新しい「無題」の文書になる
    js("cm.setValue('')")
    js("document.getElementById('mCreate').click()")
    ok = wait("document.getElementById('mveil').hidden && cm.getValue().startsWith('# 理事会 議事録')")
    check("作成すると、ダイアログが閉じ、本文が入る", ok, True)
    check("新しい文書は「無題」（ファイルが無い）で、欄の記法も残らない", (js("doc.path"), js("cm.getValue().includes('{{')")), (None, False))
    check("保存していない文書として扱われる（保存を促す）", js("isDirty()"), True)
    check("日付が、作った日で入る", js("cm.getValue().includes('日時: %s（')" % today), True)
    js("cm.undo()")
    time.sleep(.5)
    check("元に戻す（Ctrl+Z）と、空の文書に戻る", js("cm.getValue()"), '')

    # 保存していない変更があれば、先に確かめる。取り消したら、ダイアログは入力のまま戻る
    js("cm.setValue('書きかけ'); updateDirty()")
    open_dialog()
    js("(() => { const i = document.getElementById('mf_会議名'); i.value = '定例'; i.dispatchEvent(new Event('input')); })()")
    time.sleep(.5)
    js("document.getElementById('mCreate').click()")
    ok = wait("document.getElementById('veil').classList.contains('show')")
    check("保存していない変更があると、確認のダイアログが出る（テンプレートのダイアログは、隠れる）", (ok, js("document.getElementById('mveil').hidden")), (True, True))
    key(None, 'Escape')                                  # キャンセル
    wait("!document.getElementById('veil').classList.contains('show')")
    time.sleep(.3)
    check("キャンセルすると、文書はそのまま", js("cm.getValue()"), '書きかけ')
    check("キャンセルすると、ダイアログが、入力した内容のまま戻る", (js("document.getElementById('mveil').hidden"), js("document.getElementById('mf_会議名').value")), (False, '定例'))
    key(None, 'Escape')
    check("Esc で、ダイアログが閉じる", js("document.getElementById('mveil').hidden"), True)

    # 自分のテンプレート（フォルダーの .md）と、既定値と、Enter で作成
    js("cm.markClean(); doc.metaDirty = false; updateDirty()")
    open_dialog()
    js("(() => { const l = document.getElementById('mList'); l.value = [...l.options].find(o => o.textContent === '週報').value; l.dispatchEvent(new Event('change')); })()")
    wait("document.getElementById('mf_担当')")
    check("自分のテンプレート: 欄と既定値", js("[...document.querySelectorAll('#mFields input')].map(i => i.dataset.name + '=' + i.value)"), ['週=', '担当=山田'])
    js("(() => { const i = document.getElementById('mf_週'); i.value = '第3'; i.dispatchEvent(new Event('input')); i.focus(); })()")
    time.sleep(.4)
    js("document.getElementById('mf_週').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}))")
    ok = wait("document.getElementById('mveil').hidden && cm.getValue().startsWith('# 第3週報')")
    check("入力欄で Enter を押すと、作成される（既定値の「山田」と、日付が入る）",
          (ok, js("cm.getValue().includes('担当: 山田') && cm.getValue().includes('作成: %s')" % today)), (True, True))

    # 欄のないテンプレート
    open_dialog()
    js("(() => { const l = document.getElementById('mList'); l.value = 'builtin:日報・メモ'; l.dispatchEvent(new Event('change')); })()")
    wait("document.getElementById('mList').value === 'builtin:日報・メモ'")
    time.sleep(.4)
    check("日報・メモ: 欄は「題名」（既定: 日報）だけ", js("[...document.querySelectorAll('#mFields input')].map(i => i.dataset.name + '=' + i.value)"), ['題名=日報'])
    check("日報・メモ: プレビューの見出し（日付と曜日が自動で入る）", js("document.getElementById('mPrev').textContent.split('\\n')[0].startsWith('# %s（') && document.getElementById('mPrev').textContent.split('\\n')[0].endsWith('）日報')" % today), True)
    js("document.getElementById('mClose').click()")
    check("「閉じる」で、ダイアログが閉じる", js("document.getElementById('mveil').hidden"), True)

    # ダイアログが開いている間は、ほかのショートカットを受けない
    open_dialog()
    js("cm.setValue('X'); cm.markClean()")
    key(None, 's')
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'n', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(.4)
    check("ダイアログが開いている間は、Ctrl+N などを受けない（文書は、そのまま）", js("cm.getValue()"), 'X')
    js("document.getElementById('mClose').click()")

    # 場所を開く・ファイルを選ぶ
    open_dialog()
    js("document.getElementById('mOpenDir').click()")
    time.sleep(.6)
    check("「テンプレートの場所を開く」で、案内が出る（エクスプローラーは、実際には開かない）", js("document.getElementById('mInfo').textContent.includes('テンプレートの場所を開きました')"), True)
    js("document.getElementById('mClose').click()")

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
