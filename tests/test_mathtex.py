"""数式（mathtex.py と、画面への組み込み）。組版は画面側の KaTeX が行うので、ここでは、書き方の取り違えを固定する。"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mathtex
import mdeditor as mdviewer
from sanitize import sanitize

VENDOR = os.path.join(os.path.dirname(__file__), "..", "vendor", "katex")


def render(text):
    return sanitize(mdviewer.make_renderer().render(text, {"base": ""}))


def maths(html):
    """数式として包まれたもの（クラス, 中の TeX）の一覧。"""
    return re.findall(r'<(?:div|span)[^>]*class="math (block|inline)"[^>]*>(.*?)</(?:div|span)>', html, re.S)


# ---- 数式になるもの
def test_文中の数式():
    assert maths(render("式 $E=mc^2$ です")) == [("inline", "E=mc^2")]


def test_日本語の中でも_文中の数式になる():
    assert maths(render("前$x$後と、日本語の$y_i$です")) == [("inline", "x"), ("inline", "y_i")]


def test_独立した行の数式は_複数行でも_ブロックになる():
    assert maths(render("$$\n\\int_0^1 x\\,dx\n$$\n")) == [("block", "\\int_0^1 x\\,dx")]


def test_1行だけの_ドルドルも_ブロックになる():
    assert maths(render("$$ a+b $$")) == [("block", "a+b")]
    assert maths(render("$$a+b$$")) == [("block", "a+b")]


def test_mathのコードブロックは_ブロックの数式():
    out = render("```math\nx = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}\n```\n")
    assert maths(out) == [("block", "x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}")]
    assert "<pre" not in out and "highlighted" not in out


@pytest.mark.parametrize("info", ["math", "Math", "{.math}", "language-math", "math title=\"式\""])
def test_mathの書き方の揺れ(info):
    assert len(maths(render("```%s\nx^2\n```\n" % info))) == 1


def test_表のセルの中の数式():
    out = render("| a | b |\n| - | - |\n| $x$ | 2 |\n")
    assert maths(out) == [("inline", "x")]


def test_リストの中の数式():
    assert maths(render("- 項目 $x$\n\n$$\ny\n$$\n")) == [("inline", "x"), ("block", "y")]


# ---- 数式にしないもの（取り違えない）
@pytest.mark.parametrize("text", [
    "価格は$100から$200です",          # 金額
    "$ x $ は、空白ではさんでいる",
    "$5 と $10",
    "コード `$a$` の中",
    "エスケープ \\$a\\$ です",
    "$$\n未完了の式\n\n次の段落",         # 閉じていない $$ は、空行で打ち切る
    "1ドルは$1、2ドルは$2",
    "金額の $100から$200 は別物です。コード `$a$` は、そのまま。",   # 閉じの $ が、あとのコードの中の $ と組になって、コードを壊した
    "$5 です `x` と `$y$` です",
])
def test_数式にしない(text):
    assert maths(render(text)) == []


def test_金額のあとにコードがあっても_コードは壊れない():
    out = render("金額の $100から$200 は別物です。コード `$a$` は、そのまま。")
    assert maths(out) == [] and "<code>$a$</code>" in out


def test_コードの両側の数式は_どちらも数式になり_コードも残る():
    out = render("先に $x$ と、コード `$a$` と、あとの $y$ です")
    assert maths(out) == [("inline", "x"), ("inline", "y")] and "<code>$a$</code>" in out


def test_コードブロックの中のドルは_数式にしない():
    out = render("```bash\necho $HOME and $PATH\n```\n")
    assert maths(out) == [] and "$HOME" in re.sub(r"<[^>]+>", "", out)


def test_閉じていないドルドルは_以降の文書を巻き込まない():
    out = render("$$\n未完了の式\n\n次の段落は、ふつうの文章\n")
    assert maths(out) == [] and "次の段落は、ふつうの文章" in out


def test_金額と数式が_同じ段落にあっても_数式だけが数式になる():
    out = render("価格は$100から$200で、式は $a+b$ です")
    assert maths(out) == [("inline", "a+b")]


# ---- 安全
def test_TeXの中のタグは_エスケープされ_HTMLとして働かない():
    out = render("$$\n<script>alert(1)</script> a<b & c>d\n$$\n")
    assert "<script" not in out and "&lt;script&gt;" in out
    assert maths(out)[0][1].count("&lt;") >= 2


def test_ブロックの数式は_生のHTMLで書いても_そのまま残るだけ():
    out = render('<div class="math block">x^2</div>\n')
    assert maths(out) == [("block", "x^2")]        # 画面で KaTeX が組むだけ（trust を切ってあり、危険な命令は働かない）


# ---- 図とは別物として扱う
def test_mermaidとvegaは_数式にならない():
    assert 'class="mermaid-src"' in render("```mermaid\nflowchart LR\n  A-->B\n```\n")
    assert maths(render('```vega-lite\n{"mark": "bar"}\n```\n')) == []


def test_mathは_色分けの対象にしない():
    import highlight
    assert highlight.render_fence("x^2\n", "math") is None


# ---- 部品
def test_KaTeXの部品は_フォントを埋め込んだCSSになる():
    a = mathtex.katex_assets(VENDOR)
    assert a["js"].lstrip().startswith("!function") and "katex" in a["js"]
    assert "fonts/" not in a["css"]
    assert a["css"].count("data:font/woff2;base64,") == len(os.listdir(os.path.join(VENDOR, "fonts")))
    assert ".katex" in a["css"] and "KaTeX_Main" in a["css"]


def test_Apiから_KaTeXを取れる():
    api = mdviewer.Api(None)
    a = api.get_katex()
    assert set(a) == {"js", "css"} and api.get_katex() is a      # 2 回目は、作り直さない


# ---- エディタ: 編集欄とプレビューのスクロールの同期のため、ブロックの数式にも、元の行番号が付く
def test_ブロックの数式に_行番号の目印が付く():
    out = render("段落\n\n$$\nx\n$$\n\n```math\ny\n```\n")
    assert re.findall(r'<div class="math block" data-line="(\d+)"', out) == ["2", "6"]
