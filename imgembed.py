"""画像の Base64 埋め込みと、ファイルへの書き戻し（エディタ）。

Markdown ファイル1つで配布できるようにするため、文書が参照する画像ファイルを `data:` URI にして文書へ入れる。

- 書き方は参照形式にする。本文は `![説明][image1]` のまま短く、巨大な Base64 は文末の定義
  `[image1]: data:image/png;base64,…` にまとめる。本文に1行で入れると、編集欄が極端に重くなるため。
- 変換するのは、png / jpg / gif / webp / bmp。SVG は変換しない（プレビューの安全処理が data:image/svg+xml を
  通さず、埋め込むと表示できなくなるため）。
- コード（コードブロック・インラインコード）の中の記法は対象にしない。
- 対象は、`![説明](パス)`、`![説明][ラベル]` が使う定義 `[ラベル]: パス`、`<img src="パス">`。
  画像に使われていない定義（PDF へのリンクなど）は変えない。
- 「パスで参照する」書き方（`![説明](images/a.png)`）も作れる（`path_reference`）。文書を保存してあれば、
  文書のフォルダーからの相対パス（別のドライブなら絶対パス）、保存していなければ `file:///` の絶対パス。
  パスの空白・括弧などは `%20` のように符号化する（日本語はそのまま）。SVG も参照できる（プレビューが開いて表示する）。
- ファイルへ戻すときは、文書の隣の `images/` フォルダーへ `文書名_001.png` のように書き出す。
  同じ内容のファイルがすでにあれば、それを使い、別の内容のファイルを上書きしない。
"""
import base64
import hashlib
import mimetypes
import os
import re
from urllib.parse import unquote

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
EXT_OF_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp", "image/bmp": ".bmp"}
MAX_BYTES = 20 * 1024 * 1024          # プレビューが表示できる大きさ（mdeditor.MAX_INLINE_IMAGE）と同じ

FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
DEST = r"(<[^<>\n]*>|[^\s()<>]*(?:\([^\s()]*\)[^\s()<>]*)*)"
TITLE = r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\))"""
IMG_INLINE = re.compile(r"!\[((?:[^\[\]\\]|\\.)*)\]\(\s*" + DEST + r"(?:\s+" + TITLE + r")?\s*\)")
IMG_REF = re.compile(r"!\[((?:[^\[\]\\]|\\.)*)\]\[([^\[\]]*)\]")
IMG_SHORT = re.compile(r"!\[([^\[\]]+)\](?![\[(])")
DEF = re.compile(r"^( {0,3}\[((?:[^\[\]\\]|\\.)+)\]:[ \t]*)(<[^<>\n]*>|\S+)([^\n]*)$", re.M)
HTML_IMG = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
DATA_URI = re.compile(r"^data:(image/(?:png|jpeg|jpg|gif|webp|bmp));base64,([A-Za-z0-9+/=\s]+)$", re.I)


def _norm(label):
    return re.sub(r"\s+", " ", label.strip()).lower()


def mask_code(text):
    """コードの中を空白に置き換えた、同じ長さの文字列。記法の探索にだけ使い、置き換えは元の文字列に行う。"""
    out, pos, fence = [], 0, None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        keep = line[len(body):]
        if fence is None:
            m = FENCE_OPEN.match(body)
            if m:
                fence = m.group(1)
                out.append(" " * len(body) + keep)
            else:
                out.append(line)
        else:
            m = re.match(r"^ {0,3}(" + re.escape(fence[0]) + "{" + str(len(fence)) + r",})\s*$", body)
            if m:
                fence = None
            out.append(" " * len(body) + keep)
    masked = "".join(out)
    return INLINE_CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked)


def _unwrap(dest):
    return dest[1:-1] if dest.startswith("<") and dest.endswith(">") else dest


def _local_path(dest, base_dir):
    """画像の参照先が手元のファイルなら、そのパスを返す。http(s)・data:・その他のスキームは None。"""
    d = _unwrap(dest).strip()
    if not d or re.match(r"^(https?:|data:|mailto:|ftp:|//)", d, re.I):
        return None
    d = unquote(d.split("#")[0].split("?")[0])
    if d.lower().startswith("file:///"):
        d = d[8:]
    elif re.match(r"^[A-Za-z][A-Za-z0-9+.-]+:", d):          # 知らないスキーム（1文字のドライブ文字は通す）
        return None
    return d if os.path.isabs(d) else os.path.join(base_dir or "", d)


def data_uri(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as f:
        raw = f.read()
    return "data:%s;base64,%s" % (IMAGE_TYPES[ext], base64.b64encode(raw).decode("ascii")), len(raw)


def _check_file(path):
    """埋め込めるかを調べる。問題があれば、その理由（利用者に見せる文言）を返す。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        return "SVG は埋め込めません（プレビューに表示できなくなるため）"
    if ext not in IMAGE_TYPES:
        return "対応していない画像の形式です（png / jpg / gif / webp / bmp）"
    if not os.path.isfile(path):
        return "ファイルが見つかりません"
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return "ファイルが大きすぎます（20MBまで）"
    except OSError:
        return "ファイルを読めません"
    return None


def _labels_used_by_images(masked):
    used = {_norm(m.group(2) or m.group(1)) for m in IMG_REF.finditer(masked)}
    for m in IMG_SHORT.finditer(masked):
        used.add(_norm(m.group(1)))
    return used


def next_label(text):
    """`image1`, `image2`, … のうち、文書の定義にまだ無いもの。"""
    taken = {_norm(m.group(2)) for m in DEF.finditer(text)}
    n = 1
    while "image%d" % n in taken:
        n += 1
    return "image%d" % n


def embed(text, base_dir, dry_run=False):
    """文書が参照する手元の画像を Base64 にする。dry_run なら、変換の予定だけを返す（text は変えない）。
    戻り値: {"text": 新しい本文, "converted": [{"path","bytes","count"}], "skipped": [{"src","reason"}]}"""
    masked = mask_code(text)
    taken = {_norm(m.group(2)) for m in DEF.finditer(text)}
    used = _labels_used_by_images(masked)
    edits, converted, skipped = [], {}, []        # edits: (start, end, 置き換え)
    new_defs, label_of = [], {}                   # label_of: (パス, タイトル) → ラベル
    counter = [0]

    def label_for(path, title):
        key = (os.path.normcase(os.path.abspath(path)), title or "")
        if key not in label_of:
            while True:
                counter[0] += 1
                lab = "image%d" % counter[0]
                if lab not in taken:
                    break
            taken.add(lab)
            label_of[key] = lab
            uri = None if dry_run else data_uri(path)[0]
            new_defs.append("[%s]: %s%s" % (lab, uri or "…", (" " + title) if title else ""))
        return label_of[key]

    def note(path, src):
        reason = _check_file(path)
        if reason:
            skipped.append({"src": src, "reason": reason})
            return False
        c = converted.setdefault(os.path.normcase(os.path.abspath(path)), {"path": path, "bytes": os.path.getsize(path), "count": 0})
        c["count"] += 1
        return True

    for m in IMG_INLINE.finditer(masked):
        path = _local_path(m.group(2), base_dir)
        if path is None or not note(path, _unwrap(m.group(2))):
            continue
        alt, title = text[m.start(1):m.end(1)], m.group(3)
        edits.append((m.start(), m.end(), "![%s][%s]" % (alt, label_for(path, title))))

    for m in DEF.finditer(masked):
        if _norm(m.group(2)) not in used:
            continue
        path = _local_path(m.group(3), base_dir)
        if path is None or not note(path, _unwrap(m.group(3))):
            continue
        uri = "…" if dry_run else data_uri(path)[0]
        edits.append((m.start(3), m.end(3), uri))

    for m in HTML_IMG.finditer(masked):
        path = _local_path(m.group(3), base_dir)
        if path is None or not note(path, m.group(3)):
            continue
        uri = "…" if dry_run else data_uri(path)[0]
        edits.append((m.start(3), m.end(3), uri))

    result = text
    if not dry_run and edits:
        for start, end, rep in sorted(edits, reverse=True):
            result = result[:start] + rep + result[end:]
        if new_defs:
            result = result.rstrip("\n") + "\n\n" + "\n".join(new_defs) + "\n"
    return {"text": result, "converted": list(converted.values()), "skipped": skipped}


def insert_new(text, path, alt=None):
    """選んだ画像 1 つを、参照形式で挿入するための部品を返す。{"ref","definition"} か {"error"}。"""
    reason = _check_file(path)
    if reason:
        return {"error": reason}
    label = next_label(text)
    uri, size = data_uri(path)
    alt = alt if alt is not None else os.path.splitext(os.path.basename(path))[0]
    alt = re.sub(r"([\[\]\\])", r"\\\1", alt)
    return {"ref": "![%s][%s]" % (alt, label), "definition": "[%s]: %s" % (label, uri), "label": label, "bytes": size}


PATH_UNSAFE = set(" ()<>%[]\"#?\\")


def _encode_path(path):
    """Markdown の書き方に入れるパスの、空白・括弧・% など、書き方を壊す文字だけを %XX にする（日本語はそのまま）。"""
    return "".join("".join("%%%02X" % b for b in c.encode("utf-8")) if c in PATH_UNSAFE else c for c in path)


def path_reference(image_path, doc_path=None, alt=None):
    """画像ファイルを、パスで参照する Markdown の書き方にする。
    戻り値: {"markdown", "path", "relative": 相対パスか, "bytes"} か {"error"}。"""
    ext = os.path.splitext(image_path)[1].lower()
    if ext not in IMAGE_TYPES and ext != ".svg":
        return {"error": "対応していない画像の形式です（png / jpg / gif / webp / bmp / svg）"}
    if not os.path.isfile(image_path):
        return {"error": "ファイルが見つかりません"}
    relative = False
    path = None
    if doc_path:
        try:
            rel = os.path.relpath(image_path, os.path.dirname(os.path.abspath(doc_path)))
            path, relative = rel.replace(os.sep, "/"), True
        except ValueError:                                    # 別のドライブ: 相対パスにできない
            path = None
    if path is None:
        path = "file:///" + os.path.abspath(image_path).replace(os.sep, "/")
    alt = alt if alt is not None else os.path.splitext(os.path.basename(image_path))[0]
    alt = re.sub(r"([\[\]\\])", r"\\\1", alt)
    return {"markdown": "![%s](%s)" % (alt, _encode_path(path)), "path": path, "relative": relative,
            "bytes": os.path.getsize(image_path)}


def _safe_stem(name):
    stem = os.path.splitext(os.path.basename(name))[0] or "image"
    return re.sub(r"[^\w\-.぀-ヿ一-鿿]", "_", stem) or "image"


def externalize(text, doc_path, dry_run=False, folder="images"):
    """Base64 の画像を、文書の隣の `images/` フォルダーのファイルへ戻す。
    戻り値: {"text", "written": [{"name","bytes","reused"}], "skipped": [{"src","reason"}]}"""
    base = os.path.dirname(os.path.abspath(doc_path))
    out_dir = os.path.join(base, folder)
    stem = _safe_stem(doc_path)
    masked = mask_code(text)
    used = _labels_used_by_images(masked)
    edits, written, skipped = [], {}, []
    by_hash = {}                                   # 同じ内容は同じファイルにする
    reserved = set()

    def save(uri_text, where):
        m = DATA_URI.match(uri_text.strip())
        if not m:
            return None
        try:
            raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
        except Exception:
            skipped.append({"src": uri_text[:40] + "…", "reason": "Base64 として読めません"})
            return None
        digest = hashlib.sha256(raw).hexdigest()
        if digest in by_hash:
            return by_hash[digest]
        ext = EXT_OF_MIME[m.group(1).lower().replace("image/jpg", "image/jpeg")]
        n, reused = 0, False
        while True:
            n += 1
            name = "%s_%03d%s" % (stem, n, ext)
            full = os.path.join(out_dir, name)
            if name in reserved:
                continue
            if not os.path.exists(full):
                break
            try:
                with open(full, "rb") as f:
                    if hashlib.sha256(f.read()).hexdigest() == digest:
                        reused = True
                        break
            except OSError:
                pass
        reserved.add(name)
        if not reused and not dry_run:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, name), "wb") as f:
                f.write(raw)
        rel = "%s/%s" % (folder, name)
        by_hash[digest] = rel
        written[rel] = {"name": rel, "bytes": len(raw), "reused": reused}
        return rel

    def dest_text(rel):
        return "<%s>" % rel if " " in rel else rel

    for m in IMG_INLINE.finditer(masked):
        d = _unwrap(m.group(2))
        if not d.lower().startswith("data:image/"):
            continue
        rel = save(_unwrap(text[m.start(2):m.end(2)]), "inline")
        if rel:
            edits.append((m.start(2), m.end(2), dest_text(rel)))
    for m in DEF.finditer(masked):
        if _norm(m.group(2)) not in used or not _unwrap(m.group(3)).lower().startswith("data:image/"):
            continue
        rel = save(_unwrap(m.group(3)), "def")
        if rel:
            edits.append((m.start(3), m.end(3), dest_text(rel)))
    for m in HTML_IMG.finditer(masked):
        if not m.group(3).lower().startswith("data:image/"):
            continue
        rel = save(m.group(3), "html")
        if rel:
            edits.append((m.start(3), m.end(3), rel))

    result = text
    if not dry_run and edits:
        for start, end, rep in sorted(edits, reverse=True):
            result = result[:start] + rep + result[end:]
    return {"text": result, "written": list(written.values()), "skipped": skipped}
