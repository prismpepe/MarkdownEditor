"""文中の URL が自動でリンクになること（GFM の拡張自動リンク）。"""
import mdeditor
from sanitize import sanitize


def render(text):
    return sanitize(mdeditor.make_renderer().render(text, {"base": ""}))


def link(url, label=None):
    return f'<a href="{url}">{label or url}</a>'


def test_裸のURLがリンクになる():
    assert link("https://www.google.com/") in render("https://www.google.com/")


def test_引用や表や箇条書きの中でもリンクになる():
    assert link("https://example.com/q") in render("> https://example.com/q")
    assert link("https://example.com/t") in render("| URL |\n|---|\n| https://example.com/t |")
    assert link("https://example.com/l") in render("- https://example.com/l")


def test_wwwはhttpを補う():
    assert link("http://www.example.com", "www.example.com") in render("www.example.com を見て")


def test_日本語の文の中でもURLに日本語を巻き込まない():
    assert link("https://example.com/path") + "。次の文" in render("詳細はhttps://example.com/path。次の文")
    assert link("https://example.com/") + "を参照" in render("https://example.com/を参照")


def test_末尾の句読点は含めない():
    out = render("https://example.com/a. https://example.com/b, https://example.com/c! https://example.com/d?")
    for p in "abcd":
        assert link(f"https://example.com/{p}") in out


def test_括弧の釣り合い():
    assert "(" + link("https://example.com/a") + ")" in render("(https://example.com/a)")
    assert link("https://example.com/b_(c)") in render("https://example.com/b_(c)")


def test_クエリの記号を含む():
    assert link("https://example.com/a_b?x=1&amp;y=2") in render("https://example.com/a_b?x=1&y=2 です")


def test_コードの中はリンクにしない():
    assert "<a " not in render("`https://example.com/c`")
    assert "<a " not in render("```\nhttps://example.com/fence\n```")


def test_すでにリンクの文字は二重にしない():
    out = render("[リンク](https://example.com/x) と <https://example.com/y> と [https://example.com/z](https://example.com/z)")
    assert out.count("<a ") == 3
    assert "<a href=\"https://example.com/z\"><a" not in out


def test_スキームもドメインも無いものはリンクにしない():
    for text in ("readme.md や example.com", "xhttps://a.com", "https:// だけ", "www. だけ"):
        assert "<a " not in render(text), text


def test_強調の中のURL():
    assert "<strong>" + link("https://example.com/b") + "</strong>" in render("**https://example.com/b**")


def test_危険なスキームはリンクにならない():
    assert "<a " not in render("javascript:alert(1) と ftp://example.com と file:///C:/x")
