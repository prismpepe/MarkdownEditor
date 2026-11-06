"""数式（KaTeX）の表示を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_math.py

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

DOC = r"""# 数式の確認

文中の数式 $E=mc^2$ と、金額の $100から$200 は別物です。コード `$a$` は、そのまま。

$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$

```math
x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}
```

| 式 | 意味 |
| --- | --- |
| $a^2+b^2=c^2$ | 三平方の定理 |

誤りの数式（文中）: $\foo{x}$ です。

$$
\frac{1
$$

最後の段落。
"""

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


def wait(code, timeout=30):
    t = time.time()
    while time.time() - t < timeout:
        if js(code):
            return True
        time.sleep(.3)
    return bool(js(code))


def count(sel):
    return js("document.querySelectorAll(%s).length" % json.dumps(sel))


def drive():
    time.sleep(8)
    js("setView('split')")
    time.sleep(.5)
    js("cm.setValue(%s)" % json.dumps(DOC))
    ok = wait("document.querySelectorAll('#preview .math.typeset').length >= 6")
    check("数式が組まれる（6 個: 文中2・表1・ブロック3）", (ok, count('#preview .math.typeset')), (True, 6))
    time.sleep(1)

    check("正しい数式は KaTeX で組まれる（4 個）", count('#preview .math:not(.math-error) .katex'), 4)
    check("独立した行の数式は、中央に置く表示（$$ と ```math の 2 個）", count('#preview .math.block .katex-display'), 2)
    check("表のセルの中の数式も組まれる", count('#preview td .math .katex'), 1)
    check("```math は、コードブロックとして残らない", count('#preview pre'), 0)
    check("金額の文は、数式にならず、そのまま残る", js("document.querySelector('#preview p').textContent.includes('$100から$200')"), True)
    check("コードの中の $a$ は、数式にならない", js("(() => { const c = document.querySelector('#preview p code'); return c && c.textContent === '$a$' && !c.querySelector('.katex'); })()"), True)
    check("誤りの数式（文中）: 原文が残り、理由を title に持つ",
          js("(() => { const e = document.querySelector('#preview span.math-error'); return e ? [e.textContent, e.title.startsWith('数式を組めませんでした')] : null; })()"),
          ['$\\foo{x}$', True])
    check("誤りの数式（ブロック）: 原文と、理由が見える",
          js("(() => { const e = document.querySelector('#preview div.math-error'); return e ? [e.querySelector('code').textContent.includes('\\\\frac{1'), (e.querySelector('.math-error-msg') || {}).textContent.startsWith('数式を組めませんでした')] : null; })()"),
          [True, True])
    check("数式のフォント（KaTeX_Main）が読み込まれている", js("document.fonts.check('16px KaTeX_Main') && [...document.fonts].some(f => f.family.includes('KaTeX') && f.status === 'loaded')"), True)
    check("数式の文字色は、本文と同じ（ダークモードでも読める）", js("getComputedStyle(document.querySelector('#preview .katex')).color === getComputedStyle(document.querySelector('#preview p')).color"), True)

    # 行番号の目印（スクロールの同期）
    check("ブロックの数式に、元の行番号（data-line、0 始まり）が付く（$$ は 4、```math は 8、誤りの $$ は 18）",
          js("[...document.querySelectorAll('#preview .math.block')].map(e => +e.dataset.line)"), [4, 8, 18])

    # 打鍵のたびにプレビューが作り直される。組む前の TeX が、一瞬でも見えない（ちらつかない）
    js("""window.__bare = 0; window.__obs = new MutationObserver(() => {
          if (document.querySelector('#preview .math:not(.typeset)')) window.__bare++; });
        window.__obs.observe(document.getElementById('preview'), { childList: true, subtree: true }); 1""")
    for i in range(4):
        js("cm.replaceRange('あ', {line: cm.lastLine(), ch: 0}); 1")
        time.sleep(.7)
    ok = wait("document.querySelectorAll('#preview .math:not(.math-error) .katex').length === 4")
    check("文章を打っても、数式は組まれたまま", (ok, count('#preview .math.typeset')), (True, 6))
    check("プレビューを作り直しても、組む前の TeX が見える瞬間は、ない（ちらつかない）", js("window.__bare"), 0)

    # 数式の中身を打つと、プレビューが変わる
    js("cm.setValue(%s)" % json.dumps("$$\nx^2\n$$\n"))
    wait("document.querySelector('#preview .katex-display')")
    before = js("document.querySelector('#preview .katex-display').textContent")
    js("cm.setValue(%s)" % json.dumps("$$\ny^3\n$$\n"))
    time.sleep(1.2)
    after = js("document.querySelector('#preview .katex-display').textContent")
    check("数式を書き換えると、プレビューも変わる", (before != after, 'y' in after and '3' in after), (True, True))


    # 「数式を挿入…」のひな形は、すべて TeX として正しい（挿入して、組んで、エラーが出ない）
    keys = js("Object.keys(MdFormat.MATH)")
    bad = []
    for k in keys:
        js("cm.setValue(''); (() => { const d = document.getElementById('fMath'); d.value = %s; d.dispatchEvent(new Event('change')); })()" % json.dumps(k))
        wait("document.querySelectorAll('#preview .math.typeset').length >= 1", 15)
        time.sleep(.4)
        n_math, n_err, n_katex = count('#preview .math'), count('#preview .math-error'), count('#preview .math .katex')
        if n_math != 1 or n_err or n_katex != 1:
            bad.append((k, n_math, n_err, n_katex))
    check("数式のひな形（%d 種類）は、すべて、組まれて、エラーが出ない" % len(keys), bad, [])

    # 数式のない文書
    js("cm.setValue(%s)" % json.dumps("ふつうの文章です。\n"))
    time.sleep(1)
    check("数式のない文書では、数式は 0", count('#preview .math'), 0)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
