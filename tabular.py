"""表のデータ（Excel のセル、CSV）を、Markdown の表や JSON データに変換する（エディタ）。

取り込み元は、Excel のセルをコピーしたテキスト（タブ区切り）と、CSV ファイルの中身。区切り文字は自動で見分ける。
同じデータを、次のどちらにも変換する。

- Markdown の表: `| 見出し | … |` と区切り行。数値だけの列は、右寄せ（`---:`）にする。
- JSON: Vega-Lite の `data.values` やデータファイル（`data.url`）に使える、オブジェクトの配列。
  `[{"月": "一月", "売上": 3}, …]`。1行目を、キー（列の名前）として使う。

決めごと:
- 全部が空の行は捨てる。短い行は、空のセルで足す。セルの前後の空白は取る。
- 見出しが空の列は「列N」、重なった見出しは「名前_2」にする（JSON のキーが重ならないように）。
- 見出しを使わないとき（1行目もデータ）は、「列1」「列2」… を見出しにする。
- JSON では、数値のセルを数値にできる（`1,234` のような桁区切りも）。`007` のように先頭が 0 の数字や、
  `12%` は文字列のまま（番号や、単位つきの値を壊さないため）。空のセルは、null・空の文字列・項目を省略から選ぶ。
- Markdown では、セルの中の `|` を `\\|` に、改行を `<br>` にする（表が崩れないように）。
"""
import csv
import io
import json
import re

csv.field_size_limit(50 * 1024 * 1024)

MAX_ROWS = 200000
NUMBER = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
THOUSANDS = re.compile(r"^-?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?$")
PERCENT_OR_NUMBER = re.compile(r"^-?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d+)?%?$")
DELIMITERS = {"tab": "\t", "comma": ",", "semicolon": ";"}
ALIGN_MARK = {"left": ":---", "center": ":---:", "right": "---:", "none": "---"}


def detect_delimiter(text):
    """タブがあれば（Excel のセルのコピー）タブ。なければ、最初の行で多いほう（カンマかセミコロン）。"""
    lines = [l for l in text.split("\n") if l.strip()][:5]
    if any("\t" in l for l in lines):
        return "\t"
    first = lines[0] if lines else ""
    return ";" if first.count(";") > first.count(",") else ","


def parse(text, delimiter="auto"):
    """テキストを、セルの文字列の二次元の並びにする。全部が空の行は捨て、長さをそろえる。"""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    delim = detect_delimiter(text) if delimiter == "auto" else DELIMITERS.get(delimiter)
    if delim is None:
        raise ValueError("区切り文字が正しくありません")
    try:
        rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delim, quotechar='"')]
    except csv.Error as e:
        raise ValueError("表として読めません: %s" % e)
    rows = [r for r in rows if any(c for c in r)]
    if len(rows) > MAX_ROWS:
        raise ValueError("行が多すぎます（%d 行まで）" % MAX_ROWS)
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def names_of(rows, header=True):
    """列の名前。空は「列N」、重なったものは「名前_2」にする。"""
    width = len(rows[0]) if rows else 0
    raw = rows[0] if header and rows else []
    names, seen = [], set()
    for i in range(width):
        base = (raw[i] if i < len(raw) else "").strip() or "列%d" % (i + 1)
        name, n = base, 1
        while name in seen:
            n += 1
            name = "%s_%d" % (base, n)
        seen.add(name)
        names.append(name)
    return names


def body_of(rows, header=True):
    return rows[1:] if header else rows


def _number(cell):
    """数値のセルなら、その数値。そうでなければ None。"""
    if NUMBER.match(cell):
        return float(cell) if "." in cell else int(cell)
    if THOUSANDS.match(cell):
        s = cell.replace(",", "")
        return float(s) if "." in s else int(s)
    return None


def to_markdown(rows, header=True, align="auto"):
    names = names_of(rows, header)
    body = body_of(rows, header)

    def esc(c):
        return c.replace("|", "\\|").replace("\n", "<br>") if c else ""

    marks = []
    for i in range(len(names)):
        cells = [r[i] for r in body if r[i]]
        if align == "auto":
            numeric = bool(cells) and all(PERCENT_OR_NUMBER.match(c) for c in cells)
            marks.append(ALIGN_MARK["right" if numeric else "none"])
        else:
            marks.append(ALIGN_MARK[align])
    line = lambda cells: "| " + " | ".join(esc(c) for c in cells) + " |"
    out = [line(names), "| " + " | ".join(marks) + " |"] + [line(r) for r in body]
    return "\n".join(out)


def to_json(rows, header=True, numbers=True, empty="null"):
    names = names_of(rows, header)
    objects = []
    for r in body_of(rows, header):
        obj = {}
        for name, cell in zip(names, r):
            if cell == "":
                if empty == "omit":
                    continue
                obj[name] = None if empty == "null" else ""
            else:
                n = _number(cell) if numbers else None
                obj[name] = cell if n is None else n
        objects.append(obj)
    if not objects:
        return "[]"
    return "[\n" + ",\n".join("  " + json.dumps(o, ensure_ascii=False) for o in objects) + "\n]"


def convert(text, fmt="md", delimiter="auto", header=True, align="auto", numbers=True, empty="null", fence=False, limit=0):
    """変換する。戻り値: {"output","rows","cols","lines"} か {"error"}。
    limit > 0 なら、出力の最初の limit 行だけを返す（プレビュー用。変換そのものは全部行う）。"""
    if fmt not in ("md", "json"):
        return {"error": "出力の形式が正しくありません"}
    if align != "auto" and align not in ALIGN_MARK:
        return {"error": "列の配置が正しくありません"}
    if empty not in ("null", "empty", "omit"):
        return {"error": "空欄の扱いが正しくありません"}
    try:
        rows = parse(text, delimiter)
    except ValueError as e:
        return {"error": str(e)}
    if not rows:
        return {"error": "表のデータがありません"}
    out = to_markdown(rows, header, align) if fmt == "md" else to_json(rows, header, numbers, empty)
    if fmt == "json" and fence:
        out = "```json\n" + out + "\n```"
    lines = out.split("\n")
    if limit and len(lines) > limit:
        out = "\n".join(lines[:limit]) + "\n…（あと %d 行）" % (len(lines) - limit)
    return {"output": out, "rows": len(body_of(rows, header)), "cols": len(rows[0]), "lines": len(lines)}
