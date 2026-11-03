import json
import os
import re

import pytest

import mdeditor


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return mdeditor.Api(None)


def test_見出しや段落に元の行番号が付く(api):
    html = api.render("# 題名\n\n段落\n\n- a\n- b\n")
    assert re.search(r'<h1[^>]*data-line="0"', html)
    assert re.search(r'<p[^>]*data-line="2"', html)
    assert 'data-line="4"' in html        # リスト


def test_コードブロックにも行番号が付く(api):
    html = api.render("text\n\n```python\nprint(1)\n```\n")
    assert re.search(r'<pre[^>]*data-line="2"', html)
    assert "print(1)" in html


def test_mermaidのブロックは図の元として残る(api):
    html = api.render("```mermaid\nflowchart LR\n  A-->B\n```\n")
    assert 'class="mermaid-src"' in html and 'data-line="0"' in html
    assert "A--&gt;B" in html            # 記述は文字として残り、HTML にならない


def test_埋め込みHTMLの危険な要素は落ちる(api):
    html = api.render('<table><tr><td onclick="x()">a</td></tr></table>\n\n'
                      '<script>alert(1)</script>\n\n<a href="javascript:x()">b</a>\n')
    assert "<table" in html and "<td>a</td>" in html
    assert '<table data-line="0">' in html and '<p data-line="4">' in html   # 行番号の目印（スクロールの同期用）が付く
    for bad in ("<script", "onclick", "javascript:"):
        assert bad not in html


def test_相対パスの画像は埋め込まれ_保存先の無い文書では素通り(api, tmp_path):
    (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    html = api.render("![x](p.png)", str(tmp_path / "doc.md"))
    assert 'src="data:image/png;base64,' in html
    assert 'src="p.png"' in api.render("![x](p.png)", None)


def test_保存の結果が種類ごとに返る(api, tmp_path):
    path = str(tmp_path / "a.md")
    ok = api.save(path, "本文", "UTF-8", "CRLF", None)
    assert ok["ok"] and open(path, "rb").read() == "本文".encode()
    # 他で書き換えられた
    with open(path, "ab") as f:
        f.write(b"x")
    assert api.save(path, "mine", "UTF-8", "LF", ok["stamp"])["kind"] == "conflict"
    # 表せない文字
    res = api.save(path, "😀", "Shift-JIS (CP932)", "LF", None)
    assert res["kind"] == "encoding" and "😀" in res["chars"]
    # 書き込めない場所
    res = api.save(str(tmp_path / "no_such_dir" / "a.md"), "x", "UTF-8", "LF", None)
    assert res["kind"] == "error"


def test_未保存の変更があるうちは閉じるのを止める(api):
    api._window = type("W", (), {"evaluate_js": lambda self, code: None})()
    api.set_dirty(False)
    assert api.on_closing() is True
    api.set_dirty(True)
    assert api.on_closing() is False
    api._closing = True                    # 保存・破棄の確認が済んだあと
    assert api.on_closing() is True


def test_設定が保存され_次回の起動で復元される(api, tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.md").write_text("x", encoding="utf-8")
    assert api.list_files(str(folder))["files"] == ["a.md"]
    api.set_prefs({"view": "edit", "split": 40})
    init = mdeditor.Api(None).get_initial()
    assert init["folder"] == str(folder)           # 前回のフォルダー
    assert init["prefs"] == {"view": "edit", "split": 40}


def test_引数のファイルを開くとそのフォルダーの一覧も出す(api, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("x", encoding="utf-8")
    init = mdeditor.Api(str(f)).get_initial()
    assert init["file"] == str(f) and init["folder"] == str(tmp_path)


def test_相対リンクはmarkdownだけ解決する(api, tmp_path):
    (tmp_path / "b.md").write_text("x", encoding="utf-8")
    (tmp_path / "c.txt").write_text("x", encoding="utf-8")
    cur = str(tmp_path / "a.md")
    assert api.resolve_link(cur, "b.md#sec") == str(tmp_path / "b.md")
    assert api.resolve_link(cur, "c.txt") is None
    assert api.resolve_link(None, "b.md") is None


def test_画面が組み立てられ_部品の置き場が残らない():
    html = mdeditor.build_html()
    assert "/*VENDOR_JS*/" not in html and "/*VENDOR_CSS*/" not in html
    assert "CodeMirror" in html and "fromTextArea" in html


def test_アイコン集が同梱され_読み出せる(api):
    assert "logos" in api.list_icon_packs()
    data = json.loads(api.get_icon_pack("logos"))
    assert data["prefix"] == "logos"
    assert "slack-icon" in data["icons"] and "aws-lambda" in data["icons"]


@pytest.mark.parametrize("name", ["../settings", "logos/../x", "..", "", None, "LOGOS", "a.b", "logos.json"])
def test_アイコン集の名前に不正な文字があれば読まない(api, name):
    assert api.get_icon_pack(name) is None


def test_存在しないアイコン集は空で返す(api):
    assert api.get_icon_pack("no-such-pack") is None


def test_vega_liteのブロックはコードとして残り_行番号が付く(api):
    html = api.render('```vega-lite\n{"mark": "bar"}\n```\n')
    assert re.search(r'<pre[^>]*data-line="0"', html)
    assert 'class="language-vega-lite"' in html


def test_vegaの部品は決めた3つだけ渡す(api):
    with pytest.raises(ValueError):
        api.get_vendor("evil")
    with pytest.raises(ValueError):
        api.get_vendor("../mermaid")


def test_vegaの部品が同梱されている(api):
    # vendor/ に vega.min.js・vega-lite.min.js・vega-embed.min.js を置いていないと、ここで止まる
    for name in ("vega", "vega-lite", "vega-embed"):
        assert len(api.get_vendor(name)) > 1000


def test_データの相対パスは文書のフォルダー配下の決まった形式だけ読める(api, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.csv").write_text("名前,値\nあ,1\n", encoding="utf-8")
    (tmp_path / "data" / "memo.txt").write_text("x", encoding="utf-8")
    (tmp_path.parent / "secret.csv").write_text("s", encoding="utf-8")
    doc = str(tmp_path / "doc.md")

    # 保存先のない文書では読めない
    api.render("x", None)
    assert api.read_data("data/a.csv")["error"]

    api.render("x", doc)
    for ok in ("data/a.csv", "./data/a.csv", "data%2Fa.csv?x=1"):
        r = api.read_data(ok)
        assert r["error"] is None and r["text"] == "名前,値\nあ,1\n"
    for bad in ("../secret.csv", "/etc/passwd.csv", "C:/x.csv", "\\\\srv\\x.csv",
                "file:///x.csv", "data/memo.txt", "data/none.csv", ""):
        assert api.read_data(bad)["error"], bad


def test_画面にバージョンが入る():
    html = mdeditor.build_html()
    assert "__APP_VERSION__" not in html
    assert f"Markdown エディタ v{mdeditor.APP_VERSION}" in html


@pytest.fixture
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(mdeditor.os, "startfile", calls.append, raising=False)
    return calls


def test_ファイルへのリンクは許可した種類だけ関連づけられたアプリで開く(api, tmp_path, opened):
    (tmp_path / "docs" / "sub").mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    for name in ("docs/a.pdf", "docs/sub/b.DOCX", "shared/c.xlsx", "docs/日本語 仕様.pdf",
                 "docs/run.exe", "docs/m.docm"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    cur = str(tmp_path / "docs" / "cur.md")

    for href, want in (("a.pdf", "docs/a.pdf"), ("./a.pdf", "docs/a.pdf"), ("sub/b.DOCX", "docs/sub/b.DOCX"),
                       ("../shared/c.xlsx", "shared/c.xlsx"), ("a.pdf#page=3", "docs/a.pdf"),
                       ("%E6%97%A5%E6%9C%AC%E8%AA%9E%20%E4%BB%95%E6%A7%98.pdf", "docs/日本語 仕様.pdf")):
        opened.clear()
        assert api.open_local(cur, href)["error"] is None, href
        assert opened == [str(tmp_path / want)], href

    for bad in ("run.exe", "m.docm", "none.pdf", "", "#top", "\\\\srv\\x.pdf", "//srv/x.pdf",
                "file://srv/share/x.pdf", "ftp://x/a.pdf", "mailto:a@b", "/etc/a.pdf"):
        opened.clear()
        assert api.open_local(cur, bad)["error"], bad
        assert opened == [], bad


def test_保存先のない文書では相対パスのファイルリンクは開かない(api, opened):
    assert api.open_local(None, "a.pdf")["error"]
    assert opened == []


@pytest.mark.skipif(os.name != "nt", reason="file:///C:/ の形は Windows でだけ確かめる")
def test_file形式のリンクはドライブ名つきのローカルファイルだけ開く(api, tmp_path, opened):
    from pathlib import Path
    (tmp_path / "a.pdf").write_text("x", encoding="utf-8")
    assert api.open_local(None, Path(tmp_path / "a.pdf").as_uri())["error"] is None
    assert opened == [str(tmp_path / "a.pdf")]
    assert api.open_local(None, "file://srv/share/a.pdf")["error"]


def test_フォントなどの設定は検査して保存し_次回に復元する(api, tmp_path):
    api.set_prefs({"fonts": {"editor": {"family": "MS Gothic, Arial", "size": 20},
                             "body": {"family": "a{b}", "size": 9999},
                             "head": {"family": "", "sizes": {"h1": 40, "h2": 5}}},
                   "zoom": {"value": 1.5, "fit": True}, "side_hidden": True,
                   "view": "bogus", "split": 40, "editorSize": 18})
    prefs = mdeditor.Api(None).get_prefs()
    assert prefs["fonts"]["editor"] == {"family": "MS Gothic", "size": 20}    # 名前は最初の1つだけ
    assert prefs["fonts"]["body"] == {"family": "ab", "size": 0}              # 範囲外は既定に戻す
    assert prefs["fonts"]["head"]["sizes"] == {"h1": 40}
    assert prefs["zoom"] == {"value": 1.5, "fit": True} and prefs["side_hidden"] is True
    assert "view" not in prefs and prefs["split"] == 40 and prefs["editorSize"] == 18
    assert mdeditor.Api(None).get_initial()["prefs"] == prefs


def test_設定に不正な値があっても既存の設定を壊さない(api):
    api.set_prefs({"view": "edit"})
    api.set_prefs("だめ")
    api.set_prefs({"zoom": {"value": 99}, "split": "x"})
    assert api.get_prefs() == {"view": "edit"}


def test_ファイル名を指定して起動したときは使用フォルダーを記憶しない(api, tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    api.list_files(str(old))
    api.read_file(str(old / "none.md"))             # 読めなくても記憶は変わらない
    f = tmp_path / "new" / "a.md"
    f.parent.mkdir()
    f.write_text("x", encoding="utf-8")
    started = mdeditor.Api(str(f))
    started.list_files(str(f.parent))
    started.read_file(str(f))
    assert mdeditor.Api(None).get_initial()["folder"] == str(old)
    started.pick_folder = None                      # 選び直すと記憶を再開する
    started._persist_location = True
    started.list_files(str(f.parent))
    assert mdeditor.Api(None).get_initial()["folder"] == str(f.parent)


def test_ウィンドウの位置と大きさは閉じるときだけ保存する(api):
    class Native:
        WindowState = 0
        Left, Top, Width, Height = 10, 20, 1000, 700
    class Win:
        native = Native()
    api._keeper = mdeditor.WindowKeeper(Win(), 1000, 700, False)
    api.set_dirty(True)
    assert api.on_closing() is False                  # 未保存の確認中は保存しない
    assert "window" not in mdeditor.load_settings()
    api._closing = True
    assert api.on_closing() is True
    assert mdeditor.load_settings()["window"] == {"x": 10, "y": 20, "width": 1000,
                                                  "height": 700, "maximized": False}
    import uiprefs
    assert uiprefs.clean_window({"width": 10, "height": 10}) == {}


def test_JS_APIには公開の属性として関数以外を置かない(api):
    """pywebview は公開属性をたどって JS 側の API を作る。ウィンドウなどの重い物を公開属性に
    置くと、起動時にたどり続けて画面が固まる。物は _ 付きの属性に置く。"""
    api._keeper = mdeditor.WindowKeeper(object(), 100, 100, False)
    assert [n for n in vars(api) if not n.startswith("_")] == []


def test_スタンプは文字列で受け渡し_JavaScriptの数値で丸められても誤検知しない(api, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("x", encoding="utf-8")
    doc = api.read_file(str(f))["doc"]
    assert isinstance(doc["stamp"], str)
    assert api.check_changed(str(f))["stamp"] == doc["stamp"]
    ok = api.save(str(f), "y", "UTF-8", "LF", doc["stamp"])
    assert ok["ok"] and isinstance(ok["stamp"], str)
    assert api.save(str(f), "z", "UTF-8", "LF", ok["stamp"])["ok"]     # 何も変わっていなければ通る
    assert api.save(str(f), "w", "UTF-8", "LF", "壊れた値")["kind"] == "conflict"


def test_起動時は前回のフォルダーだけを復元し_ファイルは開かない(api, tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    doc = folder / "a.md"
    doc.write_text("x", encoding="utf-8")
    api.list_files(str(folder))
    assert api.read_file(str(doc))["error"] is None
    assert api.save(str(doc), "y", "UTF-8", "LF", None)["ok"]
    assert "last_file" not in mdeditor.load_settings()         # 開いたファイルは記憶しない
    init = mdeditor.Api(None).get_initial()
    assert init["folder"] == str(folder) and init["file"] is None


def test_以前の版が記録した前回のファイルがあっても_開かない(api, tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    doc = folder / "a.md"
    doc.write_text("x", encoding="utf-8")
    mdeditor.save_settings({"last_folder": str(folder), "last_file": str(doc)})
    init = mdeditor.Api(None).get_initial()
    assert init["folder"] == str(folder) and init["file"] is None


def test_表示モードは4つ_新しい設定の印も保存される(api):
    for view in ("triple", "split", "edit", "preview"):
        api.set_prefs({"view": view})
        assert api.get_prefs()["view"] == view
    api.set_prefs({"view": "bogus"})
    assert api.get_prefs()["view"] == "preview"                # 不正な値は受け付けず、直前の値のまま
    api.set_prefs({"layout_v": 2})
    assert api.get_prefs()["layout_v"] == 2
    for bad in (1, 3, "2", True, None):
        api.set_prefs({"layout_v": bad})
        assert api.get_prefs()["layout_v"] == 2                # 不正な値で、印は書き換わらない


def test_設定を続けて保存しても_先の書き込みが消えない(api):
    """画面は設定を続けて保存し、呼び出しは別のスレッドで同時に動く。順番に処理しないと、先の書き込みが消える。"""
    import threading
    patches = [{"view": ["triple", "split", "edit", "preview"][i % 4]} if i % 2 == 0
               else {"layout_v": 2} for i in range(200)]
    patches += [{"zoom": {"value": 1.5, "fit": False}}, {"split": 40}]
    threads = [threading.Thread(target=api.set_prefs, args=(p,)) for p in patches]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    prefs = api.get_prefs()
    assert prefs.get("layout_v") == 2                      # 途中の書き込みで消えていない
    assert prefs.get("zoom") == {"value": 1.5, "fit": False} and prefs.get("split") == 40
    assert prefs.get("view") in ("triple", "split", "edit", "preview")
