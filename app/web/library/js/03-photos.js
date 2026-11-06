
/* ----------------------------------------------------------------- the photos

   The grid. Newest first, in months, loaded a page at a time, and every tile is
   a real photograph rather than a row in a table. */

const QUICK = [
  ["", "All"],
  ["kinds=jpeg", "Photos"],
  ["kinds=video", "Videos"],
  ["stars_from=5", "Favourites"],
  ["located=no", "No location"],
  ["stars_to=0", "Not rated"],
];

function filterKey(){
  return Object.entries(FILTER).filter(([, v]) => v !== "" && v != null)
    .map(([k, v]) => `${k}=${v}`).sort().join("&");
}

function drawPhotos(){
  const stage = document.getElementById("stage");
  const title = ALBUM ? (albumTitle(ALBUM) || "Album") : "Photos";
  stage.innerHTML = `
    <div class="phead">
      <div><h2>${esc(title)}</h2><div class="sub" id="shotsaid">Reading...</div></div>
      <span class="spacer"></span>
      <div class="vtools">
        <input id="findshots" type="search" placeholder="Search name, camera, lens..."
          autocomplete="off" style="width:min(230px,40vw)">
        <div class="seg" role="group" aria-label="How to group them">
          <button type="button" class="${VIEWBY === "date" ? "on" : ""}"
            onclick="viewBy('date')">${icon("timeline")}<span>Timeline</span></button>
          <button type="button" class="${VIEWBY === "folder" ? "on" : ""}"
            onclick="viewBy('folder')">${icon("folder")}<span>Folders</span></button>
        </div>
        <button type="button" class="fchip${anyFilter() ? " on" : ""}" id="filtbtn"
          onclick="filterPanel()">${icon("find")} Filters${
            anyFilter() ? ` <span class="n">${filterCount()}</span>` : ""}</button>
        <button type="button" class="fchip" id="selmode" onclick="pickMode()"
          >${icon("select")} Select</button>
        <button type="button" class="fchip" id="hidebtn" hidden
          onclick="hiddenPanel()"></button>
      </div>
    </div>
    <div class="indexing" id="idxbar" hidden></div>
    <div class="fchips" id="quickchips"></div>
    <div id="filters" hidden></div>
    <div id="hiddenbox" hidden></div>
    <div id="wherebar" hidden></div>
    <div id="folderwall" hidden></div>
    <div id="picked"></div>
    <div id="grid"><div id="tiles"></div><div id="scrub"></div></div>
    <div id="more" style="height:60px"></div>`;
  drawIndexing();
  drawQuick();
  const box = document.getElementById("findshots");
  let typing = 0;
  box.value = FILTER.name || "";
  box.addEventListener("input", () => {
    clearTimeout(typing);
    typing = setTimeout(() => {
      const said = box.value.trim();
      FILTER = Object.assign({}, FILTER);
      if (said) FILTER.name = said; else delete FILTER.name;
      loadShots(true);
    }, 280);
  });
  loadShots(true);
}

/* Timeline or folders. Two ways of looking at one library - the same
   photographs, the same filter, one sort apart - and which you want depends
   entirely on whether you are looking for a moment or for a shoot. */
function viewBy(how){
  VIEWBY = how;
  try{ localStorage.setItem("pm-viewby", how); }catch(e){}
  if (how === "folder" && !WHERE) WALL = null;      // start where the library is
  drawPhotos();
}

/* ------------------------------------------------------------- the filters

   The same criteria the Search tab has, over the grid, because "the wide shots
   from 2023 with no location" is something you want while you are LOOKING at
   photographs - not a reason to go to another screen and get a table back.
   They are the same `find.Ask` fields, so there is one idea in the whole app of
   what matches. */
/* A criterion is either a menu of what the library really holds, or a box.
   "from:camera" means "the cameras in your library, as they spell themselves" -
   typing `DMC-GH5` into a library of GH4 files and concluding there is nothing
   there is a mistake nobody should be able to make twice. */
/* The same names Search gives the same facts (app/tasks/search.py), so a
   filter here and the field there are one thing. */
const FILTERS = [
  ["since", "Taken on or after", "date"], ["until", "Taken on or before", "date"],
  ["camera", "Camera", "from:camera"], ["lens", "Lens", "from:lens"],
  ["focal_from", "Focal length from (mm)", "number"],
  ["focal_to", "Focal length to (mm)", "number"],
  ["f_from", "Aperture from f/", "number"], ["f_to", "Aperture to f/", "number"],
  ["iso_from", "ISO from", "number"], ["iso_to", "ISO to", "number"],
  ["stars_from", "Stars from", "choice:,0,1,2,3,4,5"],
  ["stars_to", "Stars to", "choice:,0,1,2,3,4,5"],
  ["colour", "Colour label", "from:colour"],
  ["tags", "Tags", "from:tags"],
  ["located", "Location", "choice:,yes,no"],
  ["country", "Country", "from:country"], ["city", "City or town", "from:city"],
  ["kinds", "Which files", "from:kinds"],
  ["missing", "Missing fact",
   "choice:,taken,camera,lens,focal,aperture,iso,shutter,colour,tags"],
];

// Choices that read better as words than as their value, as Search says them.
const CHOICE_WORDS = {located: {yes: "Has a location", no: "No location"}};

/* What the library holds, read once per screenful and kept. From the index, so
   it is there the moment a panel opens rather than a second later. */
let CHOICES = null;

async function loadChoices(){
  if (CHOICES) return CHOICES;
  try{ CHOICES = await (await fetch("api/choices")).json(); }
  catch(e){ CHOICES = {}; }
  return CHOICES;
}

/* Why there is no town or country to pick.

   Two very different causes with one appearance - an empty menu - and typing a
   name into a box instead told you nothing about either. A place is a NUMBER in
   a photograph; turning it into "Granada" needs the place table, and nothing at
   all can be offered until one has been imported. */
function noPlacesWhy(){
  const p = (CHOICES || {}).places || {};
  if (!p.table)
    return "No place table has been imported, so coordinates have no names yet - "
         + "run Import places.";
  if (!p.located)
    return S.noLocationYet;
  return "";
}

function pickFrom(key, name, now, attr){
  /* A menu of what is there, with how many - and, when something is set that
     the library no longer holds, that value is still in the list rather than
     silently becoming "any". */
  const rows = ((CHOICES || {})[key] || []).slice();
  if (!rows.length && (key === "city" || key === "country")){
    const why = noPlacesWhy();
    // Said once. The same paragraph twice, side by side, reads as two problems.
    if (why) return `<small class="note fnote">${key === "country" ? esc(why)
      : "Needs the same place table."}</small>`;
  }
  if (now && !rows.some(r => String(r.name) === String(now)))
    rows.unshift({name: now, count: 0, label: now + " (nothing has it now)"});
  return `<select data-${attr}="${esc(name)}">
    <option value="">any</option>
    ${rows.map(r => `<option value="${esc(r.name)}"${
      String(r.name) === String(now) ? " selected" : ""}>${esc(r.label || r.name)}${
      r.count ? ` (${num(r.count)})` : ""}</option>`).join("")}</select>`;
}

function filterField(key, label, kind, now, attr){
  now = now == null ? "" : String(now);
  if (kind.startsWith("from:")){
    /* A note where the menu would be sits UNDER the label, as an option's
       note does on a feature's form - not run into it ("CountryNo place
       table..."), which read as one long label. */
    const got = pickFrom(kind.slice(5), key, now, attr);
    return got.startsWith("<small")
      ? `<div class="fwrap"><label>${esc(label)}</label>${got}</div>`
      : `<label>${esc(label)}${got}</label>`;
  }
  if (kind.startsWith("choice:")){
    const opts = kind.slice(7).split(",");
    /* A value set elsewhere that the menu does not offer - "taken,camera" from
       a chart cell that is both - stays in it, rather than the menu showing
       "any" and the next Show these dropping it. */
    if (now && opts.indexOf(now) < 0) opts.push(now);
    return `<label>${esc(label)}
      <select data-${attr}="${esc(key)}">${opts.map(o =>
        `<option value="${esc(o)}"${o === now ? " selected" : ""}
          >${o ? esc((CHOICE_WORDS[key] || {})[o] || o) : "any"}</option>`).join("")}</select></label>`;
  }
  return `<label>${esc(label)}
    <input data-${attr}="${esc(key)}" type="${kind === "date" ? "date"
      : kind === "number" ? "number" : "text"}" value="${esc(now)}"></label>`;
}

function anyFilter(){ return filterCount() > 0; }

function filterCount(){
  return Object.entries(FILTER)
    .filter(([k, v]) => v !== "" && v != null && k !== "name").length;
}

async function filterPanel(){
  const box = document.getElementById("filters");
  if (!box) return;
  if (!box.hidden){ box.hidden = true; return; }
  await loadChoices();
  box.hidden = false;
  box.innerHTML = `<div class="card"><b>Narrow it down</b>
    <span class="note"> - the same criteria Search uses, offering what your
      library really holds</span>
    <div class="note" id="photosreads">${esc(READS_INDEX)}</div>
    <div class="filtgrid">${FILTERS.map(([key, label, kind]) =>
      filterField(key, label, kind, FILTER[key], "f")).join("")}</div>
    <div class="act" style="margin-top:12px">
      <button onclick="applyFilters()">Show these</button>
      <button class="ghost" onclick="clearFilters()">Clear</button>
      <button class="ghost" onclick="keepAsAlbum()">Keep as an album</button>
      <button class="ghost" id="searchinstead" onclick="searchInstead()"
        >${icon("find")} Search a folder instead</button>
    </div></div>`;
  box.querySelectorAll("input,select").forEach(el =>
    el.addEventListener("keydown", e => { if (e.key === "Enter") applyFilters(); }));
}

function applyFilters(){
  const box = document.getElementById("filters");
  const was = FILTER.name;
  FILTER = {};
  if (was) FILTER.name = was;
  box.querySelectorAll("[data-f]").forEach(el => {
    const v = String(el.value || "").trim();
    if (v) FILTER[el.dataset.f] = v;
  });
  ALBUM = "";
  drawPhotos();
}

function clearFilters(){
  FILTER = {};
  ALBUM = "";
  drawPhotos();
}

function drawQuick(){
  const box = document.getElementById("quickchips");
  if (!box) return;
  const now = filterKey();
  box.innerHTML = QUICK.map(([key, label]) =>
    `<button type="button" class="fchip${now === key && !ALBUM ? " on" : ""}"
      onclick="quickPick('${key}')">${esc(label)}</button>`).join("")
    + (ALBUM ? `<button type="button" class="fchip on"
        onclick="quickPick('')">${esc(albumTitle(ALBUM))} ${icon("cross")}</button>` : "");
}

function quickPick(key){
  ALBUM = "";
  FILTER = {};
  for (const bit of key.split("&")){
    if (!bit) continue;
    const [k, v] = bit.split("=");
    FILTER[k] = v;
  }
  drawQuick();
  loadShots(true);
}

function shotQuery(offset){
  const bits = [`offset=${offset}`, `limit=240`, `by=${VIEWBY}`];
  if (ALBUM) bits.push("album=" + encodeURIComponent(ALBUM));
  else for (const [k, v] of Object.entries(FILTER))
    if (v !== "" && v != null) bits.push(`${k}=${encodeURIComponent(v)}`);
  return bits.join("&");
}

async function loadShots(reset){
  /* One grid, two ways of filling it. In the folder view the photographs are
     the ones in the folder you are standing in, which is a different question
     and a different endpoint - so it is asked there rather than by passing a
     flag through everything. */
  if (folderBrowsing()) return loadInside(reset);
  /* A next page waits for the one already out; a fresh ask (a new search, a
     new filter) goes at once and the older answer is thrown away when it
     lands, so what is on screen is always what was asked last. */
  if (LOADING && !reset) return;
  const my = ++SHOTREQ;
  LOADING = true;
  if (reset){ SHOTS = []; OFFSET = 0; MORE = true; pickClear(true); }
  const tiles = document.getElementById("tiles");
  if (tiles && reset) tiles.innerHTML = reading();
  let page;
  try{
    page = await (await fetch("api/timeline?" + shotQuery(OFFSET))).json();
  }catch(e){
    if (my !== SHOTREQ) return;
    LOADING = false;
    if (tiles && reset) tiles.innerHTML = couldNotReach("");
    return;
  }
  if (my !== SHOTREQ) return;
  if (page.error){
    if (tiles) tiles.innerHTML = `<div class="card bad">${esc(page.error)}</div>`;
    LOADING = false; return;
  }
  IDX = page.state || IDX;
  HIDDEN = page.hidden || [];
  drawHideChip();
  TOTAL = page.total || 0;
  GROUPS = page.groups || [];
  SHOTS = reset ? (page.items || []) : SHOTS.concat(page.items || []);
  OFFSET = SHOTS.length;
  MORE = SHOTS.length < TOTAL;
  LOADING = false;
  drawShots();
  watchBottom();
}

function drawShots(){
  const tiles = document.getElementById("tiles");
  if (!tiles) return;
  const said = document.getElementById("shotsaid");
  if (said && folderBrowsing()){
    const kids = ((WALL && WALL.folders) || []).length;
    const where = (WALL && WALL.crumbs && WALL.crumbs.length)
      ? WALL.crumbs[WALL.crumbs.length - 1].name : "your library";
    said.textContent = (kids ? say("wallSaid", {folders: kids}) : "")
      + (kids && TOTAL ? " and " : "")
      + (TOTAL ? say("wallPhotos", {n: TOTAL}) : (kids ? "" : "nothing here"))
      + ` in ${where}` + (DEEPER ? ", and everything below it" : "");
  }
  else if (said) said.textContent = TOTAL
    ? count(TOTAL, "photo")
      + (SHOTS.length < TOTAL ? ` - showing the newest ${num(SHOTS.length)}` : "")
      + (IDX.building ? ", and still reading" : "")
    : (IDX.building ? "Still reading the library..." : "Nothing matches.");
  if (!SHOTS.length){
    const kids = ((WALL && WALL.folders) || []).length;
    tiles.innerHTML = (folderBrowsing() && kids)
      ? ""                       // the folders above ARE what is here
      : (folderBrowsing()
         ? nothingHere({icon: "folder", title: "Nothing in this folder",
                        said: S.folderEmpty,
                        acts: [{label: "Everything below it",
                                go: "goDeeper(true)"},
                               {label: "Up one folder",
                                go: "goFolder('" + quoted(
                                  (WALL && WALL.crumbs && WALL.crumbs.length > 1)
                                    ? WALL.crumbs[WALL.crumbs.length - 2].path : "")
                                  + "')"}]})
         : emptyGrid());
    drawScrub();
    return;
  }
  /* In a folder you are STANDING IN, every photograph is in that folder - a
     heading over them saying so is the folder's own name, repeated. */
  if (folderBrowsing() && !DEEPER){
    tiles.innerHTML = `<div class="shots">`
      + SHOTS.map(one => shotHtml(one)).join("") + `</div>`;
    drawScrub();
    drawPickBar();
    return;
  }
  /* Standing in a folder with "Everything below" on, the headings are the
     folders underneath - and the counts are of what is on this screen, because
     GROUPS belongs to the timeline and is not asked for here. */
  const tally = {};
  if (folderBrowsing())
    for (const one of SHOTS) tally[one.group] = (tally[one.group] || 0) + 1;
  let html = "", group = null;
  for (const one of SHOTS){
    if (one.group !== group){
      if (group !== null) html += `</div>`;
      group = one.group;
      const m = GROUPS.find(x => x.key === group) || {};
      const q = quoted(group);
      const name = folderBrowsing()
        ? (String(group).startsWith(WHERE + "/") || String(group).startsWith(WHERE + "\\")
            ? String(group).slice(WHERE.length + 1) : (m.label || group))
        : (m.label || group);
      html += `<div class="monthrow"><b title="${esc(group)}">${esc(name)}</b>
        <span>${num(folderBrowsing() ? (tally[group] || 0) : (m.count || 0))}</span>
        <button type="button" onclick="pickGroup('${q}')">Select all</button>
        ${VIEWBY === "folder" ? `<button type="button"
           onclick="useFolder('${q}')">Use this folder</button>
         <button type="button" onclick="hideFolder('${q}')"
           title="Leave this folder out of the Photos screen">Hide</button>` : ""}</div>
        <div class="shots">`;
    }
    html += shotHtml(one);
  }
  html += `</div>`;
  tiles.innerHTML = html;
  drawScrub();
  drawPickBar();
}

/* ------------------------------------------------- nothing here, said once

   Five screens had five ways of saying the same five things: there is no
   library yet, it is still being read, nothing matches, it could not be
   reached, it was not allowed. Each was written where it was needed, which is
   how an app ends up with one empty state that offers a way out and another
   that is a grey sentence in the middle of a white page.

   One component. A glyph, a sentence, and - the part that matters - the way
   out, because an empty screen that does not say what to do next is a dead
   end wearing an explanation. */
function nothingHere(what){
  what = what || {};
  const acts = (what.acts || []).filter(Boolean);
  return `<div class="card nothing">
    <span class="nicon">${icon(what.icon || "photos")}</span>
    <b>${esc(what.title || "Nothing here")}</b>
    ${what.said ? `<div class="note">${esc(what.said)}</div>` : ""}
    ${acts.length ? `<div class="act">${acts.map((a, i) =>
      `<button type="button" class="${i ? "ghost" : ""}"
        onclick="${a.go}">${esc(a.label)}</button>`).join("")}</div>` : ""}
  </div>`;
}

/* The three that every screen over the library can be in. Said the same way
   wherever they happen, because they are the same three states. */
function noLibraryYet(){
  return nothingHere({
    icon: "photos", title: "No library yet",
    said: S.noLibrary,
    acts: [{label: "Open Setup", go: "openFeature('setup')"},
           {label: "Build a sample library", go: "openFeature('demo')"}]});
}

function stillReading(){
  return nothingHere({
    icon: "again", title: "Still reading your library",
    said: say("stillReading", {done: IDX.done || 0, total: IDX.total || 0}),
    acts: []});
}

/* The one way a screen says it is waiting. Every screen that waits also
   answers a failure with couldNotReach() below, so "Reading..." is never left
   on a screen for ever. */
function reading(){ return `<div class="note">Reading...</div>`; }

function couldNotReach(what){
  return nothingHere({
    icon: "warn", title: "Could not reach the app",
    said: (what ? what + " " : "")
        + "The page is open but the app did not answer. It may be restarting.",
    acts: [{label: "Try again", go: "location.reload()"}]});
}

function emptyGrid(){
  if (IDX.building) return stillReading();
  if (!IDX.photos) return noLibraryYet();
  return nothingHere({
    icon: "find", title: "Nothing matches",
    said: "Nothing in the library answers to that.",
    acts: [{label: "Show everything", go: "quickPick('')"}]});
}

function shotHtml(one, small){
  const q = quoted(one.path);
  const stars = one.stars ? "★".repeat(one.stars) : "";
  const marks = (stars || one.colour)
    ? `<div class="marks">${one.colour
        ? `<span class="dot" style="background:${colourOf(one.colour)}"
             title="${esc(one.colour)} label"></span>` : ""}
       <span class="st">${stars}</span></div>` : "";
  /* What a screen reader says for the tile: the name, and the marks that are
     otherwise only a row of glyphs and a coloured dot. */
  const named = [String(one.path).split(/[\\/]/).pop(),
                 one.kind === "video" ? "clip" : "",
                 one.stars ? count(one.stars, "star") : "",
                 one.colour ? `${one.colour} label` : ""].filter(Boolean).join(", ");
  return `<a class="shot${PICK.has(one.path) ? " picked" : ""}" data-p="${esc(one.path)}"
    href="#" aria-label="${esc(named)}" onclick="return tileClick(event, '${q}')">
    <img loading="lazy" alt="" src="${thumbSrc(one.path, "s", one.when)}"
      onerror="shotNoPic(this)">
    <span class="tick" onclick="return pickClick(event, '${q}')">${icon("check")}</span>
    ${one.kind === "video" ? `<span class="vid">video</span>` : ""}
    ${marks}</a>`;
}

/* A clip with no frame to show, a RAW nothing can open, a file that has gone:
   a glyph, not a browser's broken-image icon, which reads as the app failing
   rather than as this file having no picture. */
function shotNoPic(img){
  const tile = img.closest(".shot");
  if (!tile) return;
  img.remove();
  tile.classList.add("nopic");
  tile.insertAdjacentHTML("afterbegin",
    `<span class="nopicmark">${icon(tile.querySelector(".vid") ? "film" : "image")}</span>`);
}

function coverNoPic(img){
  img.remove();                      // a clip has no frame; say so with a glyph
}

/* A path inside an onclick="" attribute. Windows separators and apostrophes
   both have to survive going through HTML and then through JavaScript, and a
   folder called "Mum's" was enough to break the whole row. */
function quoted(text){
  return esc(String(text == null ? "" : text)
    .replace(/\\/g, "\\\\").replace(/'/g, "\\'"));
}

/* The five label colours are tokens in the stylesheet (--label-*), so the
   grid, the menus and the viewer cannot drift to two different yellows. */
function colourOf(name){
  const c = String(name || "").toLowerCase();
  return ["red", "yellow", "green", "blue", "purple"].includes(c)
    ? `var(--label-${c})` : "var(--dim)";
}

function drawScrub(){
  const box = document.getElementById("scrub");
  if (!box) return;
  if (GROUPS.length < 2){ box.innerHTML = ""; return; }
  let html = "", year = "";
  for (const m of GROUPS){
    const q = quoted(m.key);
    if (VIEWBY === "folder"){
      html += `<button type="button" onclick="jumpGroup('${q}')"
        title="${esc(m.label)} - ${num(m.count)}">${esc(
          String(m.label).split(/[\\/]/).pop().slice(0, 11))}
        <span style="opacity:.55">${num(m.count)}</span></button>`;
      continue;
    }
    const y = m.key.slice(0, 4);
    if (y !== year){ year = y; html += `<div class="yr">${esc(year)}</div>`; }
    html += `<button type="button" onclick="jumpGroup('${q}')"
      title="${esc(m.label)} - ${num(m.count)}">${esc(m.label.split(" ")[0].slice(0, 3))}
      <span style="opacity:.55">${num(m.count)}</span></button>`;
  }
  box.innerHTML = html;
}

/* Jumping to a month is a new WINDOW, not a scroll: the grid holds a page at a
   time, and scrolling eighty thousand tiles to reach 2014 is not navigation.
   Where that month starts is arithmetic on the counts the server already sent. */
async function jumpGroup(key){
  let before = 0;
  for (const m of GROUPS){
    if (m.key === key) break;
    before += m.count;
  }
  OFFSET = before;
  SHOTS = [];
  const my = ++SHOTREQ;
  LOADING = true;
  const tiles = document.getElementById("tiles");
  if (tiles) tiles.innerHTML = reading();
  let page;
  try{
    page = await (await fetch("api/timeline?" + shotQuery(before))).json();
  }catch(e){
    if (my !== SHOTREQ) return;
    LOADING = false;
    if (tiles) tiles.innerHTML = couldNotReach("");
    return;
  }
  if (my !== SHOTREQ) return;
  LOADING = false;
  SHOTS = page.items || [];
  GROUPS = page.groups || GROUPS;
  TOTAL = page.total || TOTAL;
  OFFSET = before + SHOTS.length;
  MORE = OFFSET < TOTAL;
  drawShots();
  window.scrollTo({top: 0});
  watchBottom();
}

let bottomWatch = null;
function watchBottom(){
  const foot = document.getElementById("more");
  if (!foot) return;
  if (bottomWatch) bottomWatch.disconnect();
  if (!MORE) return;
  bottomWatch = new IntersectionObserver(es => {
    if (es.some(e => e.isIntersecting) && MORE && !LOADING) loadShots(false);
  }, {rootMargin: "600px"});
  bottomWatch.observe(foot);
}
