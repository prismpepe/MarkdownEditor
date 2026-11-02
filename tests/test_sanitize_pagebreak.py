"""改ページの指定（class と style）が通り、それ以外の style は落ちること。"""
import pytest

from sanitize import sanitize


@pytest.mark.parametrize("cls", ["page-break", "pagebreak", "page-break-before", "page-break-after", "page-break-avoid"])
def test_改ページのclassは残る(cls):
    assert sanitize(f'<div class="{cls}"></div>') == f'<div class="{cls}"></div>'


def test_昔ながらの改ページのstyleが残る():
    out = sanitize('<div style="page-break-after: always;"></div>')
    assert out == '<div style="page-break-after: always"></div>'


def test_新しい書き方のstyleも残る():
    assert sanitize('<div style="break-before:page"></div>') == '<div style="break-before: page"></div>'


def test_大文字や空白が混ざっても残る():
    assert sanitize('<div style=" PAGE-BREAK-BEFORE : Always ; "></div>') == '<div style="page-break-before: always"></div>'


def test_改ページ以外の宣言は落ちる():
    out = sanitize('<div style="color:red; page-break-after: always; position:fixed"></div>')
    assert out == '<div style="page-break-after: always"></div>'


def test_改ページが無いstyleは属性ごと消える():
    assert sanitize('<div style="color:red"></div>') == '<div></div>'


@pytest.mark.parametrize("style", [
    "page-break-after: url(javascript:alert(1))",
    "page-break-after: always; background: url(http://x/y)",
    "break-after: expression(alert(1))",
    "page-break-after: 99",
])
def test_危険な値や知らない値は落ちる(style):
    out = sanitize(f'<div style="{style}"></div>')
    assert "url" not in out and "expression" not in out and "99" not in out
    assert "javascript" not in out


def test_スクリプトは従来どおり動かない():
    out = sanitize('<div class="page-break" onclick="x()"></div><script>x()</script>')
    assert out == '<div class="page-break"></div>'


# ---- 表の列の配置（Markdown の |:--|:-:|--:|）
@pytest.mark.parametrize("align", ["left", "center", "right"])
@pytest.mark.parametrize("tag", ["th", "td"])
def test_表のセルの配置は残る(tag, align):
    assert sanitize(f'<{tag} style="text-align:{align}">x</{tag}>') == f'<{tag} style="text-align: {align}">x</{tag}>'


def test_セル以外のtext_alignは落ちる():
    assert sanitize('<p style="text-align:center">x</p>') == '<p>x</p>'
    assert sanitize('<div style="text-align:right">x</div>') == '<div>x</div>'


def test_text_alignの知らない値は落ちる():
    assert sanitize('<td style="text-align:url(javascript:x)">x</td>') == '<td>x</td>'
    assert sanitize('<td style="text-align:start; color:red">x</td>') == '<td>x</td>'

