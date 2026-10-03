// 検索・置換。編集欄（CodeMirror）に対して働く。表示は ui.html が持つ部品を受け取る。
//
// - 一致は全てハイライトし、「n / 全部で m 件」を出す。
// - 正規表現を使えるときの置換後の文字列では $1 $& $$ を使える（使わないときは書いたとおりに置換）。
// - すべて置換は1回の取り消しで元に戻る。
// - 長さ0の一致（^ だけなど）は無かったことにする（置換で文書が壊れやすいため）。
const MdFind = (() => {
  const CAP = 10000;                      // 数える上限（巨大な文書でも固まらないように）

  function build(query, caseSensitive, useRegex) {
    if (!query) return { re: null };
    try {
      const src = useRegex ? query : query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return { re: new RegExp(src, 'gm' + (caseSensitive ? '' : 'i')) };
    } catch (e) {
      return { re: null, error: String(e.message || e).replace(/^Invalid regular expression: /, '') };
    }
  }

  function matchesOf(text, re) {
    const out = []; re.lastIndex = 0; let m;
    while ((m = re.exec(text))) {
      if (m[0].length === 0) { re.lastIndex++; continue; }
      out.push({ index: m.index, length: m[0].length, m });
      if (out.length >= CAP) break;
    }
    return out;
  }

  function expand(repl, m, useRegex) {
    if (!useRegex) return repl;
    return repl.replace(/\$(\$|&|\d{1,2})/g, (s, d) => d === '$' ? '$' : d === '&' ? m[0] : (m[+d] === undefined ? '' : m[+d]));
  }

  function create(cm, ui) {
    let overlay = null, list = [], timer = null, lastError = null;

    const opts = () => ({ q: ui.q.value, cs: ui.cs.checked, re: ui.re.checked });
    function setOverlay(re) {
      if (overlay) cm.removeOverlay(overlay);
      overlay = null;
      if (!re) return;
      const r = new RegExp(re.source, re.flags);
      overlay = { token(stream) {
        r.lastIndex = stream.pos;
        const m = r.exec(stream.string);
        if (m && m.index === stream.pos) { stream.pos += m[0].length || 1; return 'searching'; }
        if (m) stream.pos = m.index; else stream.skipToEnd();
      } };
      cm.addOverlay(overlay);
    }

    // 検索語・文書が変わったら、一致の一覧とハイライトを作り直す
    function refresh() {
      clearTimeout(timer);
      const o = opts(), b = build(o.q, o.cs, o.re);
      lastError = b.error || null;
      list = b.re ? matchesOf(cm.getValue(), b.re) : [];
      setOverlay(b.re);
      updateCount();
      ui.q.classList.toggle('bad', !!b.error);
    }
    const schedule = () => { clearTimeout(timer); timer = setTimeout(refresh, 150); };

    function currentIndex() {                  // いま選んでいる一致が何番目か（なければ -1）
      const from = cm.indexFromPos(cm.getCursor('from')), to = cm.indexFromPos(cm.getCursor('to'));
      return list.findIndex(x => x.index === from && x.index + x.length === to);
    }
    function updateCount(note) {
      let t;
      if (lastError) t = '正規表現が正しくありません';
      else if (!ui.q.value) t = '';
      else if (!list.length) t = '見つかりません';
      else {
        const i = currentIndex();
        t = (i >= 0 ? `${i + 1} / ` : '') + `${list.length}${list.length >= CAP ? '+' : ''} 件`;
      }
      ui.count.textContent = note ? `${t}（${note}）` : t;
      ui.count.classList.toggle('bad', !list.length && !!ui.q.value);
    }

    function select(item) {
      const from = cm.posFromIndex(item.index), to = cm.posFromIndex(item.index + item.length);
      cm.setSelection(from, to);
      cm.scrollIntoView({ from, to }, 90);
    }

    // dir: 1=次へ, -1=前へ
    function step(dir) {
      refresh();
      if (!list.length) return false;
      const from = cm.indexFromPos(cm.getCursor('from')), to = cm.indexFromPos(cm.getCursor('to'));
      let pick, wrapped = false;
      if (dir > 0) {
        pick = list.find(x => x.index >= to) || list.find(x => x.index >= from && x.index + x.length > to);
        if (!pick) { pick = list[0]; wrapped = true; }
      } else {
        for (let i = list.length - 1; i >= 0; i--) if (list[i].index + list[i].length <= from) { pick = list[i]; break; }
        if (!pick) { pick = list[list.length - 1]; wrapped = true; }
      }
      select(pick);
      updateCount(wrapped ? (dir > 0 ? '先頭に戻りました' : '末尾に戻りました') : '');
      return true;
    }

    function replaceOne() {
      refresh();
      const i = currentIndex();
      if (i < 0) { step(1); return 0; }       // まず次の一致へ。選んだものを確かめてから置換できる
      const item = list[i], o = opts();
      const text = expand(ui.r.value, item.m, o.re);
      cm.operation(() => cm.replaceRange(text, cm.posFromIndex(item.index), cm.posFromIndex(item.index + item.length)));
      refresh();
      step(1);
      return 1;
    }

    function replaceAll() {
      refresh();
      if (!list.length) return 0;
      const o = opts(), items = list.slice(), n = items.length;
      cm.operation(() => {                    // 後ろから置換すると、前の位置がずれない
        for (let k = items.length - 1; k >= 0; k--) {
          const it = items[k];
          cm.replaceRange(expand(ui.r.value, it.m, o.re), cm.posFromIndex(it.index), cm.posFromIndex(it.index + it.length));
        }
      });
      refresh();
      ui.count.textContent = `${n} 件を置換しました`;
      return n;
    }

    function open(withReplace) {
      ui.bar.hidden = false;
      ui.rrow.hidden = !withReplace;
      const sel = cm.getSelection();
      if (sel && !sel.includes('\n') && sel.length <= 200) ui.q.value = sel;
      ui.q.focus(); ui.q.select();
      refresh();
    }
    function close() {
      ui.bar.hidden = true;
      setOverlay(null); list = [];
      cm.focus();
    }
    const isOpen = () => !ui.bar.hidden;

    ui.q.addEventListener('input', schedule);
    ui.cs.addEventListener('change', refresh);
    ui.re.addEventListener('change', refresh);
    cm.on('change', () => { if (isOpen()) schedule(); });
    cm.on('cursorActivity', () => { if (isOpen()) updateCount(); });
    return { open, close, isOpen, step, replaceOne, replaceAll, refresh, count: () => list.length };
  }

  return { create, build, matchesOf, expand };
})();
