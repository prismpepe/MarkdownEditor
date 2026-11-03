"""編集欄とプレビューの、スクロールの同期を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_scrollsync.py

プレビューの要素の data-line（元の行番号）を目印に、編集欄のスクロールにプレビューを合わせる。HTML の表（複数続く場合も）で
目印が無いと、プレビューが動かない。編集欄を送りながら、プレビューの先頭に見えている行番号が、編集欄の先頭の行と
合っているかを調べる。設定の置き場所は一時フォルダーへ向ける。
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
import tabular

ROWS = "\n".join("%d,名前%d,%d" % (i, i, i * 10) for i in range(1, 61))
CSV = "番号,名前,値\n" + ROWS


def html_table():
    return tabular.convert(CSV, fmt="html")["output"]


def md_table():
    return tabular.convert(CSV, fmt="md")["output"]


HTML_DOC = "# HTML の表が続く\n\n" + "\n\n".join("## 表%d\n\n%s" % (i + 1, html_table()) for i in range(3)) + "\n\n最後の段落。\n"
MD_DOC = "# Markdown の表が続く\n\n" + "\n\n".join("## 表%d\n\n%s" % (i + 1, md_table()) for i in range(3)) + "\n\n最後の段落。\n"
HTML_ONLY = html_table() + "\n\n" + html_table() + "\n"                      # 文書の先頭から末尾まで、HTML の表だけ
MIXED = ('<div>\n' + '\n'.join('<p>段落%d</p>' % i for i in range(1, 40)) + '\n</div>\n\n<ul>\n' +
         '\n'.join('<li>項目%d</li>' % i for i in range(1, 40)) + '\n</ul>\n\n最後。\n')

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


def set_doc(text):
    js("cm.setValue(%s)" % json.dumps(text))
    time.sleep(2.2)


# 編集欄の先頭の行を top_line にして、プレビューを合わせ、プレビューの上端にもっとも近い目印の行番号（data-line）を返す
PROBE = """(top => {
  const y = cm.heightAtLine(top, 'local'); cm.scrollTo(null, y); syncFromTop();
  const pv = document.getElementById('pscroll'), r = pv.getBoundingClientRect();
  const els = [...document.querySelectorAll('#preview [data-line]')];
  els.sort((a, b) => Math.abs(a.getBoundingClientRect().top - r.top) - Math.abs(b.getBoundingClientRect().top - r.top));
  return JSON.stringify({scroll: Math.round(pv.scrollTop), first: els.length ? +els[0].dataset.line : -1});
})(%d)"""


def probe(top):
    return json.loads(js(PROBE % top))


def sweep(name, lines, tolerance):
    """編集欄の先頭の行を順に動かし（末尾の1画面ぶんは、画面が最後まで届いて動けないので、測らない）、プレビューが動き続けること・先頭の行番号が、編集欄の行と近いことを確かめる。"""
    seen, bad, stuck = [], [], 0
    for ln in lines:
        r = probe(ln)
        if seen and r['scroll'] < seen[-1]['scroll']:
            bad.append((ln, 'プレビューが戻った'))
        if seen and r['scroll'] == seen[-1]['scroll']:
            stuck += 1
        if r['first'] >= 0 and abs(r['first'] - ln) > tolerance:
            bad.append((ln, '先頭の行番号 %d' % r['first']))
        seen.append(r)
    check(name + ': プレビューが、編集欄に合わせて動き続ける（止まったままの区間が、少ない）', stuck <= len(lines) // 6, True)
    check(name + ': プレビューの先頭の行が、編集欄の先頭の行と近い（±%d行）' % tolerance, bad[:3], [])
    return seen


def drive():
    time.sleep(8)
    js("setView('split')")
    time.sleep(0.5)

    n = js("cm.lineCount()")
    set_doc(MD_DOC)
    total = js("cm.lineCount()")
    sweep('Markdown の表が続く文書', list(range(2, total - 38, 9)), 4)

    set_doc(HTML_DOC)
    total = js("cm.lineCount()")
    check("HTML の表の行に、行番号の目印が付く", js("document.querySelectorAll('#preview tr[data-line]').length"), 3 * 61)
    seen = sweep('HTML の表が複数続く文書', list(range(2, total - 38, 9)), 4)
    check("HTML の表が続く文書: 編集欄を末尾まで送ると、プレビューも末尾へ届く",
          js("(() => { const pv = document.getElementById('pscroll'); cm.scrollTo(null, 1e9); syncFromTop(); return pv.scrollHeight - pv.clientHeight - pv.scrollTop; })()") < 400, True)

    set_doc(HTML_ONLY)
    total = js("cm.lineCount()")
    sweep('文書全体が HTML の表だけ', list(range(0, total - 38, 7)), 4)

    set_doc(MIXED)
    total = js("cm.lineCount()")
    sweep('HTML の段落・箇条書きが続く文書', list(range(0, total - 38, 3)), 4)

    print("RESULT", sum(results), "/", len(results), flush=True)
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
