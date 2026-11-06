"""表示モード・フォルダーの切替・ツールバーの折り返しを、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_layout.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。旧い設定からの引き継ぎは、
設定を書いたうえで起動し直す必要があるので、引数つきで自分自身を起動して確かめる。
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
SCENARIO = sys.argv[1] if len(sys.argv) > 1 else ''

# ---- 旧い設定からの引き継ぎ: 「書いておく設定」→「起動したあとの表示モード」
MIGRATION = {
    'old_split_list_visible': ({'prefs': {'view': 'split'}}, 'triple'),                      # 旧: 2画面+一覧あり = 今の3画面
    'old_split_list_hidden': ({'prefs': {'view': 'split'}, 'side_hidden': True}, 'split'),   # 旧: 2画面+一覧なし = 今の2画面
    'old_edit': ({'prefs': {'view': 'edit'}}, 'edit'),
    'old_preview': ({'prefs': {'view': 'preview'}}, 'preview'),
    'new_user': ({}, 'triple'),                                                               # 設定なし = 3画面
    'already_new': ({'prefs': {'view': 'split', 'layout_v': 2}}, 'split'),                    # 新しい設定の2画面は、一覧なしのまま
}

if not SCENARIO:       # 親: 引き継ぎの各場合を別の起動で確かめ、そのあと通常の確認を行う
    ok = True
    for name in MIGRATION:
        out = subprocess.run([sys.executable, __file__, name], capture_output=True, text=True, encoding='utf-8').stdout
        line = [l for l in out.splitlines() if l.startswith(('OK ', 'NG '))]
        print(line[-1] if line else f'NG {name}: 結果が出ませんでした', flush=True)
        ok = ok and bool(line) and line[-1].startswith('OK ')
    os.execv(sys.executable, [sys.executable, __file__, 'main'])

os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor

if SCENARIO in MIGRATION:
    mdeditor.save_settings(MIGRATION[SCENARIO][0])

tmp = tempfile.mkdtemp()
folder_a, folder_b = os.path.join(tmp, 'A'), os.path.join(tmp, 'B')
os.makedirs(folder_a)
os.makedirs(folder_b)
doc_a = os.path.join(folder_a, 'a.md')
open(doc_a, 'w', encoding='utf-8', newline='\n').write("# Aの文書\n\n本文\n")
open(os.path.join(folder_b, 'b.md'), 'w', encoding='utf-8').write("# Bの文書\n")

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=800, x=20, y=20)
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
        time.sleep(.3)
    return bool(js(code))


def state():
    return json.loads(js("""JSON.stringify({
      view: prefs.view,
      side: !document.getElementById('side').classList.contains('hidden'),
      editor: getComputedStyle(document.getElementById('editorPane')).display !== 'none',
      preview: getComputedStyle(document.getElementById('previewPane')).display !== 'none',
      splitter: getComputedStyle(document.getElementById('split')).display !== 'none',
      active: ['vTriple','vSplit','vEdit','vPrev'].filter(i => document.getElementById(i).classList.contains('active')) })"""))


def click_dialog(label):
    js("[...document.querySelectorAll('#dBtns button')].find(b => b.textContent === %s).click()" % json.dumps(label))


def finish():
    # hidden 属性の要素は、実際に隠れている（display を指定した CSS が、hidden を打ち消していないか）
    shown = js("[...document.querySelectorAll('[hidden]')].filter(e => getComputedStyle(e).display !== 'none').map(e => e.id || e.className || e.tagName)")
    check("hidden 属性の要素が、すべて隠れている", shown, [])

    # 編集ボタンの列: 5つのグループ。見出しの名前と並び、引用がコードブロックの隣、折り返しはグループ単位
    check("編集ボタンのグループの名前と並び", js("[...document.querySelectorAll('#fmt .fgroup .glabel')].map(e => e.textContent)"),
          ['書式', 'リスト・ブロック', '画像・表・データ', '目次・チャート・数式', '編集'])
    check("引用は、リスト・ブロックのグループで、コードブロックの隣", js("[...document.querySelectorAll('#fmt .fgroup')[1].querySelectorAll('button')].map(b => b.dataset.f)"),
          ['ul', 'ol', 'task', 'quote', 'codeblock', 'rule'])
    check("書式のグループは、文字単位のもの（見出し・装飾・リンク）だけ", js("[...document.querySelectorAll('#fmt .fgroup')[0].querySelectorAll('button')].map(b => b.dataset.f)"),
          ['bold', 'italic', 'strike', 'code', 'link'])
    check("チャートの選択欄の名前", js("document.querySelector('#fDiagram option').textContent"), 'チャート・数式を挿入…')
    check("既定の3画面（幅1400）では、3段（2+1+2グループ）に折り返す", (w.resize(1400, 700), time.sleep(0.8), js("""(() => { const tops = [...document.querySelectorAll('#fmt .fgroup')].map(g => Math.round(g.getBoundingClientRect().top));
        const u = [...new Set(tops)].sort((a, b) => a - b); return u.map(t => tops.filter(x => x === t).length).join('+'); })()"""))[2], '2+1+2')
    for width in (1400, 900, 600, 420):
        w.resize(width, 700)
        time.sleep(0.8)
        split = js("""[...document.querySelectorAll('#fmt .fgroup')].filter(g => {
            const tops = new Set([...g.querySelectorAll('.gbtns > *')].map(e => Math.round(e.getBoundingClientRect().top)));
            return tops.size > 1; }).map(g => g.querySelector('.glabel').textContent)""")
        check("幅 %d: どのグループも、途中で折り返さない" % width, split, [])
        clipped = js("""(() => { const f = document.getElementById('fmt').getBoundingClientRect();
            return [...document.querySelectorAll('#fmt .fgroup')].filter(g => g.getBoundingClientRect().right > f.right + 1 && g.getBoundingClientRect().width <= f.width).length; })()""")
        check("幅 %d: グループが、列の右端からはみ出さない" % width, clipped, 0)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


def drive_migration():
    time.sleep(8)
    want = MIGRATION[SCENARIO][1]
    s = state()
    saved = mdeditor.load_settings().get('prefs', {})
    ok = s['view'] == want and saved.get('layout_v') == 2 and saved.get('view') == want and s['active'] == [
        {'triple': 'vTriple', 'split': 'vSplit', 'edit': 'vEdit', 'preview': 'vPrev'}[want]]
    print(('OK ' if ok else 'NG ') + f'旧い設定の引き継ぎ（{SCENARIO}）→ {want}'
          + ('' if ok else f'  実際: view={s["view"]} 保存={saved} active={s["active"]}'), flush=True)
    os._exit(0)


def drive():
    time.sleep(8)
    # ---- 表示を切り替えるボタンが1か所にまとまっている
    check("「一覧を隠す」のボタンはない", js("document.getElementById('bSide')"), None)
    check("表示のボタンは4つ", js("[...document.querySelectorAll('#vTriple, #vSplit, #vEdit, #vPrev')].map(b => b.textContent).join('/')"),
          '3画面/2画面/編集のみ/プレビューのみ')
    expect = {
        'triple': dict(side=True, editor=True, preview=True, splitter=True, active=['vTriple']),
        'split': dict(side=False, editor=True, preview=True, splitter=True, active=['vSplit']),
        'edit': dict(side=False, editor=True, preview=False, splitter=False, active=['vEdit']),
        'preview': dict(side=False, editor=False, preview=True, splitter=False, active=['vPrev']),
    }
    for view, btn in (('triple', 'vTriple'), ('split', 'vSplit'), ('edit', 'vEdit'), ('preview', 'vPrev')):
        js(f"document.getElementById('{btn}').click()")
        time.sleep(.4)
        s = state()
        s.pop('view')
        check(f"「{view}」: 一覧・編集・プレビューの出し方", s, expect[view])
    js("document.getElementById('vTriple').click()")
    time.sleep(.3)
    js("toggleSide()")
    check("Ctrl+\\（一覧の表示切替）: 3画面 → 2画面", state()['view'], 'split')
    js("toggleSide()")
    check("Ctrl+\\: 2画面 → 3画面", state()['view'], 'triple')
    js("document.getElementById('vEdit').click()")
    js("toggleSide()")
    check("Ctrl+\\: 編集のみ → 3画面", state()['view'], 'triple')
    for key, want in (('1', 'triple'), ('2', 'split'), ('3', 'edit'), ('4', 'preview')):
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key: %s, ctrlKey: true, bubbles: true}))" % json.dumps(key))
        time.sleep(.3)
        check(f"Ctrl+{key} → {want}", state()['view'], want)
    check("選んだ表示モードが保存される", mdeditor.load_settings()['prefs']['view'], 'preview')
    js("document.getElementById('vTriple').click()")

    # ---- フォルダーを変えたときの文書の扱い
    js(f"loadFolder({json.dumps(folder_a)}).then(() => openPath({json.dumps(doc_a)}))")
    wait("doc.path && doc.path.endsWith('a.md')")
    check("文書が開いている", js("cm.getValue().startsWith('# Aの文書')"), True)
    js(f"switchFolder({json.dumps(folder_a)})")
    time.sleep(1)
    check("同じフォルダーを選び直しても、文書は開いたまま（確認も出ない）",
          (js("doc.path") is not None, js("document.getElementById('veil').classList.contains('show')")), (True, False))

    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    wait("window.__r !== null")
    check("未保存でなければ、確認なしで別のフォルダーへ移り、文書を閉じる",
          (js("doc.path"), js("cm.getValue()"), js("files.join(',')")), (None, '', 'b.md'))
    check("ファイル名の表示は「無題」・変更なし", (js("document.getElementById('title').textContent"), js("isDirty()")), ('無題', False))
    check("一覧に選択中の行はない", js("document.querySelectorAll('#list .item.sel').length"), 0)

    # 未保存の変更があるとき: キャンセル → 移らない
    js(f"switchFolder({json.dumps(folder_a)}).then(() => openPath({json.dumps(doc_a)}))")
    wait("doc.path && doc.path.endsWith('a.md')")
    js("cm.replaceRange('追記\\n', {line: 0, ch: 0})")
    check("未保存の変更がある", js("isDirty()"), True)
    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    check("保存を促す確認が出る", wait("document.getElementById('veil').classList.contains('show')"), True)
    check("確認の文言に文書名がある", 'a.md' in js("document.getElementById('dText').textContent"), True)
    click_dialog('キャンセル')
    wait("window.__r !== null")
    check("キャンセルすると、フォルダーも文書も、そのまま", (js("window.__r"), js("folder") == folder_a, js("doc.path") is not None, js("isDirty()")), (False, True, True, True))

    # 保存しない → 変更を捨てて移る
    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    wait("document.getElementById('veil').classList.contains('show')")
    click_dialog('保存しない')
    wait("window.__r !== null")
    check("「保存しない」: 移って、文書は空白になる", (js("window.__r"), js("doc.path"), js("cm.getValue()"), js("files.join(',')")), (True, None, '', 'b.md'))
    check("「保存しない」: ファイルは書き換わっていない", open(doc_a, encoding='utf-8').read(), "# Aの文書\n\n本文\n")

    # 保存する → 保存してから移る
    js(f"switchFolder({json.dumps(folder_a)}).then(() => openPath({json.dumps(doc_a)}))")
    wait("doc.path && doc.path.endsWith('a.md')")
    js("cm.replaceRange('保存する追記\\n', {line: 0, ch: 0})")
    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    wait("document.getElementById('veil').classList.contains('show')")
    click_dialog('保存する')
    wait("window.__r !== null")
    check("「保存する」: 保存してから移り、文書は空白になる",
          (js("window.__r"), js("doc.path"), js("cm.getValue()"), open(doc_a, encoding='utf-8').read().startswith('保存する追記')), (True, None, '', True))

    # 書きかけの「無題」も、保存を促す
    js("cm.setValue('書きかけ')")
    js(f"window.__r = null; switchFolder({json.dumps(folder_a)}).then(v => {{ window.__r = v; }})")
    check("書きかけの「無題」でも、保存を促す", wait("document.getElementById('veil').classList.contains('show')"), True)
    click_dialog('キャンセル')
    wait("window.__r !== null")
    check("キャンセルすると、書きかけは残る", (js("window.__r"), js("cm.getValue()")), (False, '書きかけ'))
    js("cm.setValue('')")

    # ---- 一覧が、時間か件数の上限で途中までのときの表示
    js("listTruncated = true; renderList()")
    check("一覧が途中までのとき、件数の行で知らせる", '途中までです' in js("document.getElementById('count').textContent"), True)
    check("途中までの知らせは、色でも目立たせる", js("document.getElementById('count').style.color") != '', True)
    js("listTruncated = false; renderList()")
    check("途中でなければ、知らせは出ない", '途中' in js("document.getElementById('count').textContent"), False)

    # ---- ツールバーの折り返し
    def toolbar():
        return json.loads(js("""(() => {
          const t = document.getElementById('toolbar');
          const btns = [...t.querySelectorAll('button')];
          const tops = [...new Set(btns.map(b => Math.round(b.getBoundingClientRect().top)))];
          return JSON.stringify({ maxBtnH: Math.max(...btns.map(b => b.getBoundingClientRect().height)), rows: tops.length,
                                  overflowX: t.scrollWidth > t.clientWidth + 1 });
        })()"""))
    for width in (700, 520, 380):
        w.resize(width, 800)
        time.sleep(1)
        r = toolbar()
        check(f"幅{width}px: ボタンが縦長にならない（高さ {r['maxBtnH']:.0f}px）", r['maxBtnH'] < 45, True)
        check(f"幅{width}px: ツールバーが横にはみ出さない（{r['rows']}行）", r['overflowX'], False)
    finish()


(drive_migration if SCENARIO in MIGRATION else drive)() if False else None
threading.Thread(target=drive_migration if SCENARIO in MIGRATION else drive, daemon=True).start()
webview.start()
