/* ---------------------------------------------- one page per tool, its group beside it

   A tool used to open with a row of tabs naming its relatives: Sort into
   folders carried Place names, Cull by rating carried five more. Which ones
   were relatives was fixed in the source (`parent`), so after somebody moved
   Find blurry into a group of their own on All tools, Cull still offered it
   as a tab and their own group did not. Two arrangements of the same tools,
   one of them yours and one not.

   So a tool is a page of its own, and down the right of it is the group it is
   in, read from FAMILIES - the same arrangement the rail and All tools draw -
   with the open one lit. Move a tool on All tools and this list follows.

   Nothing that was reachable from a tab row stops being reachable: a tool
   that is in no group (Put a run back and Clear the history, opened from
   History's rows) is listed under the tool it belongs to, below the group. */

/* The group a tool is listed under: one of yours, or Settings. */
function sideGroup(name){
  const fam = (typeof FAMILIES !== "undefined" && FAMILIES.length) ? FAMILIES : [];
  return fam.concat([SETFAM]).find(f => f.tasks.indexOf(name) >= 0) || null;
}

function sideRow(t, on, sub){
  return `<button type="button" class="siderow${on ? " on" : ""}${sub ? " sub" : ""}"
    data-t="${esc(t.name)}" ${on ? 'aria-current="page"' : ""}
    title="${esc(t.line || "")}" onclick="show('${quoted(t.name)}')">${icon(t.icon)}
    <span>${esc(t.tab || t.title)}</span></button>`;
}

/* The NAS pair is one line here as it is in the rail and on the Settings
   card, with its two tools under it while you are in one of them. */
function sideRows(f, here){
  return f.tasks.map(name => {
    const t = byName(name);
    if (!t) return "";
    const g = typeof tabGroup === "function" ? tabGroup(name) : null;
    if (!g) return sideRow(t, name === here, false);
    const mine = f.tasks.filter(n => g.tasks.indexOf(n) >= 0 && byName(n));
    if (mine[0] !== name) return "";
    const inside = mine.indexOf(here) >= 0;
    return `<button type="button" class="siderow${inside ? " on" : ""}"
        data-t="${esc(name)}" data-g="${esc(g.key)}"
        onclick="show('${quoted(name)}')">${icon(g.icon)}
        <span>${esc(g.label)}</span></button>`
      + (inside ? mine.map(n => sideRow(byName(n), n === here, true)).join("") : "");
  }).join("");
}

function drawToolSide(){
  const side = document.getElementById("toolside");
  if (!side) return;
  const holder = side.parentNode;
  const t = CURRENT;
  const fam = t ? (sideGroup(t.name) || (t.parent && sideGroup(t.parent))) : null;
  const listed = new Set();
  ((typeof FAMILIES !== "undefined" && FAMILIES) || []).concat([SETFAM])
    .forEach(f => f.tasks.forEach(n => listed.add(n)));
  const root = t && t.parent ? (byName(t.parent) || t) : t;
  const extra = !t ? [] : [root, ...kids(root.name)].filter(x => !listed.has(x.name));
  if (!fam && !extra.length){
    side.hidden = true;
    side.innerHTML = "";
    holder.classList.remove("withside");
    return;
  }
  side.hidden = false;
  side.setAttribute("aria-label", S.sideLabel);
  holder.classList.add("withside");
  side.innerHTML = (fam ? `<button type="button" class="sidehead ${esc(fam.tone || "grey")}"
        data-fam="${esc(fam.key)}" title="${esc(S.sideOpenGroup)}"
        onclick="goScreen('tools', {fam: '${quoted(fam.key)}'})">
        <span class="ring">${icon(fam.icon)}</span><b>${esc(fam.label)}</b></button>
      <div class="sidelist">${sideRows(fam, t.name)}</div>` : "")
    + (extra.length ? `<div class="sidesub">${esc(root.tab || root.title)}</div>
      <div class="sidelist">${extra.map(x => sideRow(x, x.name === t.name, false))
        .join("")}</div>` : "");
}

const sideShow = show;
show = function(name){
  const out = sideShow(name);
  drawToolSide();
  return out;
};
