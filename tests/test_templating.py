"""テンプレートから新しい文書を作る（templating.py）。結果は、変数のないふつうの Markdown になる。"""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import templating

NOW = datetime.datetime(2026, 11, 7, 9, 5)        # 2026-11-07（土）


# ---- 欄を見つける
def test_欄は_最初に出てきた順に_1つずつ返す():
    text = "# {{題名}}\n\n{{担当}} と {{題名}} と {{場所:会議室A}} と {{担当}}\n"
    assert templating.fields(text) == [
        {"name": "題名", "default": ""}, {"name": "担当", "default": ""}, {"name": "場所", "default": "会議室A"}]


def test_既定値は_最初の1つ目を使い_名前は最初の_コロンまで():
    assert templating.fields("{{開始:10:00}} {{開始:11:00}}") == [{"name": "開始", "default": "10:00"}]
    assert templating.fields("{{ 名前 : 既定 }}") == [{"name": "名前", "default": "既定"}]


def test_全角コロンも_既定値の区切りになる():
    assert templating.fields("{{場所：会議室}}") == [{"name": "場所", "default": "会議室"}]


def test_組み込みの欄は_聞かない():
    assert templating.fields("{{日付}} {{曜日}} {{年}} {{月}} {{日}} {{日時}} {{時刻}} {{年月日}}") == []


@pytest.mark.parametrize("text", [
    "{{1}}", "{{-b}}", "{{ $x }}", "{{ .Values.image }}", "{{a b}}", "{{}}", "{{ }}", "{{:既定}}",
    "\\frac{{1}}{{3}}", "{{{x}}}", "{x} {y}",
])
def test_欄ではない書き方は_欄にしない(text):
    assert templating.fields(text) == []
    assert templating.render(text, {}, NOW) == text         # そのまま残る


def test_エスケープした欄は_欄にならず_文字そのものになる():
    text = "書き方は \\{{名前}} です。{{名前}}"
    assert templating.fields(text) == [{"name": "名前", "default": ""}]
    assert templating.render(text, {"名前": "太郎"}, NOW) == "書き方は {{名前}} です。太郎"


# ---- 置き換え
def test_値に置き換わる():
    assert templating.render("# {{題名}}\n担当: {{担当}}", {"題名": "報告", "担当": "山田"}, NOW) == "# 報告\n担当: 山田"


def test_組み込みの欄は_作った日時になる():
    out = templating.render("{{日付}}|{{年月日}}|{{日時}}|{{時刻}}|{{年}}|{{月}}|{{日}}|{{曜日}}", {}, NOW)
    assert out == "2026-11-07|2026年11月7日|2026-11-07 09:05|09:05|2026|11|07|土"


@pytest.mark.parametrize("day,week", [(2, "月"), (3, "火"), (4, "水"), (5, "木"), (6, "金"), (7, "土"), (8, "日")])
def test_曜日(day, week):
    assert templating.render("{{曜日}}", {}, datetime.datetime(2026, 11, day)) == week


def test_値が無い欄は_既定値_無ければ空():
    assert templating.render("[{{場所:会議室A}}] [{{担当}}]", {}, NOW) == "[会議室A] []"


def test_値が空なら_空のまま_既定値には戻さない():
    assert templating.render("[{{場所:会議室A}}]", {"場所": ""}, NOW) == "[]"


def test_同じ欄は_すべて置き換わる():
    assert templating.render("{{v}} / {{v}} / {{v}}", {"v": "1.2.3"}, NOW) == "1.2.3 / 1.2.3 / 1.2.3"


def test_結果に_欄の記法は残らない():
    out = templating.render(templating.BUILTIN["リリースノート"], {"アプリ名": "X", "バージョン": "1.0"}, NOW)
    assert "{{" not in out and "}}" not in out


def test_値の中の_括弧は_再び置き換えない():
    assert templating.render("{{a}}", {"a": "{{b}}", "b": "NG"}, NOW) == "{{b}}"


def test_値は_文字列として入る():
    assert templating.render("{{n}}", {"n": 3}, NOW) == "3"


def test_日本語の欄名_英字_アンダースコア():
    assert templating.render("{{会議名}} {{ver}} {{_x}} {{Name2}}", {"会議名": "理事会", "ver": "1", "_x": "a", "Name2": "b"}, NOW) == "理事会 1 a b"


def test_markdownの他の記法を_壊さない():
    text = "| a | b |\n| - | - |\n| {{x}} | `{{y}}` |\n\n```bash\necho {{x}}\n```\n\n数式 $\\frac{{1}}{{2}}$ と $x_{i}$\n"
    out = templating.render(text, {"x": "X", "y": "Y"}, NOW)
    assert "| X | `Y` |" in out and "echo X" in out
    assert "$\\frac{{1}}{{2}}$" in out and "$x_{i}$" in out        # 数式の波括弧は、欄ではない


# ---- 組み込みのテンプレート
@pytest.mark.parametrize("name", list(templating.BUILTIN))
def test_組み込みのテンプレートは_すべて_作れる(name):
    text = templating.BUILTIN[name]
    values = {f["name"]: f["name"] + "の値" for f in templating.fields(text)}
    out = templating.render(text, values, NOW)
    assert "{{" not in out and out.startswith("#")
    assert all(v in out for v in values.values())


def test_議事録の既定値に_コロンを含む時刻が入る():
    f = {x["name"]: x["default"] for x in templating.fields(templating.BUILTIN["議事録"])}
    assert f["開始時刻"] == "10:00"
    assert "2026-11-07（土） 10:00〜" in templating.render(templating.BUILTIN["議事録"], {"開始時刻": "10:00"}, NOW)


def test_組み込みの一覧():
    items = templating.builtin_templates()
    assert [i["name"] for i in items] == list(templating.BUILTIN)
    assert all(i["id"] == "builtin:" + i["name"] and i["kind"] == "builtin" for i in items)


# ---- 自分のテンプレート（フォルダー）
def test_フォルダーの_mdだけを_名前順に一覧にする(tmp_path):
    for n in ("b議事.md", "A メモ.md", "c.txt", "d.MD"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "z.md").write_text("x", encoding="utf-8")
    items = templating.user_templates(str(tmp_path))
    assert [i["name"] for i in items] == ["A メモ", "b議事", "d"]            # 大文字小文字を区別せず、サブフォルダーは見ない
    assert all(i["kind"] == "user" and i["id"].startswith("file:") for i in items)


def test_フォルダーが無ければ_空(tmp_path):
    assert templating.user_templates(str(tmp_path / "none")) == []


def test_フォルダーの内側かの判定(tmp_path):
    f = tmp_path / "t"
    f.mkdir()
    assert templating.inside(str(f), str(f / "a.md"))
    assert not templating.inside(str(f), str(f))
    assert not templating.inside(str(f), str(tmp_path / "other.md"))
    assert not templating.inside(str(f), str(f / ".." / "other.md"))
    assert not templating.inside(str(f), str(f) + "2/a.md")                 # 名前が前方一致するだけの別のフォルダー


# ---- Api（画面が呼ぶ）
@pytest.fixture
def api(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return mdeditor.Api(None)


def test_Api_一覧は_組み込みと_自分のテンプレート(api):
    os.makedirs(api.template_folder())
    open(os.path.join(api.template_folder(), "週報.md"), "w", encoding="utf-8").write("# {{週}}週報\n")
    r = api.list_templates()
    assert r["folder"] == api.template_folder()
    assert [i["name"] for i in r["items"]] == list(templating.BUILTIN) + ["週報"]


def test_Api_組み込みを_取れる(api):
    r = api.get_template("builtin:リリースノート")
    assert r["error"] is None and r["name"] == "リリースノート"
    assert [f["name"] for f in r["fields"]] == ["アプリ名", "バージョン"]


def test_Api_自分のテンプレートを_取れる_Shift_JISでも(api):
    os.makedirs(api.template_folder())
    path = os.path.join(api.template_folder(), "旧形式.md")
    open(path, "wb").write("# {{題名}}\n本文です\n".encode("cp932"))
    r = api.get_template("file:" + path)
    assert r["error"] is None and r["text"].startswith("# {{題名}}") and r["fields"] == [{"name": "題名", "default": ""}]


def test_Api_任意のパスは_読ませない(api, tmp_path):
    other = tmp_path / "secret.md"
    other.write_text("# 機密 {{x}}", encoding="utf-8")
    assert "使えません" in api.get_template("file:" + str(other))["error"]
    assert "使えません" in api.get_template("file:" + os.path.join(api.template_folder(), "..", "..", "secret.md"))["error"]
    assert "使えません" in api.get_template("builtin:存在しない")["error"]
    assert "使えません" in api.get_template("unknown:x")["error"]


def test_Api_ファイルを選んだものだけは_場所の外でも_読める(api, tmp_path, monkeypatch):
    import dialogs
    chosen = tmp_path / "選んだ.md"
    chosen.write_text("# {{題名}}", encoding="utf-8")
    monkeypatch.setattr(dialogs, "pick_file", lambda initial=None, title="": str(chosen))
    tid = api.pick_template_file()
    assert tid == "file:" + str(chosen) and api.get_template(tid)["error"] is None


def test_Api_ファイル選択を取り消すと_None(api, monkeypatch):
    import dialogs
    monkeypatch.setattr(dialogs, "pick_file", lambda initial=None, title="": None)
    assert api.pick_template_file() is None


def test_Api_大きすぎる_文字コード不明は_断る(api):
    os.makedirs(api.template_folder())
    big = os.path.join(api.template_folder(), "大.md")
    open(big, "wb").write(b"a" * (templating.MAX_BYTES + 1))
    assert "大きすぎる" in api.get_template("file:" + big)["error"]
    bad = os.path.join(api.template_folder(), "不明.md")
    open(bad, "wb").write(b"\xff\xfe\x00\x81\x00\x00\xfa\xfb")
    r = api.get_template("file:" + bad)
    assert r["error"] is None or "文字コード" in r["error"]            # 判定できた場合を除き、断る


def test_Api_置き換え(api):
    out = api.render_template("# {{題名}}（{{日付}}）{{未入力:既定}}", {"題名": "報告"})
    assert out.startswith("# 報告（20") and out.endswith("）既定") and "{{" not in out


def test_Api_場所を開く_無ければ作る(api, monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p), raising=False)
    r = api.open_template_folder()
    assert r["error"] is None and os.path.isdir(api.template_folder()) and opened == [api.template_folder()]
