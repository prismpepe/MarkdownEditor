import pytest

import printing as p


@pytest.mark.parametrize("text,total,want", [
    ("", None, ""),
    ("   ", None, ""),
    ("3", None, "3"),
    ("1-3,5", None, "1-3,5"),
    (" 2 - 4 ", None, "2-4"),
    ("2-2", None, "2"),
    ("5-", 12, "5-12"),
    ("1,3,5-7", 9, "1,3,5-7"),
    ("１ー３、５", None, "1-3,5"),          # 全角の数字・ハイフン・読点
])
def test_ページ指定を出力用の形に直す(text, total, want):
    assert p.parse_ranges(text, total) == want


@pytest.mark.parametrize("text,total", [
    ("0", None), ("3-1", None), ("a", None), ("1,,2", None), (",", None), ("1-2-3", None),
    ("1-99", 10), ("11", 10), ("5-", None), ("-3", None),
])
def test_誤ったページ指定は利用者に見せる文言で断る(text, total):
    with pytest.raises(ValueError) as e:
        p.parse_ranges(text, total)
    assert str(e.value)


def test_PDFのページ数を数える():
    pdf = (b"%PDF-1.4\n1 0 obj\n<</Type /Pages /Count 2>>\nendobj\n"
           b"2 0 obj\n<</Type /Page /Parent 1 0 R>>\nendobj\n3 0 obj\n<</Type/Page>>\nendobj\n")
    assert p.count_pdf_pages(pdf) == 2          # /Pages（ページの集まり）は数えない


def test_用紙の大きさは縦向きの寸法で持つ():
    for name, (w, h) in p.PAPERS.items():
        assert w < h, name
    assert round(p.PAPERS["A4"][0] * 25.4) == 210 and round(p.PAPERS["A4"][1] * 25.4) == 297
