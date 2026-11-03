"""表・データの取り込み（Excel のセル・CSV → Markdown の表・JSON）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_table.py

ボタンを実際に押して進める。Windows のファイル選択ダイアログだけは、開くと止まるので、選んだパスを返す関数に
差し替える。クリップボードは、確認のために書き換えるので、終わったら元に戻す。設定の置き場所は一時フォルダーへ向ける。
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
import clipboard
import mdeditor

TSV = "月\t売上\t備考\r\n一月\t1,234\t好調\r\n二月\t987\t\r\n"
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'data'))
CSV = "区分,件数\nA,10\nB,20\n"
csv_path = os.path.join(tmp, '売上.csv')
open(csv_path, 'wb').write(CSV.replace("\n", "\r\n").encode('cp932'))            # Excel が出す Shift-JIS の CSV
doc_path = os.path.join(tmp, '資料.md')
open(doc_path, 'w', encoding='utf-8', newline='\n').write("段落です。\n")

api = mdeditor.Api(doc_path)
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
        time.sleep(0.1)
    return bool(js(code))


def set_src(text):
    js("document.getElementById('tSrc').value = %s; document.getElementById('tSrc').dispatchEvent(new Event('input'))" % json.dumps(text))
    time.sleep(0.7)


def set_ctl(cid, value):
    if isinstance(value, bool):
        js("(() => { const e = document.getElementById(%s); e.checked = %s; e.dispatchEvent(new Event('change')); })()" % (json.dumps(cid), json.dumps(value)))
    else:
        js("(() => { const e = document.getElementById(%s); e.value = %s; e.dispatchEvent(new Event('change')); })()" % (json.dumps(cid), json.dumps(value)))
    time.sleep(0.5)


def visible(i):
    return js("(() => { const e = document.getElementById(%s); return e.getBoundingClientRect().height > 0 && getComputedStyle(e).display !== 'none'; })()" % json.dumps(i))


def preview():
    return js("document.getElementById('tPrev').textContent")


def drive():
    saved_clip = clipboard.get_text()
    try:
        time.sleep(8)
        js("openPath(%s)" % json.dumps(doc_path))
        wait("doc.path && cm.getValue().length > 0")
        time.sleep(1)

        # ---- 開く
        js("document.getElementById('fTable').click()")
        check("ボタンでダイアログが開く", visible('tdlg'), True)
        check("データが無いうちは、挿入できない", js("document.getElementById('tInsert').disabled"), True)
        check("Markdown の表のときは、JSON の項目と保存ボタンは出ない", (visible('tJsonOpts'), visible('tSave'), visible('tMdOpts')), (False, False, True))

        # ---- Excel のセルを貼り付け（クリップボードから）
        clipboard.set_text(TSV)
        js("document.getElementById('tClip').click()")
        wait("document.getElementById('tSrc').value.length > 0")
        time.sleep(0.8)
        check("クリップボードの内容が、貼り付け欄に入る（改行は、欄の仕様で LF にそろう）", js("document.getElementById('tSrc').value"), TSV.replace("\r\n", "\n"))
        check("列数・行数が出る", js("document.getElementById('tInfo').textContent"), "3 列 × 2 行（データ）")
        check("Markdown の表のプレビュー", preview().split("\n")[:2], ["| 月 | 売上 | 備考 |", "| --- | ---: | --- |"])

        # ---- 文書へ挿入（行の末尾で）
        js("cm.setCursor({line: 0, ch: 5})")
        js("document.getElementById('tInsert').click()")
        wait("document.getElementById('tveil').hidden")
        t = js("cm.getValue()")
        check("段落の後ろに、空行を挟んで表が入る", t.startswith("段落です。\n\n| 月 | 売上 | 備考 |\n| --- | ---: | --- |\n| 一月 | 1,234 | 好調 |\n| 二月 | 987 |  |\n"), True)
        time.sleep(1.5)
        check("プレビューに表が出て、数値の列は右寄せ", js("[document.querySelectorAll('#preview table').length, document.querySelectorAll('#preview td[style*=\"right\"]').length]"), [1, 2])
        js("cm.undo()")
        check("元に戻す（Ctrl+Z）1回で、挿入前に戻る", js("cm.getValue()"), "段落です。\n")

        # ---- 表のオプション
        js("document.getElementById('fTable').click()")
        set_src(TSV)
        set_ctl('tHead', False)
        check("1行目を見出しにしないと、列N が見出しになる", preview().split("\n")[0], "| 列1 | 列2 | 列3 |")
        set_ctl('tHead', True)
        set_ctl('tAlign', 'center')
        check("列の配置を中央にできる", preview().split("\n")[1], "| :---: | :---: | :---: |")
        set_ctl('tAlign', 'auto')
        set_src("a|b,c\n1,2\n")
        check("セルの中の縦線がエスケープされる", preview().split("\n")[0], "| a\\|b | c |")

        # ---- JSON
        set_src(TSV)
        set_ctl('tFmt', 'json')
        check("JSON のときは、JSON の項目と保存ボタンが出る", (visible('tJsonOpts'), visible('tSave'), visible('tMdOpts')), (True, True, False))
        data = json.loads(preview())
        check("JSON のプレビュー（数値は数値、空欄は null）", data, [{"月": "一月", "売上": 1234, "備考": "好調"}, {"月": "二月", "売上": 987, "備考": None}])
        set_ctl('tNum', False)
        check("数値を数値にしない指定", json.loads(preview())[0]["売上"], "1,234")
        set_ctl('tNum', True)
        set_ctl('tEmpty', 'omit')
        check("空欄の項目を省く指定", json.loads(preview())[1], {"月": "二月", "売上": 987})
        set_ctl('tEmpty', 'null')

        # ---- JSON を、グラフの spec の中へ挿入する
        spec = '```vega-lite\n{"mark": "bar", "data": {"values": \n```\n'
        js("document.getElementById('tClose').click(); cm.setValue(%s)" % json.dumps(spec))
        js("cm.setCursor({line: 0, ch: 0})")
        js("cm.setCursor({line: 1, ch: cm.getLine(1).length})")
        js("document.getElementById('fTable').click()")
        set_ctl('tFmt', 'json')
        set_src("月,売上\n一月,3\n二月,5\n")
        js("document.getElementById('tInsert').click()")
        wait("document.getElementById('tveil').hidden")
        t = js("cm.getValue()")
        check("JSON が、カーソルの位置にそのまま入る", '"values": [\n  {"月": "一月", "売上": 3},\n  {"月": "二月", "売上": 5}\n]' in t, True)

        js("document.getElementById('fTable').click()")
        check("挿入したときの設定（JSON）が、次に開いたときに覚えられている", js("document.getElementById('tFmt').value"), 'json')
        js("document.getElementById('tClose').click()")

        # ---- そのグラフが描かれる（JSON を完成させる）
        full = ('```vega-lite\n{"mark": "bar", "data": {"values": [\n  {"月": "一月", "売上": 3},\n  {"月": "二月", "売上": 5}\n]},\n'
                '"encoding": {"x": {"field": "月", "type": "nominal"}, "y": {"field": "売上", "type": "quantitative"}}}\n```\n')
        js("cm.setValue(%s)" % json.dumps(full))
        ok = wait("document.querySelectorAll('#preview .vega-embed svg').length > 0", 25)
        check("変換した JSON で、Vega-Lite のグラフが描かれる", ok, True)

        # ---- CSV ファイル（Shift-JIS）を読み込む
        js("cm.setValue('')")
        js("api.pick_data_file = () => Promise.resolve(%s)" % json.dumps(csv_path))
        js("document.getElementById('fTable').click()")
        js("document.getElementById('tFile').click()")
        wait("document.getElementById('tSrc').value.length > 0")
        time.sleep(0.8)
        check("Shift-JIS の CSV が、文字化けせずに読み込まれる", js("document.getElementById('tSrc').value"), CSV)
        check("読み込んだ CSV の情報", js("document.getElementById('tInfo').textContent"), "2 列 × 2 行（データ）")

        # ---- JSON をファイルに保存する
        out = os.path.join(tmp, 'data', '売上.json')
        js("api.pick_json_save = (d, n) => { window._jsonName = n; return Promise.resolve(%s); }" % json.dumps(out))
        js("document.getElementById('tSave').click()")
        wait("document.getElementById('tveil').hidden")
        time.sleep(0.5)
        check("保存の初期のファイル名は、CSV の名前から決まる", js("window._jsonName"), '売上.json')
        check("JSON ファイルが書かれる", json.loads(open(out, encoding='utf-8').read()), [{"区分": "A", "件数": 10}, {"区分": "B", "件数": 20}])
        msg = js("document.getElementById('status').textContent") if js("!!document.getElementById('status')") else ''
        check("保存の知らせに、data.url に書く相対パスが出る", 'data/売上.json' in js("document.body.innerText"), True)

        # ---- JSON から表を作る（逆向き）
        js("document.getElementById('fTable').click()")
        set_ctl('tFmt', 'md')
        set_src('[{"月": "一月", "売上": 1234, "備考": "好調"}, {"月": "二月", "売上": 987, "備考": null}, {"月": "三月", "地域": {"a": 1}}]')
        check("JSON を貼り付けると、表のプレビューになる（列の順は、キーが出てきた順）", preview().split("\n")[:2], ["| 月 | 売上 | 備考 | 地域 |", "| --- | ---: | --- | --- |"])
        check("入れ子は、属性つきで、1つのセルに入る", '| 三月 |  |  | {"a": 1} |' in preview(), True)
        check("JSON として読んだことが、情報に出る", 'JSON として読みました' in js("document.getElementById('tInfo').textContent"), True)
        set_ctl('tSource', 'table')
        check("入力の形式を「表」にすると、JSON の文字も表として読む", 'JSON として読みました' in js("document.getElementById('tInfo').textContent"), False)
        set_ctl('tSource', 'json')
        set_src("a,b\n1,2\n")
        check("入力の形式を「JSON」にして読めないときは、理由が赤く出る", (js("document.getElementById('tInfo').classList.contains('bad')"), 'JSON として読めません' in js("document.getElementById('tInfo').textContent")), (True, True))
        set_ctl('tSource', 'auto')
        json_path = os.path.join(tmp, 'd.json')
        open(json_path, 'w', encoding='utf-8').write('[{"区分": "A", "件数": 10}]')
        js("api.pick_data_file = () => Promise.resolve(%s)" % json.dumps(json_path))
        js("document.getElementById('tFile').click()")
        wait("document.getElementById('tSrc').value.startsWith('[')")
        time.sleep(0.8)
        check("JSON ファイルを読み込める", preview().split("\n")[0], "| 区分 | 件数 |")
        js("document.getElementById('tClose').click()")

        # ---- Esc・読み取り専用
        js("document.getElementById('fTable').click()")
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        check("Esc でダイアログが閉じる", js("document.getElementById('tveil').hidden"), True)
        js("doc.readonly = true; applyDocMeta()")
        check("読み取り専用では、ボタンが押せない", js("document.getElementById('fTable').disabled"), True)
        js("openTableDlg()")
        check("読み取り専用では、ダイアログも開かない", js("document.getElementById('tveil').hidden"), True)
        js("doc.readonly = false; applyDocMeta()")

        print("RESULT", sum(results), "/", len(results), flush=True)
    finally:
        clipboard.set_text(saved_clip or "")
        os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
