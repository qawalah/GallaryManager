
/* ------------------------------------------------------------------ one photo

   The detail view is the viewer this app already has - the stars, the colours,
   the tags, the histogram, the shot details, the swipe, the delete - with a
   panel beside it carrying what the index knows and what is on the disk next to
   it. One viewer, not two: a second one would be the two-tooltip-engines
   mistake wearing a bigger coat. */

let INFO = {tab: "details", path: "", data: null};

function openShot(path){
  peek(path, SHOTS.map(s => s.path));
  infoOpen(wantsInfo());
  // The panel follows the viewer rather than being told once - see the wrapper
  // around `viewerShow` at the bottom of this file. Telling it here as well
  // would read the same photograph twice on the way in.
  followShot();
}

function wantsInfo(){
  try{ return localStorage.getItem("pm-info") !== "no" && !isPhone(); }
  catch(e){ return !isPhone(); }
}

/* THE PANEL BELONGS TO THE VIEWER, NOT TO ONE WAY IN.

   It was built by the one caller that opened the viewer from the Photos grid,
   so a photograph opened from the file explorer, from a folder you had walked
   into, or from a plan got a viewer with no panel AND no button to ask for one.
   The details were not hidden - there was no way to reach them at all.

   Building it is now the viewer's own business, done once per viewer, wherever
   it was opened from. */
function infoBuild(){
  const v = document.getElementById("viewer");
  if (!v) return null;
  let box = document.getElementById("vinfo");
  if (box) return box;
  box = document.createElement("aside");
  box.id = "vinfo";
  box.className = "vinfo";
  v.appendChild(box);
  const top = v.querySelector(".vtop .vmenu");
  if (top){
    const b = document.createElement("button");
    b.type = "button";
    b.className = "vbtn";
    b.id = "vinfob";
    b.title = S.viewerInfoTip;
    /* Its own glyph: the bar already has an (i) for the shot details, and two
       identical buttons beside each other is a guess every single time. */
    b.innerHTML = icon("panel");
    b.onclick = e => { e.stopPropagation(); infoOpen(!v.classList.contains("withinfo")); };
    top.parentNode.insertBefore(b, top);
  }
  return box;
}

function infoReady(){
  const v = document.getElementById("viewer");
  if (!v) return;
  infoBuild();
  if (v.dataset.infoset) return;           // only the first frame decides
  v.dataset.infoset = "1";
  v.classList.toggle("withinfo", wantsInfo());
}

function infoOpen(on){
  const v = document.getElementById("viewer");
  if (!v) return;
  infoBuild();
  v.dataset.infoset = "1";
  v.classList.toggle("withinfo", !!on);
  try{ localStorage.setItem("pm-info", on ? "yes" : "no"); }catch(e){}
  if (on) drawInfo();
}

async function loadInfo(path){
  INFO.path = path;
  INFO.data = null;
  drawInfo();
  try{
    const got = await (await fetch("api/item?path=" + encodeURIComponent(path))).json();
    if (INFO.path !== path) return;          // moved on while it was fetching
    INFO.data = got;
  }catch(e){
    if (INFO.path !== path) return;          // and the same for a failure
    INFO.data = {error: "could not be read"};
  }
  if (INFO.path !== path) return;
  drawInfo();
}

/* THE PANEL FOLLOWS THE PHOTOGRAPH.

   It was told what to show once, when the viewer opened, and never again - so
   swiping to the next frame left the details, the location and the file list of
   the one before it on screen, under the right picture. Everything about that
   is wrong in the worst way: it does not look broken, it looks like the answer. */
function followShot(){
  if (!document.getElementById("viewer")) return;
  const path = (typeof viewerPath === "function") ? viewerPath() : "";
  if (!path) return;
  if (path === INFO.path && INFO.data) return;    // already showing this one
  loadInfo(path);
}

function infoTab(which){ INFO.tab = which; drawInfo(); }

function drawInfo(){
  const box = document.getElementById("vinfo");
  if (!box) return;
  const d = INFO.data;
  const name = basename(INFO.path || "");
  const tabs = [["details", "Details"], ["location", "Location"],
                ["files", "Files"], ["history", "History"]];
  box.innerHTML = `
    <h3>${esc(name)}</h3>
    <div class="when">${d && d.taken ? esc(d.taken) : "no capture time in the file"}</div>
    ${d ? infoMarks(d) : ""}
    <div class="dtabs">${tabs.map(([k, label]) =>
      `<button type="button" class="${INFO.tab === k ? "on" : ""}"
        onclick="infoTab('${k}')">${label}</button>`).join("")}</div>
    <div id="infobody">${d ? infoBody(d) : reading()}</div>`;
  if (INFO.tab === "location" && d && d.lat != null && typeof drawMap === "function"){
    const holder = document.getElementById("infomap");
    if (holder) drawMap([[d.lat, d.lon, name]]);
  }
}

function infoMarks(d){
  const stars = [1, 2, 3, 4, 5].map(n =>
    `<button type="button" class="${(d.stars || 0) >= n ? "on" : ""}"
      onclick="viewerStars(${n})" aria-label="${esc(say("nStars", {n: n}))}">★</button>`).join("");
  const cols = ["red", "yellow", "green", "blue", "purple"].map(c =>
    `<button type="button" class="${d.colour === c ? "on" : ""}"
      style="background:${colourOf(c)}" title="${c}"
      onclick="viewerColour('${c}', false)"></button>`).join("");
  return `<div class="dstars">${stars}</div><div class="dcols">${cols}</div>`;
}

function infoBody(d){
  if (d.error) return `<div class="note">${esc(d.error)}</div>`;
  if (INFO.tab === "details"){
    const rows = [
      ["Camera", d.camera || "not said"],
      ["Lens", d.lens || "not said"],
      ["ISO", d.iso ? num(d.iso) : "-"],
      ["Aperture", d.fnumber ? "f/" + d.fnumber : "-"],
      ["Shutter", d.shutter || "-"],
      ["Focal length", d.focal ? d.focal + "mm"
        + (d.focal35 ? ` (${d.focal35}mm full-frame)` : "") : "-"],
      ["Kind", d.kind || "-"],
      ["Size", bytes(d.size || 0)],
      ["Tags", (d.tags || []).join(", ") || "none"],
      ["Folder", shortText(d.folder || "")],
    ];
    return `<div class="facts">` + rows.map(([k, v]) =>
      `<div>${esc(k)}</div><div>${esc(String(v))}</div>`).join("") + `</div>`;
  }
  if (INFO.tab === "location"){
    if (d.lat == null) return `<div class="note">${esc(S.viewerNoLocation)}</div>
      <div class="act" style="margin-top:10px">
        <button class="ghost" onclick="viewerClose();openFeature('geotag')">Open Geotag</button>
      </div>`;
    return `<div class="facts"><div>Latitude</div><div>${d.lat}</div>
      <div>Longitude</div><div>${d.lon}</div></div>
      <div class="dmini"><div class="pmmap" id="pmmap" style="height:100%"></div></div>
      <div class="act" style="margin-top:10px">
        <button class="ghost" onclick="viewerUnlocate('${quoted(d.path)}')"
          >Strip the location</button></div>`;
  }
  if (INFO.tab === "files"){
    const files = d.files || [];
    return files.map(f => `<div class="rel"><span class="what">${esc(f.what)}</span>
      <span class="nm" title="${esc(f.path)}">${esc(basename(f.path))}</span>
      <span class="note">${bytes(f.size || 0)}</span></div>`).join("")
      + `<div class="note" style="margin-top:9px">${esc(S.viewerFilesNote)}</div>`;
  }
  return `<div class="note">${esc(S.viewerHistory)}</div>
    <div class="act" style="margin-top:10px">
      <button class="ghost" onclick="viewerClose();openFeature('history')"
        >Open History</button></div>`;
}
