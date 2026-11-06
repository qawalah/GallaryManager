
/* -------------------------------------------------------------- the selection

   "Select photographs, then do something to them" is the sentence the whole
   3.0 shift is about. Two kinds of something, and the difference is honest:

   STARS AND COLOURS are written straight through, one file at a time, by the
   same endpoint the viewer has always used. They are per-photograph facts and
   making you open a feature to put a star on one would be ceremony.

   EVERYTHING ELSE hands the selection to the feature that does it, with the
   folders your photographs are in already filled in. The tasks here work on
   folders - that is what makes "move four hundred files" safe to check before
   it runs - so the honest bridge is to carry the folders across and let you
   read the plan, rather than to invent a second half of the app that writes
   without one. */

function pickMode(){
  if (document.body.classList.contains("picking")) return pickClear();
  document.body.classList.add("picking");
  drawPickBar();
}

function pickClick(ev, path){
  ev.preventDefault(); ev.stopPropagation();
  document.body.classList.add("picking");
  pickToggle(path, ev.shiftKey);
  return false;
}

function tileClick(ev, path){
  ev.preventDefault();
  if (document.body.classList.contains("picking")){
    pickToggle(path, ev.shiftKey);
    return false;
  }
  openShot(path);
  return false;
}

function pickToggle(path, range){
  if (range && LASTPICK){
    const all = SHOTS.map(s => s.path);
    const a = all.indexOf(LASTPICK), b = all.indexOf(path);
    if (a >= 0 && b >= 0){
      for (const p of all.slice(Math.min(a, b), Math.max(a, b) + 1)) PICK.add(p);
      LASTPICK = path;
      return paintPicks();
    }
  }
  if (PICK.has(path)) PICK.delete(path); else PICK.add(path);
  LASTPICK = path;
  paintPicks();
}

function pickGroup(group){
  document.body.classList.add("picking");
  const mine = SHOTS.filter(s => s.group === group).map(s => s.path);
  const all = mine.every(p => PICK.has(p));
  for (const p of mine){ if (all) PICK.delete(p); else PICK.add(p); }
  paintPicks();
}

function pickAll(){
  const all = SHOTS.every(s => PICK.has(s.path));
  for (const s of SHOTS){ if (all) PICK.delete(s.path); else PICK.add(s.path); }
  paintPicks();
}

function pickClear(quiet){
  PICK.clear();
  LASTPICK = "";
  document.body.classList.remove("picking");
  if (!quiet) paintPicks();
}

function paintPicks(){
  document.querySelectorAll(".shot").forEach(el =>
    el.classList.toggle("picked", PICK.has(el.dataset.p)));
  drawPickBar();
}

function pickedPaths(){ return [...PICK]; }

function pickFolders(){
  const out = [];
  for (const p of PICK){
    const folder = p.replace(/[\\/][^\\/]*$/, "");
    if (folder && !out.includes(folder)) out.push(folder);
  }
  return out;
}

/* THE SELECTION BAR SAYS WHAT IT WILL DO.

   The buttons were right and the words were not. "Organize" is a category, not
   an act - it opens Sort into folders; "Develop" sounds like it changes the
   photographs, and it copies them somewhere; "Rate" could be anything. A person
   who has just selected forty photographs is deciding whether to press a button
   that might move all of them, and the label is the whole of what they have to
   decide on.

   So: the real name of the thing each one opens, and a sentence under the
   cursor saying what it would do to the photographs that are selected. No new
   buttons - the review was explicit about that - the same six, able to be read.
*/
const PICKBAR = [
  ["rate", "star", "Rate", "rateMenu(event)",
   S.selRateTip],
  ["geo", "globe", "Geotag", "pickInto('geotag')",
   "Work out where these were taken, from your timeline, and write it in."],
  ["org", "calendar", "Sort into folders", "pickInto('bydate')",
   S.selSortTip],
  ["dev", "send", "Send to develop", "pickInto('develop')",
   S.selDevelopTip],
  ["", "tools", "Tools", "toolsMenu(event)",
   S.selToolsTip],
  ["", "menu", "More", "moreMenu(event)",
   S.selMoreTip],
];

function drawPickBar(){
  const bar = document.getElementById("picked");
  if (!bar) return;
  const n = PICK.size;
  bar.innerHTML = `
    <b>${n ? `${num(n)} selected` : esc(S.selectPhotos)}</b>
    <button type="button" class="fchip" onclick="pickAll()">All on screen</button>
    <span class="spacer"></span>`
    + PICKBAR.map(([tone, glyph, label, go, why]) =>
      `<button type="button" class="pillbtn${tone ? " act-" + tone : ""}"
        ${n ? "" : "disabled"} onclick="${go}"
        data-tip="${esc(why)}" data-tipnoclick
        >${icon(glyph)} ${esc(label)}</button>`).join("")
    + `<button type="button" class="fchip" onclick="pickClear()">${
        typeof WORDS === "object" ? WORDS.done : "Done"}</button>`;
  /* Tips are not bound here. The bubble is one set of document listeners bound
     once at boot, delegated on [data-tip], so these buttons are already
     covered; binding again on every redraw stacked a listener per redraw and
     an even number of them opened and shut a bubble in one tap. */
}

function rateMenu(ev){
  const rows = [5, 4, 3, 2, 1, 0].map(n =>
    `<button class="vopt" onclick="rateThem(${n})">${n ? "★".repeat(n) : "No stars"}</button>`)
    .join("")
    + `<div class="vsep"></div>`
    + ["red", "yellow", "green", "blue", "purple", ""].map(c =>
      `<button class="vopt" onclick="colourThem('${c}')">
        <span class="cdot" style="background:${c ? colourOf(c) : "transparent"};
          border:1px solid var(--line)"></span>
        ${c ? c[0].toUpperCase() + c.slice(1) : "No colour"}</button>`).join("");
  pageMenu(ev, rows, ev.currentTarget);
}

/* The same menu the Tools screen would give, with the same words - a person
   should recognise "Separate RAWs" whether they reached it from here, from
   Tools, or from the rail. The line under each is the feature's own one-liner,
   which is the line it carries everywhere else too. */
function toolsMenu(ev){
  const offer = ["bydate", "unpair", "previews", "tags", "cull", "duplicates",
                 "retime", "label"];
  pageMenu(ev, `<div class="mhead">${num(PICK.size)} selected</div>`
    + offer.map(name => {
      const t = byName(name);
      if (!t) return "";
      return `<button class="vopt vopt2" onclick="pickInto('${name}')">
        ${icon(t.icon)}<span><b>${esc(t.tab || t.title)}</b>
        <span>${esc(t.line || "")}</span></span></button>`;
    }).join(""), ev.currentTarget);
}

/* More is the overflow, and the last thing in it is the one that cannot be
   taken back - named in red, with what it actually does to the files. */
function moreMenu(ev){
  pageMenu(ev, `<div class="mhead">${num(PICK.size)} selected</div>
    <button class="vopt vopt2" onclick="pickToFiles()">${icon("folder")}
      <span><b>Show in File explorer</b>
      <span>The folders themselves, with these picked out.</span></span></button>
    <button class="vopt vopt2" onclick="copyPicked()">${icon("copy")}
      <span><b>Copy the paths</b>
      <span>Every selected file's full path, onto the clipboard.</span></span></button>
    <div class="vsep"></div>
    <button class="vopt vopt2 bad" onclick="deletePicked()">${icon("trash")}
      <span><b>Delete to the Recycle Bin</b>
      <span>Moves them into the Recycle Bin, with their RAWs and
      previews. Undo is offered for a few seconds.</span></span></button>`,
    ev.currentTarget);
}

/* One at a time, through the endpoint the viewer uses - so a rating made here
   lands on the JPEG, its RAW and its preview exactly as it does there, and
   there is one place in the app that knows how a star is written. */
async function eachPicked(body, saying){
  const paths = pickedPaths();
  if (!paths.length) return;
  let done = 0, failed = 0, why = "";
  const moves = [];
  const bar = document.getElementById("picked");
  for (const path of paths){
    try{
      const r = await fetch("api/photo", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(Object.assign({path: path}, body))});
      const got = await r.json();
      if (!r.ok || got.error){ failed++; why = why || got.error || ""; }
      else { done++; moves.push(...(got.moves || [])); }
    }catch(e){ failed++; }
    if (bar) bar.querySelector("b").textContent =
      `${num(done + failed)} of ${num(paths.length)}...`;
  }
  const said = failed ? `${saying} ${num(done)} - ${num(failed)} could not be written`
                        + (why ? ` (${why})` : "")
                      : `${saying} ${num(done)}`;
  /* A delete hands back where every file went, so it can be put back, the
     same as the viewer's delete. Without that the dialog's "Undo is offered"
     was a promise the toast did not keep. */
  if (moves.length && body.do === "delete"){
    toast(said, failed ? 9000 : 8000, "Undo", async () => {
      let back = {};
      try{
        const r = await fetch("api/photo", {method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({do: "undo", moves: moves})});
        back = await r.json();
      }catch(e){ back = {}; }
      toast(back.restored ? "Put back" : "Could not put it back", 2500);
      SUMS = null;
      loadShots(true);
    });
  } else {
    toast(said, failed ? 6000 : 2200);
  }
  pickClear();
  SUMS = null;
  loadShots(true);
}

function rateThem(n){
  closePageMenu();
  eachPicked({do: "stars", value: n}, n ? say("putStars", {n: n}) : "Cleared the stars on");
}
function colourThem(c){
  closePageMenu();
  eachPicked({do: "colour", value: c}, c ? `Labelled ${c}` : "Cleared the label on");
}

/* The bridge. The folders the selection sits in, written into the feature's own
   folder boxes - then its ordinary plan, which you read before anything moves. */
function pickInto(task){
  closePageMenu();
  const folders = pickFolders();
  const n = PICK.size;
  openFeature(task, {folders: folders});
  setTimeout(() => {
    const note = document.getElementById("followed");
    if (note) note.textContent =
      say("fromSelection", {n: n, folders: folders.length});
  }, 60);
  pickClear(true);
}

function fillFolders(folders){
  if (!folders || !folders.length) return;
  const first = folders[0];
  const box = document.getElementById("o_folder");
  if (!box) return;
  const many = CURRENT && (CURRENT.options || []).some(
    o => o.name === "folder" && (o.many || o.kind === "folders"));
  if (many){
    box.value = folders.join("\n");
    if (typeof drawChips === "function") drawChips("folder");
  } else {
    box.value = first;
  }
  box.dispatchEvent(new Event("input", {bubbles: true}));
  box.dispatchEvent(new Event("change", {bubbles: true}));
}

async function pickToFiles(){
  closePageMenu();
  const paths = pickedPaths();
  pickClear(true);
  openFeature("files");
  setTimeout(() => { if (typeof fmShowFound === "function") fmShowFound(paths); }, 260);
}

async function copyPicked(){
  closePageMenu();
  const text = pickedPaths().join("\n");
  try{ await navigator.clipboard.writeText(text); toast("Paths copied"); }
  catch(e){ toast(S.copyRefused); }
}

async function deletePicked(){
  closePageMenu();
  const n = PICK.size;
  const yes = await askSure({
    title: say("deletePhotos", {n: n}),
    body: "They go to the Recycle Bin with their RAWs and previews, and Undo "
          + "is offered for a few seconds. Where there is no Recycle Bin, "
          + "nothing is deleted.",
    yes: `Delete ${num(n)}`});
  if (!yes) return;
  await eachPicked({do: "delete"}, "Deleted");
}
