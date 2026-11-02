"""目次の作成。リンクが、プレビューの見出しの id と必ず一致すること。"""
import re

import mdeditor
import toc
from sanitize import sanitize

DOC = """# 題名

## はじめに

本文

## 使い方

### 手順 1

### 手順 1

```
# コードの中の見出しは数えない
```

## <span style="color:red">色つき</span> 見出し

<h2>HTML の見出し</h2>

<h3 id="own-id">id のある HTML の見出し</h3>

見出し（Setext）
================
"""


def md():
    return mdeditor.make_renderer()


def ids_in_preview(text):
    html = sanitize(md().render(text, {"base": ""}))
    return set(re.findall(r'\bid="([^"]+)"', html))


def links(text):
    return re.findall(r"\]\(#([^)]+)\)", text)


def test_目次のリンクは全てプレビューの見出しのidと一致する():
    r = toc.update(DOC, md(), cursor_line=2, min_level=1, max_level=6)
    assert "error" not in r
    ids = ids_in_preview(r["text"])
    assert links(r["text"]), r["text"]
    for target in links(r["text"]):
        assert target in ids, (target, sorted(ids))


def test_コードブロックの中の見出しは目次に入らない():
    r = toc.update(DOC, md(), 0, 1, 6)
    assert "コードの中" not in r["text"].split("<!-- /toc -->")[0]


def test_同じ見出しが続くと番号が付き_どちらも別のリンクになる():
    r = toc.update(DOC, md(), 0, 1, 6)
    block = r["text"].split("<!-- /toc -->")[0]
    assert block.count("[手順 1]") == 2
    assert len(set(links(block))) == len(links(block))


def test_インラインのHTMLは文字だけ拾う():
    r = toc.update(DOC, md(), 0, 1, 6)
    assert "[色つき 見出し]" in r["text"]
    assert "<span" not in r["text"].split("<!-- /toc -->")[0]


def test_HTMLの見出しにidが無ければ足し_あれば使う():
    r = toc.update(DOC, md(), 0, 1, 6)
    assert r["added_ids"] == 1
    assert "<h2 id=" in r["text"]
    assert "(#own-id)" in r["text"]
    assert r["text"].count('id="own-id"') == 1


def test_範囲の外の見出しは入れない():
    r = toc.update(DOC, md(), 0, 2, 2)
    block = r["text"].split("<!-- /toc -->")[0]
    assert "[題名]" not in block and "[手順 1]" not in block
    assert "[はじめに]" in block


def test_入れ子は段が飛んでも1段ずつ():
    r = toc.update("# A\n\n#### D\n\n## B\n", md(), 0, 1, 6)
    lines = [l for l in r["text"].split("\n") if l.lstrip().startswith("- [")]
    assert lines == ["- [A](#a)", "  - [D](#d)", "  - [B](#b)"]


def test_印があれば作り直し_印の外は変えない():
    text = "前の文\n\n<!-- toc -->\n\n- [古い](#old)\n\n<!-- /toc -->\n\n## 新しい見出し\n\n後の文\n"
    r = toc.update(text, md(), 0, 1, 6)
    assert r["updated"] is True
    assert "古い" not in r["text"] and "[新しい見出し](#新しい見出し)" in r["text"]
    assert r["text"].startswith("前の文\n\n<!-- toc -->") and r["text"].endswith("後の文\n")


def test_二度目の更新で変わらない():
    first = toc.update(DOC, md(), 2, 1, 6)["text"]
    second = toc.update(first, md(), 0, 1, 6)
    assert second["updated"] is True and second["text"] == first


def test_印が無ければカーソルの行へ入れる():
    r = toc.update("# A\n\n本文\n\n## B\n", md(), 2, 1, 6)
    assert r["updated"] is False
    assert r["text"].split("\n")[:3] == ["# A", "", "<!-- toc -->"] and "\n本文\n" in r["text"]


def test_目次という見出しは除ける():
    text = "# 題名\n\n## 目次\n\n## 本編\n"
    assert "[目次]" not in toc.update(text, md(), 0, 1, 6, skip_title=True)["text"]
    assert "[目次]" in toc.update(text, md(), 0, 1, 6, skip_title=False)["text"]


def test_コードブロックの中の印は無視する():
    text = "# A\n\n```\n<!-- toc -->\n<!-- /toc -->\n```\n"
    r = toc.update(text, md(), 0, 1, 6)
    assert r["updated"] is False


def test_終わりの印が無ければ作らない():
    r = toc.update("# A\n\n<!-- toc -->\n\n本文\n", md(), 0, 1, 6)
    assert "error" in r and "/toc" in r["error"]


def test_見出しが無ければ作らない():
    assert "error" in toc.update("本文だけ\n", md(), 0, 1, 6)
    assert "error" in toc.update("# A\n", md(), 0, 3, 2)


def test_記号を含む見出しのラベルは壊れない():
    r = toc.update("# 配列 [0] と C:\\path\n", md(), 0, 1, 6)
    assert "[配列 \\[0\\] と C:\\\\path]" in r["text"]
    assert not links("x") and links(r["text"])


# ---- 目次の指定の保存（uiprefs）
def test_目次の指定は正しいものだけ保存する():
    import uiprefs
    assert uiprefs.clean_prefs({"toc": {"min": 2, "max": 4, "skip": 1}}) == {"toc": {"min": 2, "max": 4, "skip": True}}
    for bad in ({"min": 0, "max": 3}, {"min": 5, "max": 2}, {"min": "1", "max": 3}, {"min": 1, "max": 7},
                {"min": True, "max": 3}, "x", None):
        assert uiprefs.clean_prefs({"toc": bad}) == {}
