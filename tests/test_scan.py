"""一覧の読み込みに、件数と時間の上限があること（巨大なフォルダー・ドライブを開いても、長く待たされない）。"""
import pytest

import mdeditor


def make_tree(root, dirs=30, per_dir=1):
    (root / "top.md").write_text("x", encoding="utf-8")
    for i in range(dirs):
        d = root / f"sub{i:02d}"
        d.mkdir()
        for j in range(per_dir):
            (d / f"{j}.md").write_text("x", encoding="utf-8")


def test_小さなフォルダーは_全部を読み_途中ではない(tmp_path):
    make_tree(tmp_path, dirs=3)
    files, truncated = mdeditor.scan_markdown(str(tmp_path))
    assert truncated is False
    assert files == ["top.md", "sub00/0.md", "sub01/0.md", "sub02/0.md"]


def test_時間の上限に達したら_そこまでの一覧を返し_途中だと知らせる(tmp_path):
    make_tree(tmp_path, dirs=30)
    files, truncated = mdeditor.scan_markdown(str(tmp_path), max_seconds=0)     # 上限0秒 = 最初のフォルダーのあとで止まる
    assert truncated is True
    assert files == ["top.md"]                                                   # 全31件ではなく、最初のフォルダーの分だけ


def test_件数の上限に達したら_途中だと知らせる(tmp_path, monkeypatch):
    make_tree(tmp_path, dirs=5)
    monkeypatch.setattr(mdeditor, "MAX_FILES", 3)
    files, truncated = mdeditor.scan_markdown(str(tmp_path))
    assert truncated is True and len(files) == 3


def test_除外するフォルダーは_数えない(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.md").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "y.md").write_text("x", encoding="utf-8")
    (tmp_path / "ok.md").write_text("x", encoding="utf-8")
    assert mdeditor.scan_markdown(str(tmp_path)) == (["ok.md"], False)


def test_従来の_list_markdown_は一覧だけを返す(tmp_path):
    make_tree(tmp_path, dirs=2)
    assert mdeditor.list_markdown(str(tmp_path)) == ["top.md", "sub00/0.md", "sub01/0.md"]


def test_APIの一覧には_途中かどうかが含まれる(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    folder = tmp_path / "docs"
    folder.mkdir()
    make_tree(folder, dirs=4)
    api = mdeditor.Api(None)
    r = api.list_files(str(folder))
    assert r["truncated"] is False and len(r["files"]) == 5
    monkeypatch.setattr(mdeditor, "MAX_FILES", 2)
    r = api.list_files(str(folder))
    assert r["truncated"] is True and len(r["files"]) == 2
