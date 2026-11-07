import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lint as L
import mdeditor


@pytest.fixture(scope="module")
def md():
    return mdeditor.make_renderer()


def run(md, text, **kw):
    return L.lint(text, md, **kw)


def rules(md, text, **kw):
    return [i["rule"] for i in run(md, text, **kw)]


def test_clean_document_has_no_issues(md):
    assert run(md, "# 題名\n\n本文です。\n\n## 節\n\n- a\n- b\n") == []


def test_heading_increment(md):
    assert "MD001" in rules(md, "# a\n\n### b\n")
    assert "MD001" not in rules(md, "# a\n\n## b\n\n### c\n")


def test_trailing_spaces_allow_hard_break(md):
    assert "MD009" in rules(md, "# a\n\n行末  \n\n")          # 次が空行なら改行にならない
    assert "MD009" not in rules(md, "一行目  \n二行目\n")      # ちょうど2つで続くなら改行
    assert "MD009" in rules(md, "一行目   \n二行目\n")         # 3つは指摘


def test_blank_lines(md):
    r = run(md, "a\n\n\n\nb\n")
    assert [i["line"] for i in r if i["rule"] == "MD012"] == [2]


def test_heading_without_space(md):
    assert "MD018" in rules(md, "#見出し\n")
    assert "MD018" not in rules(md, "#123 の件\n")
    assert "MD018" not in rules(md, "```\n#見出し\n```\n")


def test_blank_around_heading(md):
    assert "MD022" in rules(md, "本文\n# 見出し\n本文\n")
    assert "MD022" not in rules(md, "本文\n\n# 見出し\n\n本文\n")


def test_duplicate_and_multiple_h1(md):
    r = rules(md, "# a\n\n## x\n\n## x\n\n# b\n")
    assert "MD024" in r and "MD025" in r


def test_default_off_rules_are_listed_but_still_work_when_enabled(md):
    text = "# 見出し。\n\n```\nコード\n```\n\n![](x.png)\n"
    r = rules(md, text)
    assert {"MD026", "MD040", "MD045"} <= set(r)       # lint() 自体は全部調べる。既定で切るのは画面側
    assert set(L.DEFAULT_OFF) == {"MD010", "MD026", "MD040", "MD045"}


def test_disabled_rules_are_skipped(md):
    assert "MD001" not in rules(md, "# a\n\n### b\n", disabled=["MD001"])


def test_empty_link_and_fragment(md):
    r = run(md, "# 概要\n\n[空]()\n\n[内部](#概要)\n\n[無い](#存在しない)\n")
    assert [i["line"] for i in r if i["rule"] == "MD042"] == [2]
    assert [i["line"] for i in r if i["rule"] == "MD051"] == [6]


def test_fragment_to_html_id(md):
    assert "MD051" not in rules(md, '<a id="top"></a>\n\n[先頭](#top)\n')


def test_undefined_reference(md):
    assert "MD052" in rules(md, "[文字][なし]\n")
    assert "MD052" not in rules(md, "[文字][あり]\n\n[あり]: http://example.com\n")


def test_unclosed_fence(md):
    r = run(md, "本文\n\n```python\nprint(1)\n")
    assert [i["line"] for i in r if i["rule"] == "X005"] == [2]
    assert "X005" not in rules(md, "```python\nprint(1)\n```\n")


def test_leftover_emphasis_marks(md):
    assert "X004" in rules(md, "これは** 太字 **です\n")
    assert "X004" not in rules(md, "これは**太字**です\n")
    assert "X004" not in rules(md, "`**` はコードの中\n")


def test_unclosed_math_block(md):
    assert "X006" in rules(md, "$$\nx = 1\n")
    assert "X006" not in rules(md, "$$\nx = 1\n$$\n")


def test_table_problems(md):
    assert "X007" in rules(md, "| a | b |\n|--|--|\n| 1 | 2 | 3 |\n")           # 切り捨て
    assert "X007" in rules(md, "| a | b |\n|--|\n| 1 | 2 |\n")                  # 列数が合わず表にならない
    assert "X007" not in rules(md, "| a | b |\n|--|--|\n| 1 | 2 |\n")


def test_vega_lite_json_error(md):
    r = run(md, "```vega-lite\n{\"a\": 1,}\n```\n")
    assert any(i["rule"] == "X008" for i in r)
    assert "X008" not in rules(md, "```vega-lite\n{\"a\": 1}\n```\n")


def test_html_dropped_by_sanitizer(md):
    assert "X003" in rules(md, "<script>alert(1)</script>\n")
    assert "X003" in rules(md, '<div onclick="x()">a</div>\n')
    assert "X003" in rules(md, "<font color=red>赤</font>\n")
    assert "X003" not in rules(md, '<div align="center">a</div>\n')
    assert "X003" not in rules(md, "<!-- コメント -->\n\n本文\n")


def test_missing_files_only_when_saved(md, tmp_path):
    doc = tmp_path / "a.md"
    (tmp_path / "ok.png").write_bytes(b"x")
    text = "[あり](ok.png) [無い](none.pdf) ![図](ok.png) ![図](none.png) [web](https://x.example)\n"
    assert "X001" not in rules(md, text) and "X002" not in rules(md, text)     # 保存前は調べない
    r = run(md, text, doc_path=str(doc))
    assert [i["rule"] for i in r if i["rule"] in ("X001", "X002")] == ["X001", "X002"]


def test_directives(md):
    text = "<!-- lint-disable MD001 -->\n# a\n\n### b\n<!-- lint-enable MD001 -->\n\n##### c\n"
    r = run(md, text)
    assert [i["line"] for i in r if i["rule"] == "MD001"] == [6]
    assert "MD018" not in rules(md, "<!-- lint-disable-next-line MD018 -->\n#見出し\n")
    assert "MD018" in rules(md, "<!-- lint-disable-next-line MD018 -->\n\n#見出し\n")
    assert rules(md, "<!-- markdownlint-disable -->\n#見出し\n") == []


def test_directive_in_code_is_ignored(md):
    assert "MD018" in rules(md, "```\n<!-- lint-disable -->\n```\n\n#見出し\n")


def test_code_regions_are_not_checked(md):
    assert rules(md, "```\n#見出し   \n\n\n\n**x\n```\n", ) == ["MD040"]


def test_huge_document_is_skipped(md):
    assert run(md, "a" * (L.MAX_CHARS + 1)) == []


def test_issue_cap(md):
    text = "".join("#x\n\n" for _ in range(800))
    assert len(run(md, text)) == L.MAX_ISSUES


def test_rule_table_is_consistent():
    ids = [r[0] for r in L.RULES]
    assert len(ids) == len(set(ids))
    for r in L.RULES:
        assert r[1] and r[3]


def test_clean_lint_prefs():
    import uiprefs
    c = uiprefs.clean_lint({"auto": False, "open": True, "disabled": ["MD001", "ZZ", 5, "MD001", "X004"]})
    assert c == {"auto": False, "open": True, "disabled": ["MD001", "X004"]}
    assert uiprefs.clean_lint({"auto": "yes", "disabled": "MD001"}) == {}
    assert uiprefs.clean_lint(None) == {}
    assert uiprefs.clean_prefs({"lint": {"auto": True}}) == {"lint": {"auto": True}}
    assert uiprefs.clean_prefs({"lint": {"x": 1}}) == {}


def test_api_lint(tmp_path):
    api = mdeditor.Api(None)
    r = api.lint("# a\n\n### b\n", None, [])
    assert [i["rule"] for i in r["issues"]] == ["MD001"]
    assert api.lint("# a\n\n### b\n", None, ["MD001"])["issues"] == []
    assert api.lint(None)["issues"] == []
    assert api.lint("a" * (L.MAX_CHARS + 1))["skipped"] is True
    assert any(x["id"] == "X009" for x in api.lint_rules())
