
/* ------------------------------------------------- folders you can walk into

   The folder view was the timeline sorted differently: every photograph in the
   library, in one list, with a heading each time the folder changed. Eighty
   thousand tiles to scroll past to reach the shoot you wanted, no way to see
   that a folder HAS folders in it until you had scrolled through everything,
   and nothing you could press to get to the folder itself.

   A folder view should be a place. Where you are, the folders that are here
   with a cover and a count, and the photographs that are in THIS folder - with
   the way down into the next one, and the way out to the file explorer where
   the files themselves live. */

let WHERE = "";              // the folder the grid is standing in
let DEEPER = false;          // everything below here, rather than what is here
let WALL = null;             // the last answer, kept so a redraw costs nothing

function folderBrowsing(){ return VIEWBY === "folder" && !ALBUM; }

async function loadInside(reset){
  if (!folderBrowsing()) return;
  if (LOADING && !reset) return;           // the same rule as loadShots
  const my = ++SHOTREQ;
  LOADING = true;
  if (reset){ SHOTS = []; OFFSET = 0; MORE = true; pickClear(true); }
  const tiles = document.getElementById("tiles");
  if (tiles && reset) tiles.innerHTML = reading();
  const bits = [`offset=${OFFSET}`, `limit=240`,
                `deep=${DEEPER ? 1 : 0}`,
                WHERE ? "path=" + encodeURIComponent(WHERE) : ""];
  for (const [k, v] of Object.entries(FILTER))
    if (v !== "" && v != null) bits.push(`${k}=${encodeURIComponent(v)}`);
  let got;
  try{ got = await (await fetch("api/inside?" + bits.filter(Boolean).join("&"))).json(); }
  catch(e){
    if (my !== SHOTREQ) return;
    LOADING = false;
    if (tiles && reset) tiles.innerHTML = couldNotReach("");
    return;
  }
  if (my !== SHOTREQ) return;
  if (got.error){
    if (tiles) tiles.innerHTML = couldNotReach(got.error);
    LOADING = false;
    return;
  }
  WALL = got;
  WHERE = got.where || "";
  IDX = got.state || IDX;
  HIDDEN = got.hidden || [];
  drawHideChip();
  TOTAL = got.total || 0;
  SHOTS = reset ? (got.items || []) : SHOTS.concat(got.items || []);
  OFFSET = SHOTS.length;
  MORE = SHOTS.length < TOTAL;
  LOADING = false;
  /* The month rail belongs to the timeline. Standing in a folder, the months
     of the whole library are not a way to anywhere. */
  GROUPS = [];
  drawScrub();
  drawWhere();
  drawWall();
  drawShots();
  watchBottom();
}

function drawWhere(){
  const bar = document.getElementById("wherebar");
  if (!bar) return;
  if (!folderBrowsing() || !WALL){ bar.hidden = true; return; }
  bar.hidden = false;
  const crumbs = WALL.crumbs || [];
  const up = crumbs.length > 1 ? crumbs[crumbs.length - 2].path : "";
  bar.innerHTML = `<div class="wherebar">
    <button type="button" class="ghost" ${(up || !WALL.at_top) ? "" : "disabled"}
      onclick="goFolder('${quoted(up)}')" title="Up one folder">${icon("back")}</button>
    <span class="crumbs">
      <button type="button" class="crumb" onclick="goFolder('')">All folders</button>
      ${crumbs.map((c, i) => `<span class="sep">/</span>
        <button type="button" class="crumb${i === crumbs.length - 1 ? " on" : ""}"
          onclick="goFolder('${quoted(c.path)}')">${esc(c.name)}</button>`).join("")}
    </span>
    <span class="spacer"></span>
    ${WHERE ? `<button type="button" class="fchip${DEEPER ? " on" : ""}"
      onclick="goDeeper(!DEEPER)"
      title="${esc(S.deeperTip)}"
      >${icon("layers")} Everything below</button>
    <button type="button" class="fchip" onclick="openInExplorer('${quoted(WHERE)}')"
      title="The same folder, with the files themselves"
      >${icon("folder")} File explorer</button>
    <button type="button" class="fchip" onclick="useFolder('${quoted(WHERE)}')"
      title="${esc(S.useFolderTip)}">${icon("tools")} Use this folder</button>` : ""}
  </div>`;
}

function drawWall(){
  const wall = document.getElementById("folderwall");
  if (!wall) return;
  const folders = (WALL && WALL.folders) || [];
  if (!folderBrowsing() || !folders.length){ wall.hidden = true; return; }
  wall.hidden = false;
  wall.innerHTML = `<div class="wall">` + folders.map(f => {
    const n = f.photos + f.videos;
    return `<div class="fold">
      <button type="button" class="foldcard" onclick="goFolder('${quoted(f.path)}')">
        <span class="cover">${f.cover
          ? `<img loading="lazy" alt="" src="${thumbSrc(f.cover, "m", f.cover_when)}"
               onerror="coverNoPic(this)">`
          : `<span class="nocover">${icon("folder")}</span>`}</span>
        <span class="who"><b>${esc(f.name)}</b>
          <span>${n ? say("nPhotos", {n: n}) : "nothing in it yet"}${
            f.raws ? ` · ${num(f.raws)} RAW` : ""}</span></span>
      </button>
      <button type="button" class="foldmore" title="What to do with this folder"
        onclick="wallMenu('${quoted(f.path)}')">${icon("menu")}</button>
    </div>`;
  }).join("") + `</div>`;
}

/* The card's own menu: everything "Use this folder" offers, plus the one thing
   that only makes sense from here - leaving this folder out of the Photos
   screen without touching the index or the files. */
function wallMenu(path){
  const q = quoted(path);
  useFolder(path);
  const box = document.querySelector(".pmenu");
  if (!box) return;
  /* First, not last: the twelve features below are the same twelve everywhere
     in the app, and this is the one thing that only makes sense standing in
     front of this card. At the bottom of a list that scrolls, it is hidden. */
  const head = box.querySelector(".mhead");
  const row = `<button class="vopt" onclick="closePageMenu(); hideFolder('${q}')"
       title="It stays in the library and in the index - it just stops filling
              up the Photos screen">${icon("folder-x")} Leave out of Photos</button>
     <div class="mline"></div>`;
  if (head) head.insertAdjacentHTML("afterend", row);
  else box.insertAdjacentHTML("afterbegin", row);
}

function goFolder(path){
  WHERE = path || "";
  DEEPER = false;
  SHOTS = []; OFFSET = 0; MORE = true;
  loadInside(true);
}

function goDeeper(on){
  DEEPER = !!on;
  SHOTS = []; OFFSET = 0; MORE = true;
  loadInside(true);
}

/* The folder you are looking at, opened where the files themselves are. The
   one thing the old folder view could not do at all. */
function openInExplorer(path){
  openFeature("files", {folders: [path || WHERE]});
}
