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
  };
  function diagram(cm, kind) {
    const d = DIAGRAMS[kind];
    if (d) insertBlock(cm, '```mermaid\n' + d[1] + '\n```');
  }

  return { inline, heading, linePrefix, codeBlock, link, image, table, rule, diagram, DIAGRAMS };
})();
