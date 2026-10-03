import json
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
    assert "<table>" in html and "<td>a</td>" in html
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
