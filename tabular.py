"""表のデータ（Excel のセル、CSV）を、Markdown の表や JSON データに変換する（エディタ）。

取り込み元は、Excel のセルをコピーしたテキスト（タブ区切り）と、CSV ファイルの中身、JSON のデータ。
区切り文字や、表か JSON かは、自動で見分ける。
同じデータを、次のどちらにも変換する。

- Markdown の表: `| 見出し | … |` と区切り行。数値だけの列は、右寄せ（`---:`）にする。
- HTML の表: `<table>`（見出しがあれば `<thead>`、データは `<tbody>`）。配置は `align` 属性（数値だけの列は右寄せ）、
  罫線は `border="1"` を付けるか選べる。セルの `&` `<` `>` は文字として出し、改行は `<br>`。
  出力の中に空行は入れない（Markdown の中の HTML は、空行で終わるため）。見出しを使わないときは `<thead>` を付けない。
- JSON: Vega-Lite の `data.values` やデータファイル（`data.url`）に使える、オブジェクトの配列。
  `[{"月": "一月", "売上": 3}, …]`。1行目を、キー（列の名前）として使う。

決めごと:
- 全部が空の行は捨てる。短い行は、空のセルで足す。セルの前後の空白は取る。
- 見出しが空の列は「列N」、重なった見出しは「名前_2」にする（JSON のキーが重ならないように）。
- 見出しを使わないとき（1行目もデータ）は、「列1」「列2」… を見出しにする。
- JSON では、数値のセルを数値にできる（`1,234` のような桁区切りも）。`007` のように先頭が 0 の数字や、
  `12%` は文字列のまま（番号や、単位つきの値を壊さないため）。空のセルは、null・空の文字列・項目を省略から選ぶ。
- Markdown では、セルの中の `|` を `\\|` に、改行を `<br>` にする（表が崩れないように）。

JSON から表を作るとき（Excel・CSV から JSON への変換の、逆向き）:
- 読めるのは、オブジェクトの配列 `[{…}, {…}]`。`{"values": [...]}` と、`data.values` を持つ Vega-Lite のグラフの定義、
  配列の配列 `[["月", "売上"], ["一月", 3]]`（1行目を見出しにするかは、表と同じ指定）も読める。
- 列の名前はキー。列の順は、キーが最初に出てきた順（全部のオブジェクトを見る。「空欄は項目を省く」で作った JSON でも、列が欠けない）。
- null は空のセル、数値・真偽値は、その文字（`1234`、`true`）。入れ子のもの（値がオブジェクトや配列）は、
  `{"a": 1, "b": 2}` のように、属性（キー）つきの JSON の文字列にして、1つのセルに入れる。
- 往復しても食い違わないようにしてある（CSV → JSON → 表 が、CSV → 表 と同じ）。ただし、`1,234` は `1234` になる
  （JSON にしたときに数値にしたため）。
"""
import csv
import html
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


def _cell_of(value):
    """JSON の値を、表のセルの文字にする。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)         # 入れ子は、属性（キー）つきで、1つのセルに入れる
    if isinstance(value, float):
        return json.dumps(value)
    return str(value)


def from_json(text):
    """JSON を、表にする。戻り値: {"kind": "json", "rows": [...], "header": 見出しの行があるか, "objects": オブジェクトの並び か None}。
    読めないときは ValueError（利用者に見せる文言）。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("JSON として読めません（%d 行目 %d 文字目付近: %s）" % (e.lineno, e.colno, e.msg))
    if isinstance(data, dict):
        inner = data.get("values")
        if inner is None and isinstance(data.get("data"), dict):
            inner = data["data"].get("values")                  # Vega-Lite のグラフの定義
        if not isinstance(inner, list):
            raise ValueError("JSON は、オブジェクトの配列 [{…}, …] で指定してください（{\"values\": [...]} も使えます）")
        data = inner
    if not isinstance(data, list):
        raise ValueError("JSON は、オブジェクトの配列 [{…}, …] で指定してください")
    if len(data) > MAX_ROWS:
        raise ValueError("行が多すぎます（%d 行まで）" % MAX_ROWS)
    if not data:
        raise ValueError("表のデータがありません")
    if all(isinstance(r, dict) for r in data):
        names = []
        seen = set()
        for r in data:                                          # 列の順は、キーが最初に出てきた順（全部のオブジェクトを見る）
            for k in r:
                if k not in seen:
                    seen.add(k)
                    names.append(k)
        rows = [list(names)] + [[_cell_of(r.get(k)).strip() for k in names] for r in data]
        return {"kind": "json", "rows": rows, "header": True, "objects": data}
    if all(isinstance(r, list) for r in data):
        width = max(len(r) for r in data)
        rows = [[_cell_of(c).strip() for c in r] + [""] * (width - len(r)) for r in data]
        return {"kind": "json", "rows": rows, "header": None, "objects": None}
    raise ValueError("JSON は、オブジェクトの配列 [{…}, …]（または配列の配列）で指定してください")


def load(text, source="auto", delimiter="auto"):
    """表か JSON かを見分けて読む。自動のときは、`[` か `{` で始まり、JSON として読めれば JSON、読めなければ表として扱う。"""
    stripped = text.lstrip("\ufeff").strip()
    if source in ("auto", "json") and stripped[:1] in ("[", "{"):
        try:
            return from_json(stripped)
        except ValueError:
            if source == "json":
                raise
    elif source == "json":
        raise ValueError("JSON として読めません（[ か { で始まるデータを指定してください）")
    return {"kind": "table", "rows": parse(text, delimiter), "header": None, "objects": None}


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


def to_html(rows, header=True, align="auto", border=False):
    """HTML の表。見出しを使わないとき（header=False）は、`<thead>` を付けず、全部の行を `<tbody>` に入れる。"""
    body = body_of(rows, header)
    width = len(rows[0]) if rows else 0

    def mark(i):
        if align == "auto":
            cells = [r[i] for r in body if r[i]]
            return "right" if cells and all(PERCENT_OR_NUMBER.match(c) for c in cells) else None
        return None if align == "none" else align

    marks = [mark(i) for i in range(width)]

    def cell(tag, i, text):
        attr = ' align="%s"' % marks[i] if marks[i] else ""
        return "<%s%s>%s</%s>" % (tag, attr, html.escape(text, quote=False).replace("\n", "<br>"), tag)

    out = ['<table border="1">' if border else "<table>"]
    if header:
        names = names_of(rows, True)
        out += ["  <thead>", "    <tr>" + "".join(cell("th", i, n) for i, n in enumerate(names)) + "</tr>", "  </thead>"]
    if body:
        out.append("  <tbody>")
        out += ["    <tr>" + "".join(cell("td", i, c) for i, c in enumerate(r)) + "</tr>" for r in body]
        out.append("  </tbody>")
    out.append("</table>")
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


def convert(text, fmt="md", delimiter="auto", header=True, align="auto", numbers=True, empty="null", fence=False, limit=0, source="auto", border=False):
    """変換する。戻り値: {"output","rows","cols","lines","source"} か {"error"}。source は、読み取った形（"table" か "json"）。
    limit > 0 なら、出力の最初の limit 行だけを返す（プレビュー用。変換そのものは全部行う）。"""
    if fmt not in ("md", "html", "json"):
        return {"error": "出力の形式が正しくありません"}
    if align != "auto" and align not in ALIGN_MARK:
        return {"error": "列の配置が正しくありません"}
    if empty not in ("null", "empty", "omit"):
        return {"error": "空欄の扱いが正しくありません"}
    if source not in ("auto", "table", "json"):
        return {"error": "入力の形式が正しくありません"}
    try:
        data = load(text, source, delimiter)
    except ValueError as e:
        return {"error": str(e)}
    rows = data["rows"]
    if not rows:
        return {"error": "表のデータがありません"}
    if data["header"] is not None:
        header = data["header"]                      # オブジェクトの配列は、キーが列の名前（「1行目を、列の名前にする」は効かない）
    if fmt == "md":
        out = to_markdown(rows, header, align)
    elif fmt == "html":
        out = to_html(rows, header, align, bool(border))
    elif data["objects"] is not None:                # JSON を JSON に直すときは、元の値のまま、整えて出す
        out = "[\n" + ",\n".join("  " + json.dumps(o, ensure_ascii=False) for o in data["objects"]) + "\n]"
    else:
        out = to_json(rows, header, numbers, empty)
    if fmt == "json" and fence:
        out = "```json\n" + out + "\n```"
    lines = out.split("\n")
    if limit and len(lines) > limit:
        out = "\n".join(lines[:limit]) + "\n…（あと %d 行）" % (len(lines) - limit)
    return {"output": out, "rows": len(body_of(rows, header)), "cols": len(rows[0]), "lines": len(lines), "source": data["kind"]}
