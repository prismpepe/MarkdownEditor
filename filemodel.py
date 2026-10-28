"""文書の読み書き。文字コード・BOM・改行を保ったまま保存する。

他のエディターで作った文書を、保存で壊さないことが目的。
- 読むとき: 文字コードと改行を判定し、本文は改行を "\\n" に揃えて返す。
- 書くとき: 判定した（または利用者が選んだ）文字コード・BOM・改行で書き戻す。
- 上書きの前に、元のファイルを退避する（最新 KEEP_BACKUPS 世代）。
- 書き込みは一時ファイル → 置き換えで行い、途中で失敗しても元のファイルを壊さない。
- 読み込み後に他のアプリがファイルを書き換えていたら、保存を止める。
"""
import datetime
import hashlib
import os
import shutil
import tempfile

# 表示名 → (Python のコーデック, BOM)
ENCODINGS = {
    "UTF-8": ("utf-8", b""),
    "UTF-8 (BOM付き)": ("utf-8", b"\xef\xbb\xbf"),
    "Shift-JIS (CP932)": ("cp932", b""),
    "UTF-16 LE (BOM付き)": ("utf-16-le", b"\xff\xfe"),
    "UTF-16 BE (BOM付き)": ("utf-16-be", b"\xfe\xff"),
}
NEWLINES = {"CRLF": "\r\n", "LF": "\n", "CR": "\r"}
DEFAULT_ENCODING = "UTF-8"
DEFAULT_NEWLINE = "CRLF"          # Windows の既定。新規文書と、改行の無い文書に使う
KEEP_BACKUPS = 5          # 退避は、置き場全体で直近5回の上書き分だけ残す（ファイルごとではない）


class Conflict(Exception):
    """読み込み後に、他のアプリがファイルを書き換えた。"""


class EncodingFailure(Exception):
    """選んだ文字コードで表せない文字がある。"""

    def __init__(self, encoding, chars):
        super().__init__(f"{encoding} で表せない文字: {''.join(chars)}")
        self.encoding = encoding
        self.chars = chars


def stamp_of(path):
    st = os.stat(path)
    return [st.st_mtime_ns, st.st_size]


def detect_encoding(raw):
    """(表示名, 本文のバイト列, 読み取り専用か, 注意) を返す。"""
    for label, (codec, bom) in ENCODINGS.items():
        if bom and raw.startswith(bom):
            body = raw[len(bom):]
            try:
                body.decode(codec)
            except UnicodeDecodeError:
                continue
            return label, body, False, None
    try:
        raw.decode("utf-8")
        return "UTF-8", raw, False, None
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("cp932")
        return "Shift-JIS (CP932)", raw, False, None
    except UnicodeDecodeError:
        # 判定できないまま開いて保存すると、読めなかった文字を失う。編集させない
        return ("UTF-8", raw, True,
                "文字コードを判定できません（UTF-8 でも Shift-JIS でもありません）。"
                "文字を失わないよう、読み取り専用で開いています。")


def detect_newline(text):
    """(改行の表示名, 混在しているか)。"""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    counts = {"CRLF": crlf, "LF": lf, "CR": cr}
    total = sum(counts.values())
    if total == 0:
        return DEFAULT_NEWLINE, False
    kind = max(counts, key=lambda k: (counts[k], k == DEFAULT_NEWLINE))
    return kind, sum(1 for v in counts.values() if v) > 1


def normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_document(path):
    with open(path, "rb") as f:
        raw = f.read()
    stamp = stamp_of(path)
    label, body, readonly, warning = detect_encoding(raw)
    codec = ENCODINGS[label][0]
    text = body.decode(codec, errors="replace" if readonly else "strict")
    newline, mixed = detect_newline(text)
    return {
        "text": normalize_newlines(text),
        "encoding": label,
        "newline": newline,
        "mixed_newlines": mixed,
        "readonly": readonly,
        "warning": warning,
        "stamp": stamp,
    }


def encode_document(text, encoding, newline):
    codec, bom = ENCODINGS[encoding]
    converted = normalize_newlines(text).replace("\n", NEWLINES[newline])
    try:
        return bom + converted.encode(codec)
    except UnicodeEncodeError:
        bad = []
        for ch in converted:
            try:
                ch.encode(codec)
            except UnicodeEncodeError:
                if ch not in bad:
                    bad.append(ch)
                    if len(bad) >= 10:
                        break
        raise EncodingFailure(encoding, bad) from None


def backup_folder(backup_root, path):
    key = hashlib.sha1(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:10]
    return os.path.join(backup_root, f"{key}_{os.path.basename(path)}")


def prune_backups(backup_root, keep=KEEP_BACKUPS):
    """退避の置き場全体で、新しい順に keep 個だけを残し、古いものを消す（空になったフォルダーも消す）。

    退避の名前は日時で始まるので、名前の順がそのまま古い順になる。
    """
    found = []
    try:
        with os.scandir(backup_root) as folders:
            for folder in folders:
                if not folder.is_dir():
                    continue
                with os.scandir(folder.path) as files:
                    found += [(f.name, f.path) for f in files if f.is_file() and f.name.endswith(".bak")]
    except OSError:
        return
    found.sort()
    for _, path in found[:-keep] if keep > 0 else found:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        with os.scandir(backup_root) as folders:
            for folder in folders:
                if folder.is_dir() and not os.listdir(folder.path):
                    os.rmdir(folder.path)
    except OSError:
        pass


def make_backup(path, backup_root):
    folder = backup_folder(backup_root, path)
    os.makedirs(folder, exist_ok=True)
    name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".bak"
    shutil.copy2(path, os.path.join(folder, name))
    prune_backups(backup_root)


def write_document(path, text, encoding, newline, expected_stamp=None,
                   backup_root=None):
    """保存して、新しいスタンプを返す。

    expected_stamp を渡すと、読み込み後に他で書き換えられていないかを確かめる
    （None なら確かめない＝上書きすると決めたとき・新規ファイル）。
    """
    data = encode_document(text, encoding, newline)       # 先に変換。失敗してもファイルは無傷
    exists = os.path.exists(path)
    if exists and expected_stamp is not None and stamp_of(path) != list(expected_stamp):
        raise Conflict(path)
    if exists and backup_root:
        make_backup(path, backup_root)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".~", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return stamp_of(path)
