"""Excel のセル・CSV から、Markdown の表と JSON への変換。"""
import json
import re

import mdeditor
import tabular
from sanitize import sanitize

EXCEL = "月\t売上\t備考\r\n一月\t1,234\t好調\r\n二月\t987\t\r\n"       # Excel のセルをコピーしたテキスト（末尾に改行つき）


def convert(text, **kw):
    r = tabular.convert(text, **kw)
    assert "error" not in r, r
    return r


# ---- 読み取り ---------------------------------------------------------------
def test_Excelのセルのコピーを読む():
    assert tabular.parse(EXCEL) == [["月", "売上", "備考"], ["一月", "1,234", "好調"], ["二月", "987", ""]]


def test_カンマ区切りとセミコロン区切りを見分ける():
    assert tabular.parse("a,b\n1,2\n") == [["a", "b"], ["1", "2"]]
    assert tabular.parse("a;b\n1;2\n") == [["a", "b"], ["1", "2"]]


def test_区切りを指定できる():
    assert tabular.parse("a,b\t c\n", "comma") == [["a", "b\t c"]]
    assert tabular.parse("a,b\tc\n", "tab") == [["a,b", "c"]]


def test_引用符つきのセルの中のタブ_改行_引用符():
    text = 'a\tb\n"x\ty"\t"line1\nline2"\n"he said ""hi"""\t5"\n'
    rows = tabular.parse(text)
    assert rows[1] == ["x\ty", "line1\nline2"]
    assert rows[2][0] == 'he said "hi"'


def test_BOMと空行と短い行():
    rows = tabular.parse("\ufeffa,b,c\n\n1,2\n,,\n3\n")
    assert rows == [["a", "b", "c"], ["1", "2", ""], ["3", "", ""]]


def test_セルの前後の空白は取る():
    assert tabular.parse(" a , b \n 1 , 2 \n") == [["a", "b"], ["1", "2"]]


# ---- 見出し ---------------------------------------------------------------------
def test_空の見出しと重なった見出し():
    assert tabular.names_of([["", "a", "a", "a", ""], ["1", "2", "3", "4", "5"]]) == ["列1", "a", "a_2", "a_3", "列5"]


def test_見出しを使わないときは列N():
    rows = [["x", "y"], ["1", "2"]]
    assert tabular.names_of(rows, header=False) == ["列1", "列2"]
    assert json.loads(tabular.to_json(rows, header=False)) == [{"列1": "x", "列2": "y"}, {"列1": 1, "列2": 2}]


# ---- JSON -------------------------------------------------------------------
def test_JSONはオブジェクトの配列_日本語はそのまま():
    out = convert(EXCEL, fmt="json")["output"]
    assert json.loads(out) == [{"月": "一月", "売上": 1234, "備考": "好調"}, {"月": "二月", "売上": 987, "備考": None}]
    assert "一月" in out and "\\u" not in out


def test_数値の判定():
    rows = [["v"], ["12"], ["-3"], ["0.5"], ["1,234"], ["1,234.5"], ["007"], ["12%"], ["1e3"], [".5"], ["5."], ["1,23"], ["abc"], ["0"]]
    values = [o["v"] for o in json.loads(tabular.to_json(rows))]
    assert values == [12, -3, 0.5, 1234, 1234.5, "007", "12%", "1e3", ".5", "5.", "1,23", "abc", 0]


def test_数値を数値にしない指定():
    assert json.loads(tabular.to_json([["v"], ["12"]], numbers=False)) == [{"v": "12"}]


def test_空欄の扱い():
    rows = [["a", "b"], ["1", ""]]
    assert json.loads(tabular.to_json(rows, empty="null")) == [{"a": 1, "b": None}]
    assert json.loads(tabular.to_json(rows, empty="empty")) == [{"a": 1, "b": ""}]
    assert json.loads(tabular.to_json(rows, empty="omit")) == [{"a": 1}]


def test_データが無ければ空の配列():
    assert tabular.to_json([["a", "b"]]) == "[]"


def test_JSONをコードブロックで囲める():
    out = convert("a,b\n1,2\n", fmt="json", fence=True)["output"]
    assert out.startswith("```json\n[") and out.endswith("]\n```")


# ---- Markdown の表 --------------------------------------------------------------
def render(md):
    return sanitize(mdeditor.make_renderer().render(md, {"base": ""}))


def test_Markdownの表に変換され_プレビューで表になる():
    out = convert(EXCEL, fmt="md")["output"]
    assert out.split("\n")[0] == "| 月 | 売上 | 備考 |"
    html = render(out)
    assert html.count("<table") == 1
    assert [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", html)] == \
        ["月", "売上", "備考", "一月", "1,234", "好調", "二月", "987", ""]


def test_数値だけの列は右寄せ():
    out = convert(EXCEL, fmt="md")["output"]
    assert out.split("\n")[1] == "| --- | ---: | --- |"
    assert 'style="text-align: right"' in render(out)


def test_列の配置を指定できる():
    for align, mark in (("left", ":---"), ("center", ":---:"), ("right", "---:"), ("none", "---")):
        assert convert("a,b\n1,2\n", fmt="md", align=align)["output"].split("\n")[1] == "| %s | %s |" % (mark, mark)


def test_セルの縦線と改行が表を壊さない():
    out = convert('a,b\n"x|y","l1\nl2"\n', fmt="md")["output"]
    assert out.split("\n")[2] == "| x\\|y | l1<br>l2 |"
    html = render(out)
    assert html.count("<tr") == 2 and "x|y" in html


def test_パスのバックスラッシュはそのまま():
    assert "C:\\work\\a.txt" in convert("p\nC:\\work\\a.txt\n", fmt="md")["output"]


def test_見出しだけでも表になる():
    out = convert("a,b\n", fmt="md")["output"]
    assert out.split("\n") == ["| a | b |", "| --- | --- |"]


# ---- 変換の入口 ---------------------------------------------------------------
def test_プレビューは先頭の行だけ返し_行数は全体():
    text = "n\n" + "\n".join(str(i) for i in range(100)) + "\n"
    r = convert(text, fmt="md", limit=10)
    assert r["rows"] == 100 and r["lines"] == 102
    assert r["output"].endswith("…（あと 92 行）") and len(r["output"].split("\n")) == 11


def test_誤りは理由を返す():
    assert "データがありません" in tabular.convert("   \n\n")["error"]
    assert "error" in tabular.convert("a,b\n1,2\n", fmt="xml")
    assert "error" in tabular.convert("a,b\n1,2\n", empty="x")
    assert "error" in tabular.convert("a,b\n1,2\n", delimiter="pipe")


def test_大きな表でも現実的な時間で変換できる():
    import time
    text = "id\tname\tvalue\n" + "\n".join("%d\t名前%d\t%d.5" % (i, i, i) for i in range(50000))
    t0 = time.time()
    r = convert(text, fmt="json")
    assert time.time() - t0 < 5 and r["rows"] == 50000
