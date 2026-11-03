"""コードブロックの色分け（highlight.py と、画面への組み込み）。"""
import html
import os
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import highlight
import mdeditor as mdviewer
from sanitize import sanitize


def text_of(markup):
    """タグを除いた、見える文字。"""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def render(md_text):
    return sanitize(mdviewer.make_renderer().render(md_text, {"base": ""}))


SAMPLES = {
    "bat": '@echo off\nREM コメント\nset NAME=world\nif exist "%~dp0a.txt" (\n  echo Hello %NAME%\n) else goto :end\n:end\nfor %%i in (*.txt) do type %%i\n',
    "powershell": '# 日本語コメント\nfunction Get-Foo($a) { Write-Host "x $a"; $env:PATH | Out-Null }\nGet-ChildItem -Recurse | Where-Object { $_.Length -gt 1 }\n',
    "bash": '#!/bin/bash\n# コメント\nNAME="a"\nif [ -f "$NAME" ]; then echo "${NAME}" | grep -E \'x\'; fi\nfor f in *.txt; do cat $f; done\n',
    "python": '@dec\ndef f(x: int) -> str:\n    """説明"""\n    return f"{x}"  # c\n',
    "javascript": 'const a = (x) => `v${x}`; // コメント\nclass A { constructor() { this.x = /re+/g; } }\n',
    "typescript": 'interface A { x: number }\nconst f = <T,>(a: T): T => a;\n',
    "java": 'public class A { @Override public String toString() { return "a" + 1; } }\n',
    "c": '#include <stdio.h>\nint main(void) { printf("%d\\n", 1 << 2); return 0; }\n',
    "cpp": 'template <class T> struct A { T x; };\nauto f = [](int a) { return a; };\n',
    "csharp": 'public record P(string Name);\nvar x = $"{1}";\n',
    "go": 'package main\nfunc main() { ch := make(chan int); go func() { ch <- 1 }() }\n',
    "rust": 'fn main() { let v: Vec<i32> = vec![1]; println!("{:?}", v); }\n',
    "php": '<?php echo "a" . $b; ?>\n',
    "ruby": 'def f(x) = x.map { |a| a * 2 }\nputs "a#{1}"\n',
    "sql": "SELECT a, COUNT(*) FROM t WHERE b = 'x' -- コメント\nGROUP BY a;\n",
    "html": '<div class="a" id="b">本文 &amp; <b>太字</b></div>\n',
    "css": 'a:hover > b { color: #fff; margin: 0 auto; } /* c */\n',
    "json": '{"a": [1, 2.5, true, null], "b": "文字"}\n',
    "yaml": 'a: 1\nb:\n  - x\n  - "y"\n# コメント\n',
    "toml": '[a]\nb = "c"\nd = 1\n',
    "ini": '[section]\nkey=value\n; コメント\n',
    "diff": '--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n',
    "dockerfile": 'FROM python:3\nRUN pip install x \\\n  && echo ok\n',
    "makefile": 'all: a.o\n\t$(CC) -o $@ $^\n',
    "vbscript": 'Dim a\na = "x" & vbCrLf\nMsgBox a\n',
    "console": '$ ls -l\ntotal 0\n',
}


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_主要な言語は_色が付き_文字は1字も変わらない(lang):
    code = SAMPLES[lang]
    out = highlight.highlight(code, lang)
    assert out is not None and "tok-" in out, lang
    assert text_of(out) == code, lang


@pytest.mark.parametrize("name", ["bat", "batch", "cmd", "dos", "powershell", "ps1", "pwsh", "bash", "sh", "zsh", "shell",
                                  "js", "ts", "py", "c++", "cs", "yml", "jsonc", "patch", "vb", "vba", "gradle"])
def test_バッチ_シェルなどの別名も通る(name):
    assert highlight.lexer_for(name) is not None, name


def test_バッチは_コメント_変数_キーワードが分かれる():
    out = highlight.highlight(SAMPLES["bat"], "bat")
    assert re.search(r'tok-c1">REM コメント', out)
    assert 'tok-nv">NAME' in out and 'tok-nv">%~dp0' in out
    assert 'tok-k">echo' in out and 'tok-k">goto' in out


def test_シェルは_コメント_変数_文字列が分かれる():
    out = highlight.highlight(SAMPLES["bash"], "bash")
    assert 'tok-ch">#!/bin/bash' in out and 'tok-c1"># コメント' in out
    assert "tok-nv" in out and "tok-s2" in out and 'tok-k">if' in out


def test_PowerShellは_コメント_変数_コマンドが分かれる():
    out = highlight.highlight(SAMPLES["powershell"], "powershell")
    assert 'tok-c">#' in out or 'tok-c1">#' in out
    assert "tok-nv" in out and "tok-nb" in out


@pytest.mark.parametrize("info,want", [("python", "python"), ("Python", "python"), ("{.python}", "python"), ("{python}", "python"),
                                      ('python title="a.py"', "python"), ("language-bat", "bat"), ("", ""), ("  ", ""), (None, "")])
def test_言語名の読み取り(info, want):
    assert highlight.language_of(info) == want


@pytest.mark.parametrize("info", ["", "unknownlang", "mermaid", "vega-lite", "vegalite", "vega", "text", "txt", "plain"])
def test_言語が無い_知らない_図_ただの文字は_色を付けない(info):
    assert highlight.render_fence("a = 1\n", info) is None


def test_大きすぎるコードと_復帰文字を含むコードは_色を付けない():
    assert highlight.highlight("x\n" * (highlight.MAX_CHARS // 2 + 1), "python") is None
    assert highlight.highlight("a\r\nb\r\n", "python") is None        # 解析器が改行をそろえると、文字が変わるため


def test_末尾に改行が無いコードでも_文字が変わらない():
    for lang in ("bat", "bash", "python"):
        out = highlight.highlight("echo hi", lang)
        assert text_of(out) == "echo hi", lang
    out = highlight.highlight("a\n\n\n", "python")
    assert text_of(out) == "a\n\n\n"


def test_HTMLの特殊文字は_エスケープされ_タグとして働かない():
    code = '<script>alert("x")</script> & <b>\n'
    for lang in ("html", "python", "bash"):
        out = highlight.highlight(code, lang)
        assert "<script>" not in out and text_of(out) == code, lang


def test_コードブロックは_色付きのHTMLになり_サニタイザーを通る():
    html_out = render("```bat\n@echo off\nREM メモ\n```\n")
    assert '<code class="language-bat highlighted">' in html_out
    assert 'tok-k">echo' in html_out and "REM メモ" in html_out
    assert "<span" in html_out


def test_言語なしと_知らない言語は_従来どおり():
    assert "highlighted" not in render("```\nabc\n```\n")
    out = render("```unknownlang\nabc\n```\n")
    assert "highlighted" not in out and "abc" in out


def test_図とグラフのコードは_触らない():
    assert 'class="mermaid-src"' in render("```mermaid\nflowchart LR\n  A-->B\n```\n")
    out = render('```vega-lite\n{"mark": "bar"}\n```\n')
    assert '<code class="language-vega-lite">' in out and "<span" not in out


def test_インラインのコードは_色を付けない():
    assert "<span" not in render("文中の `echo hi` です\n")


def test_色分けしても_コードの文字は元のまま():
    code = SAMPLES["bash"]
    out = render("```bash\n" + code + "```\n")
    m = re.search(r"<pre[^>]*><code[^>]*>(.*)</code></pre>", out, re.S)
    assert text_of(m.group(1)) == code


def test_数千行のコードでも_現実的な時間で終わる():
    code = "\n".join('echo "line %d" # コメント $VAR' % i for i in range(3000)) + "\n"
    start = time.perf_counter()
    out = highlight.highlight(code, "bash")
    assert out is not None and text_of(out) == code
    assert time.perf_counter() - start < 5


def test_エディタでは_行番号の目印が_色付きのコードブロックにも付く():
    out = render("段落\n\n```bat\n@echo off\n```\n")
    assert re.search(r'<pre data-line="2"><code class="language-bat highlighted">', out)
    plain = render("```\nabc\n```\n")
    assert '<pre data-line="0">' in plain
