"""テンプレートから、新しい文書（ふつうの Markdown）を作る。

テンプレートは、ふつうの Markdown ファイルで、`{{名前}}` の欄を持つ。欄を値に置き換えた結果が、新しい文書になる。
**結果には、変数も、特別な記法も残らない**ので、どのツール（GitHub など）で開いても、同じに見える。

書き方
    {{名前}}           利用者が入れる欄
    {{名前:既定値}}    既定値つきの欄（最初の「:」までが名前）
    {{日付}} など      組み込みの欄。作った日時で自動に入る（利用者には聞かない）
    \\{{...}}           置き換えず、`{{...}}` という文字そのものにする

欄の名前は、文字（かな・漢字・英字）か _ で始まり、空白と { } : を含まない。
それ以外の `{{ ... }}`（`{{1}}`、`{{-b}}`、`{{ $x }}`、`{{ .Values.x }}` など、数式やテンプレートエンジンの書き方）は、
欄ではなく、そのまま残す。

置き換えだけを行う。命令の実行や、ほかのファイルの取り込みはしない。
"""
import datetime
import os
import re

MAX_BYTES = 1_000_000        # これより大きなファイルは、テンプレートにしない

PLACEHOLDER = re.compile(r"(\\?)(?<!\{)\{\{([^{}\n]*)\}\}(?!\})")      # {{{x}}} のように、波括弧が続くものは、欄にしない
NAME = re.compile(r"^[A-Za-z_぀-ヿ㐀-鿿ｦ-ﾟ][^\s{}:：]*$")
WEEKDAYS = "月火水木金土日"

BUILTIN_NAMES = ("日付", "年月日", "日時", "時刻", "年", "月", "日", "曜日")


def builtin_values(now=None):
    """組み込みの欄の値。"""
    now = now or datetime.datetime.now()
    return {
        "日付": now.strftime("%Y-%m-%d"),
        "年月日": f"{now.year}年{now.month}月{now.day}日",
        "日時": now.strftime("%Y-%m-%d %H:%M"),
        "時刻": now.strftime("%H:%M"),
        "年": str(now.year),
        "月": f"{now.month:02d}",
        "日": f"{now.day:02d}",
        "曜日": WEEKDAYS[now.weekday()],
    }


def parse(inner):
    """{{ }} の中身を、(名前, 既定値) にする。名前が欄の名前として正しくなければ、名前は None。"""
    inner = inner.strip()
    cut = min([i for i in (inner.find(":"), inner.find("：")) if i >= 0], default=-1)
    name, default = (inner, "") if cut < 0 else (inner[:cut].strip(), inner[cut + 1:].strip())
    return (name if NAME.match(name) else None), default


def fields(text):
    """利用者に聞く欄を、最初に出てきた順に返す。[{"name": 名前, "default": 既定値}]。
    同じ名前は 1 つにまとめる（既定値は、最初のもの）。組み込みの欄と、エスケープしたものは含めない。"""
    seen, out = set(), []
    for m in PLACEHOLDER.finditer(text):
        if m.group(1):
            continue
        name, default = parse(m.group(2))
        if name is None or name in BUILTIN_NAMES or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "default": default})
    return out


def render(text, values=None, now=None):
    """欄を値に置き換えた、新しい文書の本文を返す。
    values に無い欄は、既定値（無ければ空）になる。値が空文字なら、空のまま（既定値には戻さない）。"""
    values = values or {}
    builtin = builtin_values(now)

    def replace(m):
        if m.group(1):                                  # \{{ ... }} → {{ ... }}（置き換えない）
            return m.group(0)[1:]
        name, default = parse(m.group(2))
        if name is None:
            return m.group(0)
        if name in builtin:
            return builtin[name]
        value = values.get(name)
        return default if value is None else str(value)

    return PLACEHOLDER.sub(replace, text)


# ---- 組み込みのテンプレート（そのまま使える見本。自分のテンプレートは、フォルダーに .md を置く）
BUILTIN = {
    "議事録": """# {{会議名}} 議事録

- 日時: {{日付}}（{{曜日}}） {{開始時刻:10:00}}〜
- 場所: {{場所}}
- 出席者: {{出席者}}
- 記録者: {{記録者}}

## 議題

1.

## 決定事項

-

## 持ち帰り事項

| 内容 | 担当 | 期限 |
| --- | --- | --- |
|  |  |  |
""",
    "リリースノート": """# {{アプリ名}} {{バージョン}} リリースノート

リリース日: {{日付}}

## 追加

-

## 変更

-

## 修正

-

## 注意

-
""",
    "日報・メモ": """# {{日付}}（{{曜日}}）{{題名:日報}}

## 今日やったこと

-

## 明日やること

-

## メモ

""",
    "README のひな形": """# {{プロジェクト名}}

{{概要}}

## 使い方



## 開発

- バージョン: {{バージョン:0.1.0}}
- 更新日: {{日付}}
""",
}


def builtin_templates():
    return [{"id": "builtin:" + name, "name": name, "kind": "builtin"} for name in BUILTIN]


def user_templates(folder):
    """フォルダーの中の .md を、名前順に返す（サブフォルダーは見ない。無ければ空）。"""
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(".md") and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        return []
    names.sort(key=lambda n: n.casefold())
    return [{"id": "file:" + os.path.join(folder, n), "name": os.path.splitext(n)[0], "kind": "user"} for n in names]


def inside(folder, path):
    """path が folder の中にあるか（.. などで外へ出ていないか）。"""
    try:
        folder, path = os.path.normcase(os.path.abspath(folder)), os.path.normcase(os.path.abspath(path))
        return os.path.commonpath([folder, path]) == folder and path != folder
    except ValueError:                                  # ドライブが違うなど
        return False
