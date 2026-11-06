"""数式（TeX）の書き方を、HTML にする。ビューアとエディタで同じ内容を使う。

書き方は、GitHub などと同じ 3 つ。

    ```math            コードブロック（言語名 math）。独立した行の数式
    E = mc^2
    ```

    $$ ... $$          独立した行の数式（複数行も可）
    $E=mc^2$           文中の数式

ここでは、TeX の文字を HTML に包むだけで、数式の組版は、画面側の KaTeX がする（図を Mermaid が描くのと同じ流れ）。
  - 独立した行の数式 → <div class="math block">TeX</div>
  - 文中の数式       → <span class="math inline">TeX</span>

文中の $ は、金額（$100）などを数式と取り違えないよう、厳しめの規則にしている。
  - $ の内側が空白で始まる・終わる（「$ x $」）ものは、数式にしない
  - 開きの $ の前後・閉じの $ の前後が数字（「$100から$200」）なら、数式にしない
  - 閉じていない $$ は、空行で打ち切る（以降の文書を、数式にしてしまわない）
  - コードの中（`$a$`、コードブロック）は、数式にしない。\\$ と書くと、ただの $ になる
"""
from markdown_it.common.utils import escapeHtml
from mdit_py_plugins.dollarmath import dollarmath_plugin

LANG = "math"          # コードブロックの言語名


def block_html(tex, line=None):
    """独立した行の数式の HTML。line を渡すと、元の行番号（data-line）を付ける（エディタのスクロールの同期用）。"""
    attr = f' data-line="{line}"' if line is not None else ""
    return f'<div class="math block"{attr}>{escapeHtml(tex.strip())}</div>\n'


def apply(md, lines=False):
    """markdown-it に、$...$ と $$...$$ を足す。lines=True なら、行番号の目印（data-line）も付ける。"""
    md.use(dollarmath_plugin, allow_labels=False, allow_space=False, allow_digits=False,
           double_inline=False, allow_blank_lines=False)

    def math_block(self, tokens, idx, options, env):
        tok = tokens[idx]
        return block_html(tok.content, tok.map[0] if lines and tok.map else None)

    md.add_render_rule("math_block", math_block)
    guard_code_spans(md)


def guard_code_spans(md):
    """文中の数式が、コード（`...`）の範囲をまたいで成立したら、取り消す。

    プラグインは、閉じの $ を、あとにあるコードの中まで探しに行く。金額の $ が、あとのコード `$a$` の中の $ と
    組になり、「$100 ... コード `$」が数式になって、コードが壊れた（実データで見つけた）。
    バッククォートを含む一致は、数式にせず、$ をただの文字として進める。そのあと、コードは、ふつうに読まれる。
    """
    rule = next(r for r in md.inline.ruler.__rules__ if r.name == "math_inline")
    original = rule.fn

    def guarded(state, silent):
        start = state.pos
        if not original(state, silent):
            return False
        if "`" in state.src[start:state.pos]:
            if not silent:
                state.tokens.pop()               # 作った数式のトークンを捨てる
            state.pos = start
            return False
        return True

    md.inline.ruler.at("math_inline", guarded)


def katex_assets(vendor_dir):
    """KaTeX の部品を、画面へ渡せる形にして返す。{"js": 描画部品, "css": フォントを埋め込んだ CSS}。

    この画面は、ファイルの読み込み元を持たない（html を文字列で渡している）ので、CSS の
    url(fonts/...) は読めない。フォント（woff2）を data URI にして、CSS の中へ埋め込む。
    CSS の既定は woff2・woff・ttf の 3 つを並べているが、Chromium は woff2 を使うので、woff2 だけにする。
    """
    import base64
    import os
    import re

    with open(os.path.join(vendor_dir, "katex.min.js"), encoding="utf-8") as f:
        js = f.read()
    with open(os.path.join(vendor_dir, "katex.min.css"), encoding="utf-8") as f:
        css = f.read()

    def embed(m):
        with open(os.path.join(vendor_dir, "fonts", m.group(1) + ".woff2"), "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f'url(data:font/woff2;base64,{data}) format("woff2")'

    css = re.sub(r'url\(fonts/([^)]+)\.woff2\) format\("woff2"\),url\(fonts/[^)]+\.woff\) format\("woff"\),'
                 r'url\(fonts/[^)]+\.ttf\) format\("truetype"\)', embed, css)
    if "fonts/" in css:
        raise RuntimeError("KaTeX の CSS の、フォントの指定を読み替えられませんでした（形が変わった可能性）")
    return {"js": js, "css": css}
