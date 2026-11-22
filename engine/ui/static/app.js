/* Editor de montajes: una sola página sin dependencias. Habla con engine/ui/server.py. */
'use strict';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = t => { t = Math.max(0, t); return Math.floor(t / 60) + ':' + (t % 60).toFixed(1).padStart(4, '0'); };
const clone = o => JSON.parse(JSON.stringify(o));
const S = { name: null, data: null, tab: 'clips', sel: null, dirty: false, clip: null, kills: null, poll: null, busy: false, previews: [] };
const COLORS = ['#7fb4ff', '#c79bff', '#5fd08a', '#ff9d6c', '#6fd6e0', '#f08fc0', '#b9d36a', '#9aa7ff'];
const TRANS = [['', 'La que toque en la rotación'], ['whip_lr', 'Barrido a la derecha'], ['whip_rl', 'Barrido a la izquierda'], ['light', 'Destello de luz'], ['zoom', 'Zoom'], ['mega', 'Golpe grande (para un drop)']];

async function api(method, url, body, raw) {
  const r = await fetch(url, { method, headers: raw ? {} : { 'Content-Type': 'application/json' }, body: raw ? body : (body === undefined ? undefined : JSON.stringify(body)) });
  const d = await r.json().catch(() => ({ error: 'El servidor no respondió.' }));
  if (!r.ok) throw new Error(d.error || 'Algo falló.');
  return d;
}
function toast(msg, err) { const t = $('#toast'); t.textContent = msg; t.className = 'on' + (err ? ' err' : ''); clearTimeout(toast.h); toast.h = setTimeout(() => t.className = '', err ? 6000 : 2600); }
const guard = fn => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, true); } };

/* ---------- navegación ---------- */
window.addEventListener('hashchange', route);
window.addEventListener('beforeunload', e => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });
async function route() {
  clearInterval(S.poll);
  const m = location.hash.match(/^#\/p\/([a-z0-9_]+)(?:\/(\w+))?/);
  if (!m) { S.name = null; $('#crumbs').innerHTML = ''; return home(); }
  S.tab = m[2] || S.tab || 'clips';
  if (S.name !== m[1] || !S.data) { S.name = m[1]; S.sel = null; S.dirty = false; S.clip = null; S.kills = null; await load(); }
  else { draw(); watch(); }
}
const load = guard(async () => { S.data = await api('GET', '/api/projects/' + S.name); S.edit = S.data.edit ? clone(S.data.edit) : null; draw(); watch(); });
function go(tab) { location.hash = `#/p/${S.name}/${tab}`; }

/* ---------- inicio ---------- */
const home = guard(async () => {
  const ps = await api('GET', '/api/projects');
  const kind = { edit: ['ok', 'editable'], plan: ['', 'plan.py'], nuevo: ['warn', 'sin armar'] };
  $('#app').innerHTML = `
    <div class="row spread" style="margin-bottom:24px">
      <div><h1>Tus proyectos</h1><p class="muted">Cada proyecto es un edit: sus clips, su canción y su plan.</p></div>
      <form id="new" class="row"><div class="field"><label for="nn">Nombre del proyecto nuevo</label>
        <input id="nn" type="text" placeholder="mi_edit" pattern="[a-z0-9][a-z0-9_]*" required style="width:220px"></div>
        <button class="primary" style="align-self:end">Crear proyecto</button></form>
    </div>
    ${ps.length ? `<div class="projects">${ps.map(p => `<a class="pcard" href="#/p/${p.name}">
        <strong>${esc(p.name.replace(/_/g, ' '))}</strong>
        <span class="muted small">${p.clips} clips</span>
        <div class="row" style="margin-top:10px;gap:6px"><span class="tag ${kind[p.kind][0]}">${kind[p.kind][1]}</span>
        ${p.final ? '<span class="tag ok">video final</span>' : p.draft ? '<span class="tag">borrador</span>' : ''}</div></a>`).join('')}</div>`
      : `<div class="empty"><h2>Todavía no hay proyectos</h2><p>Creá uno arriba, subí tus clips y una canción, y el editor arma el primer borrador.</p></div>`}`;
  $('#new').onsubmit = guard(async e => { e.preventDefault(); const n = $('#nn').value.trim(); await api('POST', '/api/projects', { name: n }); location.hash = '#/p/' + n; });
});

/* ---------- proyecto ---------- */
const TABS = [['clips', 'Clips y kills'], ['editor', 'Editor'], ['estilo', 'Estilo'], ['render', 'Render']];
function draw() {
  const d = S.data; if (!d) return;
  $('#crumbs').innerHTML = `<span>/</span><b>${esc(d.name.replace(/_/g, ' '))}</b>${S.dirty ? '<span class="tag warn">cambios sin guardar</span>' : ''}`;
  $('#app').innerHTML = `<div class="row spread"><h1>${esc((S.edit?.song?.title || d.name).replace(/_/g, ' '))}</h1>
      <span class="muted">${d.timeline ? fmt(d.timeline.TOTAL) + ' de video, ' + d.timeline.kills.length + ' kills' : ''}</span></div>
    <div class="steps" role="tablist">${TABS.map(([k, l], i) => `<button role="tab" aria-selected="${S.tab === k}" data-tab="${k}"><span class="n">${i + 1}</span>${l}</button>`).join('')}</div>
    <section id="view"></section>`;
  document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => go(b.dataset.tab));
  ({ clips: viewClips, editor: viewEditor, estilo: viewStyle, render: viewRender }[S.tab] || viewClips)();
}
function watch() {
  clearInterval(S.poll);
  S.poll = setInterval(async () => {
    if (!S.name) return;
    let st; try { st = await api('GET', `/api/projects/${S.name}/state`); } catch { return; }
    const was = S.data.job?.running; S.data.job = st.job; S.data.status = st.status;
    if (was && !st.job?.running) { await load(); toast(st.job.code === 0 ? 'Tarea terminada.' : 'La tarea falló: mirá el detalle.', st.job.code !== 0); return; }
    if (S.tab === 'render') paintRender(); else if (st.job?.running) paintJob();
  }, 1200);
}
const runTask = guard(async (task, args) => { S.data.job = await api('POST', `/api/projects/${S.name}/run`, { task, args }); draw(); });
function jobBox() {
  const j = S.data.job; if (!j || (!j.running && j.code === 0)) return '<div id="job"></div>';
  const names = { auto: 'Analizando y armando el edit', shots: 'Recalculando disparos', draft: 'Renderizando el borrador', final: 'Renderizando el video final', preview: 'Renderizando vistas previas', shorts: 'Armando shorts' };
  return `<div id="job" class="banner ${j.running ? 'warn' : 'err'}"><strong>${j.running ? (names[j.task] || j.task) + '…' : 'La última tarea falló'}</strong>
    <span class="muted small"> ${j.running ? Math.round(j.elapsed) + ' s' : ''}</span><pre class="report" style="margin-top:8px;max-height:140px">${esc((j.log || '').split('\n').slice(-8).join('\n'))}</pre></div>`;
}
function paintJob() { const el = $('#job'); if (el) el.outerHTML = jobBox(); }

/* ---------- 1. clips y kills ---------- */
function viewClips() {
  const d = S.data, v = $('#view');
  if (!d.clips.length) {
    v.innerHTML = `<div class="stack">${jobBox()}<div class="panel"><h2>Subí tus clips y una canción</h2>
      <p class="muted" style="margin:4px 0 16px">Clips en .mp4 (los originales no se modifican) y una canción en .mp3, .wav, .m4a o .flac. Opcional: logo.png.</p>
      <div class="drop" id="drop"><p>Arrastrá los archivos acá</p><p style="margin-top:8px"><label class="btn" style="display:inline-block;color:var(--text);cursor:pointer">Elegir archivos<input id="pick" type="file" multiple accept=".mp4,.mp3,.wav,.m4a,.flac,.png" hidden></label></p></div>
      <ul class="files" id="ups">${d.uploads.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
      <div class="row" style="margin-top:20px"><button class="primary" id="go" ${d.uploads.some(f => /\.mp4$/i.test(f)) && d.uploads.some(f => /\.(mp3|wav|m4a|flac)$/i.test(f)) && !d.job?.running ? '' : 'disabled'}>Analizar y armar el primer edit</button>
      <span class="muted small">Lee el killfeed de cada clip, analiza la canción y elige las mejores plays. Tarda unos minutos.</span></div></div></div>`;
    const drop = $('#drop'), send = guard(async files => {
      for (const f of files) { const li = document.createElement('li'); li.textContent = f.name + ' (subiendo…)'; $('#ups').append(li);
        await api('PUT', `/api/projects/${S.name}/upload?name=${encodeURIComponent(f.name)}`, f, true); li.textContent = f.name; }
      await load();
    });
    drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); }; drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); send([...e.dataTransfer.files]); };
    $('#pick').onchange = e => send([...e.target.files]); $('#go').onclick = () => runTask('auto');
    return;
  }
  if (!S.kills) S.kills = Object.fromEntries(d.clips.map(c => [c.clip, c.kills.map(k => ({ ...k }))]));
  const used = new Set((d.timeline?.segments || []).map(s => s.clip));
  const doubts = d.clips.reduce((n, c) => n + S.kills[c.clip].filter(k => k.conf !== null && k.conf < 0.6).length, 0);
  if (S.clip === null) S.clip = (d.clips.find(c => S.kills[c.clip].some(k => k.conf !== null && k.conf < 0.6)) || d.clips[0]).clip;
  v.innerHTML = `<div class="stack">${jobBox()}
    ${d.kind === 'nuevo' ? `<div class="banner warn row spread"><span>Los clips están analizados pero el proyecto todavía no tiene un edit armado.</span><button class="primary" id="auto">Armar el edit automáticamente</button></div>` : ''}
    <div class="clips"><div class="panel tight" style="padding:0">
      <div class="row spread" style="padding:12px 16px;border-bottom:1px solid var(--line)"><div><h2>${d.clips.length} clips</h2>
        <p class="muted small">${doubts ? `${doubts} kills dudosas para mirar (en naranja)` : 'Sin kills dudosas'}. Elegí un clip para verlo.</p></div>
        <button id="savek" class="primary" ${S.killsDirty ? '' : 'disabled'}>Guardar kills corregidas</button></div>
      <div>${d.clips.map(c => `<div class="cliprow ${c.clip === S.clip ? 'sel' : ''}" data-clip="${c.clip}">
          <span class="id">c${c.clip}</span>
          <span class="kills">${S.kills[c.clip].length ? S.kills[c.clip].map((k, i) => `<span class="k ${k.conf !== null && k.conf < 0.6 ? 'doubt' : ''}" title="${esc(k.why || 'agregada a mano')}"><a href="#" data-seek="${c.clip}:${k.t}">${k.t.toFixed(2)}</a><button aria-label="Quitar la kill de ${k.t.toFixed(2)} s" data-del="${c.clip}:${i}">×</button></span>`).join('') : `<span class="muted small">${c.sin_killfeed ? 'killfeed no legible: revisar el clip entero' : 'sin kills'}</span>`}</span>
          <span class="row" style="gap:6px">${used.has(c.clip) ? '<span class="tag ok">en el edit</span>' : ''}<span class="tag" title="Puntaje automático de la play (0-100)">${c.score}</span></span></div>`).join('')}</div></div>
      <div class="sticky stack"><div class="panel tight"><h3 style="margin-bottom:8px">Clip c${S.clip}</h3>
        <video id="vid" src="/media/${S.name}/clips/c${S.clip}.mp4" controls preload="metadata"></video>
        <div class="row" style="margin-top:12px"><button id="addk">Marcar una kill en este instante</button><span class="muted small" id="now"></span></div>
        <p class="muted small" style="margin-top:8px">Tocá un tiempo de la lista para saltar ahí. Una kill es cuando tu nombre queda a la izquierda de una entrada con borde rojo en el killfeed.</p></div></div></div></div>`;
  const vid = $('#vid'); vid.ontimeupdate = () => $('#now').textContent = vid.currentTime.toFixed(2) + ' s';
  if (S.seek != null) { vid.currentTime = Math.max(0, S.seek - 1.2); S.seek = null; vid.play().catch(() => {}); }
  v.querySelectorAll('.cliprow').forEach(r => r.onclick = e => { if (e.target.closest('button,a')) return; S.clip = +r.dataset.clip; draw(); });
  v.querySelectorAll('[data-seek]').forEach(a => a.onclick = e => { e.preventDefault(); const [c, t] = a.dataset.seek.split(':'); if (+c !== S.clip) { S.clip = +c; S.seek = +t; draw(); } else { vid.currentTime = Math.max(0, t - 1.2); vid.play().catch(() => {}); } });
  v.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { const [c, i] = b.dataset.del.split(':'); S.kills[c].splice(+i, 1); S.killsDirty = true; draw(); });
  $('#addk').onclick = () => { S.kills[S.clip].push({ t: +vid.currentTime.toFixed(2), conf: null, why: '', tipo: [] }); S.kills[S.clip].sort((a, b) => a.t - b.t); S.killsDirty = true; draw(); };
  $('#savek').onclick = guard(async () => { const body = Object.fromEntries(Object.entries(S.kills).map(([c, ks]) => [c, ks.map(k => k.t)]));
    S.data.job = await api('PUT', `/api/projects/${S.name}/kills`, body); S.killsDirty = false; S.kills = null; toast('Kills guardadas. Recalculando los disparos…'); draw(); });
  if ($('#auto')) $('#auto').onclick = () => runTask('auto', { force: true });
}

/* ---------- 2. editor ---------- */
function playsOf() { return [...S.edit.act1.map((p, i) => ({ p, act: 'act1', i, id: i })), ...S.edit.act2.map((p, i) => ({ p, act: 'act2', i, id: 100 + i }))]; }
function clipOf(p) { return p.clip ?? (p.burst ? p.burst[0][0] : '?'); }
function color(id) { return COLORS[(id >= 100 ? id - 100 + 3 : id) % COLORS.length]; }
function viewEditor() {
  const d = S.data, v = $('#view');
  if (d.kind === 'nuevo') { v.innerHTML = `<div class="empty"><h2>Todavía no hay un edit</h2><p>Primero subí y analizá los clips en el paso 1.</p></div>`; return; }
  if (d.kind === 'plan') { v.innerHTML = `<div class="stack">${d.timeline ? timelineSvg(d.timeline, d.song) : ''}<div class="banner warn row spread"><span>Este proyecto usa un plan.py (formato anterior): se puede ver y renderizar, pero no editar acá.</span><button id="mig" class="primary">Pasarlo al formato editable</button></div></div>`;
    $('#mig').onclick = guard(async () => { await api('POST', `/api/projects/${S.name}/migrate`); toast('Listo: ahora el edit se puede editar acá.'); S.data = null; await load(); }); return; }
  const T = d.timeline, plays = playsOf();
  const sel = S.sel === 'song' ? null : plays.find(x => x.id === S.sel);
  const lines = (d.check || '').split('\n'); const probs = +(d.check.match(/(\d+) problema/) || [0, 0])[1];
  const warns = lines.filter(l => /aviso\(s\)|CORTE\(S\)/.test(l)).length;
  v.innerHTML = `<div class="stack">${d.error ? `<div class="banner err">${esc(d.error)}</div>` : ''}
    ${T ? timelineSvg(T, d.song) : ''}
    <div class="legend"><span><i style="background:var(--accent)"></i>energía de la canción</span><span><i style="background:var(--kill)"></i>kill</span><span><i style="background:var(--info)"></i>momento de sincronía</span><span><i style="background:#fff"></i>transición</span><span>Tocá una play para editarla.</span></div>
    <div class="editor"><div class="stack"><div class="panel tight" style="padding:0">
        <div class="acthead row spread"><span>CANCIÓN Y ESTRUCTURA</span><button class="ghost" id="songbtn">Editar</button></div>
        <div class="acthead">ACTO 1, hasta el drop principal</div><ul class="playlist">${plays.filter(x => x.act === 'act1').map(rowPlay).join('') || '<li class="muted">Sin plays</li>'}</ul>
        <div class="acthead">ACTO 2, desde el drop principal</div><ul class="playlist">${plays.filter(x => x.act === 'act2').map(rowPlay).join('')}</ul>
        <div class="row" style="padding:12px">${addPlaySelect()}</div></div>
      <div class="panel tight"><div class="row spread"><h2>Control de kills</h2><span class="tag ${probs ? 'kill' : 'ok'}">${probs ? probs + ' problema(s)' : 'sin problemas'}</span></div>
        <p class="muted small" style="margin:4px 0 8px">Que cada kill se vea entera, sin tiempos muertos y lejos de las transiciones.${warns ? ' Hay avisos para revisar.' : ''}</p>
        <pre class="report">${esc(lines.filter(l => /^\s+- |problema|aviso|CORTE|Tabla limpia|sincronía/.test(l)).join('\n') || 'Guardá el edit para controlarlo.')}</pre></div></div>
      <div class="sticky"><div class="panel tight stack" id="form">${S.sel === 'song' ? formSong() : sel ? formPlay(sel) : `<p class="muted">Elegí una play de la lista o de la línea de tiempo para cambiar su título, sus cortes o su transición.</p>`}
        <div class="row" style="border-top:1px solid var(--line);padding-top:16px"><button class="primary" id="save" ${S.dirty ? '' : 'disabled'}>Guardar y volver a calcular</button>
        ${S.dirty ? '<button id="undo" class="ghost">Descartar cambios</button>' : ''}</div></div></div></div></div>`;
  v.querySelectorAll('[data-play]').forEach(el => el.addEventListener('click', () => { S.sel = +el.dataset.play; draw(); }));
  $('#songbtn').onclick = () => { S.sel = 'song'; draw(); };
  $('#save').onclick = saveEdit; if ($('#undo')) $('#undo').onclick = () => { S.edit = clone(S.data.edit); S.dirty = false; draw(); };
  const add = $('#addplay'); if (add) add.onchange = () => { if (!add.value) return; const c = d.clips.find(x => x.clip === +add.value); const sh = c.shots;
    S.edit.act1.push({ clip: c.clip, segs: [{ kill: 0, end: +(sh[sh.length - 1] + 0.9).toFixed(2), lead: 1.2, kills: sh.map((_, i) => i) }] }); S.sel = S.edit.act1.length - 1; S.dirty = true; draw(); };
  bindForm();
}
function rowPlay(x) {
  const p = x.p, n = p.burst ? p.burst.length : (p.segs || []).reduce((a, s) => a + s.kills.length, 0);
  return `<li data-play="${x.id}" class="${S.sel === x.id ? 'sel' : ''}"><span class="sw" style="background:${color(x.id)}"></span>
    <span><strong>c${clipOf(p)}</strong> <span class="muted">${p.burst ? 'ráfaga de ' + n : n + (n === 1 ? ' kill' : ' kills')}${p.cap ? ' · ' + esc(p.cap[0]) : ''}</span></span>
    <span class="muted small">${p.kill_at ? 'anclada ' + (+p.kill_at).toFixed(1) + ' s' : ''}</span></li>`;
}
function addPlaySelect() {
  const used = new Set(playsOf().map(x => clipOf(x.p))); used.add(S.edit.open.clip);
  const free = S.data.clips.filter(c => !used.has(c.clip) && c.shots.length).sort((a, b) => b.score - a.score);
  return free.length ? `<div class="field" style="flex:1"><label for="addplay">Agregar una play (ordenadas por puntaje)</label><select id="addplay"><option value="">Elegir un clip…</option>${free.map(c => `<option value="${c.clip}">c${c.clip}: ${c.shots.length} kills, puntaje ${c.score}</option>`).join('')}</select></div>` : '<span class="muted small">Todos los clips con kills ya están en el edit.</span>';
}
function formSong() {
  const e = S.edit, s = e.song, sg = S.data.song?.suggest;
  return `<h2>Canción y estructura</h2>
    <div class="field"><label for="f-title">Título que aparece en la intro</label><input id="f-title" type="text" data-path="song.title" value="${esc(s.title)}"></div>
    <div class="grid"><div class="field"><label for="f-start">El video arranca en (s)</label><input id="f-start" type="number" step="0.01" data-path="song.start" value="${s.start}"></div>
      <div class="field"><label for="f-d1">Primer drop (s)</label><input id="f-d1" type="number" step="0.01" data-path="song.drop1" value="${s.drop1}"></div>
      <div class="field"><label for="f-d2">Drop principal (s)</label><input id="f-d2" type="number" step="0.01" data-path="song.drop2" value="${s.drop2}"></div></div>
    ${sg ? `<p class="muted small">Sugerencia del análisis: arranque ${sg.start.toFixed(2)}, primer drop ${sg.drop1.toFixed(2)}, drop principal ${sg.drop2.toFixed(2)}. Son segundos de la canción; confirmá el drop a oído.</p>` : ''}
    <div class="grid"><div class="field"><label for="f-oc">Clip de apertura</label><input id="f-oc" type="number" data-path="open.clip" value="${e.open.clip}"></div>
      <div class="field"><label for="f-oe">La apertura corta en (s del clip)</label><input id="f-oe" type="number" step="0.05" data-path="open.end" value="${e.open.end}"></div>
      <div class="field"><label for="f-cl">Cierre con la cámara (s)</label><input id="f-cl" type="number" step="0.5" data-path="close.len" value="${e.close.len ?? 6}"></div></div>
    <label class="check"><input type="checkbox" data-path="reveal" ${e.reveal ? 'checked' : ''}> Revelación antes del drop principal (la play se acerca y se ilumina)</label>`;
}
function formPlay(x) {
  const p = x.p, c = S.data.clips.find(k => k.clip === clipOf(p)), shots = c ? c.shots : [];
  if (p.burst) return `<h2>Ráfaga</h2><p class="muted">Una kill de un clip distinto en cada golpe. Se edita en edit.json (ver docs/edit-json.md).</p>${moveBtns(x)}`;
  return `<div class="row spread"><h2>Play del clip c${p.clip}</h2><a class="muted small" href="#/p/${S.name}/clips" data-see="${p.clip}">Ver el clip</a></div>
    <div class="grid"><div class="field"><label for="f-cap">Título (ACE, 4K, CLUTCH)</label><input id="f-cap" type="text" data-cap="0" value="${esc(p.cap?.[0] || '')}"></div>
      <div class="field"><label for="f-sub">Subtítulo (arma o mapa)</label><input id="f-sub" type="text" data-cap="1" value="${esc(p.cap?.[1] || '')}"></div></div>
    <div class="grid"><div class="field"><label for="f-tin">Transición de entrada</label><select id="f-tin" data-key="tin">${TRANS.map(([k, l]) => `<option value="${k}" ${(p.tin || '') === k ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      <div class="field"><label for="f-ka">Anclar la primera kill en (s de la canción)</label><input id="f-ka" type="number" step="0.01" data-key="kill_at" value="${p.kill_at ?? ''}" placeholder="el próximo golpe"></div></div>
    <h3>Tomas</h3>
    ${p.segs.map((s, i) => `<div class="segbox stack"><div class="row spread"><strong>Toma ${i + 1}</strong>${p.segs.length > 1 ? `<button class="ghost danger" data-delseg="${i}">Quitar toma</button>` : ''}</div>
      <div class="grid"><div class="field"><label>Kill que cae en el golpe</label><select data-seg="${i}:kill">${s.kills.map(j => `<option value="${j}" ${j === s.kill ? 'selected' : ''}>kill ${j + 1} (${(shots[j] ?? 0).toFixed(2)} s)</option>`).join('')}</select></div>
        <div class="field"><label>Corta en (s del clip)</label><input type="number" step="0.05" data-seg="${i}:end" value="${s.end}"></div>
        <div class="field"><label>Segundos antes de la kill</label><input type="number" step="0.1" min="0.3" data-seg="${i}:lead" value="${s.lead}"></div></div>
      <div class="row">${shots.map((t, j) => `<label class="check"><input type="checkbox" data-segk="${i}:${j}" ${s.kills.includes(j) ? 'checked' : ''}> ${t.toFixed(2)} s</label>`).join('')}</div></div>`).join('')}
    <div class="row"><button id="addseg">Agregar una toma</button></div>
    <div class="field"><label>Kills poco visibles (enemigo lejos o entre humo): piden más tiempo en pantalla</label>
      <div class="row">${shots.map((t, j) => `<label class="check"><input type="checkbox" data-hard="${j}" ${(p.hard || []).includes(j) ? 'checked' : ''}> ${t.toFixed(2)} s</label>`).join('')}</div></div>
    ${moveBtns(x)}`;
}
function moveBtns(x) { return `<div class="row"><button data-mv="-1" ${x.i === 0 ? 'disabled' : ''}>Subir</button><button data-mv="1" ${x.i === S.edit[x.act].length - 1 ? 'disabled' : ''}>Bajar</button>
  <button data-act>${x.act === 'act1' ? 'Pasar al acto 2' : 'Pasar al acto 1'}</button><button class="danger" data-rm ${x.act === 'act2' && S.edit.act2.length === 1 ? 'disabled' : ''}>Quitar del edit</button></div>`; }
function touch() { S.dirty = true; const b = $('#save'); if (b) b.disabled = false; $('#crumbs').innerHTML = `<span>/</span><b>${esc(S.name.replace(/_/g, ' '))}</b><span class="tag warn">cambios sin guardar</span>`; }
function bindForm() {
  const f = $('#form'); if (!f) return;
  const x = playsOf().find(k => k.id === S.sel), p = x?.p;
  f.querySelectorAll('[data-path]').forEach(el => el.oninput = () => { const ks = el.dataset.path.split('.'); let o = S.edit; ks.slice(0, -1).forEach(k => o = o[k] ??= {});
    o[ks.at(-1)] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? +el.value : el.value; touch(); });
  if (!p) return;
  f.querySelectorAll('[data-cap]').forEach(el => el.oninput = () => { const a = [$('#f-cap').value.trim().toUpperCase(), $('#f-sub').value.trim().toUpperCase()]; if (a[0]) p.cap = a; else delete p.cap; touch(); });
  f.querySelectorAll('[data-key]').forEach(el => el.oninput = () => { const k = el.dataset.key; if (el.value === '') delete p[k]; else p[k] = el.type === 'number' ? +el.value : el.value; touch(); });
  f.querySelectorAll('[data-seg]').forEach(el => el.oninput = () => { const [i, k] = el.dataset.seg.split(':'); p.segs[i][k] = +el.value; touch(); });
  f.querySelectorAll('[data-segk]').forEach(el => el.onchange = () => { const [i, j] = el.dataset.segk.split(':').map(Number), s = p.segs[i];
    s.kills = el.checked ? [...new Set([...s.kills, j])].sort((a, b) => a - b) : s.kills.filter(q => q !== j);
    if (!s.kills.length) { s.kills = [j]; toast('Una toma necesita al menos una kill.', true); } if (!s.kills.includes(s.kill)) s.kill = s.kills[0]; S.dirty = true; draw(); });
  f.querySelectorAll('[data-hard]').forEach(el => el.onchange = () => { const j = +el.dataset.hard; p.hard = el.checked ? [...new Set([...(p.hard || []), j])] : (p.hard || []).filter(q => q !== j); if (!p.hard.length) delete p.hard; touch(); });
  f.querySelectorAll('[data-delseg]').forEach(el => el.onclick = () => { p.segs.splice(+el.dataset.delseg, 1); S.dirty = true; draw(); });
  const as = $('#addseg'); if (as) as.onclick = () => { const c = S.data.clips.find(k => k.clip === p.clip), usedK = new Set(p.segs.flatMap(s => s.kills)); const j = c.shots.findIndex((_, i) => !usedK.has(i));
    if (j < 0) return toast('Todas las kills del clip ya están en una toma.', true); p.segs.push({ kill: j, end: +(c.shots[j] + 0.9).toFixed(2), lead: 0.8, kills: [j] }); p.segs.sort((a, b) => a.kill - b.kill); S.dirty = true; draw(); };
  f.querySelectorAll('[data-mv]').forEach(el => el.onclick = () => { const a = S.edit[x.act], j = x.i + +el.dataset.mv; [a[x.i], a[j]] = [a[j], a[x.i]]; S.sel = (x.act === 'act2' ? 100 : 0) + j; S.dirty = true; draw(); });
  const ab = f.querySelector('[data-act]'); if (ab) ab.onclick = () => { const to = x.act === 'act1' ? 'act2' : 'act1'; if (x.act === 'act2' && S.edit.act2.length === 1) return toast('El acto 2 necesita al menos una play.', true);
    S.edit[x.act].splice(x.i, 1); S.edit[to].push(p); S.sel = (to === 'act2' ? 100 : 0) + S.edit[to].length - 1; S.dirty = true; draw(); };
  const rm = f.querySelector('[data-rm]'); if (rm) rm.onclick = () => { S.edit[x.act].splice(x.i, 1); S.sel = null; S.dirty = true; draw(); };
  const see = f.querySelector('[data-see]'); if (see) see.onclick = () => { S.clip = +see.dataset.see; };
}
const saveEdit = guard(async () => {
  const b = $('#save'); b.classList.add('busy'); b.disabled = true;
  try { const r = await api('PUT', `/api/projects/${S.name}/edit`, S.edit);
    Object.assign(S.data, { edit: clone(S.edit), timeline: r.timeline, check: r.check, style: r.style, error: null }); S.dirty = false; toast('Guardado. El edit dura ' + fmt(r.timeline.TOTAL) + '.'); draw(); }
  catch (e) { b.classList.remove('busy'); b.disabled = false; throw e; }
});
function timelineSvg(T, song) {
  const total = T.TOTAL, pps = Math.max(7, 1240 / total), W = Math.ceil(total * pps), H = 150, a0 = T.SONG_A0;
  let area = '';
  if (song?.beats?.length && song.energy?.length) {
    const pts = []; song.beats.forEach((b, i) => { const x = (b - a0) * pps; if (x >= -5 && x <= W + 5 && song.energy[i] != null) pts.push([x, 60 - 52 * song.energy[i]]); });
    if (pts.length > 2) area = `<path d="M${pts[0][0].toFixed(1)},60 ${pts.map(p => 'L' + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ')} L${pts.at(-1)[0].toFixed(1)},60 Z" fill="#f5b942" opacity=".28"/>
      <path d="M${pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' L')}" fill="none" stroke="#f5b942" stroke-width="1.5"/>`;
  }
  const ticks = []; for (let t = 0; t <= total; t += 10) ticks.push(`<line x1="${t * pps}" x2="${t * pps}" y1="62" y2="${H - 16}" stroke="#2f3442"/><text x="${t * pps + 3}" y="${H - 4}">${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}</text>`);
  const sync = (T.SYNC || []).map(s => `<line x1="${(s - a0) * pps}" x2="${(s - a0) * pps}" y1="4" y2="${H - 18}" stroke="#7fb4ff" stroke-dasharray="3 3"/>`).join('');
  const kindFill = { logo: '#3a3f4f', interlude: '#3a3f4f', outro: '#3a3f4f', slowmo: '#d7dbe6' };
  const segs = T.segments.map(s => { const x = s.o0 * pps, w = Math.max(1, (s.o1 - s.o0) * pps - 1), play = s.kind === 'zoom_out' ? null : s.play;
    const fill = kindFill[s.kind] || (s.play >= 0 ? color(s.play) : '#3a3f4f'), label = { logo: 'logo', outro: 'cierre', interlude: 'luces' }[s.kind] || (w > 26 ? 'c' + s.clip : '');
    return `<g class="seg" ${play != null && s.play >= 0 && s.kind !== 'face_out' ? `data-play="${s.play}"` : ''}><title>${s.kind === 'play' ? 'clip c' + s.clip : s.kind} · ${fmt(s.o0)} a ${fmt(s.o1)}</title>
      <rect x="${x.toFixed(1)}" y="70" width="${w.toFixed(1)}" height="46" rx="3" fill="${fill}" ${S.sel === s.play && s.kind === 'play' ? 'stroke="#fff" stroke-width="2"' : ''}/><text class="lbl" x="${(x + 5).toFixed(1)}" y="98">${label}</text></g>`; }).join('');
  const kills = T.kills.map(k => `<rect x="${(k * pps - 1).toFixed(1)}" y="64" width="2" height="58" fill="#ef5350"/>`).join('');
  const bounds = T.boundaries.map(b => `<path d="M${(b[0] * pps).toFixed(1)},120 l4,5 l-4,5 l-4,-5 z" fill="#fff" opacity=".85"><title>${b[1]}</title></path>`).join('');
  return `<div class="tl" role="img" aria-label="Línea de tiempo del edit: ${T.segments.length} tramos, ${T.kills.length} kills, ${fmt(total)}"><svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${area}${ticks.join('')}${sync}${segs}${kills}${bounds}</svg></div>`;
}

/* ---------- 3. estilo ---------- */
const STYLE = [
  ['Canal', [['channel.name', 'Nombre en la intro', 'text'], ['channel.tagline', 'Bajada de la intro', 'text'], ['channel.outro_text', 'Texto del cierre', 'text'], ['channel.link', 'Link del cierre', 'text'], ['channel.player', 'Tu nick en el juego (para leer el killfeed)', 'text']]],
  ['Colores del logo', [['colors.ring.0', 'Anillo 1', 'color'], ['colors.ring.1', 'Anillo 2', 'color'], ['colors.ring.2', 'Anillo 3', 'color']]],
  ['Imagen', [['look.contrast', 'Contraste', 'range', 0, 0.8, 0.01], ['look.saturation', 'Saturación', 'range', 0.8, 1.6, 0.01], ['look.sharpen', 'Nitidez', 'range', 0, 0.6, 0.01], ['look.bloom', 'Brillo en las luces', 'range', 0, 0.4, 0.01], ['look.vignette', 'Viñeta', 'range', 0, 0.7, 0.01]]],
  ['Efectos', [['transitions.intensity', 'Fuerza de las transiciones', 'range', 0.3, 1.6, 0.05], ['kill_fx.intensity', 'Fuerza de los efectos de kill', 'range', 0.3, 1.8, 0.05], ['kill_fx.energy_follow', 'Que el efecto siga la energía de la canción', 'range', 0, 1, 0.1]]],
  ['Títulos', [['captions.size', 'Tamaño del título', 'number'], ['captions.from_bottom', 'Distancia al borde inferior (px)', 'number'], ['captions.duration', 'Segundos en pantalla', 'number']]],
  ['Audio', [['audio.game_vs_music', 'Juego respecto de la música (dB)', 'range', -18, -6, 0.5], ['audio.music_duck', 'Cuánto se aparta la música en cada tiro', 'range', 0.2, 0.8, 0.02], ['audio.loudness.target_lufs', 'Loudness final (LUFS, vacío = lo más fuerte que deje el pico)', 'number']]],
];
const get = (o, path) => path.split('.').reduce((a, k) => a?.[k], o);
function setPath(o, path, val) { const ks = path.split('.'); ks.slice(0, -1).forEach((k, i) => { o = o[k] ??= (/^\d+$/.test(ks[i + 1]) ? [] : {}); }); o[ks.at(-1)] = val; }
function viewStyle() {
  const d = S.data, v = $('#view'), st = d.style;
  if (d.kind !== 'edit') { v.innerHTML = `<div class="empty"><h2>El estilo se ajusta sobre un edit editable</h2><p>${d.kind === 'plan' ? 'Pasá este proyecto al formato editable desde el paso 2.' : 'Armá primero el edit en el paso 1.'}</p></div>`; return; }
  const cur = path => { const ov = get(S.edit.style || {}, path); return ov !== undefined ? ov : get(st, path); };
  const t0 = d.timeline ? [2.0, +(d.timeline.kills[Math.min(3, d.timeline.kills.length - 1)] + 0.05).toFixed(2)] : [2.0];
  v.innerHTML = `<div class="stack">${jobBox()}<div class="editor" style="margin-top:0"><div class="panel stack">
      <div class="row spread"><div><h2>Estilo de este edit</h2><p class="muted small">Parte del preset <strong>${esc(st.name)}</strong>. Lo que cambies acá vale solo para este proyecto.</p></div>
        <div class="row"><button id="reset" class="ghost" ${S.edit.style ? '' : 'disabled'}>Volver al preset</button><button class="primary" id="save" ${S.dirty ? '' : 'disabled'}>Guardar estilo</button></div></div>
      ${STYLE.map(([title, fields]) => `<div><h3 style="margin-bottom:8px">${title}</h3><div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(${fields[0][2] === 'color' ? 90 : 210}px,1fr))">${fields.map(([path, label, type, min, max, step]) => { const val = cur(path), id = 's-' + path.replace(/\./g, '-');
        const show = Array.isArray(val) ? val.join(', ') : val ?? '';
        return `<div class="field"><label for="${id}">${label}${type === 'range' ? ` <b id="${id}-v" style="color:var(--text)">${val}</b>` : ''}</label><input id="${id}" data-style="${path}" type="${type}" ${type === 'range' ? `min="${min}" max="${max}" step="${step}"` : ''} ${type === 'number' ? 'step="any"' : ''} value="${esc(show)}"></div>`; }).join('')}</div></div>`).join('')}</div>
    <div class="sticky"><div class="panel tight stack"><h2>Vista previa</h2><p class="muted small">Renderiza cuadros sueltos con el estilo guardado, sin hacer el video entero.</p>
      <div class="row"><div class="field" style="flex:1"><label for="pv">Segundos del video (separados por coma)</label><input id="pv" type="text" value="${t0.join(', ')}"></div><button id="dopv" style="align-self:end" ${d.job?.running || S.dirty ? 'disabled' : ''}>Ver</button></div>
      ${S.dirty ? '<p class="muted small">Guardá el estilo para ver la vista previa.</p>' : ''}
      ${S.previews.map(t => `<img class="frame" alt="Cuadro del segundo ${t}" src="/media/${S.name}/previews/pv_${(+t).toFixed(2).padStart(6, '0')}.jpg?${Date.now()}">`).join('')}</div></div></div></div>`;
  v.querySelectorAll('[data-style]').forEach(el => el.oninput = () => { let val = el.value; const path = el.dataset.style;
    if (el.type === 'range' || el.type === 'number') val = el.value === '' ? null : +el.value;
    if (path === 'channel.player') val = val.trim() ? (val.includes(',') ? val.split(',').map(s => s.trim()).filter(Boolean) : val.trim()) : null;
    S.edit.style ??= {}; if (path.startsWith('colors.ring') && !S.edit.style.colors) S.edit.style.colors = { ring: [...st.colors.ring] };
    setPath(S.edit.style, path, val); const o = $('#' + el.id + '-v'); if (o) o.textContent = val; touch(); });
  $('#save').onclick = saveEdit; $('#reset').onclick = () => { delete S.edit.style; S.dirty = true; draw(); };
  $('#dopv').onclick = () => { S.previews = $('#pv').value.split(',').map(s => +s.trim()).filter(x => x >= 0); runTask('preview', { times: S.previews }); };
}

/* ---------- 4. render ---------- */
function viewRender() {
  const d = S.data;
  $('#view').innerHTML = `<div class="render"><div class="panel stack"><h2>Renderizar</h2>
      <p class="muted small">El borrador (960x540, 30 fps) sale en menos de un minuto y sirve para mirar el edit entero. El final es 1080p a 60 fps.</p>
      <div class="row"><button class="primary" id="draft">Renderizar el borrador</button><button id="final">Render final</button><button id="stop" class="ghost danger" hidden>Detener</button></div>
      ${S.dirty ? '<div class="banner warn small">Hay cambios sin guardar en el editor: el render usa lo último guardado.</div>' : ''}
      <ol class="stages" id="stages"></ol><div id="prog"></div></div>
    <div class="stack"><div id="result"></div><div class="panel tight"><h3>Detalle</h3><pre class="report" id="log" style="margin-top:8px"></pre></div></div></div>`;
  $('#draft').onclick = () => runTask('draft'); $('#final').onclick = () => runTask('final');
  $('#stop').onclick = guard(async () => { await api('POST', `/api/projects/${S.name}/stop`); toast('Render detenido.'); });
  if (d.kind === 'nuevo') { $('#draft').disabled = $('#final').disabled = true; }
  S.shown = null; paintRender();
}
function paintRender() {
  const d = S.data, st = d.status, j = d.job, el = $('#stages'); if (!el) return;
  const rendering = j?.running && (j.task === 'draft' || j.task === 'final');
  $('#draft').disabled = $('#final').disabled = !!j?.running || d.kind === 'nuevo'; $('#stop').hidden = !rendering;
  const stages = st?.stages || [['preparando', 'Leer el plan y el estilo'], ['render', 'Render de video'], ['audio', 'Mezcla de audio'], ['uniendo', 'Unir video y audio'], ['verificando', 'Verificar el resultado'], ['listo', 'Listo']].map(([id, label]) => ({ id, label }));
  const cur = st ? stages.findIndex(s => s.id === st.stage) : -1, failed = st?.stage === 'error' || (j && !j.running && j.code && (j.task === 'draft' || j.task === 'final'));
  el.innerHTML = stages.filter(s => s.id !== 'camaras_lentas' || st?.stage === 'camaras_lentas').map((s) => { const i = stages.indexOf(s);
    const cls = !st ? '' : st.stage === 'listo' || i < cur ? 'done' : i === cur ? (failed ? 'fail' : rendering ? 'now' : 'done') : '';
    const extra = s.id === 'render' && st && st.total ? `${st.done}/${st.total} pedazos` : '';
    return `<li class="${cls}"><span class="dot">${cls === 'done' ? '✓' : cls === 'fail' ? '!' : ''}</span><span>${s.label}${s.id === 'render' && cls === 'now' && st.total ? `<div class="bar"><i style="width:${(100 * st.done / st.total).toFixed(1)}%"></i></div>` : ''}</span><span class="muted small">${extra}</span></li>`; }).join('');
  $('#prog').innerHTML = st ? `<p class="muted small">${st.device === 'gpu' ? 'En la placa (' + esc(st.gpu || 'GPU') + ')' : 'En el procesador'}, codificador ${esc(st.encoder || '')}. ${Math.round(st.elapsed || 0)} s${rendering && st.eta != null && st.stage === 'render' ? ', faltan unos ' + Math.ceil(st.eta) + ' s' : ''}.</p>
    ${failed ? `<div class="banner err small" style="margin-top:8px">${esc(st.message || 'El render se cortó: mirá el detalle.')}</div>` : ''}` : '<p class="muted small">Todavía no se renderizó este proyecto en esta sesión.</p>';
  $('#log').textContent = (j?.log || '').split('\n').slice(-14).join('\n') || 'Sin actividad.';
  const done = st?.stage === 'listo' && !j?.running, key = done ? st.out + st.updated : (d.files.final ? 'final' : d.files.draft ? 'draft' : '');
  if (key !== S.shown) { S.shown = key;
    const src = done ? (st.draft ? `/media/${S.name}/borrador.mp4` : `/media/_out/${S.name}`) : d.files.final ? `/media/_out/${S.name}` : d.files.draft ? `/media/${S.name}/borrador.mp4` : null;
    $('#result').innerHTML = src ? `<div class="panel tight stack"><div class="row spread"><h2>${src.includes('borrador') ? 'Borrador' : 'Video final'}</h2>${done ? `<span class="tag ok">listo en ${Math.round(st.elapsed)} s</span>` : ''}</div>
      <video controls preload="metadata" src="${src}?${Date.now()}"></video>
      ${done && st.check ? `<pre class="report">${esc(st.check)}</pre>` : ''}<p class="muted small">${done ? esc(st.out) : ''}</p></div>`
      : `<div class="empty"><h2>Acá va a aparecer el video</h2><p>Renderizá el borrador para mirarlo entero antes del final.</p></div>`; }
}

/* ---------- arranque ---------- */
(async () => { route(); try { const h = await api('GET', '/api/doctor'); const gpu = h.modo === 'gpu';
  $('#hw').innerHTML = h.error ? '' : `<i class="${gpu ? '' : 'cpu'}"></i>${gpu ? 'Render en la placa: ' + esc(h.placa || '') : 'Render en el procesador'}`; } catch { /* sin diagnóstico: no molesta */ } })();
