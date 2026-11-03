"""表・データの取り込みで、画面が呼ぶ API（CSV の読み込み、JSON の保存、変換）。"""
import json
import os

import pytest

import mdeditor


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return mdeditor.Api(None)


CSV = "月,売上,備考\n一月,1234,好調\n二月,987,\n"


def test_UTF8のCSVを読む(api, tmp_path):
    p = tmp_path / "a.csv"
    p.write_text(CSV, encoding="utf-8")
    assert api.read_table_file(str(p)) == {"text": CSV, "name": "a.csv"}


def test_ExcelのShiftJISのCSVを読む(api, tmp_path):
    p = tmp_path / "excel.csv"
    p.write_bytes(CSV.replace("\n", "\r\n").encode("cp932"))
    r = api.read_table_file(str(p))
    assert "error" not in r and r["text"] == CSV                       # 文字化けせず、改行は LF にそろう


def test_BOM付きUTF8のCSVを読む(api, tmp_path):
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbf" + CSV.encode("utf-8"))
    assert api.read_table_file(str(p))["text"] == CSV


def test_読めないファイルは理由を返す(api, tmp_path):
    (tmp_path / "x.xlsx").write_bytes(b"PK")
    assert "csv" in api.read_table_file(str(tmp_path / "x.xlsx"))["error"].lower()
    assert "読めません" in api.read_table_file(str(tmp_path / "none.csv"))["error"]


def test_読んだ内容から表とJSONに変換できる(api, tmp_path):
    p = tmp_path / "a.csv"
    p.write_text(CSV, encoding="utf-8")
    text = api.read_table_file(str(p))["text"]
    assert api.table_convert(text, {"fmt": "md"})["output"].startswith("| 月 | 売上 | 備考 |")
    assert json.loads(api.table_convert(text, {"fmt": "json"})["output"])[0] == {"月": "一月", "売上": 1234, "備考": "好調"}


def test_変換の指定が壊れていても落ちない(api):
    assert "error" in api.table_convert("a,b\n1,2\n", {"fmt": "xml"})
    assert "output" in api.table_convert("a,b\n1,2\n", "壊れた指定")
    assert "output" in api.table_convert("a,b\n1,2\n", {"header": "no"})


def test_JSONを書く(api, tmp_path):
    doc = tmp_path / "doc.md"
    out = tmp_path / "data" / "sales.json"
    out.parent.mkdir()
    r = api.write_json_file(str(out), '[{"a": 1}]', str(doc))
    assert r["ok"] and r["relative"] == "data/sales.json"
    raw = out.read_bytes()
    assert raw == b'[{"a": 1}]\n' and not raw.startswith(b"\xef\xbb\xbf")        # UTF-8・BOM なし・LF


def test_日本語のJSONをUTF8で書く(api, tmp_path):
    out = tmp_path / "d.json"
    api.write_json_file(str(out), '[{"月": "一月"}]')
    assert json.loads(out.read_text(encoding="utf-8")) == [{"月": "一月"}]


def test_拡張子が無ければjsonを足す(api, tmp_path):
    r = api.write_json_file(str(tmp_path / "data"), "[]")
    assert r["path"].endswith("data.json") and os.path.isfile(r["path"])


def test_文書のフォルダーの外なら相対パスは返さない(api, tmp_path):
    doc = tmp_path / "docs" / "doc.md"
    doc.parent.mkdir()
    r = api.write_json_file(str(tmp_path / "outside.json"), "[]", str(doc))
    assert r["ok"] and r["relative"] is None


def test_書けないときは理由を返す(api, tmp_path):
    assert "保存できませんでした" in api.write_json_file(str(tmp_path / "no_dir" / "x.json"), "[]")["error"]


def test_表の設定は正しい項目だけ覚える():
    import uiprefs
    ok = {"fmt": "json", "delim": "tab", "header": False, "align": "right", "numbers": False, "empty": "omit", "fence": True}
    assert uiprefs.clean_prefs({"table": ok}) == {"table": ok}
    assert uiprefs.clean_prefs({"table": {"fmt": "xml", "delim": "pipe", "header": "yes", "x": 1}}) == {}
    assert uiprefs.clean_prefs({"table": {"fmt": "md", "bad": 1}}) == {"table": {"fmt": "md"}}


def test_JSONファイルを読んで表にできる(api, tmp_path):
    p = tmp_path / "d.json"
    p.write_text('[{"月": "一月", "売上": 3}]', encoding="utf-8")
    r = api.read_table_file(str(p))
    assert "error" not in r and r["name"] == "d.json"
    out = api.table_convert(r["text"], {"fmt": "md"})
    assert out["source"] == "json" and out["output"].split("\n")[0] == "| 月 | 売上 |"


def test_入力の形式を指定できる_誤りは理由を返す(api):
    assert api.table_convert('[{"a": 1}]', {"source": "table"})["source"] == "table"
    assert "JSON として読めません" in api.table_convert("a,b\n1,2\n", {"source": "json"})["error"]
    assert "error" in api.table_convert("a,b\n", {"source": "xml"})


def test_入力の形式も覚える():
    import uiprefs
    assert uiprefs.clean_prefs({"table": {"source": "json"}}) == {"table": {"source": "json"}}
    assert uiprefs.clean_prefs({"table": {"source": "xml"}}) == {}
