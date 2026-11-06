
/* ------------------------------------------------------------------- the home

   What is in there, measured already. No button, because there is nothing to
   press: the numbers were counted when the index was built and they say how old
   they are. The newest photographs are on it because a library you cannot see
   is a filing cabinet.

   4.0 puts them first. The photographs are hung as plates along the top, the
   newest one twice the size of the rest, and the four facts are printed in a
   ruled row under them, so the screen opens on the library rather than on its
   weight in kilobytes. */

async function drawHomeScreen(){
  const stage = document.getElementById("stage");
  if (!SUMS) stage.innerHTML = `<div class="phead"><h2>Home</h2></div>
    ${reading()}`;
  let got = SUMS;
  if (!got){
    try{ got = SUMS = await (await fetch("api/dashboard")).json(); }
    catch(e){ stage.innerHTML = couldNotReach(""); return; }
  }
  if (SCREEN !== "home") return;
  const o = got.overview || {};
  const tiles = [
    ["Photos", num(o.photos || 0), say("homeVideos", {n: o.videos || 0}), "blue", "photos"],
    ["Everything weighs", bytes(o.size || 0), say("homeRaws", {n: o.raws || 0}), "", "layers"],
    ["With a location", shareOf(o.located, o.shown), `${num(o.located || 0)} of ${num(o.shown || 0)}`, "teal", "globe"],
    ["Rated", shareOf(o.rated, o.shown), `${num(o.rated || 0)} carry stars`, "amber", "star"],
  ];
  stage.innerHTML = `
    <div class="phead">
      <div><h2>Home</h2>
        <div class="sub">${got.measured ? `Counted ${esc(got.measured)}, from the index -
          nothing was opened.` : "Nothing indexed yet."}</div></div>
      <span class="spacer"></span>
      <div class="vtools">
        ${rereadButton()}
      </div>
    </div>
    <div class="indexing" id="idxbar" hidden></div>
    ${!IDX.photos && !IDX.building ? `<div class="card" id="homefirst">
      <b>No library yet</b>
      <div class="note">${esc(S.noLibrary)}</div>
      ${firstSteps()}</div>` : ""}
    <div class="homelatest"><div class="cardhead"><b>Latest</b>
        <span class="note">the newest thing in the library</span>
        <button type="button" class="fchip" onclick="goScreen('photos')"
          >${esc(S.seeAllPhotos)}</button></div>
      <div class="strip plates" id="homestrip"></div></div>
    <div class="bigtiles">${tiles.map(([k, v, n, tone, ico]) =>
      `<div class="bigtile ${tone}"><span class="k">${icon(ico)}${esc(k)}</span>
        <span class="v">${esc(v)}</span><span class="n">${esc(n)}</span></div>`).join("")}</div>
    ${(got.tiles || []).length || (got.charts || []).length ? `
      <div class="homesec"><h3>Your dashboard</h3>
        <span class="note">arranged on the Library tab, counted from the index</span></div>
      <div id="homecharts"></div>` : ""}
    <div id="homefolders"></div>
    <div id="homeruns"></div>`;
  drawIndexing();
  drawFolderBoard();
  /* The four big tiles above already say these, so the dashboard's copies of
     them (and the two meters saying the same shares) are left out here - the
     same number twice on one screen, sometimes
     rounded two ways, made the page look as if it disagreed with itself. Its
     other tiles, and every chart, are still the ones arranged on Library. */
  const big = ["tile:photos", "tile:weight", "tile:rated", "tile:placed",
               "meter:rated", "meter:located"];
  const board = Object.assign({}, got,
    {tiles: (got.tiles || []).filter(t => !big.includes(t.widget)),
     done: (got.done || []).filter(m => !big.includes(m[3]))});
  if (document.getElementById("homecharts"))
    document.getElementById("homecharts").innerHTML = chartsCard({charts: board});
  const strip = document.getElementById("homestrip");
  if (strip){
    try{
      const page = await (await fetch("api/timeline?limit=12")).json();
      const items = page.items || [];
      strip.innerHTML = items.map(plateHtml).join("")
        || `<div class="note">Nothing indexed yet.</div>`;
      /* The lead plate is drawn at twice the size of the others, so it asks
         for the next size of thumbnail up rather than stretching a small one. */
      const lead = strip.querySelector(".shot img");
      if (lead && items[0]) lead.src = thumbSrc(items[0].path, "m", items[0].when);
    }catch(e){ strip.innerHTML = ""; }
  }
}

/* A plate and its wall label: the folder it hangs in, then its own name, then
   the day it was taken, a line each, the way a print is labelled on a gallery
   wall. On one line the day was the part a narrow plate cut off. */
function plateHtml(one){
  const parts = String(one.path).split(/[\\/]/);
  const where = parts.length > 1 ? parts[parts.length - 2] : "";
  const day = one.taken ? String(one.taken).slice(0, 10) : "";
  return `<figure class="plate">${shotHtml(one, true)}<figcaption>
    <b>${esc(where)}</b><span>${esc(one.name || parts[parts.length - 1])}</span>${
    day ? `<time datetime="${esc(day)}">${esc(day)}</time>` : ""}</figcaption></figure>`;
}

function bytes(n){
  n = +n || 0;
  const u = ["bytes", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1){ n /= 1024; i++; }
  return i ? `${n.toFixed(1)} ${u[i]}` : `${n} bytes`;
}
function shareOf(part, whole){
  return whole ? Math.round(100 * (+part || 0) / whole) + "%" : "-";
}
