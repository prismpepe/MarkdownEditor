import os

import pytest

import filemodel as fm


def write_raw(tmp_path, name, raw):
    p = tmp_path / name
    p.write_bytes(raw)
    return str(p)


@pytest.mark.parametrize("label,raw", [
    ("UTF-8", "日本語\nabc\n".encode("utf-8")),
    ("UTF-8 (BOM付き)", b"\xef\xbb\xbf" + "日本語\r\n".encode("utf-8")),
    ("Shift-JIS (CP932)", "日本語の文書\r\n".encode("cp932")),
    ("UTF-16 LE (BOM付き)", b"\xff\xfe" + "日本語\r\n".encode("utf-16-le")),
    ("UTF-16 BE (BOM付き)", b"\xfe\xff" + "日本語\r\n".encode("utf-16-be")),
])
def test_読んだ文字コードのまま書き戻すとバイト列が一致する(tmp_path, label, raw):
    path = write_raw(tmp_path, "a.md", raw)
    doc = fm.read_document(path)
    assert doc["encoding"] == label
    assert "日本語" in doc["text"]
    fm.write_document(path, doc["text"], doc["encoding"], doc["newline"])
    assert open(path, "rb").read() == raw          # 何も編集しなければ1バイトも変わらない


def test_本文の改行はLFに揃えて返し_書くときに元の改行へ戻す(tmp_path):
    path = write_raw(tmp_path, "a.md", b"a\r\nb\r\n")
    doc = fm.read_document(path)
    assert doc["text"] == "a\nb\n"
    assert doc["newline"] == "CRLF" and not doc["mixed_newlines"]


def test_改行が混在していれば知らせ_多いほうに統一する(tmp_path):
    path = write_raw(tmp_path, "a.md", b"a\nb\nc\r\n")
    doc = fm.read_document(path)
    assert doc["newline"] == "LF" and doc["mixed_newlines"]
    fm.write_document(path, doc["text"], doc["encoding"], doc["newline"])
    assert open(path, "rb").read() == b"a\nb\nc\n"


def test_改行の無い文書は既定の改行になる(tmp_path):
    path = write_raw(tmp_path, "a.md", b"abc")
    assert fm.read_document(path)["newline"] == fm.DEFAULT_NEWLINE


def test_空のファイルを開ける(tmp_path):
    doc = fm.read_document(write_raw(tmp_path, "e.md", b""))
    assert doc["text"] == "" and not doc["readonly"]


def test_判定できない文字コードは読み取り専用にして文字を失う保存をさせない(tmp_path):
    path = write_raw(tmp_path, "x.md", b"abc \x81\x20 \xff\xfe\xfd")
    doc = fm.read_document(path)
    assert doc["readonly"] and doc["warning"]


def test_選んだ文字コードで表せない文字は保存せず知らせる(tmp_path):
    path = write_raw(tmp_path, "a.md", "あ".encode("cp932"))
    before = open(path, "rb").read()
    with pytest.raises(fm.EncodingFailure) as e:
        fm.write_document(path, "あ😀", "Shift-JIS (CP932)", "LF")
    assert "😀" in e.value.chars
    assert open(path, "rb").read() == before        # 元のファイルは無傷


def test_読み込み後に他で書き換えられたら保存を止める(tmp_path):
    path = write_raw(tmp_path, "a.md", b"one")
    doc = fm.read_document(path)
    with open(path, "wb") as f:
        f.write(b"changed by someone else")
    with pytest.raises(fm.Conflict):
        fm.write_document(path, "mine", "UTF-8", "LF", expected_stamp=doc["stamp"])
    assert open(path, "rb").read() == b"changed by someone else"
    # 上書きすると決めたとき（スタンプなし）は書ける
    fm.write_document(path, "mine", "UTF-8", "LF")
    assert open(path, "rb").read() == b"mine"


def test_上書き前に退避し_世代数を超えたら古いものから消す(tmp_path):
    path = write_raw(tmp_path, "a.md", b"v0")
    backup = str(tmp_path / "bk")
    for i in range(1, fm.KEEP_BACKUPS + 4):
        fm.write_document(path, f"v{i}", "UTF-8", "LF", backup_root=backup)
    folder = fm.backup_folder(backup, path)
    names = sorted(os.listdir(folder))
    assert len(names) == fm.KEEP_BACKUPS
    newest = open(os.path.join(folder, names[-1]), "rb").read()
    assert newest == f"v{fm.KEEP_BACKUPS + 2}".encode()   # 最後の上書き直前の内容


def test_新規ファイルは退避せず作れる(tmp_path):
    path = str(tmp_path / "new.md")
    fm.write_document(path, "本文", "UTF-8", "CRLF", backup_root=str(tmp_path / "bk"))
    assert open(path, "rb").read() == "本文".encode("utf-8")
    assert not (tmp_path / "bk").exists()


def test_書き込みに失敗しても一時ファイルを残さない(tmp_path, monkeypatch):
    path = write_raw(tmp_path, "a.md", b"keep")
    def boom(*a, **k):
        raise PermissionError("denied")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(PermissionError):
        fm.write_document(path, "x", "UTF-8", "LF")
    assert open(path, "rb").read() == b"keep"
    assert [n for n in os.listdir(tmp_path) if n.endswith(".tmp")] == []
