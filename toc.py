"""見出しから目次（内部リンク）を作り、Markdown 本文へ埋め込む（エディタ）。

- 見出しは、プレビューと同じ変換器（markdown-it）で読む。コードブロックの中の `#` は見出しにならず、
  内部リンクの id も、プレビューが見出しに付ける id そのもの（日本語はそのまま。同じ見出しが続くと `-1` `-2`）になる。
  だから、目次のリンクは、このアプリのプレビューで必ず飛べる。
- `# 見出し`・`見出し\\n===`（Setext）・`## <span>…</span> 見出し`（インラインの HTML は文字だけ拾う）・
  `<h2>見出し</h2>`（HTML の見出し）を拾う。HTML の見出しに id が無いときは、id を足す（リンク先が無いため）。
- 目次は `<!-- toc -->` と `<!-- /toc -->` の間に入れる。印があれば、その間だけを作り直す（見出しを直したあとの更新）。
  印が無ければ、指定した行に、印ごと挿入する。
"""
import html as htmllib
import re

from mdit_py_plugins.anchors.index import slugify

TOC_TITLES = {"目次", "もくじ", "table of contents", "contents", "toc"}
BEGIN = re.compile(r"^[ \t]*<!--\s*toc\s*-->[ \t]*$", re.I)
END = re.compile(r"^[ \t]*<!--\s*/toc\s*-->[ \t]*$", re.I)
HTML_HEADING = re.compile(r"<h([1-6])\b([^>]*)>(.*?)</h\1\s*>", re.I | re.S)
ID_ATTR = re.compile(r"""\bid\s*=\s*(["'])(.*?)\1""", re.I)


def _plain(children):
    """見出しの中身の、表示される文字。インラインの HTML タグは捨て、強調などの記号は外す。"""
    parts = []
    for c in children or []:
        if c.type in ("text", "code_inline"):
            parts.append(c.content)
        elif c.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif c.type == "image":
            parts.append(_plain(c.children))
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _html_label(inner):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]*>", "", inner))).strip()


def _unique(slug, taken):
    base, n = slug, 0
    while slug in taken:
        n += 1
        slug = "%s-%d" % (base, n)
    taken.add(slug)
    return slug


def _code_lines(tokens):
    lines = set()
    for t in tokens:
        if t.type in ("fence", "code_block") and t.map:
            lines.update(range(t.map[0], t.map[1]))
    return lines


def headings(text, md):
    """文書の見出しを、出てくる順に返す: [{"level","label","id","line","html_at"}]。
    html_at は、HTML の見出しで id を足す場所（文字位置）。足す必要が無ければ None。"""
    tokens = md.parse(text)
    offsets, pos = [], 0
    for line in text.split("\n"):
        offsets.append(pos)
        pos += len(line) + 1
    found, taken = [], set()
    for i, t in enumerate(tokens):
        if t.type == "heading_open" and t.map:
            ident = t.attrs.get("id") if hasattr(t, "attrs") else None
            if ident:
                taken.add(ident)
            label = _plain(tokens[i + 1].children) if i + 1 < len(tokens) else ""
            found.append({"level": int(t.tag[1]), "label": label, "id": ident, "line": t.map[0], "html_at": None})
        elif t.type == "html_block" and t.map:
            for m in HTML_HEADING.finditer(t.content):
                idm = ID_ATTR.search(m.group(2))
                line = t.map[0] + t.content[:m.start()].count("\n")
                at = None
                if idm:
                    taken.add(idm.group(2))
                else:
                    at = offsets[t.map[0]] + m.start() + len("<h" + m.group(1))
                found.append({"level": int(m.group(1)), "label": _html_label(m.group(3)),
                              "id": idm.group(2) if idm else None, "line": line, "html_at": at})
    for h in found:                                   # id の無い HTML の見出しに、id を決める
        if h["html_at"] is not None:
            h["id"] = _unique(slugify(h["label"]) or "section", taken)
    return found


def _items(found, min_level, max_level, skip_title):
    chosen = [h for h in found if min_level <= h["level"] <= max_level and h["label"] and h["id"]]
    if skip_title:
        chosen = [h for h in chosen if h["label"].lower() not in TOC_TITLES]
    lines, stack = [], []
    for h in chosen:
        while stack and stack[-1] >= h["level"]:       # 段が飛んでも、入れ子は1段ずつにする
            stack.pop()
        label = re.sub(r"([\[\]\\])", r"\\\1", h["label"])
        lines.append("%s- [%s](#%s)" % ("  " * len(stack), label, h["id"]))
        stack.append(h["level"])
    return lines


def update(text, md, cursor_line=0, min_level=1, max_level=4, skip_title=True):
    """本文に目次を入れる（印があれば更新）。
    戻り値: {"text","count","updated","added_ids"}。入れられなければ {"error"}。"""
    if not (1 <= min_level <= max_level <= 6):
        return {"error": "見出しの範囲が正しくありません"}
    found = headings(text, md)
    items = _items(found, min_level, max_level, skip_title)
    if not items:
        return {"error": "目次にできる見出しがありません（見出し%d〜%dの範囲）" % (min_level, max_level)}

    # 目次に入れる、id の無い HTML の見出しへ id を足す（後ろの位置から。前の位置がずれない）
    in_toc = {(h["line"], h["id"]) for h in found if min_level <= h["level"] <= max_level and h["label"]
              and not (skip_title and h["label"].lower() in TOC_TITLES)}
    added = 0
    for h in sorted((h for h in found if h["html_at"] is not None and (h["line"], h["id"]) in in_toc),
                    key=lambda h: -h["html_at"]):
        text = text[:h["html_at"]] + ' id="%s"' % h["id"] + text[h["html_at"]:]
        added += 1

    block = ["<!-- toc -->", ""] + items + ["", "<!-- /toc -->"]
    lines = text.split("\n")
    code = _code_lines(md.parse(text))
    begin = next((i for i, l in enumerate(lines) if i not in code and BEGIN.match(l)), None)
    end = None
    if begin is not None:
        end = next((i for i in range(begin + 1, len(lines)) if i not in code and END.match(lines[i])), None)
        if end is None:
            return {"error": "<!-- toc --> の終わりの印 <!-- /toc --> がありません"}
    if begin is not None:
        lines[begin:end + 1] = block
        updated = True
    else:
        at = max(0, min(cursor_line, len(lines)))
        ins = list(block)
        if at > 0 and lines[at - 1].strip():
            ins = [""] + ins
        if at < len(lines) and lines[at].strip():
            ins = ins + [""]
        lines[at:at] = ins
        updated = False
    return {"text": "\n".join(lines), "count": len(items), "updated": updated, "added_ids": added}
