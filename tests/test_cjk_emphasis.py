"""日本語の文で、記号（括弧など）に接した `**強調**` が効くこと。"""
import pytest
from markdown_it import MarkdownIt

import cjk_emphasis


@pytest.fixture
def md():
    m = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    return cjk_emphasis.apply(m)


def render(md, text):
    return md.render(text).strip()


def test_報告された例_括弧を含む強調が効く(md):
    text = ("被害賠償については、発生住戸（加害住戸）が加入している**「個人賠償責任保険」"
            "（火災保険特約、自動車保険特約、クレジットカード特約等）の優先使用を原則**とする。")
    html = render(md, text)
    assert "<strong>「個人賠償責任保険」（火災保険特約、自動車保険特約、クレジットカード特約等）の優先使用を原則</strong>とする。" in html
    assert "**" not in html


@pytest.mark.parametrize("text,want", [
    # 開始側: 前が日本語の文字、後ろが記号
    ("加入している**「保険」の使用**とする", "<strong>「保険」の使用</strong>"),
    ("対象は**（注意）事項**です", "<strong>（注意）事項</strong>"),
    # 終了側: 前が記号、後ろが日本語の文字
    ("価格は**100円（税込）**です", "<strong>100円（税込）</strong>"),
    ("これは**重要な「決定」**になる", "<strong>重要な「決定」</strong>"),
    # 両側が記号
    ("これは**（注意）**です", "<strong>（注意）</strong>"),
    # 斜体・取り消し線も同じ
    ("対象は*「保険」*です", "<em>「保険」</em>"),
    ("対象は~~「旧制度」~~です", "<s>「旧制度」</s>"),
    # もとから効いていた形は変わらない
    ("これは**重要**です", "<strong>重要</strong>"),
    ("これは **重要** です", "<strong>重要</strong>"),
    ("**太字**と*斜体*", "<strong>太字</strong>と<em>斜体</em>"),
])
def test_日本語の強調(md, text, want):
    assert want in render(md, text)


@pytest.mark.parametrize("text", [
    "2 ** 3 ** 4",                 # 前後が空白の記号は強調にならない
    "word**(x)**word",             # 英数字だけの文は、CommonMark の規則のまま
    "a**「b」**c",                 # 前後が英字のときも従来どおり
    "`**コード**`",                # コードの中は触らない
])
def test_強調にならないものは_ならないまま(md, text):
    html = render(md, text)
    assert "<strong>" not in html


def test_コードの中の記号はそのまま(md):
    assert "<code>**コード**</code>" in render(md, "`**コード**`")


def test_強調記号が対にならなければ_そのまま表示する(md):
    html = render(md, "加入している**「保険」の使用とする")
    assert "<strong>" not in html and "**" in html


def test_リストや表の中でも効く(md):
    html = render(md, "- 原則**「個人保険」（特約）の使用**とする\n\n| 項目 | 内容 |\n|---|---|\n| 保険 | **「個人賠償」（特約）**です |")
    assert html.count("<strong>") == 2


@pytest.mark.parametrize("ch,want", [
    ("あ", True), ("ア", True), ("ー", True), ("漢", True), ("한", True), ("ｱ", True),
    ("「", False), ("（", False), ("、", False), ("。", False),   # 日本語の記号は文字ではない
    ("a", False), ("1", False), (" ", False), ("(", False),
])
def test_日本語の文字の判定(ch, want):
    assert cjk_emphasis.is_cjk(ch) is want
