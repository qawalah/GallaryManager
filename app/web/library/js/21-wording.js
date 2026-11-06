/* ------------------------------------------------------- Setup > Wording

   The text of every tool, editable in place: title, tab, summary, each
   option's label and help, each choice, each group heading. Shown only with
   Setup's developer switch on.

   Edits are overrides kept beside the settings (core/wording.py), never the
   source, so a new release keeps them and the tests keep testing what ships.
   Each card saves on its own, when the box loses focus or on Ctrl+S, and the
   task list is read again so the tool's own form says the new words at once.
   Download gives the file to hand back: every edit with the text it
   replaces and the source line it belongs on, which tools/merge_wording.py
   merges.

   The rules on each card are the style guide's (audit section 10), from the
   server, so the editor and tests/test_wording.py cannot disagree about them.
   Only a label or heading of five words is refused; the rest are warnings.

   The last two entries of the list are the page's own strings and the Guide
   (app/pagetext.py). Their edits reach the page when it is next loaded, since
   they are put in as it is sent. */

const WD = {task: "", fields: [], all: null, q: "", counts: {}, tasks: []};

TAB_EDITORS.wording = startWording;

async function startWording(){
  const box = document.getElementById("tabedit");
  if (!box) return;
  box.innerHTML = reading();
  if (!WD.task){
    const here = (TASKS || []).find(t => t.name !== "wording" && !t.parent);
    WD.task = here ? here.name : "setup";
  }
  await wdLoad();
}

async function wdLoad(){
  const box = document.getElementById("tabedit");
  if (!box) return;
  let got;
  try{
    const r = await fetch("api/wording?task=" + encodeURIComponent(WD.task));
    got = await r.json();
    if (!r.ok) throw new Error(got.error || "refused");
  }catch(e){
    box.innerHTML = `<div class="note bad">Could not read the wording: ${esc(e.message || e)}</div>`;
    return;
  }
  WD.fields = got.fields || [];
  WD.counts = got.counts || {};
  WD.tasks = got.tasks || [];
  WD.unknown = got.unknown || [];
  wdDraw();
}

function wdCounts(){
  const c = WD.counts || {};
  const n = (k, one, many) => `${num(c[k] || 0)} ${(c[k] || 0) === 1 ? one : many}`;
  return `<span>${n("edited", "edited", "edited")}</span>
    <span>${n("no_help", "with no help", "with no help")}</span>
    <span>${n("long_labels", "label over four words", "labels over four words")}</span>
    ${c.unknown ? `<span class="bad">${n("unknown", "edit the app no longer ships",
                                       "edits the app no longer ships")}</span>` : ""}`;
}

function wdDraw(){
  const box = document.getElementById("tabedit");
  if (!box) return;
  const opts = WD.tasks.map(t =>
    `<option value="${esc(t.name)}"${t.name === WD.task ? " selected" : ""}>${
      t.parent ? " " : ""}${esc(t.title)}${t.edits ? ` (${t.edits})` : ""}</option>`).join("");
  box.innerHTML = `
    <div class="wdbar">
      <label class="wdpick"><span>Tool</span>
        <select id="wdtask" onchange="wdPick(this.value)">${opts}</select></label>
      <input id="wdq" type="search" placeholder="Find any text..." value="${esc(WD.q)}"
        oninput="wdFind(this.value)" aria-label="Find any text">
      ${WD.task === "page" ? ""
        : WD.task === "guide"
        ? `<button type="button" class="ghost" onclick="guideOpen()"
            >${icon("play")} Open the Guide</button>`
        : `<button type="button" class="ghost" onclick="openFeature(WD.task)"
            >${icon("play")} Open the tool</button>`}
    </div>
    <div class="wdcounts" id="wdcounts">${wdCounts()}</div>
    <div id="wdcards">${wdCards()}</div>
    <div class="act wdfoot">
      <button type="button" onclick="wdDownload()">${icon("download")} Download wording.json</button>
      <label class="ghost wdup">${icon("copy")} Upload wording.json
        <input type="file" accept=".json,application/json" hidden
          onchange="wdUpload(this)"></label>
      <label class="wdrep"><input type="checkbox" id="wdreplace"> Replace my edits</label>
      <button type="button" class="ghost bad" onclick="wdResetAll()"
        >${icon("trash")} Reset everything</button>
    </div>`;
}

function wdShown(){
  if (!WD.q) return WD.fields;
  const q = WD.q.toLowerCase();
  return (WD.all || []).filter(f =>
    String(f.text).toLowerCase().includes(q)
    || String(f.shipped).toLowerCase().includes(q)
    || f.key.toLowerCase().includes(q)).slice(0, 80);
}

function wdCards(){
  const rows = wdShown();
  if (!rows.length)
    return `<div class="note">${WD.q ? "Nothing says that." : "This tool shows no text of its own."}</div>`;
  return rows.map(wdCard).join("")
    + (WD.q && rows.length === 80 ? `<div class="note">The first 80. Type more to narrow it.</div>` : "");
}

/* "cull › min_stars › help": the key, read as a path. The page's strings
   and the Guide are "page › name" and "guide › welcome › paragraph 1". */
function wdName(f){
  const bits = f.key.split(".");
  const task = bits[0];
  if (task === "page") return `page › ${bits.slice(1).join(".")}`;
  if (task === "guide") return bits[2] === "body"
    ? `guide › ${bits[1]} › paragraph ${bits[3]}` : `guide › ${bits[1]} › title`;
  if (bits[1] === "option"){
    const tail = bits[3] === "choice" ? `choice ${bits.slice(4).join(".") || "(blank)"}` : bits[3];
    return `${task} › ${bits[2]} › ${tail}`;
  }
  if (bits[1] === "group") return `${task} › group › ${bits.slice(2).join(".")}`;
  return `${task} › ${bits[1]}`;
}

function wdLong(f){ return ["help", "summary", "body", "string"].includes(f.kind); }

function wdCard(f){
  const id = "wd_" + f.key.replace(/[^A-Za-z0-9_-]/g, "_");
  const box = wdLong(f)
    ? `<textarea id="${id}" rows="3" data-key="${esc(f.key)}">${esc(f.text)}</textarea>`
    : `<input id="${id}" type="text" data-key="${esc(f.key)}" value="${esc(f.text)}">`;
  return `<div class="wdcard${f.edited ? " edited" : ""}" data-key="${esc(f.key)}">
      <div class="wdhead"><small>${esc(wdName(f))}</small>
        ${f.where ? `<small class="wdwhere">${esc(f.where)}</small>` : ""}</div>
      ${f.edited || !f.text ? `<div class="wdship">${f.shipped
        ? esc(f.shipped) : "<i>shipped with no text</i>"}</div>` : ""}
      ${box}
      <div class="wdinfo">${wdInfo(f.kind, f.text, f.problems || [])}
        ${f.edited ? `<button type="button" class="quiet"
          onclick="wdReset('${quoted(f.key)}')">Reset to shipped</button>` : ""}
        <span class="wdsaid"></span></div>
    </div>`;
}

/* Counted as you type, the way the test counts: words for a name, sentences
   for a bubble. The problems come from the server on each save. */
function wdInfo(kind, text, problems){
  return wdCount(kind, text)
    + problems.map(p => `<span class="wdwarn">${icon("warn")}${esc(p)}</span>`).join("");
}

function wdCount(kind, text){
  const said = String(text || "").trim();
  const words = said ? said.split(/\s+/).length : 0;
  let count;
  if (["help", "summary", "body", "string"].includes(kind)){
    const n = said ? said.split(/(?<=[.!?])\s+/).filter(Boolean).length : 0;
    count = `${n} sentence${n === 1 ? "" : "s"}`;
  } else {
    count = `${words} word${words === 1 ? "" : "s"}`;
  }
  const over = (kind === "label" || kind === "group") && words > 4;
  return `<span class="wdcount${over ? " bad" : ""}">${count}</span>`;
}

async function wdPick(name){
  WD.task = name;
  WD.q = "";
  await wdLoad();
}

let WDFIND = 0;
async function wdFind(q){
  WD.q = String(q || "").trim();
  const mine = ++WDFIND;
  if (WD.q && !WD.all){
    try{
      const got = await (await fetch("api/wording?task=*")).json();
      WD.all = got.fields || [];
    }catch(e){ WD.all = []; }
  }
  if (mine !== WDFIND) return;
  const cards = document.getElementById("wdcards");
  if (cards) cards.innerHTML = wdCards();
}

/* Save on leaving the box, or Ctrl+S inside it. Nothing is sent when the
   text has not moved, so tabbing through a tool writes nothing. */
document.addEventListener("focusout", e => {
  const el = e.target;
  if (el && el.dataset && el.dataset.key && el.closest(".wdcard")) wdSave(el);
});
document.addEventListener("keydown", e => {
  const el = e.target;
  if ((e.ctrlKey || e.metaKey) && e.key === "s" && el && el.dataset
      && el.dataset.key && el.closest(".wdcard")){
    e.preventDefault();
    wdSave(el);
  }
});
document.addEventListener("input", e => {
  const el = e.target;
  if (!el || !el.dataset || !el.dataset.key || !el.closest(".wdcard")) return;
  const f = wdField(el.dataset.key);
  const info = el.closest(".wdcard").querySelector(".wdinfo .wdcount");
  if (f && info) info.outerHTML = wdCount(f.kind, el.value);
});

function wdField(key){
  return WD.fields.find(f => f.key === key)
      || (WD.all || []).find(f => f.key === key);
}

async function wdPost(body){
  const r = await fetch("api/wording", {method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const got = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(got.error || "refused");
  return got;
}

async function wdSave(el){
  const key = el.dataset.key, f = wdField(key);
  if (!f || el.value === f.text) return;
  const card = el.closest(".wdcard");
  const said = card && card.querySelector(".wdsaid");
  try{
    const got = await wdPost({key, text: el.value});
    Object.assign(f, {text: got.text, edited: got.edited, problems: got.problems});
    WD.counts = got.counts || WD.counts;
    if (card) card.outerHTML = wdCard(f);
    const c = document.getElementById("wdcounts");
    if (c) c.innerHTML = wdCounts();
    refreshTasks();
  }catch(err){
    if (said) said.innerHTML = `<span class="bad">Not saved. ${esc(err.message || err)}</span>`;
  }
}

async function wdReset(key){
  const f = wdField(key);
  try{
    const got = await wdPost({key, reset: true});
    if (f) Object.assign(f, {text: got.text, edited: false, problems: got.problems});
    WD.counts = got.counts || WD.counts;
    const card = document.querySelector(`.wdcard[data-key="${CSS.escape(key)}"]`);
    if (card && f) card.outerHTML = wdCard(f);
    const c = document.getElementById("wdcounts");
    if (c) c.innerHTML = wdCounts();
    refreshTasks();
  }catch(err){ toast("Not reset: " + (err.message || err), 4000); }
}

async function wdResetAll(){
  const ok = await askSure({title: "Reset every edit?",
    body: "Every tool goes back to the text it shipped with. Download the "
        + "file first if you want to keep what you wrote.",
    yes: "Reset everything"});
  if (!ok) return;
  try{ await wdPost({reset_all: true}); }
  catch(err){ toast("Not reset: " + (err.message || err), 4000); return; }
  WD.all = null;
  refreshTasks();
  await wdLoad();
}

async function wdDownload(){
  let got;
  try{ got = await (await fetch("api/wording?export=1")).json(); }
  catch(e){ toast("Could not read the edits", 4000); return; }
  const blob = new Blob([JSON.stringify(got, null, 2) + "\n"], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "wording.json";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

async function wdUpload(input){
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  let body;
  try{ body = JSON.parse(await file.text()); }
  catch(e){ toast("That is not a wording.json file", 4000); return; }
  const replace = !!(document.getElementById("wdreplace") || {}).checked;
  try{
    const got = await wdPost({file: body, replace});
    const n = (got.refused || []).length;
    toast(n ? `Loaded. ${n} line${n === 1 ? " was" : "s were"} left out: `
            + got.refused.slice(0, 3).map(r => `${r.key} (${r.why})`).join("; ")
            : "Loaded", n ? 8000 : 3000);
  }catch(err){ toast("Not loaded: " + (err.message || err), 5000); return; }
  WD.all = null;
  refreshTasks();
  await wdLoad();
}
