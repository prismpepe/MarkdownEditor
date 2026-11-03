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


# ---- JSON から表（Excel・CSV から JSON への変換の、逆向き） -------------------------------
JSON_DATA = '[{"月": "一月", "売上": 1234, "備考": "好調"}, {"月": "二月", "売上": 987, "備考": null}]'


def test_JSONのオブジェクトの配列から表を作る():
    r = convert(JSON_DATA, fmt="md")
    assert r["source"] == "json" and r["rows"] == 2 and r["cols"] == 3
    assert r["output"].split("\n") == ["| 月 | 売上 | 備考 |", "| --- | ---: | --- |", "| 一月 | 1234 | 好調 |", "| 二月 | 987 |  |"]


def test_列の順はキーが最初に出てきた順_全部のオブジェクトを見る():
    out = convert('[{"a": 1}, {"b": 2, "a": 3}, {"c": 4}]', fmt="md")["output"].split("\n")
    assert out[0] == "| a | b | c |"
    assert out[2:] == ["| 1 |  |  |", "| 3 | 2 |  |", "|  |  | 4 |"]


def test_値の変換_null_真偽値_数値():
    rows = tabular.load('[{"n": null, "t": true, "f": false, "i": 5, "x": 0.5, "s": "007"}]')["rows"]
    assert rows[1] == ["", "true", "false", "5", "0.5", "007"]


def test_入れ子は_属性つきで1つのセルに入れる():
    rows = tabular.load('[{"id": 1, "pos": {"x": 1, "y": 2}, "tags": ["a", "b"]}]')["rows"]
    assert rows[1] == ["1", '{"x": 1, "y": 2}', '["a", "b"]']
    out = convert('[{"id": 1, "pos": {"x": 1, "y": 2}}]', fmt="md")["output"]
    html = render(out)
    assert "{&quot;x&quot;: 1, &quot;y&quot;: 2}" in html or '{"x": 1, "y": 2}' in html


def test_日本語のキーと値はそのまま():
    assert convert('[{"月": "一月"}]', fmt="md")["output"].split("\n")[0] == "| 月 |"


def test_valuesを持つ形と_Vega_Liteの定義からも読める():
    assert convert('{"values": [{"a": 1}]}', fmt="md")["rows"] == 1
    spec = '{"mark": "bar", "data": {"values": [{"a": 1}, {"a": 2}]}, "encoding": {}}'
    assert convert(spec, fmt="md")["rows"] == 2


def test_配列の配列は_1行目を見出しにするかを選べる():
    text = '[["月", "売上"], ["一月", 3]]'
    assert convert(text, fmt="md", header=True)["output"].split("\n")[0] == "| 月 | 売上 |"
    assert convert(text, fmt="md", header=False)["output"].split("\n")[0] == "| 列1 | 列2 |"


def test_JSONを読んだときは_1行目を見出しにする指定は効かない():
    assert convert(JSON_DATA, fmt="md", header=False)["output"].split("\n")[0] == "| 月 | 売上 | 備考 |"


def test_JSONをJSONに直すときは_元の値のまま整える():
    out = convert('[{"a":"1","b":[1,2]},{"a":2}]', fmt="json")["output"]
    assert json.loads(out) == [{"a": "1", "b": [1, 2]}, {"a": 2}]            # "1"（文字列）が数値に変わらない
    assert out.count("\n") == 3


def test_自動では_JSONとして読めなければ表として読む():
    r = convert("[a],b\n1,2\n", fmt="md")
    assert r["source"] == "table" and r["output"].split("\n")[0] == "| [a] | b |"


def test_JSONを指定したのに読めないときは理由を返す():
    r = tabular.convert("[a],b\n1,2\n", source="json")
    assert "JSON として読めません" in r["error"] and "1 行目" in r["error"]
    assert "JSON として読めません" in tabular.convert("a,b\n1,2\n", source="json")["error"]
    assert "オブジェクトの配列" in tabular.convert('{"a": 1}', source="json")["error"]
    assert "オブジェクトの配列" in tabular.convert('[1, 2, 3]', source="json")["error"]
    assert "データがありません" in tabular.convert('[]', source="json")["error"]


def test_表として読むことを指定できる():
    assert tabular.convert('[{"a": 1}]', source="table")["source"] == "table"


def test_往復しても食い違わない_CSVからJSONを経て表にしたものが_CSVから直接の表と同じ():
    csv_text = "月,売上,割合,備考,番号\n一月,1234,12%,好調,007\n二月,987,3.5%,,008\n三月,0,-5%,\"a|b\",1e3\n"
    direct = convert(csv_text, fmt="md")["output"]
    for empty in ("null", "empty", "omit"):
        as_json = convert(csv_text, fmt="json", empty=empty)["output"]
        assert convert(as_json, fmt="md")["output"] == direct, empty


def test_往復_桁区切りだけが数値になる_1234():
    src = 'v\n"1,234"\n'                                    # Excel・CSV では、桁区切りの数値は、引用符で囲まれて届く
    first = convert(src, fmt="md")["output"]
    back = convert(convert(src, fmt="json")["output"], fmt="md")["output"]
    assert "1,234" in first and "| 1234 |" in back                            # 数値にしたので、桁区切りは戻らない（仕様）


def test_往復_列の順番が変わらない():
    csv_text = "z,a,m\n1,2,3\n"
    out = convert(convert(csv_text, fmt="json")["output"], fmt="md")["output"].split("\n")[0]
    assert out == "| z | a | m |"


def test_JSONの大きな表でも現実的な時間():
    import time
    text = "[" + ",".join('{"id": %d, "name": "名前%d", "value": %d.5}' % (i, i, i) for i in range(50000)) + "]"
    t0 = time.time()
    r = convert(text, fmt="md")
    assert time.time() - t0 < 5 and r["rows"] == 50000


# ---- HTML の表 -----------------------------------------------------------------
def cells_of(html_text):
    return [re.sub(r"<[^>]+>", "", c) for c in re.findall(r"<t[hd](?:\s[^>]*)?>(.*?)</t[hd]>", html_text, re.S)]


def test_HTMLの表の形():
    out = convert("月,売上\n一月,3\n二月,5\n", fmt="html")["output"]
    assert out.split("\n") == [
        "<table>", "  <thead>", '    <tr><th>月</th><th align="right">売上</th></tr>', "  </thead>", "  <tbody>",
        '    <tr><td>一月</td><td align="right">3</td></tr>', '    <tr><td>二月</td><td align="right">5</td></tr>',
        "  </tbody>", "</table>"]


def test_HTMLの表は_プレビューで表になる_配置も残る():
    out = convert(EXCEL, fmt="html")["output"]
    html = render(out)
    assert html.count("<table") == 1 and html.count("<thead>") == 1
    assert cells_of(html) == ["月", "売上", "備考", "一月", "1,234", "好調", "二月", "987", ""]
    assert 'align="right"' in html


def test_HTMLの表に_空行は入らない_Markdownの中で壊れない():
    out = convert("a,b\n1,\n,2\n\n3,4\n", fmt="html")["output"]
    assert "\n\n" not in out
    md_doc = "前の段落\n\n" + out + "\n\n後の段落 **太字**\n"
    html = render(md_doc)
    assert html.count("<table") == 1 and "<strong>太字</strong>" in html


def test_HTMLの特殊文字と改行():
    out = convert('a,b\n"x<y & z","l1\nl2"\n', fmt="html")["output"]
    assert "<td>x&lt;y &amp; z</td>" in out and "<td>l1<br>l2</td>" in out
    html = render(out)
    assert "<script" not in html and cells_of(html)[2] == "x<y & z" or "x&lt;y" in html


def test_HTMLの表に_タグや属性を差し込めない():
    out = convert('a\n"<script>alert(1)</script>"\n"<img src=x onerror=alert(1)>"\n', fmt="html")["output"]
    assert "<script>" not in out and "<img" not in out
    html = render(out)
    assert "<script" not in html and "<img" not in html and "onerror" not in html.replace("&lt;img src=x onerror=alert(1)&gt;", "")


def test_HTMLの表_罫線の指定():
    assert convert("a\n1\n", fmt="html", border=True)["output"].split("\n")[0] == '<table border="1">'
    assert convert("a\n1\n", fmt="html", border=False)["output"].split("\n")[0] == "<table>"
    assert 'border="1"' in render(convert("a\n1\n", fmt="html", border=True)["output"])


def test_HTMLの表_配置の指定():
    for align, attr in (("left", ' align="left"'), ("center", ' align="center"'), ("right", ' align="right"'), ("none", "")):
        out = convert("a,b\n1,x\n", fmt="html", align=align)["output"]
        assert out.count("<th%s>" % attr) == 2 and out.count("<td%s>" % attr) == 2, align


def test_HTMLの表_見出しを使わないときは_theadを付けない():
    out = convert("x,y\n1,2\n", fmt="html", header=False)["output"]
    assert "<thead>" not in out and "<th" not in out
    assert out.count("<tr>") == 2


def test_HTMLの表_見出しだけなら_tbodyは付けない():
    out = convert("a,b\n", fmt="html")["output"]
    assert "<thead>" in out and "<tbody>" not in out and out.endswith("</table>")


def test_JSONから_HTMLの表にできる():
    out = convert(JSON_DATA, fmt="html")["output"]
    assert cells_of(out) == ["月", "売上", "備考", "一月", "1234", "好調", "二月", "987", ""]


def test_HTMLの表と_Markdownの表は_プレビューで同じ内容():
    for text in (EXCEL, "a,b\n1,2\n", "x|y,z\n<1>,2\n", 'a,b\n"l1\nl2",&\n'):
        md_html = render(convert(text, fmt="md")["output"])
        html_html = render(convert(text, fmt="html")["output"])
        assert cells_of(md_html) == cells_of(html_html), text
