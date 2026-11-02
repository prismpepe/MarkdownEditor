"""Markdown に埋め込まれた HTML を、許可したタグ・属性だけ残して通す。

方針は許可リスト方式。ここに無いタグは外し（中身は残す）、script・style・
iframe など中身ごと危険なものは中身も捨てる。on* 属性・javascript: のリンクは
落とす。style 属性は、改ページの指定（page-break-after: always など）と、
表のセルの text-align（Markdown の列の配置）だけ残す。構文エラーのある HTML でも出力は必ず
ここで組み立て直したものだけになる。
"""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

TAGS = {
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup",
    "col", "div", "span", "p", "br", "hr", "b", "strong", "i", "em", "u", "s",
    "del", "ins", "sub", "sup", "small", "mark", "code", "pre", "kbd", "samp",
    "var", "blockquote", "ul", "ol", "li", "dl", "dt", "dd", "h1", "h2", "h3",
    "h4", "h5", "h6", "a", "img", "details", "summary", "figure", "figcaption",
    "abbr", "cite", "q", "center", "input",
}
VOID = {"br", "hr", "img", "col", "input"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript",
                     "template", "textarea", "select", "button", "form", "svg",
                     "math", "title", "head", "link", "meta", "base"}
COMMON = {"id", "class", "title", "lang", "dir", "data-line"}
ATTRS = {
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "table": {"border", "cellpadding", "cellspacing", "width", "align"},
    "th": {"colspan", "rowspan", "align", "valign", "scope", "width", "height"},
    "td": {"colspan", "rowspan", "align", "valign", "width", "height"},
    "col": {"span", "width"},
    "colgroup": {"span"},
    "ol": {"start", "type", "reversed"},
    "li": {"value"},
    "details": {"open"},
    "input": {"type", "checked", "disabled"},
    "p": {"align"}, "div": {"align"}, "h1": {"align"}, "h2": {"align"},
    "h3": {"align"}, "h4": {"align"}, "h5": {"align"}, "h6": {"align"},
}
LINK_SCHEMES = {"", "http", "https", "mailto", "file"}   # file: は、開いてよいか Api.open_local が確かめる
IMG_SCHEMES = {"", "http", "https"}
_CONTROL = re.compile(r"[\x00-\x20\x7f]+")

# style 属性は原則として落とす。ただし、改ページの指定だけは通す（印刷・PDF で使うため）。
# `<div style="page-break-after: always"></div>` のような、よくある書き方に応える。
PAGE_BREAK_PROPS = {"page-break-before", "page-break-after", "page-break-inside",
                    "break-before", "break-after", "break-inside"}
PAGE_BREAK_VALUES = {"auto", "always", "avoid", "page", "left", "right", "recto", "verso",
                     "avoid-page"}


# 表のセルの左寄せ・中央寄せ・右寄せ。Markdown の `|:--|:-:|--:|` は、変換されると
# `<th style="text-align:center">` になる。これを落とすと、コロンで指定した配置が効かなくなる。
CELL_TAGS = {"th", "td"}
TEXT_ALIGN_VALUES = {"left", "center", "right", "justify"}


def safe_style(value, tag=""):
    """許可した宣言（改ページ、表のセルの text-align）だけを集めて返す。1つも無ければ None。"""
    kept = []
    for decl in html.unescape(value).split(";"):
        name, sep, val = decl.partition(":")
        name, val = name.strip().lower(), val.strip().lower()
        if not sep:
            continue
        if name in PAGE_BREAK_PROPS and val in PAGE_BREAK_VALUES:
            kept.append(f"{name}: {val}")
        elif name == "text-align" and tag in CELL_TAGS and val in TEXT_ALIGN_VALUES:
            kept.append(f"text-align: {val}")
    return "; ".join(kept) or None



def safe_url(value, schemes, allow_data_image=False):
    cleaned = _CONTROL.sub("", html.unescape(value))
    if allow_data_image and re.match(r"data:image/(png|jpe?g|gif|webp|bmp);base64,",
                                     cleaned, re.I):
        return value
    try:
        scheme = urlsplit(cleaned).scheme.lower()
    except ValueError:
        return None
    # "C:\x" のような絶対パスは1文字の「スキーム」に見える。ローカルパスとして通す
    if len(scheme) == 1:
        scheme = ""
    return value if scheme in schemes else None


class _Sanitizer(HTMLParser):
    def __init__(self, image_rewriter=None):
        super().__init__(convert_charrefs=False)
        self.out = []
        self.skip = 0          # 中身ごと捨てているタグの深さ
        self.skip_tag = None
        self.image_rewriter = image_rewriter

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag == self.skip_tag:
                self.skip += 1
            return
        if tag in DROP_WITH_CONTENT:
            if tag not in VOID:
                self.skip, self.skip_tag = 1, tag
            return
        if tag not in TAGS:
            return
        allowed = COMMON | ATTRS.get(tag, set()) | {"style"}
        parts = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed:
                continue
            if value is None:
                value = ""
            if tag == "input" and name == "type" and value.lower() != "checkbox":
                return                      # チェックボックス以外の入力欄は出さない
            if name == "style":
                value = safe_style(value, tag)
            elif name == "href":
                value = safe_url(value, LINK_SCHEMES)
            elif name == "src":
                value = safe_url(value, IMG_SCHEMES, allow_data_image=True)
                if value is not None and self.image_rewriter:
                    value = self.image_rewriter(value)
            if value is None:
                continue
            parts.append(f' {name}="{html.escape(value, quote=True)}"')
        if tag == "input" and not any(p.startswith(" type=") for p in parts):
            return
        self.out.append(f"<{tag}{''.join(parts)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip_tag:
                self.skip -= 1
            return
        if tag in TAGS and tag not in VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data.replace("<", "&lt;").replace(">", "&gt;"))

    def handle_entityref(self, name):
        if not self.skip:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skip:
            self.out.append(f"&#{name};")

    # コメント・宣言・処理命令は捨てる（何も出力しない）


def sanitize(markup, image_rewriter=None):
    parser = _Sanitizer(image_rewriter)
    parser.feed(markup)
    parser.close()
    return "".join(parser.out)
