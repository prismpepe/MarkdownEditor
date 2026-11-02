"""検索・置換・コピー・貼り付けを、実際の画面で確かめる（pytest には含めない）。

    .venv\\Scripts\\python tests\\gui_check_find.py

クリップボードを使うので、実行中は書き換わる。文字列が入っていれば、終わったあとに戻す。
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, '.')
import tempfile as _tf
os.environ['APPDATA'] = _tf.mkdtemp(prefix='md_appdata_')   # 利用者の設定・バックアップを書き換えない
import webview
import clipboard
import mdeditor

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1300, height=800, x=20, y=20)
api._window = w
results = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def setdoc(text):
    js(f"cm.setValue({json.dumps(text)}); cm.setCursor({{line:0,ch:0}});")


def val():
    return js("cm.getValue()")


def setq(q, cs=False, re=False, r=None):
    js(f"document.getElementById('fq').value={json.dumps(q)};"
       f"document.getElementById('fCase').checked={str(cs).lower()};"
       f"document.getElementById('fRegex').checked={str(re).lower()};"
       + (f"document.getElementById('fr').value={json.dumps(r)};" if r is not None else ""))
    js("finder.refresh()")


def sel():
    return js("cm.getSelection()")


def count_text():
    return js("document.getElementById('fCount').textContent")


def drive():
    saved = clipboard.get_text()
    try:
        time.sleep(6)
        js("openFind(true)")
        check("検索バーが開く（置換欄つき）", js("[!document.getElementById('find').hidden, !document.getElementById('rrow').hidden].join()"), "true,true")
        VIS = "(id => { const e = document.getElementById(id); return e.getBoundingClientRect().height > 0 && getComputedStyle(e).display !== 'none'; })"
        check("Ctrl+H: 置換の行が、実際に見えている", js(VIS + "('rrow')"), True)
        js("finder.close(); openFind(false)")
        check("Ctrl+F: 検索バーは見え、置換の行は見えない（hidden 属性だけでなく、実際の表示）", (js(VIS + "('find')"), js(VIS + "('rrow')")), (True, False))
        js("finder.close(); document.querySelector('#fmt [data-e=find]').click()")
        check("🔍 ボタン: 検索だけが開く（置換の行は見えない）", (js(VIS + "('find')"), js(VIS + "('rrow')")), (True, False))
        js("finder.close(); document.querySelector('#fmt [data-e=replace]').click()")
        check("⇄ ボタン: 置換の行も見える", (js(VIS + "('find')"), js(VIS + "('rrow')")), (True, True))
        check("⇄ ボタン: 検索欄に焦点がある（すぐ打てる）", js("document.activeElement.id"), 'fq')
        js("finder.close(); openFind(true)")

        setdoc("Apple apple APPLE banana\napple pie")
        setq("apple")
        check("大文字小文字を区別しないで4件", js("finder.count()"), 4)
        check("件数の表示", count_text(), "4 件")
        check("全ての一致がハイライトされる", js("document.querySelectorAll('.cm-searching').length"), 4)
        setq("apple", cs=True)
        check("大文字小文字を区別すると2件", js("finder.count()"), 2)
        setq("zzz")
        check("見つからない表示", count_text(), "見つかりません")

        setq("apple")
        js("finder.step(1)")
        check("次へ: 最初の一致を選ぶ", (sel(), js("cm.getCursor('from').ch")), ("Apple", 0))
        js("finder.step(1)")
        check("次へ: 2番目", (sel(), js("cm.getCursor('from').ch")), ("apple", 6))
        check("n / 全部の表示", count_text(), "2 / 4 件")
        js("finder.step(-1)")
        check("前へ", js("cm.getCursor('from').ch"), 0)
        js("finder.step(-1)")
        check("前へ: 先頭から末尾へ戻る", (js("cm.getCursor('from').line"), count_text()), (1, "4 / 4 件（末尾に戻りました）"))
        js("finder.step(1)")
        check("次へ: 末尾から先頭へ戻る", (js("cm.getCursor('from').line"), count_text()), (0, "1 / 4 件（先頭に戻りました）"))

        # 置換
        setdoc("cat dog cat")
        setq("cat", r="bird")
        js("finder.replaceOne()")          # 1回目: 選ぶだけ
        check("置換: まず一致を選ぶ（まだ置換しない）", (val(), sel()), ("cat dog cat", "cat"))
        js("finder.replaceOne()")          # 2回目: 置換して次へ
        check("置換: 選んでいる一致を置換し、次へ進む", (val(), sel()), ("bird dog cat", "cat"))
        js("finder.replaceAll()")
        check("すべて置換", val(), "bird dog bird")
        check("置換した件数の表示", count_text(), "1 件を置換しました")

        setdoc("a a a a")
        setq("a", r="bb")
        js("finder.replaceAll()")
        check("すべて置換（4件）", val(), "bb bb bb bb")
        js("cm.undo()")
        check("すべて置換は1回の取り消しで元に戻る", val(), "a a a a")

        setdoc("2026-10-03")
        setq(r"(\d+)-(\d+)-(\d+)", re=True, r=r"$3/$2/$1")
        js("finder.replaceAll()")
        check("正規表現の置換で $1 $2 $3 が使える", val(), "03/10/2026")
        setdoc("価格は100円です")
        setq("100", r="$1")
        js("finder.replaceAll()")
        check("正規表現でないときは $ を書いたとおりに置換", val(), "価格は$1円です")

        setq("(", re=True)
        check("正規表現の誤りを知らせる", (count_text(), js("document.getElementById('fq').classList.contains('bad')")), ("正規表現が正しくありません", True))
        setq("a.c", re=False)
        setdoc("abc a.c")
        setq("a.c")
        check("正規表現でないとき . は文字のまま", js("finder.count()"), 1)
        setdoc("a\nb\nc")
        setq("^", re=True)
        check("長さ0の一致は数えない", js("finder.count()"), 0)

        # 閉じる
        js("finder.close()")
        check("閉じるとハイライトが消える", (js("document.getElementById('find').hidden"), js("document.querySelectorAll('.cm-searching').length")), (True, 0))

        # 選択文字が検索語になる
        setdoc("hello world")
        js("cm.setSelection({line:0,ch:6},{line:0,ch:11}); openFind(false)")
        check("選択した文字が検索語に入る", js("document.getElementById('fq').value"), "world")
        js("finder.close()")

        # クリップボードのボタン
        setdoc("コピーする文字")
        js("cm.setSelection({line:0,ch:0},{line:0,ch:4}); document.querySelector('#fmt [data-e=copy]').click()")
        time.sleep(.6)
        check("コピー: クリップボードに入る", clipboard.get_text(), "コピーす")
        js("cm.setSelection({line:0,ch:4},{line:0,ch:7}); document.querySelector('#fmt [data-e=cut]').click()")
        time.sleep(.6)
        check("切り取り: 文字が消えてクリップボードに入る", (val(), clipboard.get_text()), ("コピーす", "る文字"))
        js("cm.setCursor({line:0,ch:3}); document.querySelector('#fmt [data-e=paste]').click()")
        time.sleep(.6)
        check("貼り付け", val(), "コピーる文字す")
        clipboard.set_text("行1\r\n行2")
        js("cm.setValue(''); document.querySelector('#fmt [data-e=paste]').click()")
        time.sleep(.6)
        check("貼り付け: Windows の改行を取り込める", val(), "行1\n行2")

        # 元に戻す／やり直し
        setdoc("abc")
        js("cm.clearHistory(); cm.replaceRange('X', {line:0,ch:0}); updateEditButtons()")
        check("元に戻すボタンが使える", js("document.querySelector('#fmt [data-e=undo]').disabled"), False)
        js("document.querySelector('#fmt [data-e=undo]').click()")
        check("元に戻す", val(), "abc")
        check("やり直しボタンが使える", js("document.querySelector('#fmt [data-e=redo]').disabled"), False)
        js("document.querySelector('#fmt [data-e=redo]').click()")
        check("やり直し", val(), "Xabc")

        # 右クリックのメニュー
        js("cm.setSelection({line:0,ch:0},{line:0,ch:2}); document.querySelector('.CodeMirror').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:300,clientY:300,cancelable:true}))")
        check("右クリックでメニューが出る", js("[...document.querySelectorAll('#ctx .citem span:first-child')].map(e=>e.textContent).join(',')"),
              "元に戻す,やり直し,切り取り,コピー,貼り付け,すべて選択,検索…,置換…")
        js("[...document.querySelectorAll('#ctx .citem')].find(b=>b.textContent.startsWith('すべて選択')).click()")
        check("メニュー: すべて選択", sel(), "Xabc")
        check("メニューは操作後に閉じる", js("document.getElementById('ctx').hidden"), True)
        js("cm.setCursor({line:0,ch:0}); document.querySelector('.CodeMirror').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:300,clientY:300,cancelable:true}))")
        check("選択がなければ切り取り・コピーは使えない", js("[...document.querySelectorAll('#ctx .citem')].filter(b=>b.disabled).map(b=>b.firstChild.textContent).join(',')"), "やり直し,切り取り,コピー")
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        check("Esc でメニューが閉じる", js("document.getElementById('ctx').hidden"), True)

        # 読み取り専用
        js("doc.readonly=true; applyDocMeta(); openFind(true)")
        check("読み取り専用: 検索はできるが置換欄は出ない", js("[!document.getElementById('find').hidden, document.getElementById('rrow').hidden].join()"), "true,true")
        check("読み取り専用: 貼り付け・切り取りは使えない", js("['cut','paste'].every(k=>document.querySelector('#fmt [data-e='+k+']').disabled)"), True)
        check("読み取り専用: コピー・検索は使える", js("['copy','find'].every(k=>!document.querySelector('#fmt [data-e='+k+']').disabled)"), True)
        check("読み取り専用: 置換ボタンは使えない", js("document.querySelector('#fmt [data-e=replace]').disabled"), True)
        js("doc.readonly=false; applyDocMeta(); finder.close()")

        # 貼り付けイベント（Ctrl+V でブラウザーが送るものと同じ）を編集欄へ送る。
        # 実際のキー入力は、別のウィンドウへ送ってしまう恐れがあるので使わない
        js("cm.setValue(''); cm.focus()")
        js("""(() => { const dt = new DataTransfer(); dt.setData('text/plain', 'キー貼付');
          cm.getInputField().dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); })()""")
        time.sleep(.5)
        check("貼り付けイベントで貼り付く（Ctrl+V 相当）", val(), "キー貼付")
    finally:
        if saved is not None:
            clipboard.set_text(saved)
        print("RESULT", sum(results), "/", len(results), flush=True)
        api._dirty = False
        api._closing = True
        os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
