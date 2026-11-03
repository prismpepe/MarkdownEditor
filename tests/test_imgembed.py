"""画像の Base64 埋め込みと、ファイルへの書き戻し。"""
import base64
import os
import re
import time

import pytest

import imgembed
import mdeditor
from sanitize import sanitize

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
PNG2 = PNG + b"\x00"          # 別の内容


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "a.png").write_bytes(PNG)
    (tmp_path / "images" / "b.png").write_bytes(PNG2)
    (tmp_path / "pic one.png").write_bytes(PNG)
    (tmp_path / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (tmp_path / "note.pdf").write_bytes(b"%PDF-1.4")
    return tmp_path


def run(text, folder, dry_run=False):
    return imgembed.embed(text, str(folder), dry_run=dry_run)


def render(text):
    return sanitize(mdeditor.make_renderer().render(text, {"base": ""}))


def test_相対パスの画像が参照形式になる(folder):
    r = run("# 題\n\n![図A](images/a.png)\n", folder)
    assert "![図A][image1]" in r["text"]
    assert re.search(r"^\[image1\]: data:image/png;base64,[A-Za-z0-9+/=]+$", r["text"], re.M)
    assert r["text"].index("![図A][image1]") < r["text"].index("[image1]: data:")      # 定義は文末
    assert r["converted"][0]["bytes"] == len(PNG)


def test_変換した文書でも_プレビューは画像を表示する(folder):
    out = run("![図A](images/a.png)\n", folder)["text"]
    assert re.search(r'<img src="data:image/png;base64,[A-Za-z0-9+/=]+" alt="図A"', render(out))


def test_同じ画像は定義を1つにまとめる(folder):
    out = run("![1](images/a.png)\n\n![2](images/a.png)\n", folder)["text"]
    assert out.count("[image1]: data:") == 1 and "![1][image1]" in out and "![2][image1]" in out


def test_別の画像は別のラベルになる(folder):
    out = run("![1](images/a.png)\n\n![2](images/b.png)\n", folder)["text"]
    assert "[image1]: data:" in out and "[image2]: data:" in out


def test_タイトルは定義へ移る(folder):
    out = run('![図](images/a.png "説明文")\n', folder)["text"]
    assert re.search(r'^\[image1\]: data:image/png;base64,\S+ "説明文"$', out, re.M)
    assert "![図][image1]" in out


def test_空白を含むパスも変換できる(folder):
    out = run("![x](<pic one.png>)\n\n![y](pic%20one.png)\n", folder)["text"]
    assert out.count("[image1]: data:") == 1


def test_既存のラベルと重ならない(folder):
    out = run("![x](images/a.png)\n\n[image1]: https://example.com/\n", folder)["text"]
    assert "![x][image2]" in out and "[image1]: https://example.com/" in out


def test_画像に使われる定義だけを_その場で書き換える(folder):
    text = "![図][pic]\n\nリンクは [資料][doc]\n\n[pic]: images/a.png\n[doc]: note.pdf\n"
    out = run(text, folder)["text"]
    assert re.search(r"^\[pic\]: data:image/png;base64,\S+$", out, re.M)
    assert "[doc]: note.pdf" in out
    assert "image1" not in out


def test_HTMLのimgはsrcへ直接入る(folder):
    out = run('<img src="images/a.png" width="10">\n', folder)["text"]
    assert re.search(r'<img src="data:image/png;base64,\S+" width="10">', out)


def test_コードの中は変えない(folder):
    text = "```\n![x](images/a.png)\n```\n\n`![y](images/a.png)`\n"
    r = run(text, folder)
    assert r["text"] == text and r["converted"] == []


def test_ネットの画像とdata_URIは対象にしない(folder):
    text = "![x](https://example.com/a.png)\n\n![y](data:image/png;base64,AAAA)\n"
    r = run(text, folder)
    assert r["text"] == text and r["converted"] == [] and r["skipped"] == []


def test_変換できないものは理由つきで残す(folder):
    text = "![a](logo.svg)\n\n![b](missing.png)\n\n![c](note.pdf)\n"
    r = run(text, folder)
    assert r["text"] == text and r["converted"] == []
    reasons = {s["src"]: s["reason"] for s in r["skipped"]}
    assert "SVG" in reasons["logo.svg"] and "見つかりません" in reasons["missing.png"] and "形式" in reasons["note.pdf"]


def test_確認だけなら本文を変えない(folder):
    text = "![x](images/a.png)\n"
    r = run(text, folder, dry_run=True)
    assert r["text"] == text and len(r["converted"]) == 1


def test_選んだ画像を挿入する部品(folder):
    r = imgembed.insert_new("# 題\n\n[image1]: https://example.com/\n", str(folder / "images" / "a.png"))
    assert r["ref"] == "![a][image2]" and r["definition"].startswith("[image2]: data:image/png;base64,")
    assert "error" in imgembed.insert_new("", str(folder / "logo.svg"))


# ---- ファイルへ戻す --------------------------------------------------------
def test_Base64をファイルへ戻す(folder):
    doc = str(folder / "手順書.md")
    embedded = run("![図A](images/a.png)\n", folder)["text"]
    r = imgembed.externalize(embedded, doc)
    assert [w["name"] for w in r["written"]] == ["images/手順書_001.png"]
    assert (folder / "images" / "手順書_001.png").read_bytes() == PNG
    assert "![図A][image1]" in r["text"] and "[image1]: images/手順書_001.png" in r["text"]
    assert "base64" not in r["text"]


def test_戻した文書でも_プレビューは相対パスの画像を出す(folder):
    doc = str(folder / "d.md")
    out = imgembed.externalize(run("![x](images/a.png)\n", folder)["text"], doc)["text"]
    html = mdeditor.make_renderer().render(out, {"base": str(folder)})
    assert "data:image/png;base64," in sanitize(html, lambda src: mdeditor.inline_image(src, str(folder)))


def test_同じ内容があれば再利用し_別の内容は上書きしない(folder):
    doc = str(folder / "d.md")
    (folder / "images" / "d_001.png").write_bytes(PNG)               # 同じ内容: 再利用
    (folder / "images" / "d_002.png").write_bytes(PNG + b"")     # 書き出す画像のどれとも違う内容: 残す
    embedded = run("![a](images/a.png)\n\n![b](images/b.png)\n", folder)["text"]
    r = imgembed.externalize(embedded, doc)
    names = {w["name"]: w["reused"] for w in r["written"]}
    assert names == {"images/d_001.png": True, "images/d_003.png": False}
    assert (folder / "images" / "d_002.png").read_bytes() == PNG + b""
    assert (folder / "images" / "d_003.png").read_bytes() == PNG2


def test_確認だけならファイルを書かない(folder):
    doc = str(folder / "d.md")
    embedded = run("![a](images/a.png)\n", folder)["text"]
    r = imgembed.externalize(embedded, doc, dry_run=True)
    assert r["text"] == embedded and not (folder / "images" / "d_001.png").exists()
    assert len(r["written"]) == 1


def test_壊れたBase64は残す(folder):
    text = "![x](data:image/png;base64,@@@@)\n"
    r = imgembed.externalize(text, str(folder / "d.md"))
    assert r["text"] == text


def test_埋め込みと書き戻しを往復しても画像は同じ(folder):
    doc = str(folder / "d.md")
    original = "# 題\n\n![A](images/a.png)\n\n![B](images/b.png \"t\")\n"
    back = imgembed.externalize(run(original, folder)["text"], doc)
    for w in back["written"]:
        data = (folder / w["name"]).read_bytes()
        assert data in (PNG, PNG2)
    assert len(back["written"]) == 2


def test_大きな画像でも_変換とプレビューが現実的な時間で終わる(folder):
    big = os.urandom(3 * 1024 * 1024)
    (folder / "big.png").write_bytes(big)
    t0 = time.time()
    out = run("![大](big.png)\n", folder)["text"]
    html = render(out)
    assert time.time() - t0 < 5
    assert "data:image/png;base64," in html


# ---- 画像を、パスで参照する書き方 ------------------------------------------------
def test_文書のフォルダーの中の画像は_相対パス(folder):
    doc = str(folder / "d.md")
    r = imgembed.path_reference(str(folder / "images" / "a.png"), doc)
    assert r["markdown"] == "![a](images/a.png)" and r["relative"] is True and r["bytes"] == len(PNG)


def test_同じフォルダーの画像():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "x.png"), "wb").write(PNG)
        assert imgembed.path_reference(os.path.join(d, "x.png"), os.path.join(d, "d.md"))["markdown"] == "![x](x.png)"


def test_上の階層の画像は_相対パスに_二つの点が付く(folder):
    sub = folder / "docs"
    sub.mkdir()
    r = imgembed.path_reference(str(folder / "images" / "a.png"), str(sub / "d.md"))
    assert r["markdown"] == "![a](../images/a.png)" and r["relative"] is True


def test_空白や括弧や_パーセントは符号化し_日本語はそのまま(folder):
    for name, want in (("pic one.png", "pic%20one.png"), ("a(1).png", "a%281%29.png"), ("100%.png", "100%25.png"),
                       ("図 1.png", "図%201.png"), ("a#b.png", "a%23b.png")):
        (folder / name).write_bytes(PNG)
        r = imgembed.path_reference(str(folder / name), str(folder / "d.md"))
        assert r["markdown"].endswith("(%s)" % want), (name, r["markdown"])


def test_保存していない文書では_絶対パス(folder):
    r = imgembed.path_reference(str(folder / "images" / "a.png"), None)
    assert r["relative"] is False and r["markdown"].startswith("![a](file:///") and r["markdown"].endswith("/images/a.png)")


def test_別のドライブなら_絶対パス(folder, monkeypatch):
    def boom(*a, **k):
        raise ValueError("path is on mount 'F:', start on mount 'C:'")
    monkeypatch.setattr(os.path, "relpath", boom)
    r = imgembed.path_reference(str(folder / "images" / "a.png"), str(folder / "d.md"))
    assert r["relative"] is False and "file:///" in r["markdown"]


def test_説明文を指定でき_括弧はエスケープする(folder):
    r = imgembed.path_reference(str(folder / "images" / "a.png"), str(folder / "d.md"), alt="図[1]")
    assert r["markdown"] == "![図\\[1\\]](images/a.png)"


def test_SVGも参照できる(folder):
    r = imgembed.path_reference(str(folder / "logo.svg"), str(folder / "d.md"))
    assert r["markdown"] == "![logo](logo.svg)"


def test_参照できない画像は理由を返す(folder):
    assert "見つかりません" in imgembed.path_reference(str(folder / "none.png"), str(folder / "d.md"))["error"]
    assert "形式" in imgembed.path_reference(str(folder / "note.pdf"), str(folder / "d.md"))["error"]


def test_参照の書き方で_プレビューに画像が出る(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = mdeditor.Api(None)
    (folder / "pic one.png").write_bytes(PNG)
    doc = str(folder / "d.md")
    for image in ("images/a.png", "pic one.png"):
        md = imgembed.path_reference(str(folder / image), doc)["markdown"]
        html = api.render(md + "\n", doc)
        assert "data:image/png;base64," in html, (md, html)


def test_絶対パスの書き方は_どれでもプレビューに画像が出る(folder, tmp_path, monkeypatch):
    """file:///… も、C:/… も、ドライブを省いた /… も（利用者の報告: file:/// が文字のまま出ていた）。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = mdeditor.Api(None)
    (folder / "pic one.png").write_bytes(PNG)
    doc = str(folder / "d.md")
    absolute = str(folder / "images" / "a.png").replace("\\", "/")
    spelled = [
        "file:///" + absolute,
        "file:///" + str(folder / "pic one.png").replace("\\", "/").replace(" ", "%20"),
        absolute,
        "../" + folder.name + "/images/a.png",
    ]
    if os.name == "nt":
        spelled.append(absolute[2:])                      # ドライブを省いた /Users/…（文書と同じドライブとみなす）
    for src in spelled:
        html = api.render("![図](%s)\n" % src, doc)
        assert "data:image/png;base64," in html, (src, html)
        assert "![図]" not in html, src                    # 画像にならず文字のまま出ていないこと
