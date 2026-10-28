"""エクスプローラーへの登録（ファイルの「プログラムから開く」と、フォルダーの右クリック）。

本物の登録（Software\\Classes）には触れず、テスト用の別のキーの下に書いて確かめる。終わったら消す。
"""
import os
import uuid
import winreg

import pytest

import mdeditor
import shellreg

EXE = r"C:\Program Files\Markdown Tools\MarkdownEditor.exe"       # 空白を含む場所でも、引用符で囲めること
PROG = "MarkdownEditor.File"
VERB = "MarkdownEditor"
TEXT = "Markdown エディタで開く"


@pytest.fixture
def classes():
    base = rf"Software\MarkdownEditorTest_{uuid.uuid4().hex[:8]}"
    yield rf"{base}\Classes"
    shellreg.delete_tree(base)


def read(key, name=""):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
        return winreg.QueryValueEx(k, name)[0]


def exists(key):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, key))
        return True
    except OSError:
        return False


def values(key):
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumValue(k, i)[0])
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def test_ファイルの登録_プログラムから開くの一覧に出る(classes):
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    assert read(rf"{classes}\{PROG}\shell\open") == TEXT
    assert read(rf"{classes}\{PROG}\shell\open\command") == f'"{EXE}" "%1"'
    assert read(rf"{classes}\{PROG}\DefaultIcon") == f'"{EXE}",0'
    for ext in (".md", ".markdown"):
        assert PROG in values(rf"{classes}\{ext}\OpenWithProgids")


def test_フォルダーを右クリックしたメニューに出る(classes):
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    base = rf"{classes}\Directory\shell\{VERB}"
    assert read(base) == TEXT                                     # メニューの文言
    assert read(base, "Icon") == f'"{EXE}",0'
    assert read(rf"{base}\command") == f'"{EXE}" "%1"'            # %1 = 右クリックしたフォルダー


def test_フォルダーの中の何もない場所を右クリックしたメニューにも出る(classes):
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    base = rf"{classes}\Directory\Background\shell\{VERB}"
    assert read(base) == TEXT
    assert read(base, "Icon") == f'"{EXE}",0'
    assert read(rf"{base}\command") == f'"{EXE}" "%V"'            # %V = 開いているフォルダー


def test_2つのアプリは別のキー名で登録され_互いに上書きしない(classes):
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    viewer = r"C:\Tools\MarkdownViewer.exe"
    shellreg.register(viewer, "MarkdownViewer.File", "Markdown ビューアで開く", "MarkdownViewer", classes)
    assert read(rf"{classes}\Directory\shell\{VERB}\command") == f'"{EXE}" "%1"'
    assert read(rf"{classes}\Directory\shell\MarkdownViewer\command") == f'"{viewer}" "%1"'
    shellreg.unregister("MarkdownViewer.File", "MarkdownViewer", classes)       # 片方を解除しても、もう片方は残る
    assert exists(rf"{classes}\Directory\shell\{VERB}\command")
    assert not exists(rf"{classes}\Directory\shell\MarkdownViewer")


def test_何度登録しても同じ(classes):
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    assert read(rf"{classes}\Directory\shell\{VERB}\command") == f'"{EXE}" "%1"'
    assert values(rf"{classes}\.md\OpenWithProgids").count(PROG) == 1


def test_exeを移して登録し直すと_新しい場所に変わる(classes):
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    moved = r"D:\新しい場所\MarkdownEditor.exe"
    shellreg.register(moved, PROG, TEXT, VERB, classes)
    assert read(rf"{classes}\Directory\shell\{VERB}\command") == f'"{moved}" "%1"'
    assert read(rf"{classes}\{PROG}\shell\open\command") == f'"{moved}" "%1"'


def test_解除すると登録したものだけが消え_ほかのアプリの登録は残る(classes):
    # ほかのアプリが、同じ場所に登録していたものを、先に作っておく
    other = rf"{classes}\Directory\shell\OtherTool"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{other}\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, r'"C:\other.exe" "%1"')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{classes}\.md\OpenWithProgids") as k:
        winreg.SetValueEx(k, "Other.File", 0, winreg.REG_NONE, b"")
    shellreg.register(EXE, PROG, TEXT, VERB, classes)
    shellreg.unregister(PROG, VERB, classes)
    assert not exists(rf"{classes}\{PROG}")
    assert not exists(rf"{classes}\Directory\shell\{VERB}")
    assert not exists(rf"{classes}\Directory\Background\shell\{VERB}")
    assert PROG not in values(rf"{classes}\.md\OpenWithProgids")
    assert "Other.File" in values(rf"{classes}\.md\OpenWithProgids")            # ほかのアプリの分は残る
    assert read(rf"{other}\command") == r'"C:\other.exe" "%1"'


def test_登録していなくても解除は落ちない(classes):
    shellreg.unregister(PROG, VERB, classes)
    shellreg.unregister(PROG, VERB, classes)


@pytest.mark.parametrize("arg,want", [
    ('F:"', 'F:\\'),                                  # "%V" がドライブのルートのとき（F:\" が引用符として解釈される）
    ('C:\\my dir"', 'C:\\my dir\\'),
    ('C:\\docs', 'C:\\docs'),                         # ふつうのパスは、そのまま
    ('C:\\ドキュメント\\議事録', 'C:\\ドキュメント\\議事録'),
    ('', ''),
    (None, None),
])
def test_起動引数の末尾に残った引用符を直す(arg, want):
    assert shellreg.clean_path_arg(arg) == want


def test_フォルダーを渡して起動すると_そのフォルダーの一覧を開き_ファイルは開かない(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    folder = tmp_path / "議事録 2026 (確定)"                    # 空白・日本語・括弧を含む
    folder.mkdir()
    (folder / "a.md").write_text("x", encoding="utf-8")
    init = mdeditor.Api(str(folder)).get_initial()
    assert init["folder"] == str(folder) and init["file"] is None and init["error"] is None


def test_存在しないフォルダーを渡されたら_理由を返す(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    init = mdeditor.Api(str(tmp_path / "ない")).get_initial()
    assert init["error"] and init["folder"] is None


def test_登録は_exeから実行したときだけ行う(monkeypatch):
    shown = []
    monkeypatch.setattr(mdeditor, "message", lambda text, *a, **k: shown.append(text))
    monkeypatch.setattr(mdeditor.sys, "frozen", False, raising=False)
    mdeditor.register_association()
    assert shown == ["exe 版から実行してください。"]            # 開発中に、本物の登録を書き換えない
