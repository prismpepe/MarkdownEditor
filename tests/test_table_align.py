"""Markdown の表の列の配置（コロン）が、変換と HTML の安全処理を通って最後まで届くこと。"""
import mdeditor
from sanitize import sanitize

TABLE = "| 左 | 中 | 右 | 指定なし |\n|:--|:-:|--:|---|\n| 1 | 2 | 3 | 4 |\n"


def render(text):
    return sanitize(mdeditor.make_renderer().render(text, {"base": ""}))


def test_コロンの指定がセルの配置として残る():
    html = render(TABLE)
    assert html.count('style="text-align: left"') == 2        # 見出しのセルと、本文のセル
    assert html.count('style="text-align: center"') == 2
    assert html.count('style="text-align: right"') == 2


def test_指定なしの列には配置を付けない():
    html = render(TABLE)
    assert "<th>指定なし</th>" in html
    assert "<td>4</td>" in html
