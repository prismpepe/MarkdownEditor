"""ドロップの対象の決め方: Markdown ファイル1つとフォルダー1つだけを開き、ほかは無視する。"""
import filedrop


def is_md(p):
    return p.lower().endswith((".md", ".markdown"))


def test_markdownファイル1つは開く(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# a", encoding="utf-8")
    assert filedrop.classify([str(f)], is_md) == ("file", str(f))


def test_大文字の拡張子も開く(tmp_path):
    f = tmp_path / "A.MD"
    f.write_text("# a", encoding="utf-8")
    assert filedrop.classify([str(f)], is_md) == ("file", str(f))


def test_フォルダー1つは開く(tmp_path):
    assert filedrop.classify([str(tmp_path)], is_md) == ("folder", str(tmp_path))


def test_markdown以外は無視する(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert filedrop.classify([str(f)], is_md) is None


def test_複数のドロップは無視する(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    assert filedrop.classify([str(a), str(b)], is_md) is None
    assert filedrop.classify([str(a), str(tmp_path)], is_md) is None


def test_何も無い_存在しないものは無視する(tmp_path):
    assert filedrop.classify([], is_md) is None
    assert filedrop.classify([str(tmp_path / "none.md")], is_md) is None


def test_イベントから実パスを集める():
    ev = {"dataTransfer": {"files": [{"name": "a.md", "pywebviewFullPath": r"C:\x\a.md"}, {"name": "b.md"}]}}
    assert filedrop.dropped_paths(ev) == [r"C:\x\a.md"]


def test_形の違うイベントでも落ちない():
    assert filedrop.dropped_paths({}) == []
    assert filedrop.dropped_paths({"dataTransfer": None}) == []
    assert filedrop.dropped_paths(None) == []
