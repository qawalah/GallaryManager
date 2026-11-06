
/* ------------------------------------------------- the tools, your way round

   The grouping this app ships with is a good default and a bad rule. Somebody
   who never shoots RAW has four features about separating negatives in front of
   him every day; somebody whose week is geotagging wants those four together
   under a heading he chose. So: put a feature wherever you like, name the
   groups yourself, put the ones you never use away.

   Nothing here can lose a feature. A tool in no group falls into "Anything
   else", visible; one dropped in the Bin is taken out of the LISTS and nothing
   else - it still exists, it still runs, and the Tools screen says how many
   are in there and opens them again in one press. */

let ARR = null;             // the arrangement being edited, or null when not
let ARRANGETOOLS = false;
let ARRDIRTY = false;       // moved something since it was opened

/* The header button is the way in and the way out. Leaving with "Done" keeps
   what you did: a page where you drag ten tools about and then lose all of it
   because the button you pressed to finish was not the one that saves is a page
   nobody arranges twice. Cancel is the one that throws it away. */
async function toolsArrange(){
  if (ARRANGETOOLS){
    if (ARRDIRTY) return arrSave();
    return arrCancel();
  }
  try{
    ARR = await (await fetch("api/toolgroups")).json();
  }catch(e){ return toast("That did not reach the app", 4000); }
  ARR.groups = (ARR.groups || []).map(g => ({...g, tasks: [...(g.tasks || [])]}));
  ARR.hidden = ARR.hidden || [];
  ARRANGETOOLS = true;
  ARRDIRTY = false;
  drawTools();
}

function arrCancel(){
  ARRANGETOOLS = false;
  ARR = null;
  ARRDIRTY = false;
  drawTools();
}

function arrFeature(name){
  return (ARR.all || []).find(t => t.name === name)
    || {name: name, title: name, line: "", icon: "dot"};
}

function arrUnfiled(){
  const filed = new Set();
  ARR.groups.forEach(g => g.tasks.forEach(t => filed.add(t)));
  return (ARR.all || []).filter(t => !t.setting && !filed.has(t.name)
                                     && ARR.hidden.indexOf(t.name) < 0)
                        .map(t => t.name);
}

/* Every place a feature can be dropped, in the order the arrow keys walk them:
   the groups, then "Not in any group" when anything is, then the Bin. */
function arrZones(){
  const out = ARR.groups.map((g, i) => String(i));
  if (arrUnfiled().length) out.push("-1");
  out.push("bin");
  return out;
}

function arrangePanel(){
  const left = arrUnfiled();
  return `<div class="card arrcard"><div class="cardhead"><b>Arranging the tools</b>
      <span class="note">Drag a tool by its handle to any group, or into the
        Bin to take it out of every list. Nothing is deleted.</span></div>
    <div class="arrgroups">${ARR.groups.map((g, i) => `
      <div class="arrgroup" data-drop="${i}">
        <div class="arrtop">
          <span class="fic">${icon(g.icon || "tools")}</span>
          <input type="text" value="${esc(g.label)}" data-g="${i}"
            onchange="arrName(${i}, this.value)" aria-label="Group name">
          <button type="button" class="ghost" onclick="arrMove(${i}, -1)"
            ${i === 0 ? "disabled" : ""} title="Move the group up">↑</button>
          <button type="button" class="ghost" onclick="arrMove(${i}, 1)"
            ${i === ARR.groups.length - 1 ? "disabled" : ""}
            title="Move the group down">↓</button>
          <button type="button" class="ghost" onclick="arrDrop(${i})"
            title="${esc(S.groupRemoveTip)}"
            >${icon("cross")}</button>
        </div>
        <div class="arrlist">${g.tasks.map(arrRow).join("")}
          <span class="note arrempty">Drop a tool here.</span></div>
      </div>`).join("")}
      ${left.length ? `<div class="arrgroup loose" data-drop="-1">
        <div class="arrtop"><span class="fic">${icon("dot")}</span>
          <b>Not in any group</b></div>
        <p class="note">Each one shows in the group it came with until you
          file it somewhere of your own.</p>
        <div class="arrlist">${left.map(arrRow).join("")}
          <span class="note arrempty">Drop a tool here.</span></div></div>` : ""}
      <div class="arrgroup bin" data-drop="bin">
        <div class="arrtop"><span class="fic">${icon("trash")}</span>
          <b>Bin</b>${ARR.hidden.length
            ? `<span class="count">${num(ARR.hidden.length)}</span>` : ""}</div>
        <p class="note">Tools in here are in no group and no list. They still
          work; drag one out to bring it back.</p>
        <div class="arrlist">${ARR.hidden.map(arrRow).join("")}
          <span class="note arrempty">Drop the tools you never use here.</span></div>
      </div>
    </div>
    <div class="act" style="margin-top:12px">
      <button onclick="arrSave()">Save this arrangement</button>
      <button class="ghost" onclick="arrNew()">${icon("plus")} New group</button>
      <button class="ghost" onclick="arrCancel()">Cancel</button>
      <button class="ghost" onclick="arrReset()">Back to the built-in five</button>
    </div></div>`;
}

/* One tool you can pick up. The handle is a button so the keyboard can reach
   it: the arrows move the tool (up and down inside its group, left and right
   to the group before or after, the Bin being the last), which is the same
   drag for somebody who cannot hold a mouse button down. */
function arrRow(name){
  const t = arrFeature(name);
  return `<div class="arrrow" data-name="${esc(name)}">
    <button type="button" class="quiet arrgrip" aria-label="Move ${esc(t.title)}"
      title="Drag to another group, or use the arrow keys">${icon("grip")}</button>
    <span class="fic">${icon(t.icon)}</span>
    <span class="arrwhat"><b>${esc(t.title)}</b>
      <span class="note">${esc(t.line || "")}</span></span></div>`;
}

function arrName(i, text){
  if (!ARR.groups[i]) return;
  ARR.groups[i].label = String(text || "").trim() || "Group";
  ARRDIRTY = true;
}

function arrMove(i, by){
  const to = i + by;
  if (to < 0 || to >= ARR.groups.length) return;
  const [one] = ARR.groups.splice(i, 1);
  ARR.groups.splice(to, 0, one);
  ARRDIRTY = true;
  drawTools();
}

function arrDrop(i){
  if (!ARR.groups[i]) return;
  ARR.groups.splice(i, 1);          // its features become unfiled, never lost
  ARRDIRTY = true;
  drawTools();
}

function arrNew(){
  ARR.groups.push({key: "mine-" + (ARR.groups.length + 1), label: "New group",
                   icon: "tools", tone: "grey", note: "", tasks: []});
  ARRDIRTY = true;
  drawTools();
}

/* Where one tool is now: a group's index as a string, "-1" for not in any,
   "bin" for the Bin. Strings, because that is what the page's data-drop
   says and a zone compared as a number and as a string is two zones. */
function arrWhere(name){
  if (ARR.hidden.indexOf(name) >= 0) return "bin";
  const i = ARR.groups.findIndex(g => g.tasks.indexOf(name) >= 0);
  return String(i);
}

/* The one move everything else is: take it out of wherever it is, put it in
   `zone` at position `at` (the end when there is none). Not in any group has
   no order of its own - it follows the list of features - so `at` means
   nothing there. */
function arrPlace(name, zone, at){
  zone = String(zone);
  ARR.groups.forEach(g => { g.tasks = g.tasks.filter(t => t !== name); });
  ARR.hidden = ARR.hidden.filter(h => h !== name);
  const end = list => (at == null || at < 0 || at > list.length) ? list.length : at;
  if (zone === "bin") ARR.hidden.splice(end(ARR.hidden), 0, name);
  else if (+zone >= 0 && ARR.groups[+zone]){
    const list = ARR.groups[+zone].tasks;
    list.splice(end(list), 0, name);
  }
  ARRDIRTY = true;
  drawTools();
}

function arrPut(name, where){ arrPlace(name, +where >= 0 ? String(+where) : "-1"); }
function arrHide(name){ arrPlace(name, "bin"); }

/* ------------------------------------------------------------ picking one up

   Pointer events rather than the browser's own drag and drop, because that one
   does nothing on a phone, and a phone is where this app is opened most. The
   row you picked up is the gap: it moves through the lists as you go, so where
   it will land is always on the screen, and a copy of it follows the pointer.

   A mouse can pick a row up anywhere on it. A finger only by the handle -
   anywhere else a finger on a list is somebody scrolling it. */
let ARRDRAG = null;

addEventListener("pointerdown", e => {
  if (!ARRANGETOOLS || !ARR || e.button > 0) return;
  const row = e.target.closest && e.target.closest(".arrcard .arrrow[data-name]");
  if (!row) return;
  const grip = e.target.closest(".arrgrip");
  if (e.pointerType !== "mouse" && !grip) return;
  e.preventDefault();             // no text selected on the way past
  ARRDRAG = {row: row, name: row.dataset.name, id: e.pointerId,
             x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY,
             on: false, ghost: null, dx: 0, dy: 0, zone: null, tick: 0};
});

addEventListener("pointermove", e => {
  const d = ARRDRAG;
  if (!d || e.pointerId !== d.id) return;
  d.x = e.clientX; d.y = e.clientY;
  if (!d.on){
    // a few pixels first, so a click on the handle stays a click
    if (Math.abs(d.x - d.x0) + Math.abs(d.y - d.y0) < 6) return;
    arrLift(d);
  }
  e.preventDefault();
  arrFollow(d);
}, {passive: false});

addEventListener("pointerup", e => {
  if (ARRDRAG && e.pointerId === ARRDRAG.id) arrLetGo(true);
});
addEventListener("pointercancel", e => {
  if (ARRDRAG && e.pointerId === ARRDRAG.id) arrLetGo(false);
});
addEventListener("keydown", e => {
  if (ARRDRAG && ARRDRAG.on && e.key === "Escape"){ e.preventDefault(); arrLetGo(false); }
});

function arrLift(d){
  d.on = true;
  const box = d.row.getBoundingClientRect();
  d.dx = d.x0 - box.left; d.dy = d.y0 - box.top;
  const ghost = d.row.cloneNode(true);
  ghost.classList.add("arrghost");
  ghost.style.width = box.width + "px";
  document.body.appendChild(ghost);
  d.ghost = ghost;
  d.row.classList.add("arrhole");
  document.body.classList.add("arrdragging");
  d.tick = requestAnimationFrame(() => arrEdge(d));
}

function arrFollow(d){
  d.ghost.style.transform = `translate(${d.x - d.dx}px, ${d.y - d.dy}px)`;
  const under = document.elementFromPoint(d.x, d.y);
  const zone = under && under.closest(".arrcard .arrgroup[data-drop]");
  document.querySelectorAll(".arrgroup.dropon").forEach(z => {
    if (z !== zone) z.classList.remove("dropon");
  });
  if (!zone) return;
  zone.classList.add("dropon");
  d.zone = zone;
  const list = zone.querySelector(".arrlist");
  // the first row whose middle is below the pointer is the one it goes before
  const rows = [...list.querySelectorAll(".arrrow")].filter(r => r !== d.row);
  const next = rows.find(r => {
    const b = r.getBoundingClientRect();
    return d.y < b.top + b.height / 2;
  });
  const before = next || list.querySelector(".arrempty");
  if (d.row.nextElementSibling !== before || d.row.parentNode !== list)
    list.insertBefore(d.row, before);
}

/* Near the top or the bottom of the window the page scrolls under the tool, so
   a group below the fold is somewhere you can drag to. */
function arrEdge(d){
  if (ARRDRAG !== d || !d.on) return;
  const edge = 70, h = innerHeight;
  let by = 0;
  if (d.y < edge) by = -Math.ceil((edge - d.y) / 5);
  else if (d.y > h - edge) by = Math.ceil((d.y - (h - edge)) / 5);
  if (by){
    const main = document.scrollingElement || document.documentElement;
    main.scrollTop += by;
    arrFollow(d);
  }
  d.tick = requestAnimationFrame(() => arrEdge(d));
}

function arrLetGo(keep){
  const d = ARRDRAG;
  ARRDRAG = null;
  if (!d || !d.on) return;
  cancelAnimationFrame(d.tick);
  if (d.ghost) d.ghost.remove();
  document.body.classList.remove("arrdragging");
  document.querySelectorAll(".arrgroup.dropon").forEach(z => z.classList.remove("dropon"));
  if (!keep) return drawTools();
  const zone = d.row.closest(".arrgroup[data-drop]");
  if (!zone) return drawTools();
  const at = [...zone.querySelectorAll(".arrrow")].indexOf(d.row);
  arrPlace(d.name, zone.dataset.drop, at);
}

/* The same moves from the keyboard, on the handle. */
addEventListener("keydown", e => {
  if (!ARRANGETOOLS || !ARR || ARRDRAG) return;
  const grip = e.target.closest && e.target.closest(".arrcard .arrgrip");
  if (!grip) return;
  const name = grip.closest(".arrrow").dataset.name;
  const zone = arrWhere(name);
  const list = zone === "bin" ? ARR.hidden
             : +zone >= 0 ? ARR.groups[+zone].tasks : null;
  const pos = list ? list.indexOf(name) : -1;
  if (e.key === "ArrowUp" || e.key === "ArrowDown"){
    if (!list) return;
    const to = pos + (e.key === "ArrowUp" ? -1 : 1);
    if (to < 0 || to >= list.length) return;
    e.preventDefault();
    arrPlace(name, zone, to);
  }else if (e.key === "ArrowLeft" || e.key === "ArrowRight"){
    const zones = arrZones();
    const to = zones[zones.indexOf(zone) + (e.key === "ArrowLeft" ? -1 : 1)];
    if (to === undefined) return;
    e.preventDefault();
    arrPlace(name, to);
  }else return;
  const again = document.querySelector(
    `.arrcard .arrrow[data-name="${CSS.escape(name)}"] .arrgrip`);
  if (again) again.focus();
});

async function arrSave(){
  try{
    const got = await (await fetch("api/toolgroups", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({groups: ARR.groups, hidden: ARR.hidden})})).json();
    await toolsReload(got);
    toast(S.arrangeSaved, 3000);
  }catch(e){ toast("That did not reach the app", 4000); }
}

async function arrReset(){
  try{
    const got = await (await fetch("api/toolgroups", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({reset: true})})).json();
    await toolsReload(got);
    toast("Back to the five this app ships with", 3000);
  }catch(e){ toast("That did not reach the app", 4000); }
}

/* The rail and the Tools screen both read FAMILIES, which arrives with the task
   list - so after an arrangement is saved they are asked for it again rather
   than being told about it twice. */
async function toolsReload(got){
  try{
    const info = await (await fetch("api/tasks")).json();
    if (info.families) FAMILIES = info.families;
  }catch(e){}
  ARRANGETOOLS = false;
  ARR = null;
  ARRDIRTY = false;
  TOOLFAM = "";
  RAILFAM = "";
  drawRail();
  drawTools();
}

/* How many are in the Bin, under All tools, with the way to them. Asked for
   after the cards are drawn, because a tool put away and never mentioned again
   is a tool somebody will look for in the wrong list for a week. */
async function toolsBinLine(){
  const line = document.getElementById("toolbin");
  if (!line) return;
  let got;
  try{ got = await (await fetch("api/toolgroups")).json(); }catch(e){ return; }
  const n = (got.hidden || []).length;
  if (!n || !document.getElementById("toolbin") || ARRANGETOOLS) return;
  line.hidden = false;
  line.innerHTML = `${icon("trash")}<span>${n === 1 ? "One tool is" : num(n) + " tools are"}
    in the Bin and in no list.</span>
    <button type="button" class="fchip" onclick="toolsArrange()">Open the Bin</button>`;
}
