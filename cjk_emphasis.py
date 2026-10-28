"""日本語の文で `**強調**` が効かなくなる問題への対処（ビューアとエディタで共通）。

CommonMark は、強調の記号（`**` `*` `~~`）が強調を始められる／終えられる条件を、記号の前後の文字で決める
（フランキング規則）。この規則は、単語の間に空白を置く言語を前提にしている。

    加入している**「個人賠償責任保険」（特約）の優先使用を原則**とする。

では、開始の `**` の前が文字（る）、後ろが記号（「）なので、規則上は強調を始められず、`**` がそのまま表示される。
日本語には単語の間の空白がないので、この並びは普通に現れる。

対処: **前後が日本語（かな・漢字・ハングル）の文字であれば、空白と同じように扱う**（記号に接していても強調を
始められる／終えられる）。これは「CJK フレンドリー」と呼ばれる拡張と同じ考え方で、CommonMark の厳密な規則とは違う。
GitHub などでは `**` のまま表示される書き方でも、このアプリでは強調になる。

英数字だけの文には影響しない（`word**(x)**word` は従来どおり強調にならない）。
"""
from markdown_it.common.utils import isMdAsciiPunct, isPunctChar, isWhiteSpace
from markdown_it.rules_inline import StateInline
from markdown_it.rules_inline.state_inline import Scanned


def is_cjk(ch):
    """かな・漢字・ハングルなど、単語の間に空白を置かずに書く文字（記号は含まない）。"""
    c = ord(ch)
    return (
        0x1100 <= c <= 0x11FF          # ハングル字母
        or 0x3040 <= c <= 0x30FF       # ひらがな・カタカナ（長音符を含む）
        or 0x3130 <= c <= 0x318F       # ハングル互換字母
        or 0x31F0 <= c <= 0x31FF       # カタカナ拡張
        or 0x3400 <= c <= 0x4DBF       # 漢字拡張A
        or 0x4E00 <= c <= 0x9FFF       # 漢字
        or 0xAC00 <= c <= 0xD7AF       # ハングル音節
        or 0xF900 <= c <= 0xFAFF       # 互換漢字
        or 0xFF66 <= c <= 0xFF9F       # 半角カタカナ
        or 0x20000 <= c <= 0x2FA1F     # 漢字拡張B以降・互換漢字補助
    ) and not isPunctChar(ch)


class CJKStateInline(StateInline):
    def scanDelims(self, start, canSplitWord):
        """標準の scanDelims との違いは、記号に接している場合の判定に「日本語の文字」を加えた点だけ。"""
        pos = start
        maximum = self.posMax
        marker = self.src[start]

        last = self.src[start - 1] if start > 0 else " "
        while pos < maximum and self.src[pos] == marker:
            pos += 1
        count = pos - start
        nxt = self.src[pos] if pos < maximum else " "

        last_punct = isMdAsciiPunct(ord(last)) or isPunctChar(last)
        next_punct = isMdAsciiPunct(ord(nxt)) or isPunctChar(nxt)
        last_space = isWhiteSpace(ord(last))
        next_space = isWhiteSpace(ord(nxt))
        last_cjk = is_cjk(last)
        next_cjk = is_cjk(nxt)

        # 記号に接しているときの例外条件に、「反対側が日本語の文字」を加える
        left_flanking = not (
            next_space or (next_punct and not (last_space or last_punct or last_cjk))
        )
        right_flanking = not (
            last_space or (last_punct and not (next_space or next_punct or next_cjk))
        )

        can_open = left_flanking and (canSplitWord or (not right_flanking) or last_punct)
        can_close = right_flanking and (canSplitWord or (not left_flanking) or next_punct)
        return Scanned(can_open, can_close, count)


def apply(md):
    """この MarkdownIt の行内の解析で、日本語向けの判定を使うようにする。"""

    def parse(src, md_, env, tokens):
        state = CJKStateInline(src, md_, env, tokens)
        md.inline.tokenize(state)
        for rule in md.inline.ruler2.getRules(""):
            rule(state)
        return state.tokens

    md.inline.parse = parse
    return md
