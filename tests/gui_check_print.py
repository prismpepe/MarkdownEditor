"""印刷・PDF 出力を、実際の画面で確かめる（pytest には含めない）。

    .venv\\Scripts\\python tests\\gui_check_print.py

PDF は一時フォルダーへ作って消す。プリンターへは実際には送らない（存在しないプリンター名で
失敗の扱いだけ確かめる）。
"""
import json
import os
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
import tempfile as _tf
os.environ['APPDATA'] = _tf.mkdtemp(prefix='md_appdata_')   # 利用者の設定・バックアップを書き換えない
import webview
import mdeditor
import printing

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'long.md')
body = ["# 長い文書", ""]
for i in range(70):
    body += [f"## 見出し{i}", "", f"本文の段落 {i}。" + "文章が続きます。" * 12, ""]
open(src, 'w', encoding='utf-8', newline='\n').write("\n".join(body))
api = mdeditor.Api(src)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1300, height=800, x=20, y=20)
api._window = w
results = []

PB = {
    'none': "# 一\n\n本文\n\n# 二\n\n本文\n",
    'class': "# 一\n\n本文\n\n<div class=\"page-break\"></div>\n\n# 二\n\n本文\n",
    'three': "# 一\n\n<div class=\"page-break\"></div>\n\n# 二\n\n<div style=\"page-break-after: always;\"></div>\n\n# 三\n\n<div class=\"pagebreak\"></div>\n\n# 四\n",
    'before': "# 一\n\n本文\n\n<p class=\"page-break-before\">ここから次のページ</p>\n\n本文\n",
    'after': "<p class=\"page-break-after\">一ページ目だけ</p>\n\n二ページ目\n",
    'inline': "# 一\n\n本文\n\n<div style=\"color:red; break-before: page\">二ページ目</div>\n",
    'trailing': "# 一\n\n本文\n\n<div class=\"page-break\"></div>\n",
}


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


BASE = dict(paper='A4', landscape=False, margin='標準', scale=1.0, backgrounds=True, header_footer=True,
            title='long.md', uri=src, printer='', copies=1, mono=False)


def pages(**kw):
    r = api.print_count({**BASE, **kw})
    return r['pages'] if r['ok'] else r


def pdf(ranges, **kw):
    path = os.path.join(tmp, f"out_{len(os.listdir(tmp))}.pdf")
    r = api.print_save_pdf({**BASE, **kw}, ranges, path)
    if not r['ok']:
        return r
    data = open(path, 'rb').read()
    media = re.search(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)', data)
    return {'pages': printing.count_pdf_pages(data), 'size': (float(media.group(1)), float(media.group(2))) if media else None,
            'head': data[:5]}


def wait_text(code, pred, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        v = js(code)
        if pred(v):
            return v
        time.sleep(.3)
    return js(code)


def drive():
    time.sleep(8)
    n = pages()
    check("長い文書は複数ページになる", isinstance(n, int) and n >= 5, True)
    print("    A4 縦の全ページ数:", n, flush=True)
    check("A3 のほうがページ数は少ない", pages(paper='A3') < n, True)
    check("横向きのほうがページ数は多い", pages(landscape=True) > n, True)
    check("余白なしのほうがページ数は少ない（同じか少ない）", pages(margin='なし') <= n, True)
    check("倍率を下げるとページ数が減る", pages(scale=0.5) < n, True)

    # ページ範囲
    full = pdf('')
    check("全ページの PDF（先頭が %PDF）", (full['head'], full['pages']), (b'%PDF-', n))
    check("A4 縦の用紙サイズ", tuple(round(v) for v in full['size']), (595, 842))
    check("ページ指定 2 → 1ページ", pdf('2')['pages'], 1)
    check("ページ指定 1-3 → 3ページ", pdf('1-3')['pages'], 3)
    check("ページ指定 1-2,4 → 3ページ", pdf('1-2,4')['pages'], 3)
    check("ページ指定 %d-%d（最後まで）→ 2ページ" % (n - 1, n), pdf(f'{n - 1}-{n}')['pages'], 2)
    land = pdf('1', landscape=True)
    check("横向きの用紙サイズ（幅 > 高さ）", land['size'][0] > land['size'][1], True)
    a3 = pdf('1', paper='A3')
    check("A3 の用紙サイズ", tuple(round(v) for v in a3['size']), (842, 1191))
    out = pdf(f'{n + 50}')
    print("    範囲外（全ページ数を超える）の指定の結果:", {k: out.get(k) for k in ('ok', 'pages', 'error')}, flush=True)

    # 本文以外（ツールバーなど）が紙に出ない: 短い文書は1ページ
    js("cm.setValue(%s)" % json.dumps("# 短い\n\n一行だけ。"))
    time.sleep(1.5)
    check("短い文書は1ページ（画面の部品は紙に出ない）", pages(), 1)

    # 改ページ（class / style）: 実際の PDF のページ数で確かめる
    def pb(name):
        js("cm.setValue(%s)" % json.dumps(PB[name]))
        time.sleep(1.5)
        return pages()
    check("改ページが無ければ1ページ", pb('none'), 1)
    check("class=page-break で2ページ", pb('class'), 2)
    check("class と style と pagebreak の混在で4ページ", pb('three'), 4)
    check("class=page-break-before で次のページへ", pb('before'), 2)
    check("class=page-break-after の後ろが次のページ", pb('after'), 2)
    check("style の改ページは通り、他の style（color）は無視される", pb('inline'), 2)
    print("    末尾の改ページ（空白ページが増えるか）:", pb('trailing'), flush=True)
    check("改ページの印はプレビューに点線で出る", js("getComputedStyle(document.querySelector('#preview .page-break')).borderTopStyle"), 'dashed')

    # 幅の広い表: 縮小の有無でページ数が変わる
    cols = 14
    rows = ["| " + " | ".join(f"項目{c}の見出し" for c in range(cols)) + " |", "|" + "---|" * cols]
    for r in range(10):
        rows.append("| " + " | ".join(f"ABCDEFGH{10000 + r * cols + c}" for c in range(cols)) + " |")
    js("cm.setValue(%s)" % json.dumps("\n".join(rows)))
    time.sleep(1.5)
    # ダイアログを開いて、縮小あり／なしでの全ページ数を比べる
    js("openPrint()")
    time.sleep(3)
    check("印刷ダイアログが開く", js("document.getElementById('pveil').classList.contains('show')"), True)
    js("var f=document.getElementById('pFit'); f.checked=false; f.dispatchEvent(new Event('change'))")
    off = js("MdPrint.currentOptions().scale")
    js("var f=document.getElementById('pFit'); f.checked=true; f.dispatchEvent(new Event('change'))")
    on = js("MdPrint.currentOptions().scale")
    print("    幅広の表: 縮小なしの倍率 =", off, " 縮小ありの倍率 =", on, flush=True)
    check("縮小しない設定では、倍率は指定どおり（100%）", off, 1.0)
    check("幅の広い表は、縮小する設定にすると倍率が下がる", 0.2 <= on < 1.0, True)
    js("var s=document.getElementById('pPaper'); s.value='A3'; s.dispatchEvent(new Event('change'))")
    a3 = js("MdPrint.currentOptions().scale")
    check("用紙が大きいほど、縮小は小さくて済む", a3 >= on, True)
    js("var s=document.getElementById('pPaper'); s.value='A4'; s.dispatchEvent(new Event('change'))")
    js("var o=document.querySelector('input[name=pOri][value=l]'); o.click()")
    land = js("MdPrint.currentOptions().scale")
    check("横向きは幅が広いので、縮小は小さくて済む", land >= on, True)
    js("document.querySelector('input[name=pOri][value=p]').click()")
    # 縮小した設定で出力でき、ページ数も取れる
    r = api.print_count({**BASE, 'scale': on})
    check("縮小した設定でもページ数を数えられる", r['ok'], True)
    # 幅の狭い文書では、縮小しない
    js("cm.setValue(%s)" % json.dumps("# 短い\n\n一行だけ。"))
    time.sleep(1.5)
    check("幅に収まる文書では倍率を下げない", js("MdPrint.currentOptions().scale"), 1.0)
    js("cm.setValue(%s)" % json.dumps("\n".join(rows)))
    time.sleep(1.5)

    # ダイアログのページ指定の検査
    js("document.querySelector('input[name=pRange][value=some]').click()")
    js("var e=document.getElementById('pRanges'); e.value='5-1'; e.dispatchEvent(new Event('input'))")
    time.sleep(1)
    check("逆順の指定は誤りと表示される", js("document.getElementById('pRanges').classList.contains('bad')"), True)
    js("var e=document.getElementById('pRanges'); e.value='1'; e.dispatchEvent(new Event('input'))")
    time.sleep(1)
    check("正しい指定は受け付けられる", (js("document.getElementById('pRanges').classList.contains('bad')"),
                                      js("document.getElementById('pRangeInfo').textContent")), (False, '1 ページを出力します'))
    js("var e=document.getElementById('pRanges'); e.value='9'; e.dispatchEvent(new Event('input'))")
    time.sleep(1)
    check("全ページ数を超える指定は誤りと表示される", js("document.getElementById('pRanges').classList.contains('bad')"), True)
    js("document.querySelector('input[name=pRange][value=all]').click()")
    check("「すべて」に戻すと指定欄は無効になる", js("document.getElementById('pRanges').disabled"), True)
    js("document.querySelector('input[name=pMode][value=pdf]').click()")
    check("PDF 保存を選ぶとプリンター欄が隠れ、ボタンが変わる",
          (js("document.getElementById('pPrintOnly').style.display"), js("document.getElementById('pRun').textContent")), ('none', 'PDF を保存…'))
    js("document.querySelector('input[name=pMode][value=print]').click()")
    check("印刷を選ぶとボタンが「印刷する」になる", js("document.getElementById('pRun').textContent"), '印刷する')
    js("document.getElementById('pClose').click()")
    time.sleep(.5)
    check("閉じられる", js("document.getElementById('pveil').classList.contains('show')"), False)

    # プリンター一覧と、使えないプリンターの扱い
    pr = api.print_printers()
    check("プリンターの一覧が取れる", isinstance(pr['printers'], list), True)
    print("    プリンター:", pr['printers'][:5], "既定:", pr['default'], flush=True)
    bad = api.print_send({**BASE, 'printer': '存在しないプリンター'}, '')
    check("存在しないプリンターは失敗として返る（落ちない）", bad['ok'], False)
    print("    メッセージ:", bad.get('error'), flush=True)

    saved = mdeditor.load_settings().get("print", {})
    check("ページ範囲は保存されない（次回は「すべて」から始まる）", ("ranges" in saved, "rangeAll" in saved), (False, False))
    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
