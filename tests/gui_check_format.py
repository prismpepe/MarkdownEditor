import sys, threading, time, os, json
sys.path.insert(0, '.')
import tempfile as _tf
os.environ['APPDATA'] = _tf.mkdtemp(prefix='md_appdata_')   # 利用者の設定・バックアップを書き換えない
import webview, mdeditor

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1300, height=800)
api._window = w

HELPER = r"""
window.T = function(text, selFrom, selTo, fn) {
  cm.setValue(text);
  const pos = i => cm.posFromIndex(i);
  cm.setSelection(pos(selFrom), pos(selTo == null ? selFrom : selTo));
  cm.operation(() => fn());
  return JSON.stringify({ v: cm.getValue(), s: cm.getSelection(), c: cm.getCursor('from').line + ':' + cm.getCursor('from').ch });
};
"""


def run(text, a, b, fn):
    code = f"T({json.dumps(text)}, {a}, {b if b is not None else 'null'}, () => {fn})"
    return json.loads(w.evaluate_js(code))


results = []


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def drive():
    time.sleep(6)
    w.evaluate_js(HELPER)
    B = "MdFormat.inline(cm,'**')"
    r = run("abc", 0, 3, B); check("太字: 選択を囲む", r['v'], "**abc**")
    r = run("**abc**", 2, 5, B); check("太字: 内側を選んで解除", r['v'], "abc")
    r = run("**abc**", 0, 7, B); check("太字: 記号ごと選んで解除", r['v'], "abc")
    r = run("", 0, 0, B); check("太字: 選択なしは記号だけ入れて間にカーソル", (r['v'], r['c']), ("****", "0:2"))
    r = run("a\nb", 0, 3, "MdFormat.inline(cm,'~~')"); check("取り消し線: 複数行も囲む", r['v'], "~~a\nb~~")
    r = run("text", 0, 0, "MdFormat.heading(cm,2)"); check("見出し2", r['v'], "## text")
    r = run("## text", 0, 0, "MdFormat.heading(cm,2)"); check("同じ見出しをもう一度で本文へ", r['v'], "text")
    r = run("## text", 0, 0, "MdFormat.heading(cm,3)"); check("見出しの段階を変える", r['v'], "### text")
    r = run("### text", 0, 0, "MdFormat.heading(cm,0)"); check("本文に戻す", r['v'], "text")
    r = run("a\n\nb", 0, 4, "MdFormat.heading(cm,1)"); check("見出し: 複数行・空行は触らない", r['v'], "# a\n\n# b")
    r = run("a\nb\n\nc", 0, 6, "MdFormat.linePrefix(cm,'ul')"); check("箇条書き: 空行は飛ばす", r['v'], "- a\n- b\n\n- c")
    r = run("- a\n- b", 0, 7, "MdFormat.linePrefix(cm,'ul')"); check("箇条書き: もう一度で解除", r['v'], "a\nb")
    r = run("a\nb", 0, 3, "MdFormat.linePrefix(cm,'ol')"); check("番号付き: 連番", r['v'], "1. a\n2. b")
    r = run("- a\n- b", 0, 7, "MdFormat.linePrefix(cm,'ol')"); check("箇条書き→番号付きへ変換", r['v'], "1. a\n2. b")
    r = run("1. a\n2. b", 0, 9, "MdFormat.linePrefix(cm,'ol')"); check("番号付き: もう一度で解除", r['v'], "a\nb")
    r = run("a", 0, 0, "MdFormat.linePrefix(cm,'task')"); check("チェックリスト", r['v'], "- [ ] a")
    r = run("- [ ] a", 0, 0, "MdFormat.linePrefix(cm,'ul')"); check("チェックリスト→箇条書きへ変換", r['v'], "- a")
    r = run("  a", 2, 2, "MdFormat.linePrefix(cm,'ul')"); check("字下げを保つ", r['v'], "  - a")
    r = run("a\nb", 0, 3, "MdFormat.linePrefix(cm,'quote')"); check("引用", r['v'], "> a\n> b")
    r = run("> a\n> b", 0, 7, "MdFormat.linePrefix(cm,'quote')"); check("引用: 解除", r['v'], "a\nb")
    r = run("", 0, 0, "MdFormat.linePrefix(cm,'ul')"); check("空行に箇条書き: 記号だけ入れる", (r['v'], r['c']), ("- ", "0:2"))
    r = run("x\ny", 0, 3, "MdFormat.codeBlock(cm)"); check("コードブロック: 選択行を囲む", r['v'], "```\nx\ny\n```")
    r = run("", 0, 0, "MdFormat.codeBlock(cm)"); check("コードブロック: 空の枠を作りカーソルは中", (r['v'], r['c']), ("```\n\n```\n", "1:0"))
    r = run("文字", 0, 2, "MdFormat.link(cm)"); check("リンク: URL を選択", (r['v'], r['s']), ("[文字](URL)", "URL"))
    r = run("", 0, 0, "MdFormat.link(cm)"); check("リンク: 選択なし", r['v'], "[リンク文字](URL)")
    r = run("", 0, 0, "MdFormat.image(cm)"); check("画像", (r['v'], r['s']), ("![代替テキスト](画像のパス)", "画像のパス"))
    r = run("", 0, 0, "MdFormat.table(cm)"); check("表: 空の文書", r['v'].startswith("| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n"), True)
    r = run("文章", 2, 2, "MdFormat.table(cm)"); check("表: 文章の下に空行をはさむ", r['v'].startswith("文章\n\n| 列1"), True)
    r = run("文章", 2, 2, "MdFormat.rule(cm)"); check("区切り線", r['v'], "文章\n\n---\n")

    # 図のひな形が実際に描けること（全種類）
    count = w.evaluate_js("Object.keys(MdFormat.DIAGRAMS).length")
    w.evaluate_js(r"""cm.setValue(''); for (const k of Object.keys(MdFormat.DIAGRAMS)) { cm.setCursor({line: cm.lineCount()-1, ch: 0}); MdFormat.diagram(cm, k); }""")
    ok = False
    for _ in range(40):
        time.sleep(.5)
        n = w.evaluate_js("document.querySelectorAll('#preview .diagram > svg').length")
        if n == count:
            ok = True
            break
    errs = w.evaluate_js("document.querySelectorAll('#preview .diagram-error').length")
    check(f"図のひな形{count}種類がプレビューで描ける", (ok, errs), (True, 0))

    # ボタン・選択欄の配線
    w.evaluate_js(HELPER)
    w.evaluate_js(r"cm.setValue('abc'); cm.setSelection({line:0,ch:0},{line:0,ch:3}); document.querySelector('#fmt [data-f=bold]').click()")
    check("太字ボタン", w.evaluate_js("cm.getValue()"), "**abc**")
    w.evaluate_js(r"cm.setValue('題名'); cm.setCursor({line:0,ch:0}); const s=document.getElementById('fHead'); s.value='2'; s.dispatchEvent(new Event('change'))")
    check("見出しの選択欄", (w.evaluate_js("cm.getValue()"), w.evaluate_js("document.getElementById('fHead').value")), ("## 題名", ""))
    w.evaluate_js(r"cm.setValue(''); const d=document.getElementById('fDiagram'); d.value='pie'; d.dispatchEvent(new Event('change'))")
    check("図の選択欄", w.evaluate_js("cm.getValue().startsWith('```mermaid\\npie')"), True)
    w.evaluate_js("doc.readonly = true; applyDocMeta();")
    check("読み取り専用では無効", w.evaluate_js("[...document.querySelectorAll('#fmt [data-f], #fmt select')].every(e=>e.disabled)"), True)
    w.evaluate_js("cm.setValue('x'); document.querySelector('#fmt [data-f=bold]').click()")
    check("読み取り専用では書式が入らない", w.evaluate_js("cm.getValue()"), "x")
    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
