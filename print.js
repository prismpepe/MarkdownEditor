// 印刷・PDF 保存のダイアログ（ビューアとエディタで共通）。
//
// 使い方: MdPrint.init({ api, content, name, dir, notify })
//   api      : window.pywebview.api
//   content  : () => 印刷する本文の要素（画面の本文領域）
//   name     : () => 文書名（ヘッダーと PDF の既定のファイル名に使う）
//   path     : () => 文書のパス（なければ null）
//   notify   : (文言) => 画面の状況表示へ出す（任意）
//
// 印刷の見た目は、各画面の `@media print`（本文以外を隠す）が決める。ここは出力の設定と操作を受け持つ。
const MdPrint = (() => {
  const PAPER_IN = { A4: [210 / 25.4, 297 / 25.4], A3: [297 / 25.4, 420 / 25.4], B5: [182 / 25.4, 257 / 25.4], B4: [257 / 25.4, 364 / 25.4], Letter: [8.5, 11] };
  const MARGIN_MM = { '標準': 15, '狭い': 8, '広い': 25, 'なし': 0 };
  const DEFAULTS = { mode: 'print', rangeAll: true, ranges: '', paper: 'A4', landscape: false, margin: '標準', scalePct: 100, fit: true, backgrounds: true, headerFooter: true, printer: '', copies: 1, mono: false };

  let cfg = null, el = null, total = 0, busy = false, countTimer = null, countSeq = 0, lastPdf = null;
  let restoreFns = [];

  const $ = id => document.getElementById(id);
  const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function build() {
    const style = document.createElement('style');
    style.textContent = `
      #pveil { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: none; align-items: center; justify-content: center; z-index: 30; }
      #pveil.show { display: flex; }
      #pdlg { background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 10px; width: min(640px, 94vw);
        max-height: 94vh; overflow: auto; padding: 18px 22px; box-shadow: 0 8px 30px rgba(0,0,0,.3); }
      #pdlg h3 { margin: 0 0 12px; font-size: 16px; }
      #pdlg .prow { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; margin: 9px 0; }
      #pdlg .plabel { width: 5.5em; color: var(--muted); font-size: 13px; }
      #pdlg label { white-space: nowrap; }
      #pdlg input[type=text], #pdlg input[type=number], #pdlg select { font: inherit; color: var(--fg); background: var(--bg);
        border: 1px solid var(--border); border-radius: 6px; padding: 3px 6px; }
      #pdlg input[type=text].bad { border-color: var(--danger); }
      #pdlg input[type=number] { width: 4.5em; text-align: right; }
      #pdlg .pinfo { color: var(--muted); font-size: 12px; min-height: 1.4em; }
      #pdlg .pinfo.bad { color: var(--danger); }
      #pdlg .pbtns { display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; margin-top: 16px; }
      #pdlg .pbtns .right { display: flex; gap: 8px; }
      #pdlg #pMsg { margin-top: 10px; min-height: 1.4em; font-size: 13px; word-break: break-all; }
      #pdlg #pMsg.bad { color: var(--danger); }
      #pdlg fieldset { border: 1px solid var(--border); border-radius: 8px; margin: 10px 0; padding: 2px 12px 8px; }
      #pdlg legend { color: var(--muted); font-size: 12px; padding: 0 6px; }
    `;
    document.head.appendChild(style);
    const box = document.createElement('div');
    box.id = 'pveil';
    box.innerHTML = `
      <div id="pdlg" role="dialog" aria-label="印刷・PDF保存">
        <h3>印刷・PDF に保存</h3>
        <div class="prow"><span class="plabel">出力先</span>
          <label><input type="radio" name="pMode" value="print"> 印刷する</label>
          <label><input type="radio" name="pMode" value="pdf"> PDF ファイルに保存する</label></div>
        <div class="prow"><span class="plabel">ページ</span>
          <label><input type="radio" name="pRange" value="all"> すべて</label>
          <label><input type="radio" name="pRange" value="some"> 指定</label>
          <input id="pRanges" type="text" size="14" placeholder="例: 1-3,5" spellcheck="false">
          <span id="pCount" class="pinfo"></span></div>
        <div class="pinfo" id="pRangeInfo" style="margin-left:6em"></div>
        <fieldset><legend>用紙と見た目</legend>
          <div class="prow"><span class="plabel">用紙</span>
            <select id="pPaper"><option>A4</option><option>A3</option><option>B5</option><option>B4</option><option>Letter</option></select>
            <label><input type="radio" name="pOri" value="p"> 縦</label>
            <label><input type="radio" name="pOri" value="l"> 横</label>
            <span class="plabel" style="width:auto">余白</span>
            <select id="pMargin"><option>標準</option><option>狭い</option><option>広い</option><option>なし</option></select></div>
          <div class="prow"><span class="plabel">倍率</span>
            <input id="pScale" type="number" min="25" max="200" step="5"> %
            <label><input id="pFit" type="checkbox"> 幅の広い表は、用紙に収まるよう縮小する</label></div>
          <div class="prow"><span class="plabel"></span>
            <label><input id="pBg" type="checkbox"> 背景色を印刷する</label>
            <label><input id="pHf" type="checkbox"> ヘッダーとフッターを付ける（ファイル名・ページ番号）</label></div>
        </fieldset>
        <fieldset id="pPrintOnly"><legend>プリンター</legend>
          <div class="prow"><span class="plabel">プリンター</span><select id="pPrinter" style="max-width:24em"></select></div>
          <div class="prow"><span class="plabel">部数</span><input id="pCopies" type="number" min="1" max="99" step="1">
            <label><input id="pMono" type="checkbox"> 白黒で印刷する</label></div>
        </fieldset>
        <div id="pMsg"></div>
        <div class="pbtns">
          <button id="pPreview" title="この設定の仕上がりを、PDF として開いて確認します">仕上がりを確認（PDF を開く）</button>
          <span class="right"><button id="pRun" class="primary"></button><button id="pClose">閉じる</button></span>
        </div>
      </div>`;
    document.body.appendChild(box);
    return box;
  }

  // ---- 設定の読み書き -------------------------------------------------------------
  let st = { ...DEFAULTS };
  const radio = (name, v) => { document.querySelectorAll(`input[name=${name}]`).forEach(r => { r.checked = r.value === v; }); };
  const radioValue = name => (document.querySelector(`input[name=${name}]:checked`) || {}).value;

  function toForm() {
    radio('pMode', st.mode); radio('pRange', st.rangeAll ? 'all' : 'some'); radio('pOri', st.landscape ? 'l' : 'p');
    $('pRanges').value = st.ranges; $('pPaper').value = st.paper; $('pMargin').value = st.margin;
    $('pScale').value = st.scalePct; $('pFit').checked = st.fit; $('pBg').checked = st.backgrounds; $('pHf').checked = st.headerFooter;
    $('pCopies').value = st.copies; $('pMono').checked = st.mono;
    if (st.printer) $('pPrinter').value = st.printer;
  }
  function fromForm() {
    st = {
      mode: radioValue('pMode'), rangeAll: radioValue('pRange') === 'all', ranges: $('pRanges').value,
      paper: $('pPaper').value, landscape: radioValue('pOri') === 'l', margin: $('pMargin').value,
      scalePct: Math.max(25, Math.min(200, parseInt($('pScale').value, 10) || 100)), fit: $('pFit').checked,
      backgrounds: $('pBg').checked, headerFooter: $('pHf').checked,
      printer: $('pPrinter').value, copies: Math.max(1, Math.min(99, parseInt($('pCopies').value, 10) || 1)), mono: $('pMono').checked,
    };
    return st;
  }

  // ---- 用紙に収める倍率 ---------------------------------------------------------------
  function printableWidthPx(s) {
    const [w, h] = PAPER_IN[s.paper] || PAPER_IN.A4;
    const page = s.landscape ? h : w;
    return Math.max(100, (page - 2 * MARGIN_MM[s.margin] / 25.4) * 96);
  }
  // 本文を、印刷の幅に置いたときに横へはみ出す幅を測る（画面には出さない）
  function measureWidth(layoutPx) {
    const node = cfg.content();
    const keep = node.getAttribute('style');
    node.style.cssText = `${keep || ''};position:fixed;left:0;top:0;width:${layoutPx}px;zoom:1;padding:0;visibility:hidden;overflow:visible;z-index:-1`;
    const w = node.scrollWidth;
    if (keep === null) node.removeAttribute('style'); else node.setAttribute('style', keep);
    return w;
  }
  function options(s) {
    const base = s.scalePct / 100;
    let scale = base;
    if (s.fit) {
      const printable = printableWidthPx(s), layout = printable / base;
      const need = measureWidth(layout);
      if (need > layout + 1) scale = Math.max(0.2, Math.floor((printable / need) * 100) / 100);
    }
    const path = cfg.path ? cfg.path() : null;
    return { paper: s.paper, landscape: s.landscape, margin: s.margin, scale, backgrounds: s.backgrounds,
      header_footer: s.headerFooter, title: cfg.name(), uri: path || '', printer: s.printer, copies: s.copies, mono: s.mono };
  }

  // ---- 表示 ---------------------------------------------------------------------------
  function msg(text, bad) { $('pMsg').textContent = text || ''; $('pMsg').classList.toggle('bad', !!bad); }
  function updateLabels() {
    const print = radioValue('pMode') === 'print';
    $('pPrintOnly').style.display = print ? '' : 'none';
    $('pRun').textContent = print ? '印刷する' : 'PDF を保存…';
    $('pRanges').disabled = radioValue('pRange') === 'all';
  }
  async function checkRanges() {
    const some = radioValue('pRange') === 'some';
    $('pRanges').classList.remove('bad'); $('pRangeInfo').textContent = ''; $('pRangeInfo').classList.remove('bad');
    if (!some) return { ok: true, ranges: '' };
    const r = await cfg.api.print_check_ranges($('pRanges').value, total || 0);
    if (!r.ok) { $('pRanges').classList.add('bad'); $('pRangeInfo').textContent = r.error; $('pRangeInfo').classList.add('bad'); }
    else if (!r.ranges) { $('pRangeInfo').textContent = 'ページを指定してください（例: 1-3,5）'; return { ok: false }; }
    else $('pRangeInfo').textContent = `${r.ranges} ページを出力します`;
    return r;
  }
  function scheduleCount() {
    clearTimeout(countTimer);
    $('pCount').textContent = 'ページ数を調べています…';
    countTimer = setTimeout(refreshCount, 500);
  }
  async function refreshCount() {
    const seq = ++countSeq;
    fromForm();
    const r = await cfg.api.print_count(options(st));
    if (seq !== countSeq) return;
    if (r.ok) { total = r.pages; $('pCount').textContent = `全 ${total} ページ`; $('pCount').classList.remove('bad'); }
    else { $('pCount').textContent = 'ページ数を調べられません'; $('pCount').classList.add('bad'); }
    checkRanges();
  }

  // ---- 実行 ---------------------------------------------------------------------------
  function setBusy(b) { busy = b; $('pRun').disabled = b; $('pPreview').disabled = b; }
  async function run(kind) {      // kind: 'run' | 'preview'
    if (busy) return;
    fromForm(); msg('');
    const rr = await checkRanges();
    if (!rr.ok) { msg('ページの指定を確かめてください', true); return; }
    const opts = options(st);
    setBusy(true);
    try {
      let r;
      if (kind === 'preview') {
        msg('仕上がりの PDF を作っています…');
        r = await cfg.api.print_preview(opts, rr.ranges);
        if (r.ok) msg('PDF を開きました（確認用。保存はされません）');
      } else if (st.mode === 'pdf') {
        const path = await cfg.api.pick_pdf_path(cfg.name().replace(/\.[^.\\/]+$/, '') + '.pdf', cfg.path && cfg.path() ? cfg.path().replace(/\\[^\\]*$/, '') : null);
        if (!path) { msg(''); return; }
        msg('PDF を作っています…');
        r = await cfg.api.print_save_pdf(opts, rr.ranges, path);
        if (r.ok) { lastPdf = path; msg(`保存しました: ${path}`); if (cfg.notify) cfg.notify('PDF を保存しました'); }
      } else {
        msg('印刷を依頼しています…');
        r = await cfg.api.print_send(opts, rr.ranges);
        if (r.ok) { msg(`印刷を依頼しました（${st.printer || '既定のプリンター'}）`); if (cfg.notify) cfg.notify('印刷を依頼しました'); }
      }
      if (!r.ok) msg(r.error, true);
    } catch (e) { msg(String(e), true); }
    finally { setBusy(false); persist(); }
  }
  // ページ範囲は覚えない（前回の指定が残っていると、気づかずに一部だけ出力してしまうため）
  function persist() {
    const { rangeAll, ranges, ...keep } = st;
    try { cfg.api.set_print_prefs(keep); } catch (e) { /* 保存できなくても印刷は続ける */ }
  }

  // ---- 開く・閉じる ----------------------------------------------------------------------
  async function open() {
    if (!cfg.content() || !cfg.hasDocument()) { if (cfg.notify) cfg.notify('印刷する文書を開いてください', true); return; }
    $('pveil').classList.add('show');
    msg(''); lastPdf = null; total = 0;
    toForm(); updateLabels();
    restoreFns = [];
    if (cfg.beforePrint) restoreFns.push(await cfg.beforePrint());     // 暗い配色の図を、紙向けの配色に描き直す等
    scheduleCount();
  }
  async function close() {
    if (busy) return;
    clearTimeout(countTimer); countSeq++;
    fromForm(); persist();
    $('pveil').classList.remove('show');
    for (const f of restoreFns.reverse()) { try { if (f) await f(); } catch (e) { /* 画面を戻せなくても閉じる */ } }
    restoreFns = [];
  }
  const isOpen = () => $('pveil').classList.contains('show');

  async function init(c) {
    cfg = c; el = build();
    try {
      const saved = await cfg.api.get_print_prefs() || {};
      delete saved.rangeAll; delete saved.ranges;
      Object.assign(DEFAULTS, saved);
    } catch (e) { /* 初回は無い */ }
    st = { ...DEFAULTS };
    try {
      const p = await cfg.api.print_printers();
      for (const n of p.printers) $('pPrinter').add(new Option(n + (n === p.default ? '（既定）' : ''), n));
      if (!st.printer || !p.printers.includes(st.printer)) st.printer = p.default || '';
      if (!p.printers.length) { $('pPrinter').add(new Option('（プリンターがありません）', '')); }
    } catch (e) { $('pPrinter').add(new Option('（取得できません）', '')); }
    document.querySelectorAll('#pdlg input[name=pMode]').forEach(r => r.addEventListener('change', () => { updateLabels(); }));
    document.querySelectorAll('#pdlg input[name=pRange]').forEach(r => r.addEventListener('change', () => { updateLabels(); checkRanges(); }));
    $('pRanges').addEventListener('input', checkRanges);
    for (const id of ['pPaper', 'pMargin', 'pScale', 'pFit']) $(id).addEventListener('change', scheduleCount);
    document.querySelectorAll('#pdlg input[name=pOri]').forEach(r => r.addEventListener('change', scheduleCount));
    $('pRun').onclick = () => run('run'); $('pPreview').onclick = () => run('preview'); $('pClose').onclick = close;
    $('pveil').addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === 'Enter' && e.target.tagName !== 'BUTTON' && e.target.tagName !== 'SELECT') { e.preventDefault(); run('run'); }
    });
  }

  return { init, open, close, isOpen, currentOptions: () => options(fromForm()) };   // 検証用
})();
