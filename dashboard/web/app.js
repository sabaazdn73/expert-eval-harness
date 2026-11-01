// Task pipeline dashboard. One file for both modes:
//  - local: served by dashboard/server.py on 127.0.0.1 (edit, upload, sign, run, export)
//  - public: a static copy on a website reads data.json (read only)
(function () {
  'use strict';
  const STATUS = { not_started: 'Not started', in_progress: 'In progress', waiting_for_human: 'Waiting for the human', done: 'Done' };
  const OWNER_HINT = { human: 'H', human_signs: 'H', ai_check: 'A+H', ai: 'A' };
  let S = null, LOCAL = false, tab = 'projects', current = null;

  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = (sel) => document.querySelector(sel);
  const pct = (x) => (x == null ? '—' : Math.round(x * 100) + ' %');

  async function api(path, body, headers) {
    const r = await fetch(path, { method: 'POST', headers: Object.assign({ 'X-Dashboard': '1', 'Content-Type': 'application/json' }, headers || {}), body: body instanceof Blob ? body : JSON.stringify(body || {}) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.status);
    return j;
  }

  async function load() {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (r.ok && (r.headers.get('content-type') || '').includes('json')) { S = await r.json(); LOCAL = S.mode === 'local'; }
    } catch (e) { /* public copy */ }
    if (!S) {
      const r = await fetch('data.json', { cache: 'no-store' });
      S = await r.json(); LOCAL = false;
    }
    $('#mode').textContent = LOCAL ? 'Local workspace' : 'Public view, read only';
    $('#mode').className = 'badge' + (LOCAL ? ' local' : '');
    $('#foot').innerHTML = LOCAL
      ? `Data folder: <span class="mono">${esc(S.data_dir)}</span> · harness: <span class="mono">${esc(S.harness)}</span> · API key in the server's shell: <b>${S.key_set ? 'set' : 'not set'}</b>. Nothing leaves this computer until you press Export.`
      : `Updated ${esc((S.generated || '').replace('T', ' '))}. Prompts, answer keys and traps are not published: a published task is a contaminated task.`;
    render();
  }

  function stagesOf(p) { return S.process.stages.map((s) => ({ ...s, st: (p.stages || {})[s.id] || { status: 'not_started' } })); }
  function ownerChip(o) { return `<span class="own own-${o}" title="${esc(S.process.owners[o])}">${esc(S.process.owners[o])}</span>`; }

  function strip(p) {
    return `<div class="strip" aria-hidden="true">${stagesOf(p).map((s) => `<i class="st-${s.st.status}" title="${s.n}. ${esc(s.title)}: ${esc(STATUS[s.st.status])}"></i>`).join('')}</div>`;
  }
  function legend() {
    return `<div class="legend"><span><i class="sw st-done"></i>Done</span><span><i class="sw st-in_progress"></i>In progress</span><span><i class="sw st-waiting_for_human"></i>Waiting for the human</span><span><i class="sw"></i>Not started</span></div>`;
  }
  function bestRun(p) {
    const r = (p.runs || []).slice().sort((a, b) => String(a.date).localeCompare(String(b.date))).pop();
    if (!r) return '';
    return r.results.map((x) => `${esc(x.model)}: ${x.c}/${x.n} passed${x.mean_score != null ? `, mean ${x.mean_score}/${x.max_score}` : ''}`).join(' · ');
  }

  // ---------- views ----------
  function viewProjects() {
    const ps = S.projects || [];
    let h = `<h2>Tasks</h2><p class="muted">Each strip is the nine stages of the pipeline. Red is a stage waiting for the human.</p>${legend()}`;
    if (LOCAL) h += `<div class="card"><h3>New task</h3><div class="controls">
      <input type="text" id="np-id" placeholder="id, e.g. p8-ramp-slab" aria-label="Task id">
      <input type="text" id="np-title" placeholder="Title" aria-label="Title">
      <input type="text" id="np-structure" placeholder="Structure, e.g. Public parking structure" aria-label="Structure">
      <input type="text" id="np-dir" placeholder="Task folder (blank: harness tasks/<id>)" aria-label="Task folder" size="34">
      <button class="btn primary" data-act="new">Create</button></div></div>`;
    h += `<div class="grid">${ps.map((p) => {
      const done = stagesOf(p).filter((s) => s.st.status === 'done').length;
      const waiting = stagesOf(p).filter((s) => s.st.status === 'waiting_for_human').map((s) => s.n);
      return `<button class="card pcard" data-open="${esc(p.id)}">
        <p class="ptitle">${esc(p.title)}</p>
        <p class="muted small">${esc(p.structure || '')}${p.domain ? ' · ' + esc(p.domain) : ''}${LOCAL ? (p.public ? ' · public' : ' · private') : ''}</p>
        ${strip(p)}
        <p class="small">${done} of 9 stages done${waiting.length ? ` · <span class="no">human needed at stage ${waiting.join(', ')}</span>` : ''}</p>
        <p class="small muted">${bestRun(p) || 'No model runs yet'}</p></button>`;
    }).join('') || '<p class="muted">No tasks yet.</p>'}</div>`;
    return h;
  }

  function viewPipeline() {
    const st = S.process.stages;
    const human = st.filter((s) => s.gate).map((s) => s.n).join(', ');
    return `<h2>Nine stages, three human gates</h2>
      <p class="muted">The human works where the truth is outside the model, or where an AI error would run in the same direction as the thing being tested. Gates (stages ${human}) cannot pass without a signature. Everything else is done by AI and checked at one decisive point.</p>
      <div class="legend">${Object.keys(S.process.owners).map((o) => ownerChip(o)).join('')}</div>
      <ol class="stages">${st.map((s) => `<li class="card stage"><span class="num">${s.n}</span><div>
        <div class="stage-h"><b>${esc(s.title)}</b>${ownerChip(s.owner)}${s.gate ? '<span class="gate">HUMAN GATE</span>' : ''}</div>
        <div class="two"><p class="who a"><span class="lab">AI</span>${esc(s.ai)}</p><p class="who h"><span class="lab">Human</span>${esc(s.human)}</p></div>
        <p class="small muted">Output: ${esc(s.output)}</p></div></li>`).join('')}</ol>`;
  }

  function viewGrader() {
    return `<h2>What the grader is given, for every task</h2>
      <p class="muted">A grader can only be as good as what it receives. These are the parts of a task package; the dashboard checks each one in the task folder.</p>
      <div class="card scroll"><table><tr><th>Part</th><th>Required</th><th>What it contains</th></tr>
      ${S.process.grader_package.map((g) => `<tr><td><b>${esc(g.item)}</b></td><td>${g.required ? 'Yes' : '<span class="opt">Optional</span>'}</td><td>${esc(g.what)}</td></tr>`).join('')}</table></div>
      <h3>Basis-of-design sheet (signed by the human at stage 2)</h3>
      <div class="card"><ul>${S.process.basis_fields.map(([, l]) => `<li>${esc(l)}</li>`).join('')}</ul></div>`;
  }

  function stageBlock(p, s) {
    const st = s.st;
    let h = `<li class="card stage"><span class="num st-${st.status}">${s.n}</span><div>
      <div class="stage-h"><b>${esc(s.title)}</b>${ownerChip(s.owner)}${s.gate ? '<span class="gate">HUMAN GATE</span>' : ''}
      <span class="status st-${st.status}">${esc(STATUS[st.status])}</span>${st.date ? `<span class="small muted">${esc(st.date)}</span>` : ''}
      ${st.signed_by ? `<span class="small ok">Signed: ${esc(st.signed_by)}</span>` : ''}${st.minutes ? `<span class="small muted">${esc(st.minutes)} min human time</span>` : ''}</div>
      <div class="two"><p class="who a"><span class="lab">AI</span>${esc(s.ai)}</p><p class="who h"><span class="lab">Human</span>${esc(s.human)}</p></div>`;
    if (LOCAL && st.note) h += `<p class="small"><b>Note:</b> ${esc(st.note)}</p>`;
    if (LOCAL) h += `<div class="controls">
      <select data-stage-status="${s.id}" aria-label="Status of stage ${s.n}">${Object.keys(STATUS).map((k) => `<option value="${k}"${k === st.status ? ' selected' : ''}>${STATUS[k]}</option>`).join('')}</select>
      <input type="number" min="0" step="5" data-stage-min="${s.id}" value="${esc(st.minutes || '')}" placeholder="minutes" aria-label="Human minutes" style="width:96px">
      <input type="text" data-stage-note="${s.id}" value="" placeholder="note (private)" aria-label="Note" size="28">
      ${s.gate ? `<input type="text" data-stage-sign="${s.id}" placeholder="sign with your name" aria-label="Signature" size="18">` : ''}
      <button class="btn" data-act="stage" data-stage="${s.id}">Save</button></div>`;
    return h + '</div></li>';
  }

  function viewProject(p) {
    const b = p.basis || {};
    let h = `<button class="back" data-act="home">← All tasks</button>
      <h2 style="margin-top:4px">${esc(p.title)}</h2><p class="muted">${esc(p.structure || '')}${p.domain ? ' · ' + esc(p.domain) : ''}</p>
      ${p.summary || p.public_summary ? `<p>${esc(p.summary || p.public_summary)}</p>` : ''}${strip(p)}${legend()}`;
    if (LOCAL) h += `<div class="card"><div class="controls">
      <label class="small"><input type="checkbox" data-meta-public ${p.public ? 'checked' : ''}> Show this task on the public page (progress and results only)</label>
      <input type="text" data-meta-summary value="${esc(p.public_summary || '')}" placeholder="One public sentence about the task" size="60" aria-label="Public summary">
      <button class="btn" data-act="meta">Save</button></div><p class="small muted mono">${esc(p.task_dir || '')}</p></div>`;

    h += `<h3>Design basis</h3><div class="card">`;
    if (LOCAL) {
      h += `<div class="kv">${S.process.basis_fields.map(([k, l]) => `<dt>${esc(l)}</dt><dd><input type="text" data-basis="${k}" value="${esc(b[k] || '')}" style="width:100%"></dd>`).join('')}
        <dt>Signed by</dt><dd><input type="text" data-basis="signed_by" value="${esc(b.signed_by || '')}" placeholder="your name, after you have read the sources"></dd></div>
        <div class="controls"><button class="btn" data-act="basis">Save basis</button>${b.signed_at ? `<span class="small ok">Signed ${esc(b.signed_at.replace('T', ' '))}</span>` : ''}</div>`;
    } else {
      h += `<dl class="kv">${[['location', 'Location'], ['adopted_code', 'Adopted code'], ['standards', 'Standards'], ['amendments', 'Local amendments']].filter(([k]) => b[k]).map(([k, l]) => `<dt>${l}</dt><dd>${esc(b[k])}</dd>`).join('') || '<dd class="muted">Not published yet.</dd>'}</dl>`;
    }
    h += `</div><h3>Stages</h3><ol class="stages">${stagesOf(p).map((s) => stageBlock(p, s)).join('')}</ol>`;

    h += `<h3>Grader package</h3><div class="card scroll"><table><tr><th>Part</th><th>In the task folder</th>${LOCAL ? '<th>What it must contain</th>' : ''}</tr>
      ${(p.package || []).map((x) => `<tr><td><b>${esc(x.item)}</b>${x.required ? '' : ' <span class="opt">(optional)</span>'}</td><td>${x.present === null ? '<span class="opt">Not used (graded by the answer key)</span>' : x.present ? '<span class="ok">Present</span>' : (x.required ? '<span class="no">Missing</span>' : '<span class="opt">Not used</span>')}</td>${LOCAL ? `<td class="small muted">${esc(x.what)}</td>` : ''}</tr>`).join('')}</table></div>`;

    if (LOCAL) {
      h += `<h3>Accepted alternatives and lures</h3><div class="card two">
        <div><p class="small muted">One defensible assumption per line, with the values it gives.</p><textarea data-list="alternatives">${esc((p.alternatives || []).join('\n'))}</textarea><button class="btn" data-act="list" data-field="alternatives">Save</button></div>
        <div><p class="small muted">One wrong answer the task is built to catch per line, with its value.</p><textarea data-list="lures">${esc((p.lures || []).join('\n'))}</textarea><button class="btn" data-act="list" data-field="lures">Save</button></div></div>
        <h3>Files</h3><div class="card">
        <div class="controls"><label class="small">Upload as <select id="up-kind"><option value="input">input file (listed in task.json)</option><option value="prompt">prompt (prompt.md)</option><option value="key">answer key (key.md)</option><option value="golden">golden solution file</option><option value="reference">reference note</option></select></label>
        <input type="file" id="up-file" multiple aria-label="Choose files"><button class="btn primary" data-act="upload">Upload</button></div>
        <div class="drop" id="drop">or drop files here</div>
        <div class="scroll"><table><tr><th>File</th><th class="num-c">Size</th><th>Modified</th></tr>${(p.files || []).map((f) => `<tr><td class="mono small">${esc(f.path)}</td><td class="num-c small">${(f.bytes / 1024).toFixed(1)} kB</td><td class="small muted">${esc(f.modified.replace('T', ' '))}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">No files yet.</td></tr>'}</table></div></div>`;
    }

    h += `<h3>Model runs</h3><div class="card scroll">`;
    if ((p.runs || []).length) {
      h += `<table><tr><th>Run</th><th>Setup</th><th>Model</th><th class="num-c">Passed</th><th>Pass rate</th><th class="num-c">pass@k</th><th class="num-c">pass^k</th><th class="num-c">Mean score</th></tr>
        ${p.runs.map((r) => r.results.map((x, i) => `<tr>${i === 0 ? `<td rowspan="${r.results.length}" class="mono small">${esc(r.run_id)}<br><span class="muted">${esc((r.date || '').slice(0, 10))}</span></td><td rowspan="${r.results.length}" class="small">k = ${r.k}${r.model_library ? ', model has the code library' : ''}${r.with_refs ? ', with references' : ''}</td>` : ''}
        <td class="small">${esc(x.model)}</td><td class="num-c">${x.c}/${x.n}</td><td><div class="bar" title="${pct(x.pass_rate)}"><i style="width:${Math.round(x.pass_rate * 100)}%"></i></div></td>
        <td class="num-c">${pct(x.pass_at_k)}</td><td class="num-c">${pct(x.pass_hat_k)}</td><td class="num-c">${x.mean_score != null ? `${x.mean_score}/${x.max_score}` : '—'}</td></tr>`).join('')).join('')}</table>`;
    } else h += '<p class="muted">No runs yet.</p>';
    if (LOCAL) h += `<div class="controls" style="margin-top:10px">
      <label class="small"><input type="checkbox" data-model value="claude-haiku-5-5" checked> Haiku 5.5</label>
      <label class="small"><input type="checkbox" data-model value="claude-sonnet-5-5" checked> Sonnet 5.5</label>
      <label class="small"><input type="checkbox" data-model value="claude-opus-5-5"> Opus 5.5</label>
      <label class="small">k <input type="number" id="run-k" value="3" min="1" max="10" style="width:56px"></label>
      <label class="small">cap <input type="number" id="run-cap" value="30" min="1" style="width:64px"></label>
      <label class="small"><input type="checkbox" id="run-jt"> equipped grader</label>
      <label class="small"><input type="checkbox" id="run-ml"> model gets code library</label>
      <input type="text" id="run-lib" placeholder="code library folder (optional)" size="26" aria-label="Code library folder">
      <button class="btn primary" data-act="run">Start run</button>
      ${S.key_set ? '' : '<span class="small no">No API key in the server\'s shell: start it after export ANTHROPIC_API_KEY=...</span>'}</div><pre class="log" id="runlog" hidden></pre>`;
    h += '</div>';

    if (LOCAL) h += `<h3>Decision log</h3><div class="card scroll"><table><tr><th>Date</th><th>Stage</th><th>Decision</th><th>Reason</th></tr>
      ${(p.log || []).slice().reverse().map((l) => `<tr><td class="small muted">${esc((l.date || '').replace('T', ' '))}</td><td class="small">${esc(l.stage || '')}</td><td class="small">${esc(l.decision)}</td><td class="small muted">${esc(l.reason || '')}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">Empty.</td></tr>'}</table>
      <div class="controls"><input type="text" id="lg-stage" placeholder="stage, e.g. s3" size="8"><input type="text" id="lg-dec" placeholder="decision" size="34"><input type="text" id="lg-why" placeholder="reason and evidence" size="34"><button class="btn" data-act="log">Add</button></div></div>
      <div class="controls"><input type="text" id="site-dir" placeholder="website folder for data.json (optional), e.g. ~/tnega/frontend/public/eval" size="52"><button class="btn" data-act="export">Export public data.json</button></div>`;
    return h;
  }

  function render() {
    document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab && !current)));
    const v = $('#view');
    if (current) {
      const p = (S.projects || []).find((x) => x.id === current);
      v.innerHTML = p ? viewProject(p) : '<p>Not found.</p>';
      if (LOCAL) bindDrop(p);
    } else v.innerHTML = tab === 'pipeline' ? viewPipeline() : tab === 'grader' ? viewGrader() : viewProjects();
  }

  function replaceProject(p) { S.projects = S.projects.map((x) => (x.id === p.id ? p : x)); render(); }
  function flash(msg) { alertBox(msg); }
  function alertBox(msg) { const n = document.createElement('p'); n.className = 'notice'; n.textContent = msg; $('#view').prepend(n); setTimeout(() => n.remove(), 6000); }

  async function upload(p, files) {
    const kind = $('#up-kind').value;
    for (const f of files) {
      try { replaceProject(await api(`/api/project/${p.id}/upload`, f, { 'Content-Type': 'application/octet-stream', 'X-Kind': kind, 'X-Filename': encodeURIComponent(f.name) })); }
      catch (e) { flash(`${f.name}: ${e.message}`); }
    }
  }
  function bindDrop(p) {
    const d = $('#drop'); if (!d || !p) return;
    d.addEventListener('dragover', (e) => { e.preventDefault(); d.classList.add('over'); });
    d.addEventListener('dragleave', () => d.classList.remove('over'));
    d.addEventListener('drop', (e) => { e.preventDefault(); d.classList.remove('over'); upload(p, [...e.dataTransfer.files]); });
  }

  async function pollLog(name) {
    const pre = $('#runlog'); if (!pre) return;
    pre.hidden = false;
    const r = await fetch(`/api/log/${encodeURIComponent(name)}`).then((x) => x.json());
    pre.textContent = r.log + (r.status === 'running' ? '\n…' : `\n[${r.status}]`);
    pre.scrollTop = pre.scrollHeight;
    if (r.status === 'running') setTimeout(() => pollLog(name), 3000); else load();
  }

  document.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-tab],[data-open],[data-act]');
    if (!t) return;
    if (t.dataset.tab) { tab = t.dataset.tab; current = null; return render(); }
    if (t.dataset.open) { current = t.dataset.open; window.scrollTo(0, 0); return render(); }
    const act = t.dataset.act, p = (S.projects || []).find((x) => x.id === current);
    try {
      if (act === 'home') { current = null; return render(); }
      if (act === 'new') {
        const np = await api('/api/project', { id: $('#np-id').value.trim(), title: $('#np-title').value.trim(), structure: $('#np-structure').value.trim(), task_dir: $('#np-dir').value.trim() || undefined });
        S.projects.push(np); current = np.id; return render();
      }
      if (act === 'stage') {
        const sid = t.dataset.stage, body = { stage: sid, status: $(`[data-stage-status="${sid}"]`).value };
        const note = $(`[data-stage-note="${sid}"]`).value.trim(); if (note) body.note = note;
        const mins = $(`[data-stage-min="${sid}"]`).value; if (mins) body.minutes = Number(mins);
        const sign = $(`[data-stage-sign="${sid}"]`); if (sign && sign.value.trim()) body.sign = sign.value.trim();
        const stage = S.process.stages.find((s) => s.id === sid);
        if (stage.gate && body.status === 'done' && !body.sign && !(p.stages[sid] || {}).signed_by) return flash(`Stage ${stage.n} is a human gate: sign it before marking it done.`);
        return replaceProject(await api(`/api/project/${p.id}/stage`, body));
      }
      if (act === 'basis') { const b = {}; document.querySelectorAll('[data-basis]').forEach((i) => { b[i.dataset.basis] = i.value; }); return replaceProject(await api(`/api/project/${p.id}/basis`, b)); }
      if (act === 'meta') return replaceProject(await api(`/api/project/${p.id}/meta`, { public: $('[data-meta-public]').checked, public_summary: $('[data-meta-summary]').value }));
      if (act === 'list') { const f = t.dataset.field; return replaceProject(await api(`/api/project/${p.id}/list`, { field: f, items: $(`[data-list="${f}"]`).value.split('\n') })); }
      if (act === 'upload') return upload(p, [...$('#up-file').files]);
      if (act === 'log') return replaceProject(await api(`/api/project/${p.id}/log`, { stage: $('#lg-stage').value, decision: $('#lg-dec').value, reason: $('#lg-why').value }));
      if (act === 'run') {
        const models = [...document.querySelectorAll('[data-model]:checked')].map((i) => i.value);
        const r = await api('/api/run', { project: p.id, models, k: Number($('#run-k').value), max_calls: Number($('#run-cap').value), judge_tools: $('#run-jt').checked, model_library: $('#run-ml').checked, ref_lib: $('#run-lib').value.trim() || undefined });
        return pollLog(r.name);
      }
      if (act === 'export') { const r = await api('/api/export', { site_dir: $('#site-dir').value.trim() || undefined }); return flash(`Wrote ${r.written} (${r.projects} public tasks).`); }
    } catch (err) { flash(err.message); }
  });

  $('#theme').addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('eval-theme', root.dataset.theme); } catch (e) { /* optional */ }
  });
  try { const t = localStorage.getItem('eval-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* optional */ }
  load();
})();
