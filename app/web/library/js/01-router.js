
/* ======================================================================
   3.0 - the library in front of the features
   ======================================================================

   One router, six screens, and a rule: no screen here reads a photograph.
   Everything comes out of /api/timeline, /api/places, /api/albums and
   /api/item, all of which answer from the index that is built
   in the background. That is what makes the app open ON the library.

   The features are untouched. `show('bydate')` still draws the same form, the
   same plan and the same Go ahead - it just happens inside a screen now. */

/* What the address said when the page ARRIVED. Read here, at the top of this
   script, because `boot()` writes the current feature into the address as soon
   as it draws one - so asking later always finds a tab and the app would open
   on a feature every single time. */
const ARRIVED = location.hash.slice(1);

let SCREEN = "home";
let FILTER = {};              // the Ask the grid is showing
let ALBUM = "";               // which album, when the grid is showing one
let SHOTS = [];               // what is on screen, in order
let GROUPS = [];              // every group in the answer, in the order drawn
let VIEWBY = (() => {
  try{ return localStorage.getItem("pm-viewby") || "date"; }catch(e){ return "date"; }
})();
let TOTAL = 0, OFFSET = 0, MORE = true, LOADING = false;
/* Which ask for photographs is the newest. A search typed while the last one
   was still out used to be dropped, and the grid showed the older answer;
   now every ask takes a number and only the newest may draw. */
let SHOTREQ = 0;
let PICK = new Set();
let IDX = {};                 // how the index is getting on
let SUMS = null;              // the overview, kept so Home redraws for free
let LASTPICK = "";            // for shift-click

const RAIL = [
  ["home", "Home", "home"],
  ["photos", "Photos", "photos"],
  ["places", "Places", "map"],
  ["albums", "Albums", "album"],
  ["people", "People", "people"],
];

/* Which tool group is opened out in the rail, and which the Tools screen is
   showing. One at a time: five groups all opened is the flat list of forty-six
   this was meant to replace. */
let RAILFAM = "";
let TOOLFAM = "";

function shellOn(){ return document.body.classList.contains("shell"); }

async function shellStart(){
  document.body.classList.add("shell");
  await refreshIndex();
  /* An address with a tab in it means a link to a FEATURE was followed, and
     that wins: landing on Home after clicking "open Geotag" would be the app
     deciding it knew better. */
  const task = ARRIVED && typeof byName === "function" && byName(ARRIVED);
  /* A new install has no library, and nothing works until it does - so it
     opens on the Checklist, which says exactly that and what else is missing.
     The same test boot() makes; without it here the shell put Home over the
     top of the Checklist boot() had just opened. */
  const fresh = !ARRIVED && typeof TREES !== "undefined" && !TREES.library
    && typeof byName === "function" && byName("checklist");
  if (task) goScreen("feature");
  else if (fresh) openFeature("checklist");
  else goScreen(remembered());
  // Where the app opens is not a place you have been, so there is nothing
  // behind it. The trail starts recording from your first move.
  TRAILON = true;
  if (typeof drawBack === "function") drawBack();
  /* Not while the tab is hidden - see whileVisible - and once straight away
     when it comes back, so the rail is not a pass behind. */
  whileVisible(tickIndex, IDX_BUSY_MS);
}

function remembered(){
  try{ return localStorage.getItem("pm-screen") || "home"; }catch(e){ return "home"; }
}

/* How often the index is asked about: often while it is being read, rarely
   when it is not. Idle, the health check and the jobs poll already keep the
   page honest, and a third request every 2.5 s was a NAS kept awake for a
   library nobody had touched. */
const IDX_BUSY_MS = 2500, IDX_IDLE_MS = 45000;
let IDXASKED = 0;

async function refreshIndex(){
  IDXASKED = Date.now();
  try{
    IDX = await (await fetch("api/index")).json();
  }catch(e){ IDX = {}; }
  return IDX;
}

/* While the library is still being read the whole app is a little bit wrong,
   so it keeps asking - and slows right down the moment it has an answer,
   because a page that polls every few seconds on a library that has not
   changed in a week is a page warming somebody's NAS for nothing. */
async function tickIndex(){
  if (!IDX.building && Date.now() - IDXASKED < IDX_IDLE_MS) return;
  const was = IDX.building, count = IDX.photos, changes = IDX.changes,
        unread = IDX.unreadable;
  await refreshIndex();
  if (!IDX.building && !was && IDX.photos === count
      && IDX.changes === changes && IDX.unreadable === unread) return;
  const bar = document.getElementById("idxbar");
  if (bar) drawIndexing();
  /* Only when a pass actually CHANGED something - the index says how many
     passes have. A pass that read nothing and dropped nothing is not news, and
     redrawing for it is why Home flickered on a library nobody had touched. */
  const moved = IDX.photos !== count || IDX.changes !== changes
                || IDX.unreadable !== unread;
  if (was && !IDX.building && moved){
    forgetIndexAnswers();
    redrawLibraryScreen();
  }
}

function goScreen(name, how){
  how = how || {};
  if (name !== "feature"){
    try{ localStorage.setItem("pm-screen", name); }catch(e){}
  }
  SCREEN = name;
  if (name !== "photos") pickClear(true);
  if (how.filter !== undefined) FILTER = how.filter || {};
  if (how.album !== undefined) ALBUM = how.album || "";
  if (how.fam !== undefined){ TOOLFAM = how.fam || ""; RAILFAM = TOOLFAM; }
  closeDrawer();
  drawRail();
  document.body.classList.toggle("onfeature", name === "feature");
  /* The address follows you. `show()` writes the feature it opened into the
     hash, and leaving that behind on a library screen meant a reload landed on
     the last feature you happened to visit rather than where you were. */
  if (name !== "feature" && location.hash){
    try{ history.replaceState(null, "", location.pathname + location.search); }
    catch(e){}
  }
  if (name === "feature") return;
  if (name === "home") return drawHomeScreen();
  if (name === "photos") return drawPhotos();
  if (name === "people") return drawPeople();
  if (name === "places") return drawPlaces();
  if (name === "albums") return drawAlbums();
  if (name === "tools") return drawTools();
}

/* ------------------------------------------------------------------ the rail */

function railRow(key, label, glyph, count){
  return `<button type="button" class="railrow${SCREEN === key ? " on" : ""}"
    data-s="${key}" onclick="goScreen('${key}')">${icon(glyph)}
    <span>${esc(label)}</span>${count ? `<span class="count">${count}</span>` : ""}
    </button>`;
}

/* A tool group in the rail: the heading, and - when it is the one you opened -
   every feature under it. Opening it also opens its page, so one press answers
   both "what is in here" and "show me". */
function railFam(f){
  const open = RAILFAM === f.key;
  return `<button type="button" class="railrow fam${open ? " open" : ""}"
      data-fam="${esc(f.key)}" data-tone="${esc(f.tone || "grey")}"
      onclick="openFam('${quoted(f.key)}')">
      ${icon(f.icon)}<span>${esc(f.label)}</span>
      <span class="twist" aria-hidden="true">\u203a</span></button>`
    + (open ? `<div class="railkids">` + f.tasks.map(name => {
        const t = byName(name);
        if (!t) return "";
        /* Tabs folded under one tab (the NAS pair) are one line here as
           well, so the rail and the tab row list the same things. */
        const g = typeof tabGroup === "function" ? tabGroup(name) : null;
        if (g){
          const mine = f.tasks.filter(n => g.tasks.indexOf(n) >= 0 && byName(n));
          if (mine[0] !== name) return "";
          const here = CURRENT && SCREEN === "feature" && mine.indexOf(CURRENT.name) >= 0;
          return `<button type="button" class="railrow kid${here ? " on" : ""}"
            data-t="${esc(name)}" data-g="${esc(g.key)}"
            onclick="openFeature('${quoted(name)}')"
            title="${esc(mine.map(n => byName(n).tab || byName(n).title).join(", "))}"
            >${icon(g.icon)}<span>${esc(g.label)}</span></button>`;
        }
        return `<button type="button" class="railrow kid${
            CURRENT && CURRENT.name === name && SCREEN === "feature" ? " on" : ""}"
          data-t="${esc(name)}" onclick="openFeature('${quoted(name)}')"
          title="${esc(t.line || "")}">${icon(t.icon)}
          <span>${esc(t.tab || t.title)}</span></button>`;
      }).join("") + `</div>` : "");
}

function openFam(key){
  RAILFAM = RAILFAM === key ? "" : key;
  goScreen("tools", {fam: RAILFAM || ""});
}

function drawRail(){
  const rail = document.getElementById("rail");
  if (!rail) return;
  const fam = (typeof FAMILIES !== "undefined" && FAMILIES.length) ? FAMILIES : [];
  const n = IDX.photos ? num(IDX.photos) : "";
  rail.innerHTML =
    RAIL.map(([k, label, glyph]) =>
      railRow(k, label, glyph, k === "photos" ? n : "")).join("")
    /* The two or three features somebody does every day, at the top level where
       the screens are - because "open Tools, open Metadata, open Geotag" three
       times a day is the list of everything being gone past, every time. */
    + (PINNED.length ? PINNED.map(pinnedRow).join("") : "")
    + `<div class="railsec">Tools</div>`
    + `<button type="button" class="railrow${
         SCREEN === "tools" && !TOOLFAM ? " on" : ""}"
         onclick="goScreen('tools', {fam: ''})">${icon("tools")}
         <span>All tools</span>
         <span class="count">${fam.reduce((k, f) => k + f.tasks.length, 0) || ""}</span></button>`
    + fam.map(railFam).join("")
    /* Settings stands apart from the tool groups by a gap rather than a
       heading over the one group under it. Setup is its first entry, so a
       line of its own below it (with the same icon) was a second door to the
       same room; History is in the header and under Maintain already. */
    + `<div class="railgap"></div>` + railFam(SETFAM)
    + `<div id="railfoot">${indexLine()}
         <div class="railhelp">
           <button type="button" class="quiet" onclick="guideOpen()">${icon("info")}Show me how</button>
           <button type="button" class="quiet" onclick="shortcutCard()"
             title="Every key this app answers to">${icon("type")}Keys</button>
         </div>
         <label class="fmcheck railnotice"><input type="checkbox" id="noticeon"
           onchange="askNotice(this.checked)"> Tell me when a run finishes</label>
         </div>`;
  /* Just drawn afresh, so it is set from what is true now. */
  if (typeof drawNotice === "function") drawNotice();
  /* The Maintain row was just rewritten without its mark, and the jobs poll
     only draws when its answer changes - so the mark goes back on here. */
  if (typeof drawBadge === "function") drawBadge();
}

function indexLine(){
  if (IDX.building){
    const part = IDX.total ? Math.round(100 * IDX.done / IDX.total) : 0;
    return `<span>Reading the library - ${num(IDX.done || 0)} of ${num(IDX.total || 0)}</span>
      <span class="railbar"><i style="width:${part}%"></i></span>`;
  }
  if (!IDX.photos) return `<span>No library indexed yet.</span>${firstSteps()}`;
  return `<span>${num(IDX.photos)} files indexed</span>
    <span>${IDX.stale ? S.indexStale
                      : "up to date"}</span>${unreadableLine()}
    ${rereadButton("margin-top:4px")}`;
}

/* One button, drawn by the rail and by Home alike: the same label and the same
   handler, and the press is told which copy was pressed so the one under your
   finger is the one that says "Reading...". */
const REREAD = "Re-read library";
function rereadButton(style){
  return `<button type="button" class="fchip"${style ? ` style="${style}"` : ""}
      onclick="reindexNow(this)">${icon("again")} ${REREAD}</button>`;
}

/* The two ways in when there is nothing indexed: the same pair Photos offers
   (noLibraryYet), so the first thing a new install shows is something to press
   rather than a sentence about Setup. */
function firstSteps(){
  return `<div class="firststeps">
    <button type="button" class="fchip" onclick="openFeature('setup')">Open Setup</button>
    <button type="button" class="fchip" onclick="openFeature('demo')">Build a sample library</button>
  </div>`;
}

/* Files the last pass found and could not read. Each is missing from the grid
   and the counts with nothing to show the gap, so the rail says how many, and
   the Checklist names them. */
function unreadableLine(){
  const n = IDX.unreadable || 0;
  if (!n) return "";
  const names = (IDX.unreadable_names || []).map(u =>
    `${String(u.path || "").split(/[\\/]/).pop()}: ${u.error || "?"}`).join("\n");
  return `<button type="button" class="quiet bad" title="${esc(names)}"
    onclick="openFeature('checklist')">${num(n)} file${n === 1 ? "" : "s"} could not be read</button>`;
}

/* Re-read library means READ IT AGAIN: every file, not only the ones whose
   name or size changed since. The button used to ask for the ordinary pass,
   which on a library nobody had touched looked at the names, opened nothing,
   and finished in a second looking as if it had never run - and while the
   minute's own pass was running it was refused outright and did nothing at
   all. Now it asks for the deep pass, and the server makes room for it. */
/* The button pressed is the one that says so. It used to look the button up
   by an id Home's copy never had, so pressing it on Home relabelled the rail's
   instead - or, on a new install, the rail's "Open Setup". */
async function reindexNow(pressed){
  const btn = pressed || document.querySelector("#railfoot .fchip");
  const was = btn ? btn.innerHTML : "";
  if (btn){ btn.disabled = true; btn.textContent = "Reading..."; }
  let ok = true;
  try{
    const r = await fetch("api/index", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({deep: true})});
    ok = r.ok;
  }catch(e){ ok = false; }
  toast(ok ? "Reading the whole library again"
           : "That did not reach the app", ok ? 3000 : 4000);
  await refreshIndex();
  if (btn && btn.isConnected){ btn.disabled = false; btn.innerHTML = was; }
  drawRail();
  drawIndexing();
}

/* Opening a feature from the library: the same `show()` the app has always
   had, with the screen switched round it. */
function openFeature(name, opts){
  goScreen("feature");
  show(name);
  if (opts && opts.folders){
    fillFolders(opts.folders);
    /* An editor tab read the folder box while `show` was drawing it, which was
       before the line above put this folder in it. Without reading it again,
       "File explorer" on a folder opens the explorer standing somewhere else -
       which is the one thing that button exists to do. */
    if (name === "files" && typeof startFiles === "function") startFiles();
    if (name === "rename" && typeof startRename === "function") startRename();
  }
}

function drawIndexing(){
  const box = document.getElementById("idxbar");
  if (!box) return;
  /* Only when it is READING. Every pass walks the library to see what changed,
     which on an unchanged library is a second of looking at names and no files
     opened at all - and announcing that every minute is how a line that matters
     ("your photographs are not all here yet") becomes one nobody reads. */
  if (!IDX.building || !(IDX.reading > 0)){ box.hidden = true; return; }
  const part = IDX.total ? Math.round(100 * IDX.done / IDX.total) : 0;
  box.hidden = false;
  box.innerHTML = `${icon("again")}
    <span>Reading your library - ${num(IDX.done || 0)} of ${num(IDX.total || 0)}.
      Everything below is what it has found so far.</span>
    <span class="ibar"><i style="width:${part}%"></i></span>`;
}
