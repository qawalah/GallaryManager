
/* ------------------------------------------------------- a folder, and albums

   Two small bridges. A folder in the grid is a folder every feature here works
   on, so "use this one" is a menu of the features that take one - and keeping
   the filters you are looking at is the same act as keeping a search, because
   an album here IS a search. */

function useFolder(path){
  const offer = [["bydate", "Sort into folders"], ["unpair", "Separate RAWs"],
                 ["videos", "Separate video"], ["previews", "Make previews"],
                 ["geotag", "Geotag"], ["retime", "Fix the clock"],
                 ["tags", "Tag photos"], ["cull", "Cull by rating"],
                 ["duplicates", "Find duplicates"], ["exposure", "Check exposure"],
                 ["rename", "Power rename"], ["files", "File explorer"]];
  const q = quoted(path);
  pageMenu(event, `<div class="mhead">${esc(path.split(/[\\/]/).pop())}</div>`
    + offer.filter(([name]) => byName(name)).map(([name, label]) =>
      `<button class="vopt" onclick="intoFeature('${name}', '${q}')"
        >${esc(label)}</button>`).join(""), event.currentTarget);
}

function intoFeature(task, folder){
  closePageMenu();
  openFeature(task, {folders: [folder]});
}

async function keepAsAlbum(){
  const ask = {};
  for (const [k, v] of Object.entries(FILTER))
    if (v !== "" && v != null && k !== "name") ask[k] = v;
  if (!Object.keys(ask).length)
    return toast(S.nothingNarrowed, 3500);
  const name = await fmAsk({title: "Call this album what?", value: "",
                            yes: "Keep as an album"});
  if (!name || !name.trim()) return;
  try{
    const r = await fetch("api/searches", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: name.trim(), ask: ask})});
    const got = await r.json();
    if (got.error) return toast(got.error, 5000);
    toast(`Kept as "${name.trim()}" - it is in Albums`, 3000);
  }catch(e){ toast("That did not reach the app", 4000); }
}

/* ------------------------------------------------------------------ people

   No face detection here, and none is coming: this app does not open a
   photograph to guess at it, and a wrong name on somebody's child is a worse
   failure than no name at all.

   What it does have is the names already written INTO the photographs - the
   keywords you or Lightroom put there - so People is the list of those, with a
   way to put one on a selection. Everything in it is a real tag in a real file,
   which means it is still true in Lightroom, in Synology Photos, and in ten
   years when none of this is running. */

let PEOPLE = [];

async function drawPeople(){
  const stage = document.getElementById("stage");
  stage.innerHTML = `<div class="phead"><div><h2>People</h2>
    <div class="sub">${esc(S.peopleSub)}</div></div>
    <span class="spacer"></span>
    <div class="vtools">
      <button type="button" class="fchip" onclick="openFeature('tags')"
        >${icon("tag")} Tag a folder</button></div></div>
    <div class="indexing" id="idxbar" hidden></div>
    <div class="faces" id="faces">${reading()}</div>`;
  drawIndexing();
  let got;
  try{ got = await (await fetch("api/people")).json(); }
  catch(e){
    const box = SCREEN === "people" && document.getElementById("faces");
    if (box) box.innerHTML = `<div style="grid-column:1/-1">${couldNotReach("")}</div>`;
    return;
  }
  if (SCREEN !== "people") return;
  PEOPLE = got.people || [];
  const box = document.getElementById("faces");
  if (!PEOPLE.length){
    box.innerHTML = `<div style="grid-column:1/-1">${nothingHere({
      icon: "people", title: "No names yet",
      said: S.peopleNone,
      acts: [{label: "Go to Photos", go: "goScreen('photos')"},
             {label: "Tag a folder", go: "openFeature('tags')"}]})}</div>`;
    return;
  }
  box.innerHTML = PEOPLE.map(one => `
    <button type="button" class="face" onclick="openPerson('${quoted(one.name)}')">
      <span class="ring"><img loading="lazy" alt=""
        src="${thumbSrc(one.cover, "m")}" onerror="coverNoPic(this)"></span>
      <b>${esc(one.name)}</b><span>${say("nPhotos", {n: one.count})}</span>
    </button>`).join("");
  drawCandidates(got.candidates || []);
}

/* Which of your tags are people. Ticking from what is already in the library
   rather than typing: quicker, and incapable of inventing a name that is not
   in a single photograph. */
function drawCandidates(rest){
  const stage = document.getElementById("stage");
  if (!stage || !rest.length) return;
  stage.insertAdjacentHTML("beforeend", `
    <div class="card" style="margin-top:18px"><b>Which of these are people?</b>
      <span class="note"> - ${esc(S.peopleCandidates)}</span>
      <div class="fchips" style="margin-top:11px">${rest.map(t =>
        `<button type="button" class="fchip" onclick="namePerson('${quoted(t.name)}')"
          >${icon("plus")}${esc(t.name)}<span class="n">${num(t.count)}</span></button>`
        ).join("")}</div></div>`);
  if (PEOPLE.length) stage.insertAdjacentHTML("beforeend", `
    <div class="note" style="margin:10px 2px">Not a person?
      ${PEOPLE.map(p => `<button type="button" class="fchip"
        onclick="unnamePerson('${quoted(p.name)}')">${esc(p.name)} ${icon("cross")}</button>`
        ).join(" ")}</div>`);
}

async function namePerson(name){ await personSend({add: name}); }
async function unnamePerson(name){ await personSend({remove: name}); }

async function personSend(body){
  try{
    await fetch("api/people", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  }catch(e){ return toast("That did not reach the app", 4000); }
  drawPeople();
}

function openPerson(name){
  goScreen("photos", {filter: {tags: name}, album: ""});
}
