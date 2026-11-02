"""取扱説明書が、アプリの実際の機能に追いついていること。

機能を足すたびに、説明書の起動方法・ボタン・ショートカットの記述が抜けたり、章の番号の参照が古くなったり
していた。その見落としを、手作業の点検ではなく、テストで見つける。

- 画面（ui.html）にあるボタン・ショートカット、起動の引数（--register など）が、説明書に書かれていること。
- 章の番号と、「N. 章の名前」という参照が、食い違っていないこと。
- 注意書きの書式（`> **注意**`）、見出しの前後の空行が、そろっていること。
"""
import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL = open(os.path.join(ROOT, "docs", "取扱説明書.md"), encoding="utf-8").read()
UI = open(os.path.join(ROOT, "ui.html"), encoding="utf-8").read()
MAIN = open(next(p for p in glob.glob(os.path.join(ROOT, "md*.py")) if os.path.basename(p) in ("mdviewer.py", "mdeditor.py")),
            encoding="utf-8").read()


def squash(s):
    return re.sub(r"[\s`]+", "", s)


MANUAL_SQ = squash(MANUAL)


def outside_code(text):
    """コードブロックの外の行を、(行番号, 行) で返す。"""
    inside = False
    for i, line in enumerate(text.split("\n")):
        if line.startswith("```"):
            inside = not inside
            continue
        if not inside:
            yield i, line


CHAPTERS = [(int(m.group(1)), m.group(2).strip()) for _, l in outside_code(MANUAL)
            for m in [re.match(r"^## (\d+)\. (.+)$", l)] if m]


# ---- 構成 -------------------------------------------------------------------
def test_章の番号が連番():
    assert [n for n, _ in CHAPTERS] == list(range(1, len(CHAPTERS) + 1))


def test_冒頭の目次が章の見出しと一致する():
    m = re.search(r"^## 目次\n\n((?:\d+\. .+\n)+)", MANUAL, re.M)
    assert m, "冒頭に「## 目次」の一覧がありません"
    listed = [(int(a), b.strip()) for a, b in re.findall(r"^(\d+)\. (.+)$", m.group(1), re.M)]
    assert listed == CHAPTERS


def test_章の参照が実在する章を指している():
    refs = re.findall(r"「(\d+)\. ([^」]+)」", MANUAL)                 # 「3. 画面の見かた」
    refs += re.findall(r"^\| .*? \| (\d+)\. ([^|]+?) \|$", MANUAL, re.M)        # 一覧表の「章」の列
    assert refs, "章への参照が1つもありません"
    for n, title in refs:
        assert (int(n), title.strip()) in CHAPTERS, f"存在しない章を参照しています: {n}. {title}"


def test_バージョン番号を直接書かない():
    assert not re.search(r"\bv\d+\.\d+\.\d+\b", MANUAL), "バージョンは、更新のたびに古くなるので、書かない"


def test_見出しの前後に空行がある():
    lines = MANUAL.split("\n")
    for i, line in outside_code(MANUAL):
        if re.match(r"^#{1,6} ", line):
            assert i == 0 or lines[i - 1] == "", f"{i + 1}行目: 見出しの前に空行がありません"
            assert i + 1 >= len(lines) or lines[i + 1] == "", f"{i + 1}行目: 見出しの後に空行がありません"


def test_注意書きは決まった書式():
    for i, line in outside_code(MANUAL):
        if line.startswith(">"):
            assert line.startswith("> **注意**　"), f"{i + 1}行目: 引用の枠は「> **注意**　」で始めてください: {line[:30]}"


def test_表のセルの中に縦線を書かない():
    """GitHub やブログなどでは、表のセルの中の `|` が、コードの中でも列の区切りになり、表が崩れる。"""
    for i, line in outside_code(MANUAL):
        if line.startswith("|"):
            for span in re.findall(r"`([^`]*)`", line):
                assert "|" not in span.replace("\\|", ""), f"{i + 1}行目: 表のセルのコードに | があります: {span}"


# ---- 起動 ---------------------------------------------------------------------
def test_起動の引数が説明されている():
    for flag in sorted(set(re.findall(r'"(--[a-z]+)"', MAIN))):
        assert flag in MANUAL, f"起動の引数 {flag} が説明書にありません"


def test_登録用のファイルが説明されている():
    for cmd in glob.glob(os.path.join(ROOT, "登録*.cmd")):
        assert os.path.basename(cmd) in MANUAL, f"{os.path.basename(cmd)} が説明書にありません"


@pytest.mark.parametrize("word", ["ダブルクリック", "ドラッグ＆ドロップ", "右クリック", "その他のオプションを表示", "コマンドライン", "起動しているウィンドウ"])
def test_起動方法のキーワードが説明されている(word):
    assert word in MANUAL


# ---- ボタン・ショートカット -------------------------------------------------------
def toolbar_labels():
    block = UI[UI.index('<div id="toolbar"'):UI.index('<div id="msg"')]
    return [re.sub(r"\s+", " ", m).strip() for m in re.findall(r"<button[^>]*>([^<]+)</button>", block)]


def test_ツールバーのボタンが説明されている():
    labels = toolbar_labels()
    assert labels
    for label in labels:
        name = re.sub(r"^[^\w]+", "", label).strip()              # 先頭の絵文字を除く
        assert name in MANUAL or label in MANUAL, f"ツールバーのボタン「{label}」が説明書にありません"


def test_書式ボタンが説明されている():
    for m in re.finditer(r'<button data-[fe]="[^"]+" title="([^"]+)"', UI):
        name = re.sub(r"\s*\(.*$", "", m.group(1)).strip()
        assert name in MANUAL, f"書式ボタン「{name}」が説明書にありません"


def test_ボタンの説明に出ているショートカットが一覧にある():
    keys = set()
    for m in re.finditer(r'title="([^"]*)"', UI):
        text = m.group(1)
        paren = re.search(r"\(([^)]*)\)\s*$", text)
        for token in re.split(r"\s*/\s*", paren.group(1) if paren else text):
            token = token.strip()
            if re.fullmatch(r"(?:Ctrl\+)?(?:Shift\+)?(?:[A-Z0-9]|F\d+|Enter|Esc|\\)", token) and ("+" in token or token.startswith("F")):
                keys.add(token)
    assert keys
    for key in sorted(keys):
        assert squash(key) in MANUAL_SQ, f"ショートカット {key} が説明書にありません"
