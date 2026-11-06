// Markdown の書式を挿入する処理。引数の CodeMirror に対して働く（画面には触らない）。
// ボタン・ショートカットの両方がここを呼ぶ。同じ操作をもう一度行うと元に戻る（トグル）。
const MdFormat = (() => {
  const HEADING = /^(#{1,6})\s+/;
  const LIST = /^(\s*)(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?/;      // 箇条書き・番号・チェックリスト
  const QUOTE = /^(\s*)>\s?/;
  const KIND = {
    ul: /^(\s*)[-*+]\s+(?!\[[ xX]\]\s)/,
    ol: /^(\s*)\d+[.)]\s+/,
    task: /^(\s*)[-*+]\s+\[[ xX]\]\s+/,
    quote: QUOTE,
  };

  // 選択している行の範囲（選択の終端が行頭ちょうどなら、その行は含めない）
  function lineRange(cm) {
    const from = cm.getCursor('from'), to = cm.getCursor('to');
    let last = to.line;
    if (to.ch === 0 && to.line > from.line) last -= 1;
    return [from.line, last];
  }

  function replaceLines(cm, first, last, lines) {
    const end = { line: last, ch: cm.getLine(last).length };
    cm.replaceRange(lines.join('\n'), { line: first, ch: 0 }, end);
    cm.setSelection({ line: first, ch: 0 }, { line: first + lines.length - 1, ch: lines[lines.length - 1].length });
  }

  // 太字・斜体・取り消し線・コードなど、前後を記号で挟むもの
  function inline(cm, mark) {
    const sel = cm.getSelection(), from = cm.getCursor('from'), to = cm.getCursor('to');
    const n = mark.length;
    if (!sel) {
      cm.replaceSelection(mark + mark);
      cm.setCursor({ line: from.line, ch: from.ch + n });
      return;
    }
    if (sel.length >= n * 2 && sel.startsWith(mark) && sel.endsWith(mark)) {          // 記号ごと選んでいる
      cm.replaceSelection(sel.slice(n, -n), 'around');
      return;
    }
    const before = cm.getRange({ line: from.line, ch: Math.max(0, from.ch - n) }, from);
    const after = cm.getRange(to, { line: to.line, ch: to.ch + n });
    if (before === mark && after === mark) {                                           // 記号の内側を選んでいる
      cm.replaceRange(sel, { line: from.line, ch: from.ch - n }, { line: to.line, ch: to.ch + n });
      cm.setSelection({ line: from.line, ch: from.ch - n }, { line: from.line === to.line ? from.line : to.line, ch: (from.line === to.line ? from.ch - n + sel.length : to.ch) });
      return;
    }
    cm.replaceSelection(mark + sel + mark, 'around');
  }

  // 見出し。level 0 は本文に戻す。すでに同じレベルなら本文に戻す
  function heading(cm, level) {
    const [first, last] = lineRange(cm);
    const lines = [];
    for (let i = first; i <= last; i++) lines.push(cm.getLine(i));
    const same = level > 0 && lines.filter(l => l.trim()).every(l => (l.match(HEADING) || [])[1] === '#'.repeat(level));
    const out = lines.map(l => {
      if (!l.trim()) return l;
      const body = l.replace(HEADING, '');
      return (level === 0 || same) ? body : '#'.repeat(level) + ' ' + body;
    });
    replaceLines(cm, first, last, out);
  }

  // 箇条書き・番号付き・チェックリスト・引用。全部の行がすでにその形なら外す
  function linePrefix(cm, kind) {
    const [first, last] = lineRange(cm);
    const lines = [];
    for (let i = first; i <= last; i++) lines.push(cm.getLine(i));
    const target = lines.filter(l => l.trim());
    if (!target.length) {                       // 空行: 記号だけ入れて、続きを書けるようにする
      replaceLines(cm, first, last, lines.map((l, i) => i === 0 ? prefixFor(kind, 1, '') : l));
      cm.setCursor({ line: first, ch: cm.getLine(first).length });
      return;
    }
    const all = target.every(l => KIND[kind].test(l));
    let n = 0;
    const out = lines.map(l => {
      if (!l.trim()) return l;
      if (all) return l.replace(KIND[kind], '$1');
      n += 1;
      const indent = (l.match(/^\s*/) || [''])[0];
      const body = kind === 'quote' ? l.replace(QUOTE, '$1') : l.replace(LIST, '$1');
      return prefixFor(kind, n, indent) + body.slice((body.match(/^\s*/) || [''])[0].length);
    });
    replaceLines(cm, first, last, out);
  }
  function prefixFor(kind, n, indent) {
    return indent + ({ ul: '- ', ol: n + '. ', task: '- [ ] ', quote: '> ' }[kind]);
  }

  // 空行をはさんで、いまの行の下（行が空ならその行）へブロックを挿入し、指定範囲を選ぶ
  function insertBlock(cm, text, selStart, selEnd) {
    const cur = cm.getCursor();
    const line = cm.getLine(cur.line);
    let at, prefix = '';
    if (line.trim()) { at = { line: cur.line, ch: line.length }; prefix = '\n\n'; }
    else at = { line: cur.line, ch: 0 };
    cm.replaceRange(prefix + text + '\n', at);
    const base = cm.indexFromPos(at) + prefix.length;
    if (selStart != null) cm.setSelection(cm.posFromIndex(base + selStart), cm.posFromIndex(base + (selEnd == null ? selStart : selEnd)));
    else cm.setCursor(cm.posFromIndex(base + text.length));
  }

  function codeBlock(cm) {
    const sel = cm.getSelection();
    if (sel) {
      const [first, last] = lineRange(cm);
      const lines = [];
      for (let i = first; i <= last; i++) lines.push(cm.getLine(i));
      replaceLines(cm, first, last, ['```', ...lines, '```']);
    } else insertBlock(cm, '```\n\n```', 4, 4);
  }

  function link(cm) {
    const sel = cm.getSelection(), from = cm.getCursor('from');
    const text = sel || 'リンク文字';
    cm.replaceSelection(`[${text}](URL)`);
    const ch = from.ch + text.length + 3;                       // 「URL」の部分を選んで、すぐ貼り付けられるように
    cm.setSelection({ line: from.line, ch }, { line: from.line, ch: ch + 3 });
  }

  function image(cm) {
    const sel = cm.getSelection(), from = cm.getCursor('from');
    const alt = sel || '代替テキスト';
    cm.replaceSelection(`![${alt}](画像のパス)`);
    const ch = from.ch + alt.length + 4;
    cm.setSelection({ line: from.line, ch }, { line: from.line, ch: ch + 5 });
  }

  function table(cm) {
    const head = '| 列1 | 列2 | 列3 |';
    insertBlock(cm, head + '\n| --- | --- | --- |\n| データ | データ | データ |\n| データ | データ | データ |', 2, 4);
  }

  function rule(cm) { insertBlock(cm, '---'); }

  const DIAGRAMS = {
    flowchart: ['フローチャート', 'flowchart TD\n  A[開始] --> B{判断}\n  B -->|はい| C[処理]\n  B -->|いいえ| D[終了]'],
    sequence: ['シーケンス図', 'sequenceDiagram\n  participant A as 利用者\n  participant B as システム\n  A->>B: リクエスト\n  B-->>A: 応答'],
    class: ['クラス図', 'classDiagram\n  class 動物 {\n    +名前\n    +鳴く()\n  }\n  動物 <|-- 犬'],
    gantt: ['ガントチャート', 'gantt\n  title スケジュール\n  dateFormat YYYY-MM-DD\n  section 準備\n  調査 :a1, 2026-10-01, 7d\n  設計 :after a1, 5d'],
    pie: ['円グラフ', 'pie title 内訳\n  "項目A" : 40\n  "項目B" : 30\n  "項目C" : 30'],
    xychart: ['XYチャート（棒グラフ・折れ線）', 'xychart-beta\n  title "月別の売上"\n  x-axis ["1月", "2月", "3月", "4月", "5月"]\n  y-axis "売上（万円）" 0 --> 100\n  bar [30, 45, 60, 55, 80]\n  line [30, 45, 60, 55, 80]'],
    radar: ['レーダーチャート', 'radar-beta\n  title 能力の比較\n  axis a["国語"], b["数学"], c["英語"], d["理科"], e["社会"]\n  curve s1["Aさん"]{80, 65, 70, 90, 55}\n  curve s2["Bさん"]{60, 85, 75, 70, 80}\n  max 100\n  min 0'],
    quadrant: ['象限図', 'quadrantChart\n  title 優先度マトリクス\n  x-axis 低コスト --> 高コスト\n  y-axis 低効果 --> 高効果\n  quadrant-1 すぐやる\n  quadrant-2 計画する\n  quadrant-3 後回し\n  quadrant-4 見直す\n  施策A: [0.3, 0.8]\n  施策B: [0.7, 0.6]\n  施策C: [0.2, 0.2]'],
    mindmap: ['マインドマップ', 'mindmap\n  root((テーマ))\n    項目A\n      詳細1\n      詳細2\n    項目B\n      詳細3'],
    state: ['状態遷移図', 'stateDiagram-v2\n  [*] --> 待機\n  待機 --> 処理中: 開始\n  処理中 --> 完了: 成功\n  処理中 --> 待機: 失敗\n  完了 --> [*]'],
    er: ['ER図', 'erDiagram\n  CUSTOMER ||--o{ ORDER : places\n  ORDER ||--|{ ITEM : contains\n  CUSTOMER {\n    string name\n    string email\n  }'],
    architecture: ['アーキテクチャ図', 'architecture-beta\n  group api(cloud)[API]\n  service db(database)[データベース] in api\n  service server(server)[サーバー] in api\n  service disk(disk)[ストレージ] in api\n  db:L -- R:server\n  disk:T -- B:server'],
    gitGraph: ['Git グラフ', 'gitGraph\n  commit\n  branch feature\n  checkout feature\n  commit\n  commit\n  checkout main\n  merge feature\n  commit'],
  };
  function diagram(cm, kind) {
    const d = DIAGRAMS[kind];
    if (d) insertBlock(cm, '```mermaid\n' + d[1] + '\n```');
  }

  // Vega-Lite のグラフのひな形（```vega-lite のコードブロックとして入れる）
  const rows = (a, b) => ({ values: a.map((x, i) => ({ [b[0]]: x, [b[1]]: b[2][i] })) });
  const CHARTS = {
    bar: ['棒グラフ（Vega-Lite）', {
      data: rows(['A', 'B', 'C', 'D'], ['category', 'value', [28, 55, 43, 91]]),
      mark: 'bar',
      encoding: { x: { field: 'category', type: 'nominal' }, y: { field: 'value', type: 'quantitative' } },
    }],
    line: ['折れ線グラフ（Vega-Lite）', {
      data: rows(['1月', '2月', '3月', '4月', '5月'], ['month', 'value', [12, 19, 15, 25, 32]]),
      mark: { type: 'line', point: true },
      encoding: { x: { field: 'month', type: 'ordinal', sort: null }, y: { field: 'value', type: 'quantitative' } },
    }],
    csv: ['CSV ファイルから（Vega-Lite）', {
      data: { url: 'data/sample.csv' },
      mark: 'bar',
      encoding: { x: { field: 'category', type: 'nominal' }, y: { field: 'value', type: 'quantitative' } },
    }],
  };
  function chart(cm, kind) {
    const c = CHARTS[kind];
    if (c) insertBlock(cm, '```vega-lite\n' + JSON.stringify(c[1], null, 2) + '\n```');
  }

  // 数式（TeX）のひな形。```math のブロック（独立した行の数式）で入れ、式の部分を選ぶので、そのまま打ち替えられる
  const MATH = {
    block: ['独立した行の数式（```math）', 'E = mc^2'],
    inline: ['文中の数式（$…$）', null],
    frac: ['分数', '\\frac{a}{b}'],
    quadratic: ['解の公式（根号）', 'x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}'],
    sum: ['総和', '\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}'],
    integral: ['積分', '\\int_0^1 x^2 \\, dx = \\frac{1}{3}'],
    matrix: ['行列', '\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}'],
    cases: ['場合分け', 'f(x) = \\begin{cases} x & (x \\ge 0) \\\\ -x & (x < 0) \\end{cases}'],
    ja: ['日本語を含む式', 'P(A) = \\frac{\\text{事象Aの数}}{\\text{全体の数}}'],
  };
  function math(cm, kind) {
    const m = MATH[kind];
    if (!m) return;
    const sel = cm.getSelection();
    if (kind === 'inline') {                                   // 選んだ文字を $ ではさむ（選ばなければ、ひな形を入れて、式を選ぶ）
      if (sel.includes('\n')) return;                          // 文中の数式は、1行
      const from = cm.getCursor('from'), text = sel || 'E=mc^2';
      cm.replaceSelection('$' + text + '$');
      cm.setSelection({ line: from.line, ch: from.ch + 1 }, { line: from.line, ch: from.ch + 1 + text.length });
      return;
    }
    if (kind === 'block' && sel) {                             // 選んだ行を、math ブロックで囲む
      const [first, last] = lineRange(cm), lines = [];
      for (let i = first; i <= last; i++) lines.push(cm.getLine(i));
      replaceLines(cm, first, last, ['```math', ...lines, '```']);
      return;
    }
    insertBlock(cm, '```math\n' + m[1] + '\n```', 8, 8 + m[1].length);
  }

  return { inline, heading, linePrefix, codeBlock, link, image, table, rule, diagram, DIAGRAMS, chart, CHARTS, math, MATH };
})();
