
/* The Timeline screen is gone. It listed every month with a count and did
   nothing the grid does not: those months are the grid's own headings, and the
   rail down its side jumps to any of them. A screen whose only content was a
   way to reach another screen is a step, not a feature. */

/* ----------------------------------------------------------------- the places

   The same map the plans draw, over the whole library. Pins are grouped by
   where they are, named where a place table has been imported and left as
   coordinates where it has not - which is the honest answer, not an empty map. */

async function drawPlaces(){
  const stage = document.getElementById("stage");
  stage.innerHTML = `<div class="phead"><div><h2>Places</h2>
    <div class="sub" id="placesaid">Reading...</div></div>
    <span class="spacer"></span>
    <div class="vtools">
      <button type="button" class="fchip"
        onclick="goScreen('photos', {filter: {located: 'no'}, album: ''})"
        >${esc(S.photosNoLocation)}</button></div></div>
    <div class="indexing" id="idxbar" hidden></div>
    <div id="placemap"><div class="pmmap" id="pmmap" style="height:100%"></div></div>
    <div class="note" style="margin:8px 2px 0">${esc(S.placesHint)}</div>
    <div class="placelist" id="placelist"></div>`;
  drawIndexing();
  let got;
  try{ got = await (await fetch("api/places?zoom=4&named=1")).json(); }
  catch(e){
    if (SCREEN !== "places") return;
    const said = document.getElementById("placesaid");
    if (said) said.textContent = "";
    const map = document.getElementById("placemap");
    if (map) map.outerHTML = couldNotReach("");
    return;
  }
  if (SCREEN !== "places") return;
  const said = document.getElementById("placesaid");
  const pins = got.pins || [];
  if (said) said.textContent = pins.length
    ? say("placesSaid", {n: got.located || 0, places: pins.length})
    : "Nothing in the library carries a location yet.";
  if (!pins.length){
    document.getElementById("placemap").outerHTML = IDX.photos
      ? nothingHere({
          icon: "map", title: "Nothing carries a location yet",
          said: S.placesNone,
          acts: [{label: "Open Geotag", go: "openFeature('geotag')"},
                 {label: "Pin a place", go: "openFeature('pin')"}]})
      : noLibraryYet();
    return;
  }
  /* The map is page.py's - tiles from OpenStreetMap to the browser, dots on
     top, no library. One map in the app, used two ways: a plan draws a still
     picture of where its rows would land, and this one you can go and look
     around. */
  PLACEPINS = pins;
  drawMap(pins.map(p => [p.lat, p.lon, say("nPhotos", {n: p.count}), p.count]),
          {interactive: true, pick: one => openPlace(one[0], one[1])});
  const list = document.getElementById("placelist");
  list.innerHTML = (got.named || []).map(one => `
    <button type="button" class="placecard" onclick="openPlace(${one.lat}, ${one.lon})">
      <img loading="lazy" alt="" src="${thumbSrc(one.cover, "s")}"
        onerror="coverNoPic(this)">
      <span><b>${esc(one.name)}</b><span>${say("nPhotos", {n: one.count})}</span></span>
    </button>`).join("");
}

let PLACEPINS = [];

/* A place opens as a SEARCH, because that is what it is: everything within a
   few kilometres of here. It used to hand the grid "has a location", which
   showed every located photograph in the library and was the same answer
   wherever you pressed - a pin that does nothing you can tell. */
function openPlace(lat, lon, km){
  goScreen("photos", {album: "", filter: {
    near_lat: Number(lat).toFixed(6), near_lon: Number(lon).toFixed(6),
    within_km: km || PLACE_KM}});
}

const PLACE_KM = 25;

/* ----------------------------------------------------------------- the albums */

let ALBUMS = [];

async function drawAlbums(){
  const stage = document.getElementById("stage");
  stage.innerHTML = `<div class="phead"><div><h2>Albums</h2>
    <div class="sub">Collections worked out from the library itself, so they are
      never out of date.</div></div>
    <span class="spacer"></span>
    <div class="vtools">
      <button type="button" class="fchip" onclick="albumMake()"
        >${icon("plus")} New album</button></div></div>
    <div class="indexing" id="idxbar" hidden></div>
    <div id="albummaker" hidden></div>
    <div class="fchips" id="albumaway" hidden></div>
    <div class="albums" id="albumgrid">${reading()}</div>`;
  drawIndexing();
  let got;
  try{ got = await (await fetch("api/albums")).json(); }
  catch(e){
    const box = SCREEN === "albums" && document.getElementById("albumgrid");
    if (box) box.innerHTML = `<div style="grid-column:1/-1">${couldNotReach("")}</div>`;
    return;
  }
  if (SCREEN !== "albums") return;
  ALBUMS = got.albums || [];
  AWAY = got.put_away || [];
  const box = document.getElementById("albumgrid");
  drawAwayLine();
  if (!ALBUMS.length && !AWAY.length){ box.innerHTML = emptyGrid(); return; }
  box.innerHTML = ALBUMS.map(a => `
    <div class="albumwrap">
    <button type="button" class="albumcard" onclick="openAlbum('${quoted(a.key)}')">
      <span class="cover"><img loading="lazy" alt=""
        src="${thumbSrc(a.cover, "m", a.cover_when)}" onerror="coverNoPic(this)">
        <span class="tag">${esc(a.why)}</span></span>
      <span class="who"><b>${esc(a.title)}</b>
        <span>${say("nPhotos", {n: a.count})}</span></span></button>
    <button type="button" class="albumx" onclick="albumAway('${quoted(a.key)}')"
      title="${a.mine ? "Forget this album" : "Put this album away"}">${icon("cross")}</button>
    ${a.mine ? `<button type="button" class="albumedit" title="Change what is in it"
      onclick="albumEdit('${quoted(a.key)}')">${icon("gear")}</button>` : ""}
    </div>`).join("")
    || `<div style="grid-column:1/-1">${nothingHere({
        icon: "album", title: "Every album is put away",
        said: "An album is a question about your library, and you have declined "
            + "to ask all of them. The line above brings any of them back.",
        acts: [{label: "Bring them all back", go: "sendAway([])"}]})}</div>`;
}

/* PUTTING AN ALBUM AWAY.

   The built-in albums are questions this app thinks are worth asking, which is
   not the same as thinking you should be asked them: a library with no video in
   it has a Videos album saying nothing, and "To develop" means nothing to
   somebody who does not develop. So any of them can go - and because an album
   IS a question rather than a list, nothing is deleted by going: the question
   is still there to be asked again, from the line under the grid.

   One made yourself is different in one way only, and it is said on the button:
   forgetting that one throws the question away too, because nothing else holds
   it. */
let AWAY = [];

async function albumAway(key){
  const one = ALBUMS.find(a => a.key === key) || {};
  if (one.mine){
    if (!await askSure({title: `Forget the album "${one.title}"?`,
                        body: S.albumForgetMine,
                        yes: "Forget it"})) return;
    await albumForget(one.title, true);
    return drawAlbums();
  }
  await sendAway(AWAY.map(a => a.key).concat([key]));
}

async function albumBack(key){
  await sendAway(AWAY.map(a => a.key).filter(k => k !== key));
}

async function sendAway(keys){
  try{
    await fetch("api/albums", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({hidden: keys})});
  }catch(e){ return toast("That did not reach the app", 4000); }
  drawAlbums();
}

function drawAwayLine(){
  const line = document.getElementById("albumaway");
  if (!line) return;
  line.hidden = !AWAY.length;
  if (!AWAY.length) return;
  line.innerHTML = `<span class="note">Put away:</span>
    ${AWAY.map(a => `<button type="button" class="fchip"
      onclick="albumBack('${quoted(a.key)}')"
      title="Ask this one again">${esc(a.title)} +</button>`).join("")}
    <button type="button" class="fchip" onclick="sendAway([])">All of them back</button>`;
}

/* ------------------------------------------------------- an album of your own

   An album here IS a question - "five stars, taken on the GH4, with no
   location" - asked again every time it is opened, which is why none of them
   can go stale. Making one is therefore the same act as asking: the criteria
   are the criteria Search uses and the grid filters use, because there is one
   idea in this app of what matches and three ways of writing it down would be
   three things to keep in step. */

async function albumMake(ask, was){
  const box = document.getElementById("albummaker");
  if (!box) return;
  if (!box.hidden && !ask){ box.hidden = true; return; }
  ask = ask || {};
  await loadChoices();
  box.hidden = false;
  box.innerHTML = `<div class="card"><b>${was ? "Change this album" : "A new album"}</b>
    <span class="note"> - anything the library knows; it is asked again every
      time the album is opened, so it can never be out of date</span>
    <label class="albumname">Call it
      <input id="albumname" type="text" value="${esc(was || "")}"
        placeholder="The wide ones from Spain" autocomplete="off"></label>
    <div class="filtgrid" id="albumasks">${FILTERS.map(([key, label, kind]) =>
      filterField(key, label, kind, ask[key], "a")).join("")}</div>
    <div class="note" id="albumsays" style="margin-top:10px">${esc(S.albumUnset)}</div>
    <div class="act" style="margin-top:12px">
      <button onclick="albumKeep('${quoted(was || "")}')">${
        was ? "Save it" : "Make the album"}</button>
      <button class="ghost" onclick="albumTry()">How many is that?</button>
      <button class="ghost" onclick="albumMake()">Cancel</button>
    </div></div>`;
  if (was) albumTry();
}

function albumAsk(){
  const out = {};
  document.querySelectorAll("#albumasks [data-a]").forEach(el => {
    const v = String(el.value || "").trim();
    if (v) out[el.dataset.a] = v;
  });
  return out;
}

/* Count it before you keep it. "412 photographs" is the difference between a
   criterion you meant and one that is a typo with a name on it. */
async function albumTry(){
  const said = document.getElementById("albumsays");
  const ask = albumAsk();
  if (!said) return 0;
  if (!Object.keys(ask).length){
    said.textContent = S.albumNoCriteria;
    return 0;
  }
  said.textContent = "Counting...";
  const bits = Object.entries(ask)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
  try{
    const got = await (await fetch(`api/timeline?limit=1&${bits}`)).json();
    if (got.error){ said.textContent = got.error; return 0; }
    said.textContent = say("albumCount", {n: got.total || 0})
      + (got.total ? "" : S.albumEmpty);
    return got.total || 0;
  }catch(e){ said.textContent = "That did not reach the app"; return 0; }
}

async function albumKeep(was){
  const name = String((document.getElementById("albumname") || {}).value || "").trim();
  if (!name) return toast("Give the album a name", 3000);
  const ask = albumAsk();
  if (!Object.keys(ask).length)
    return toast(S.albumNeedsOne, 4000);
  try{
    if (was && was !== name) await albumForget(was, true);
    const r = await fetch("api/searches", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: name, ask: ask})});
    const got = await r.json();
    if (got.error) return toast(got.error, 5000);
    toast(`"${name}" is in Albums`, 3000);
    document.getElementById("albummaker").hidden = true;
    drawAlbums();
  }catch(e){ toast("That did not reach the app", 4000); }
}

async function albumForget(name, quiet){
  if (!quiet && !await askSure({title: `Forget the album "${name}"?`,
                                body: S.albumForget,
                                yes: "Forget it"})) return;
  try{
    await fetch("api/searches", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({forget: name})});
    if (!quiet){ toast(`"${name}" is gone`, 2500); drawAlbums(); }
  }catch(e){ toast("That did not reach the app", 4000); }
}

async function albumEdit(key){
  const name = String(key || "").replace(/^kept:/, "");
  try{
    const got = await (await fetch("api/searches")).json();
    const one = (got.kept || []).find(k => k.name === name);
    albumMake(one ? one.ask : {}, name);
  }catch(e){ albumMake({}, name); }
}

function albumTitle(key){
  const got = ALBUMS.find(a => a.key === key);
  return got ? got.title : "";
}

function openAlbum(key){
  goScreen("photos", {album: key, filter: {}});
}

/* ------------------------------------------------------------------ the tools

   The forty-six, in five cards. A card is a family from core/families.py, which
   is one table with a test over it - so a feature added next month appears here
   without anybody remembering to add it. */

/* Settings is a group like the others now - a card you open, with every one of
   its features listed by icon and a line about what it does. It used to be a
   block stuck on the bottom of All tools, which is two wrongs: "where things
   are and what they mean" is not a tool, and a list of forty-eight features
   with ten settings mixed into the end of it is a list you have to read twice.
   So it has its own page, and All tools is tools. */
const SETFAM = {
  key: "settings", label: "Settings", icon: "gear", tone: "grey",
  note: "Where things are, what they mean, and what this app is allowed to do",
  get tasks(){
    return (typeof SETTINGS_TASKS !== "undefined") ? SETTINGS_TASKS : [];
  },
};

function famByKey(key){
  if (key === "settings") return SETFAM;
  const fam = (typeof FAMILIES !== "undefined" && FAMILIES.length) ? FAMILIES : [];
  return fam.find(f => f.key === key) || null;
}

function drawTools(){
  const stage = document.getElementById("stage");
  const fam = (typeof FAMILIES !== "undefined" && FAMILIES.length) ? FAMILIES : [];
  const one = TOOLFAM ? famByKey(TOOLFAM) : null;
  const shown = one ? [one] : fam;
  stage.innerHTML = `<div class="phead"><div>
      ${one ? `<button type="button" class="fchip" style="margin-bottom:8px"
          onclick="goScreen('tools', {fam: ''})">${icon("back")} All tools</button>` : ""}
      <h2>${one ? icon(one.icon) + esc(one.label) : "Tools"}</h2>
      <div class="sub">${one ? esc(one.note)
        : "Everything this app can do, grouped. Each one shows you what it would "
          + "do before it does it."}</div></div>
    <span class="spacer"></span>
    <div class="vtools">${one ? "" : `<button type="button"
      class="fchip${ARRANGETOOLS ? " on" : ""}" id="arrbtn" onclick="toolsArrange()"
      >${icon("gear")} ${ARRANGETOOLS ? "Done" : "Arrange"}</button>`}
      <input id="findtool" type="search" autocomplete="off"
      placeholder="Find a tool or action..." style="width:min(280px,52vw)"></div></div>
    ${ARRANGETOOLS && !one ? arrangePanel() : ""}
    ${one || ARRANGETOOLS ? "" : `<div class="toolbin" id="toolbin" hidden></div>`}
    <div class="cats${one ? " one" : ""}" id="cats"${ARRANGETOOLS && !one ? " hidden" : ""}>${
      shown.map(f => catCard(f, !!one)).join("")}</div>
    ${one ? "" : `<div class="note" style="margin-top:14px">
      Settings - where things are and what they mean - are a group of their own,
      in the rail under <b>Settings</b>. They are not tools and they are not in
      this list.</div>`}`;
  if (!one && !ARRANGETOOLS && typeof toolsBinLine === "function") toolsBinLine();
  const box = document.getElementById("findtool");
  box.addEventListener("input", () => toolFilter(box.value));
  box.addEventListener("keydown", e => {
    if (e.key !== "Enter") return;
    /* The tool whose NAME holds the word, before one that only mentions it:
       "cull" is Cull by rating, not Thin brackets, whose line says its spares
       go to _Culled. */
    const want = box.value.trim().toLowerCase();
    const shown = [...document.querySelectorAll(
      "#cats .cat:not([hidden]) .list button:not([hidden])")];
    const named = shown.find(b => want && (b.querySelector(".ftext b")
      || b).textContent.toLowerCase().includes(want));
    const press = named || shown[0];
    if (press) press.click();
  });
}

/* One feature in a list: its own glyph, its name, and the single line saying
   what it is for. The line comes from the registry (`Task.one_line`), so the
   rail, the cards and a category page cannot disagree about what a feature
   does - and one added next month arrives with its line already on. */
function featureRow(t, wide){
  if (!t) return "";
  return `<button type="button" class="feat${wide ? " wide" : ""}"
    data-t="${esc(t.name)}" onclick="openFeature('${quoted(t.name)}')">
    <span class="fic">${icon(t.icon)}</span>
    <span class="ftext"><b>${esc(t.tab || t.title)}</b>
      <span>${esc(t.line || "")}</span></span></button>`;
}

function catCard(f, wide){
  return `<div class="cat ${esc(f.tone || "grey")}" id="fam-${esc(f.key)}">
    <div class="top"><span class="ring">${icon(f.icon)}</span>
      <h3>${esc(f.label)}</h3>
      ${wide ? "" : `<button type="button" class="fchip"
         onclick="goScreen('tools', {fam: '${quoted(f.key)}'})">Open</button>`}</div>
    <p class="why">${esc(f.note)}</p>
    <div class="list">${f.tasks.map(name => groupedRow(f, name, wide)).join("")}
      </div></div>`;
}

/* A feature in a card, unless it is one of a folded pair of tabs (the NAS
   ones), which share one line named after the tab that holds them - the same
   one line the rail and the tab row show. */
function groupedRow(f, name, wide){
  const g = typeof tabGroup === "function" ? tabGroup(name) : null;
  if (!g) return featureRow(byName(name), wide);
  const mine = f.tasks.filter(n => g.tasks.indexOf(n) >= 0 && byName(n));
  if (mine[0] !== name) return "";
  /* Not one button but a line with a button for each tab in it, so both are
     one press from here, as every other feature is. */
  return `<div class="feat featgroup${wide ? " wide" : ""}" data-g="${esc(g.key)}">
    <span class="fic">${icon(g.icon)}</span>
    <span class="ftext"><b>${esc(g.label)}</b>
      <span>Only on a Synology NAS</span>
      <span class="featchips">${mine.map(n => `<button type="button" class="fchip"
        data-t="${esc(n)}" onclick="openFeature('${quoted(n)}')">${icon(byName(n).icon)}
        ${esc(byName(n).tab || byName(n).title)}</button>`).join("")}</span></span></div>`;
}

function toolFilter(text){
  const want = String(text || "").trim().toLowerCase();
  const said = n => {
    const t = byName(n) || {};
    return [t.title, t.tab, t.line, t.summary].join(" ").toLowerCase();
  };
  document.querySelectorAll("#cats .cat, #fam-settings").forEach(card => {
    let any = 0;
    card.querySelectorAll(".list > [data-t], .list > [data-g]").forEach(b => {
      const g = b.dataset.g && TABGROUPS.find(x => x.key === b.dataset.g);
      let hit;
      if (g){
        /* The NAS line: "permission" leaves only the Permissions button on
           it, so Enter opens that one rather than the first. */
        const all = !want || g.label.toLowerCase().includes(want);
        let some = 0;
        b.querySelectorAll("button[data-t]").forEach(c => {
          c.hidden = !all && !said(c.dataset.t).includes(want);
          if (!c.hidden) some++;
        });
        hit = all || some > 0;
      }else hit = !want || said(b.dataset.t).includes(want);
      b.hidden = !hit;
      if (hit) any++;
    });
    card.hidden = !any;
  });
}
