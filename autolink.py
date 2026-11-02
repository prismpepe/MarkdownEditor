"""URL 形式のテキストを、自動でリンクにする（GFM の拡張自動リンクに相当。ビューア・エディタ共通）。

CommonMark では `<https://…>` と書かないとリンクにならない。GFM では、文中の `https://…` や `www.…` が
そのままリンクになる。markdown-it-py の `linkify` は、別ライブラリ（linkify-it-py）を要るうえ、
`readme.md` のような名前までリンクにしてしまうので、使わずに自前で実装している。

- 対象は `http://` `https://` で始まるものと、`www.` で始まるもの（`www.` は `http://` を補う）。
- 日本語の文に埋め込まれやすいので、URL に使うのは ASCII の文字だけにする。`https://example.com/を参照` の
  「を参照」や、直後の「。」「、」は URL に含めない。日本語そのものを含むパスは、途中までのリンクになる
  （ブラウザーからコピーした URL は、通常は % エンコードされている）。
- GFM と同じく、末尾の句読点（`?!.,:;*_~'"`）と、対応する開きのない `)` は URL に含めない。
- コード（インライン・ブロック）の中、すでにリンクの中の文字は、対象にしない。
"""
import re

from markdown_it.token import Token

# URL の始まり。直前が ASCII の英数字なら、別の語の一部なので対象にしない（日本語の直後は対象）
START = re.compile(r"(?<![A-Za-z0-9])(?:https?://|www\.)[\x21-\x7e]+", re.I)
TRAILING = "?!.,:;*_~'\""


def _trim(url):
    """末尾の句読点と、対応のない閉じ括弧を外す。"""
    while url:
        last = url[-1]
        if last in TRAILING or last in "<>":
            url = url[:-1]
        elif last == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def _cut(url):
    """`<` や `>` から先は URL に含めない（タグや引用符の記号）。"""
    for ch in "<>":
        i = url.find(ch)
        if i != -1:
            url = url[:i]
    return url


def _valid(url):
    """スキームやドメインだけで中身が無いものは、リンクにしない。"""
    rest = re.sub(r"^(?:https?://|www\.)", "", url, flags=re.I)
    return bool(re.match(r"[A-Za-z0-9][A-Za-z0-9.-]*", rest))


def _split(text, make):
    """text を、リンクにする部分とそれ以外に分けたトークンの並びにして返す。変化が無ければ None。"""
    out, pos = [], 0
    for m in START.finditer(text):
        if m.start() < pos:
            continue
        url = _trim(_cut(m.group(0)))
        if not url or not _valid(url):
            continue
        end = m.start() + len(url)
        if m.start() > pos:
            out.append(make("text", text[pos:m.start()]))
        href = url if re.match(r"https?://", url, re.I) else "http://" + url
        out.extend(_link(make, href, url))
        pos = end
    if not out:
        return None
    if pos < len(text):
        out.append(make("text", text[pos:]))
    return out


def _link(make, href, label):
    opening = make("link_open", "")
    opening.tag, opening.nesting = "a", 1
    opening.attrs = {"href": href}
    opening.markup, opening.info = "autolink-gfm", "auto"
    closing = make("link_close", "")
    closing.tag, closing.nesting = "a", -1
    closing.markup, closing.info = "autolink-gfm", "auto"
    text = make("text", label)
    return [opening, text, closing]


def autolink_rule(state):
    def make(kind, content):
        tok = Token(kind, "", 0)
        tok.content = content
        return tok

    for block in state.tokens:
        if block.type != "inline" or not block.children:
            continue
        depth, result = 0, []
        for tok in block.children:
            if tok.type == "link_open":
                depth += 1
            elif tok.type == "link_close":
                depth -= 1
            if tok.type == "text" and depth == 0:
                pieces = _split(tok.content, make)
                if pieces:
                    result.extend(pieces)
                    continue
            result.append(tok)
        block.children = result


def apply(md):
    """変換器に自動リンクを組み込む。text_join（隣り合う文字のまとめ）のあとに動かす。"""
    md.core.ruler.after("text_join", "autolink_gfm", autolink_rule)
