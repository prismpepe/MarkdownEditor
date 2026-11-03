"""コードブロック（```言語名）の色分け。ビューアとエディタで同じ内容を使う。

Pygments で字句に分け、`<span class="tok-…">` にして返す。色は CSS（画面のライト／ダーク・印刷）が決める。
言語は、コードブロックの最初の語（```bat、```powershell など）で決める。書いていなければ、推測せず、色を付けない
（推測を外すと、普通の文章に色が付いて、かえって読みにくいため）。

- 色を付けないとき（言語が無い・知らない・大きすぎる）は None を返し、呼び出し側が従来の描き方にする。
- 文字は1字も変えない（タグで包むだけ）。色分けの有無で、コードの中身が変わらないことをテストで固定している。
- 図やグラフ（mermaid・vega-lite）は、別の部品が読み取るので、ここでは触れない。
"""
import re
from html import escape

from pygments.lexers import get_lexer_by_name
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound

MAX_CHARS = 200_000          # これを超えるコードは色を付けない（巨大な貼り付けで、表示が固まらないように）

# 別の部品が読み取るもの。色分けしない
SKIP = {"mermaid", "vega-lite", "vegalite", "vega"}

# Pygments が知らない呼び名のうち、よく使われるもの → Pygments の名前
ALIASES = {
    "cmd": "bat", "dos": "bat", "batch": "bat", "bat": "bat",
    "jsonc": "json", "json5": "json",
    "patch": "diff",
    "vb": "vbnet", "vba": "vbnet", "vbs": "vbscript",
    "gradle": "groovy",
    "shell-session": "console", "terminal": "console", "shellsession": "console",
    "powershell-session": "pwsh-session",
    "svelte": "html", "vue": "html",
    "jsonl": "json",
}

# 色を付けない呼び名（「ただの文字」という指定）
PLAIN = {"text", "txt", "plain", "plaintext", "none", "nohighlight", "output", "log"}

_TOKEN_CLASS = {tok: STANDARD_TYPES.get(tok, "") for tok in STANDARD_TYPES}


def language_of(info):
    """コードブロックの情報行から、言語名（小文字）を取り出す。```{.python} や ```python title="a.py" も読む。"""
    words = (info or "").strip().split()
    if not words:
        return ""
    first = words[0].strip("{}").lstrip(".").lower()
    if first.startswith("language-"):
        first = first[len("language-"):]
    return first


def lexer_for(lang):
    """言語名から Pygments の字句解析器を返す。知らなければ None。"""
    if not lang or lang in SKIP or lang in PLAIN:
        return None
    name = ALIASES.get(lang, lang)
    try:
        return get_lexer_by_name(name, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return None


def highlight(code, lang):
    """色を付けた HTML（<span> を含む、<pre><code> の中身）を返す。付けないときは None。"""
    if len(code) > MAX_CHARS or "\r" in code:        # \r があると、解析器が改行をそろえて、文字が変わってしまう
        return None
    lexer = lexer_for(lang)
    if lexer is None:
        return None
    try:
        parts = []
        for tok, text in lexer.get_tokens(code):
            cls = _TOKEN_CLASS.get(tok)
            if cls is None:                          # 副分類（Name.Function.Magic など）は、親の分類で代用する
                t = tok
                while t is not None and t not in _TOKEN_CLASS:
                    t = t.parent
                cls = _TOKEN_CLASS.get(t, "") if t is not None else ""
            body = escape(text, quote=False)
            parts.append(f'<span class="tok-{cls}">{body}</span>' if cls else body)
        out = "".join(parts)
    except Exception:                               # 解析器が壊れる入力でも、コードは普通に表示する
        return None
    # get_tokens は、末尾に改行を足すことがある。元のコードに無ければ落とす（文字を変えない）
    if not code.endswith("\n") and out.endswith("\n"):
        out = out[:-1]
    elif not code.endswith("\n") and out.endswith("\n</span>"):
        out = out[:-len("\n</span>")] + "</span>"
    return out


_LANG_CLASS = re.compile(r"[^a-z0-9_+#.-]")


def render_fence(code, info, extra_pre_attrs=""):
    """```言語名 のコードブロックの HTML。色を付けないとき（言語なし・不明）は None。"""
    lang = language_of(info)
    body = highlight(code, lang)
    if body is None:
        return None
    cls = _LANG_CLASS.sub("", lang)
    return f'<pre{extra_pre_attrs}><code class="language-{cls} highlighted">{body}</code></pre>\n'
