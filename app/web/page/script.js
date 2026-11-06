
let TASKS = [], CURRENT = null, PLAN = null, poller = null, picking = null;
let TREES = {};            // the three roots from Setup, so a box can follow a box

/* ------------------------------------------------------- one box follows another

   Pick 2022/Spain in the originals box and the RAW and previews boxes should
   already say 2022/Spain in their own trees. Typing the same sub-path into three
   boxes, correctly, is the chore Browse only halved - and getting one of them
   subtly wrong is how a shoot ends up mirrored against the wrong tree.

   Two rules keep it honest:

   - It only ever fills a box you have not typed in. The moment you edit one by
     hand it stops following, because a box that overwrites what you just typed
     is worse than one that never helped.
   - It follows a POSITION, never a guess. If the folder you picked is not inside
     a known tree there is nothing to follow to, so it leaves the roots alone
     rather than inventing a path.

   The task then strips that position back off before mirroring into it - see
   settle_trees in app/registry.py. Both halves or neither: filling the box
   without the strip writes ...Photos Raw/2022/Spain/2022/Spain. */

const typedIn = new Set();      // boxes the person edited, which stop following

function under(path, root){
  if (!path || !root) return false;
  const p = path.replace(/[\\/]+$/, "").toLowerCase();
  const r = root.replace(/[\\/]+$/, "").toLowerCase();
  return p === r || p.startsWith(r + "/") || p.startsWith(r + "\\");
}

function positionUnder(path, root){
  const p = path.replace(/[\\/]+$/, "");
  const r = root.replace(/[\\/]+$/, "");
  return p.length > r.length ? p.slice(r.length + 1) : "";
}

function joinPath(root, rel){
  if (!rel) return root;
  const sep = root.includes("\\") ? "\\" : "/";
  return root.replace(/[\\/]+$/, "") + sep + rel;
}

/* The deepest folder all of these sit in. Segment by segment, never as text:
   `Photos` and `Photos Raw` share eight characters and no folder at all. */
function commonFolder(paths){
  const cut = p => p.replace(/[\\/]+$/, "").split(/[\\/]/);
  let parts = cut(paths[0]);
  for (const one of paths.slice(1)){
    const bits = cut(one);
    let n = 0;
    while (n < parts.length && n < bits.length &&
           parts[n].toLowerCase() === bits[n].toLowerCase()) n++;
    parts = parts.slice(0, n);
  }
  const sep = paths[0].includes("\\") ? "\\" : "/";
  return parts.join(sep);
}

/* Which tree the folder you picked belongs to, and where in it. */
function whereIsIt(path){
  let best = null;
  for (const key of ["library", "raw", "previews"]){
    const root = TREES[key];
    if (root && under(path, root) && (!best || root.length > best.root.length))
      best = {key, root, rel: positionUnder(path, root)};
  }
  return best;
}

/* Mirroring on: the destination boxes are along for the ride, so they show
   where things will go and cannot be edited into disagreeing with it. Off: they
   are yours again, exactly as they were. */
function mirroring(){
  const box = document.getElementById("o_mirror");
  return !!(box && box.checked);
}

function greyDestinations(){
  if (!CURRENT) return;
  const on = mirroring();
  for (const o of CURRENT.options){
    if (!o.tree) continue;
    const el = document.getElementById("o_" + o.name);
    if (!el) continue;
    el.disabled = on;
    el.closest(".withbtn")?.classList.toggle("locked", on);
    const btn = el.closest(".withbtn")?.querySelector("button");
    if (btn) btn.disabled = on;
  }
  followTrees();
}

/* The box you filled in tells the app which TREE you are working in, and the
   others follow from it - in whichever direction. Type a previews folder into a
   task that wants originals and it is read as the matching originals folder,
   out loud, rather than the task refusing with "that is not inside the
   library" - which is true, unhelpful, and exactly what he hit.

   Only ever a translation between trees that Setup knows, and only into a box
   whose option says it wants the library. Nothing is invented. */
function sameFolderInLibrary(at){
  if (!at || at.key === "library" || !TREES.library) return "";
  const wants = (CURRENT.options || []).find(o => o.name === "folder");
  if (!wants || wants.setting !== "library") return "";
  return joinPath(TREES.library, at.rel);
}

function followTrees(){
  if (!CURRENT) return;
  const from = document.getElementById("o_folder");
  if (!from) return;
  /* Several folders: they are followed from the folder they all sit in, which
     is also where the task will build what it makes. One folder is its own. */
  const picked = from.value.split("\n").map(x => x.trim()).filter(Boolean);
  let at = whereIsIt(picked.length > 1 ? commonFolder(picked)
                                       : (picked[0] || ""));
  const note = document.getElementById("followed");
  let said = "";
  const swap = sameFolderInLibrary(at);
  if (swap){
    said = say("followedSwap", {tree: at.key});
    from.value = swap;
    at = whereIsIt(swap);
  }
  if (!at || !at.rel){ if (note) note.textContent = said; return; }

  const locked = mirroring();
  const went = [];
  for (const o of CURRENT.options){
    if (!o.tree || o.name === "folder") continue;
    const root = TREES[o.name];
    if (!root || o.name === at.key) continue;
    const el = document.getElementById("o_" + o.name);
    // while mirroring, a box you typed in earlier is overwritten on purpose:
    // it is showing where things go, not deciding it
    if (!el || (typedIn.has(o.name) && !locked)) continue;
    el.value = joinPath(root, at.rel);
    // a label is a name ("Previews tree"); in the middle of a sentence it is
    // "the previews tree", and "the RAW tree" keeps its capitals
    const word = o.label.split(" ")[0];
    went.push("the " + (word === word.toUpperCase() ? o.label
      : o.label.charAt(0).toLowerCase() + o.label.slice(1)));
  }
  if (note){
    const rest = went.length
      ? say("followedTo", {at: at.rel, trees: went.join(" and ")}) : "";
    note.textContent = said ? (rest ? said + ". " + rest : said) : rest;
  }
}

/* What each tab was left looking at.
   Switching tab and losing a result you waited two minutes for is not a small
   annoyance - it is the reason you stop switching tabs, and half of this app is
   about looking at one feature because of what another one told you. So each
   task keeps its own form values, its own last result, and its own running job,
   and coming back finds them exactly as they were.
   Held in the page, not on the server: it is what you were doing in THIS
   browser, and a reload is a fair place to start clean. */
const SEEN = {};
let WATCH = null;          // {task, id} - the run being polled, whatever tab you are on

function keepWhereYouWere(){
  if (!CURRENT) return;
  const box = SEEN[CURRENT.name] || (SEEN[CURRENT.name] = {});
  box.values = values();
  box.out = document.getElementById("out").innerHTML;
  box.plan = PLAN;
  box.folded = new Set(folded);
}

const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const icon = n => `<svg class="ic" viewBox="0 0 24 24"><use href="#i-${esc(n)}"/></svg>`;
const basename = p => String(p || "").split(/[\\/]/).pop();
const folderOf = p => {
  const s = String(p || "");
  const cut = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  return cut > 0 ? s.slice(0, cut) : s;
};
const byName = n => TASKS.find(t => t.name === n);
const kids = n => TASKS.filter(t => t.parent === n);

/* Tools that belong to one kind of machine, folded under one line of their
   own in the rail, the Settings card and the list beside a tool.
   Reindex and Permissions only mean something on a Synology NAS - one asks
   DSM to look at the library again, the other checks the share's owners - and
   among the settings everybody uses they read as things you have to do. On a
   PC the server leaves both out of the task list (core/families.NAS_ONLY), so
   this group has nothing in it there and the NAS line is not drawn. */
const TABGROUPS = [
  {key: "nas", label: "NAS", icon: "nas", tasks: ["reindex", "permissions"]},
];
function tabGroup(name){
  return TABGROUPS.find(g => g.tasks.indexOf(name) >= 0) || null;
}

/* ------------------------------------------------------------------- theme
   Auto -> Light -> Dark, remembered in this browser. Applied before anything
   is drawn so the page never flashes the wrong palette on the way in. If the
   browser refuses to remember (private window, storage off), the button still
   works for the visit - it is a preference, not data, so losing it is not an
   error worth reporting. */
const THEMES = [
  ["auto",  "auto",  "Auto"],
  ["light", "sun",   "Light"],
  ["dark",  "moon",  "Dark"],
];
let THEME = "auto";
let MACHINE = {};
/* The two viewer keys, from Setup. Defaults until the first answer arrives, so
   a page that has not finished loading still answers to the usual letters. */
let KEYS = {info: "i", histogram: "h"};
let QUICKTAGS = [];          // the words bound to Shift+1 .. Shift+5

/* ------------------------------------------------------------ what the keys do

   ONE TABLE, THREE READERS: the handler that acts on a key, the list in
   Settings, and the card that `?` opens over the viewer.
   
   It was two keys in a settings page and nine more scattered through a
   seventy-line `if` chain, which is how an app ends up with a shortcut nobody
   knows about and a settings page that lists two of them. A key that is not
   written down anywhere is a key that does not exist. */
const SHORTCUTS = [
  ["Moving",  "← →",        "The one before, the one after"],
  ["Moving",  "Esc",        "Close the viewer, or shut an open menu first"],
  ["Moving",  "Space",      S.keysPlay],
  [S.keysRating, "0 – 5",      "Stars. The same number again takes them off"],
  [S.keysRating, "6 7 8 9",    S.keysMarks],
  [S.keysRating, "T",          "Open the tags menu"],
  [S.keysRating, "Shift 1 – 5", "Put one of your quick tags on, or take it off"],
  [S.keysRating, "Delete",     "To the Recycle Bin, with Undo"],
  ["Looking", "+ -",        "Closer in, further out"],
  ["Looking", "F",          S.keysFit],
  ["Looking", "Double press", "Actual size, and back"],
  ["Looking", "O",          "The file itself rather than a preview of it"],
  ["Looking", "D",          S.keysPanel],
  ["Looking", "@info",      "What it was exposed at"],
  ["Looking", "@histogram", "The histogram"],
  ["Looking", "?",          "This list"],
];

function shortcutRows(){
  return SHORTCUTS.map(([group, key, said]) => {
    if (key === "@info") key = (KEYS.info || "i").toUpperCase();
    if (key === "@histogram") key = (KEYS.histogram || "h").toUpperCase();
    if (key === "Shift 1 – 5" && QUICKTAGS.length)
      said = "Your quick tags: " + QUICKTAGS.join(", ");
    return [group, key, said];
  });
}

/* Dark until somebody says otherwise (4.0): the photographs are the brightest
   thing on the page that way. "Auto", which follows the machine, is still one
   of the three choices and is remembered like the other two. */
function readTheme(){
  try { return localStorage.getItem("pm-theme") || "dark"; } catch(e){ return "dark"; }
}
function readLook(key, fallback){
  try { return localStorage.getItem(key) || fallback; } catch(e){ return fallback; }
}
const DARKQ = matchMedia("(prefers-color-scheme: dark)");
function paintTheme(){
  const html = document.documentElement;
  if (THEME === "auto") html.removeAttribute("data-theme");
  else html.setAttribute("data-theme", THEME);
  const mode = THEME === "auto" ? (DARKQ.matches ? "dark" : "light") : THEME;
  html.setAttribute("data-mode", mode);
  html.setAttribute("data-palette", readLook("pm-palette", "classic"));
  html.setAttribute("data-accent", readLook("pm-accent", "ink"));
  html.setAttribute("data-chrome", readLook("pm-chrome", "plain"));
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content",
    getComputedStyle(html).getPropertyValue("--bg").trim() || "#0f0f0e");
  const b = document.getElementById("theme");
  if (!b) return;
  const [, ic, label] = THEMES.find(t => t[0] === THEME) || THEMES[0];
  b.innerHTML = icon(ic) + `<span>${label}</span>`;
  const pop = document.getElementById("lookpop");
  if (pop && !pop.hidden) drawLook();
}
DARKQ.addEventListener && DARKQ.addEventListener("change", paintTheme);
function setTheme(name){
  THEME = name;
  try { localStorage.setItem("pm-theme", name); } catch(e){}
  paintTheme();
}
function setLook(key, value){
  try { localStorage.setItem(key, value); } catch(e){}
  paintTheme();
}
function themeButton(){
  paintTheme();
  const b = document.getElementById("theme");
  if (!b) return;
  b.title = S.appearanceTip;
  b.onclick = e => {
    e.stopPropagation();
    const pop = document.getElementById("lookpop");
    pop.hidden = !pop.hidden;
    if (!pop.hidden) drawLook();
  };
  /* A click inside redraws the panel, so the element clicked is gone by the
     time the page hears about it - the panel keeps its own clicks instead. */
  document.getElementById("lookpop").addEventListener("click", e => e.stopPropagation());
  document.addEventListener("click", () => {
    const pop = document.getElementById("lookpop");
    if (pop && !pop.hidden) pop.hidden = true;
  });
  addEventListener("keydown", e => {
    if (e.key === "Escape"){ const p = document.getElementById("lookpop"); if (p) p.hidden = true; }
  });
}
function drawLook(){
  /* Three rows: the mode, the surfaces, the accent. Each is live - there is
     no Save, because a colour is judged by looking at it. */
  const pop = document.getElementById("lookpop");
  const pal = readLook("pm-palette", "classic"), acc = readLook("pm-accent", "ink");
  const chrome = readLook("pm-chrome", "plain");
  const mode = document.documentElement.getAttribute("data-mode");
  pop.innerHTML = `<div class="lookhead">Appearance</div>
    <div class="looklab">Mode</div>
    <div class="lookmode">` + THEMES.map(([v, ic, label]) =>
      `<button type="button" class="${THEME === v ? "on" : ""}" onclick="setTheme('${v}')"
        >${icon(ic)}<span>${label}</span></button>`).join("") + `</div>
    <div class="looklab">Theme</div>
    <div class="lookpal">` + Object.entries(LOOKS.palettes).map(([v, p]) => {
      const sw = (mode === "dark" ? p.dark : p.light) || (mode === "dark" ? LOOKS.base.dark : LOOKS.base.light);
      return `<button type="button" class="${pal === v ? "on" : ""}" onclick="setLook('pm-palette','${v}')"
        title="${esc(p.label)}"><span class="palsw" style="background:${sw[0]}">
          <i style="background:${sw[1]};border-color:${sw[4]}"></i><b style="background:${sw[2]}"></b></span>
        <span>${esc(p.label)}</span></button>`;
    }).join("") + `</div>
    <div class="looklab">Accent</div>
    <div class="lookacc">` + Object.entries(LOOKS.accents).map(([v, a]) =>
      `<button type="button" class="${acc === v ? "on" : ""}" onclick="setLook('pm-accent','${v}')"
        title="${esc(a.label)}" aria-label="${esc(a.label)}"
        style="--sw:${mode === "dark" ? a.dark : a.light}"></button>`).join("") + `</div>
    <div class="looklab">Top bar and sidebar</div>
    <div class="lookpal">` + Object.entries(LOOKS.chromes || {}).map(([v, c]) =>
      `<button type="button" class="${chrome === v ? "on" : ""}"
        onclick="setLook('pm-chrome','${v}')" title="${esc(c.label)}"
        ><span class="chrsw chr-${v}"></span><span>${esc(c.label)}</span></button>`)
      .join("") + `</div>`;
}

/* ---------------------------------------------------------------- is it alive
   Three questions the header answers together, because on a NAS they are
   impossible to separate from the outside: is this a live process, did it load
   the code I just copied, and are the folders it was pointed at actually there.

   Every request carries a cache-buster and the server sends no-store, so
   nothing here can be a browser's memory of an hour ago. That matters more than
   it sounds: a cached page is indistinguishable from a Restart that did not
   pick up new code, and you cannot debug two faults that look the same. */

let HEALTH = null, alive = null, GONE = false;

/* ------------------------------------------------ the long path, said shortly

   Every path on this NAS begins with the same four or five folders - the
   volume, the homes share, your user - and printing them in every chip, every
   table cell and every note is most of the width of the screen spent saying
   nothing. So wherever a path is SHOWN, the part every tree has in common comes
   off: "Photos Previews/2022/Spain" rather than the whole thing.

   Only text that is displayed. A box you type in keeps the real path, because
   an editable field showing something other than its value is a trap: what you
   see would not be what is sent. The hover title on anything shortened still
   carries the whole path.

   Done once, by watching the page, rather than at each of the forty places that
   draw a path - a place added next month is shortened without being told to. */
let PREFIX = "";

let ROOTS = [];
function commonHome(){
  const roots = (ROOTS.length ? ROOTS
    : ["library", "raw", "previews"].map(k => (TREES || {})[k])).filter(Boolean);
  if (!roots.length) return "";
  const parts = roots.map(r => r.replace(/[\\/]+$/, "").split(/[\\/]/));
  const up = parts.map(p => p.slice(0, -1));   // each tree's parent folder
  let n = Math.min(...up.map(p => p.length));
  const same = [];
  for (let i = 0; i < n; i++){
    const seg = up[0][i];
    if (up.every(p => p[i] === seg)) same.push(seg); else break;
  }
  const home = same.join("/");
  return home.length > 1 ? home : "";
}

function shortText(t){
  if (!PREFIX || !t || t.indexOf(PREFIX) < 0) return t;
  return t.split(PREFIX + "/").join("");
}

function shortenIn(node){
  if (!PREFIX || !node) return;
  if (node.nodeType === 3){
    const was = node.nodeValue;
    const now = shortText(was);
    if (now !== was){
      node.nodeValue = now;
      const host = node.parentElement;
      if (host && !host.title) host.title = was.trim();
    }
    return;
  }
  if (node.nodeType !== 1) return;
  if (/^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(node.tagName)) return;
  const walk = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  let t;
  while ((t = walk.nextNode())) shortenIn(t);
}

function watchPaths(){
  PREFIX = commonHome();
  if (!PREFIX) return;
  shortenIn(document.body);
  new MutationObserver(list => {
    for (const m of list){
      if (m.type === "characterData") shortenIn(m.target);
      m.addedNodes && m.addedNodes.forEach(shortenIn);
    }
  }).observe(document.body, {childList: true, subtree: true,
                             characterData: true});
}

/* Signed out while the page was open - the ticket expired, or somebody pressed
   Sign out everywhere. Every call in this page would start failing in its own
   way, each one drawing its own confusing empty state, and the page would look
   broken rather than locked. One wrapper instead: the first 401 anywhere sends
   the browser back to the door, and the server answers that with the login
   page. */
(function(){
  const real = window.fetch;
  window.fetch = async function(...args){
    const r = await real.apply(this, args);
    if (r.status === 401 && !GONE){
      GONE = true;
      location.replace(location.pathname);
    }
    return r;
  };
})();

function ago(seconds){
  if (seconds < 60) return seconds + "s";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m";
  return Math.floor(seconds / 3600) + "h " + Math.floor((seconds % 3600) / 60) + "m";
}

function showHealth(h, reachable){
  const dot = document.getElementById("dot");
  const stamp = document.getElementById("stamp");
  const chip = document.getElementById("live");
  dot.className = reachable ? "" : "gone";
  if (!reachable){
    stamp.textContent = "Offline";
    chip.setAttribute("data-tip", "The page could not reach the app. The "
      + "container may be stopped or restarting.");
    if (TIPFOR === chip) showTip(chip, TIPHOW);
    return;
  }
  HEALTH = h;
  if (typeof settingsStamped === "function") settingsStamped(h);
  /* Only when there is a lock. A Sign out button on an app with no password is
     a button that logs you out of nothing. */
  const out = document.getElementById("signout");
  if (out) out.hidden = !h.locked;
  /* Only on a copy started as a program on a PC. A window-less program has no
     other way to be stopped than Task Manager; the one in a container on the
     NAS has a stop button already, and a Quit there would take the app off the
     network with nothing to bring it back. */
  const bye = document.getElementById("quit");
  if (bye) bye.hidden = !h.desktop;
  stamp.textContent = "Live";
  /* Two facts, not five. It answers "is the thing I copied the thing that is
     running", and that is a version and how long it has been up; the rest was
     a paragraph nobody reads twice. */
  chip.setAttribute("data-tip",
    `Version ${h.release || "?"} · running ${ago(h.uptime)}`);
  /* Open already? Then it is showing a sentence that has just gone stale - the
     uptime in it was true when it was drawn. Redrawn in place rather than left
     wrong or shut in your face while you are reading it. */
  if (TIPFOR === chip) showTip(chip, TIPHOW);

  const box = document.getElementById("trouble");
  const perm = h.permissions || {};
  if (h.trouble){
    box.innerHTML = `<b>Something is not reachable.</b> ${esc(h.trouble)}`;
    box.hidden = false;
  } else if (perm.stale && !h.desktop && CURRENT
             && (CURRENT.name === "setup" || CURRENT.parent === "setup")){
    /* Never on a PC: the job, DSM and Synology Drive are not there, and the
       server sends nothing waiting anyway. Permissions is run by hand there. */
    /* In Setup only. Across the top of every page it was a nag you could do
       nothing about from where you were standing. */
    /* Until DSM has been over them, Synology Drive cannot see these folders -
       and nothing else anywhere says so. */
    box.innerHTML = `<b>${perm.waiting} new folder${perm.waiting === 1 ? "" : "s"}`
      + ` waiting for the permissions job.</b> Synology Drive will not see`
      + ` ${perm.waiting === 1 ? "it" : "them"} until it runs.`
      + (perm.ever ? " It has not run for hours." : " It has never run.")
      + ` <a href="#setup">Setup &rsaquo; Permissions</a>`;
    box.hidden = false;
  } else box.hidden = true;
}

/* Everything running, wherever it was started - a scan, a check, an apply, on
   any feature, several at once. The page cannot know about a run begun on a tab
   it is not showing unless it asks the server what is in flight, and "is
   anything happening" is the question you have when a NAS goes quiet. */
/* When the automation last did something, and when you last looked at it.
   The seen time is per browser - it is a UI state, not data, and the worst a
   lost one can do is show a stale mark once. */
let AUTO_RESULTS = [];
let RUNNING_NOW = [];
let AUTO_STATE = null;

function autoSeen(){
  try{ return parseFloat(localStorage.getItem("pm_auto_seen") || "0") || 0; }
  catch(e){ return 0; }
}

function markAutoSeen(){
  try{ localStorage.setItem("pm_auto_seen", String(Date.now() / 1000)); }
  catch(e){}
  drawBadge();
}

function freshRuns(){
  /* The runs that DID something since you last looked at the Runs tab. A pass
     that looked and found nothing changed is the normal state and there are
     hundreds of them; a mark lit by those is one you stop seeing in a week. */
  const seen = autoSeen();
  return (AUTO_RESULTS || []).filter(r => (r && r.when ? r.when : r) > seen)
    .map(r => (r && r.when) ? r : {when: r, title: "a run", done: 0, failed: 0});
}

function saidRuns(list){
  /* "3" tells you to go and look, which is most of the way to useless. This is
     the sentence that saves you going to look at a pass that moved four
     sidecars. */
  if (!list.length) return "";
  const done = list.reduce((n, r) => n + (r.done || 0), 0);
  const failed = list.reduce((n, r) => n + (r.failed || 0), 0);
  const what = {};
  list.forEach(r => { what[r.title] = (what[r.title] || 0) + (r.done || 0); });
  const named = Object.keys(what).map(k => `${k} ${what[k].toLocaleString()}`)
    .join(", ");
  return `${list.length} run${list.length === 1 ? "" : "s"} did something`
    + (done ? ", " + say("runsDone", {n: done}) : "")
    + (failed ? `, ${failed.toLocaleString()} failed` : "")
    + (named ? ` (${named})` : "");
}

function drawBadge(){
  /* On the rail's Maintain row, which is where automation lives in 3.0. Every
     line that matches, not the first one found, so a mark added to one is
     never left behind on another. */
  const lines = [...document.querySelectorAll('#rail .railrow[data-fam="maintain"]')];
  const list = freshRuns();
  const said = saidRuns(list);
  const news = document.getElementById("autonews");
  if (news){
    news.hidden = !list.length;
    news.innerHTML = list.length
      ? `${icon("auto")}<span>${esc(said)} since you last looked.</span>
         <button class="ghost" onclick="show('autoruns')">See the runs</button>`
      : "";
  }
  for (const line of lines){
    let dot = line.querySelector(".badge");
    if (!list.length){ if (dot) dot.remove(); continue; }
    if (!dot){
      dot = document.createElement("span");
      dot.className = "badge";
      line.appendChild(dot);
    }
    dot.textContent = list.length > 99 ? "99+" : String(list.length);
    dot.title = said;
  }
}


/* A run that finishes while you are somewhere else stays in the bar - "done",
   "ready to look at", or how many failed - until you open that feature. A bar
   that emptied the moment the work ended told you nothing unless you were
   watching at the time, which is exactly when you did not need telling.
   Remembered in this browser, so a reload does not lose it either. */
let FINISHED = (() => {
  try{ return JSON.parse(localStorage.getItem("pm_finished") || "{}") || {}; }
  catch(e){ return {}; }
})();
let ENDSEEN = null;          // finished runs already accounted for

function keepFinished(){
  try{ localStorage.setItem("pm_finished", JSON.stringify(FINISHED)); }catch(e){}
}

/* ONE SHAPE FOR A TIME: "17 Oct 20:24", day first and 24-hour, which is the
   shape the server already writes into History and the explorer. The page
   used the browser's own ("Oct 17 08:29 PM"), so one screen showed both.
   `t` is seconds since 1970; the year is added only when it is not this one. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dayTime(t){
  const d = new Date(t * 1000);
  if (isNaN(d)) return "";
  const year = d.getFullYear() === new Date().getFullYear() ? "" : " " + d.getFullYear();
  return `${String(d.getDate()).padStart(2, "0")} ${MONTHS[d.getMonth()]}${year} ${clock(t)}`;
}

function clock(t){
  const d = new Date(t * 1000);
  if (isNaN(d)) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function noteFinished(ended){
  /* The server keeps runs that finished in the last half hour; anything new
     in that list is news - unless you were looking at it when it ended. The
     first list after the page opens is taken as already known, or every
     reload would fill the bar with the past. */
  const first = ENDSEEN === null;
  if (first) ENDSEEN = new Set();
  for (const j of ended || []){
    if (ENDSEEN.has(j.id)) continue;
    ENDSEEN.add(j.id);
    if (first) continue;
    const go = j.by === "automation" ? "automation" : j.task;
    if (CURRENT && CURRENT.name === j.task
        && document.visibilityState === "visible") continue;
    FINISHED[j.id] = {task: j.task, go: go, title: j.title, icon: j.icon, by: j.by,
                      planned: j.planned && !j.blocked, when: j.ended,
                      failed: j.failed, blocked: j.blocked};
    tellMe(FINISHED[j.id]);
  }
  keepFinished();
}

function clearFinished(name){
  let changed = false;
  for (const [id, f] of Object.entries(FINISHED))
    if (f.go === name || f.task === name){ delete FINISHED[id]; changed = true; }
  if (changed){ keepFinished(); showRunning(); }
}

/* What the last answer looked like, so an answer that says the same thing
   again redraws nothing. Most answers do: nothing is running, nothing finished,
   and rewriting the bar, the pill and the badges every poll for that was work
   the phone did for no visible change. The runs that finished-while-away list
   is part of it, because opening one of those changes the bar too. */
let JOBS_SEEN = "";

function jobsHash(text){
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
  return text.length + ":" + h;
}

async function showRunning(){
  let live = [];
  try{
    const r = await fetch("api/jobs?t=" + Date.now(), {cache: "no-store"});
    const text = await r.text();
    const got = JSON.parse(text);
    live = got.running || [];
    noteFinished(got.ended || []);
    RUNNING_NOW = live;
    AUTO_RESULTS = got.auto_results || [];
    MACHINE = got.machine || {};
    AUTO_STATE = got.automation || {};
    const seen = jobsHash(text + "|" + Object.keys(FINISHED).join(","));
    if (seen === JOBS_SEEN) return live;
    JOBS_SEEN = seen;
    drawAuto(AUTO_STATE, live);
    drawBadge();
  }catch(e){ live = []; JOBS_SEEN = ""; drawAuto(null, []); }
  const box = document.getElementById("running");
  const done = Object.values(FINISHED);
  if (!live.length && !done.length){ box.hidden = true; box.innerHTML = ""; return live; }
  box.hidden = false;
  box.innerHTML = done.map(f => `<div class="job jdone${f.failed ? " jfail" : ""}"
      onclick="show('${quoted(f.go)}')" title="${esc(S.noticeOpen)}">
      <span class="jname">${icon(f.icon)}<span>${esc(f.title)}</span>${f.by === "automation"
        ? `<span class="byauto">auto</span>` : ""}</span>
      <span class="jwhat">${f.failed ? `${f.failed} failed` : f.blocked ? "could not run"
        : (f.planned ? "ready to look at" : "done")}</span>
      <span class="note">${esc(clock(f.when))} - open it</span></div>`).join("")
  + live.map(j => {
    const pct = j.total ? Math.round(100 * j.done / j.total) : 0;
    const guess = j.total ? "" : " guess";   // no count yet: moving, not measured
    const what = j.phase === "planning" ? "looking" : "working";
    /* Who started it matters most for the ones you did not: the app reading
       your library on its own is the thing you want to be able to SEE, and
       until now it was the one kind of run that never appeared here at all. */
    const mine = j.by === "automation"
      ? `<span class="byauto" title="started by Automation, not by you">auto</span>`
      : "";
    return `<div class="job" onclick="show('${quoted(j.by === "automation"
                                                 ? "automation" : j.task)}')">
      <span class="jname">${icon(j.icon)}<span>${esc(j.title)}</span>${mine}</span>
      <span class="note">${what}${j.cancelled ? " - stopping" : ""}</span>
      <span class="jbar${guess}"><i style="width:${j.total ? pct : 35}%"></i></span>
      <span class="jnote">${j.total ? `${j.done} of ${j.total}` : ""}</span>
      <span class="jnow">${esc(j.now || "")}</span>
      <span class="note" title="what it is costing the NAS">${esc(j.cost || ago(j.seconds))}</span></div>`;
  }).join("");
  return live;
}

/* How often to ask what is running. Quickly while something is - the bar is
   moving and a finish should show at once - slowly when nothing is, and not at
   all in a tab nobody is looking at: a phone with the page open in the
   background was asking a NAS what it was doing every 0.7 s, all night. */
const JOBS_BUSY_MS = 700, JOBS_IDLE_MS = 2500;
let JOBS_TIMER = null;

async function pollJobs(){
  clearTimeout(JOBS_TIMER);
  JOBS_TIMER = null;
  if (document.hidden) return;
  const live = await showRunning();
  clearTimeout(JOBS_TIMER);
  JOBS_TIMER = document.hidden ? null
    : setTimeout(pollJobs, (live && live.length) ? JOBS_BUSY_MS : JOBS_IDLE_MS);
}

/* setInterval, minus the ticks that land while the tab is hidden, plus one at
   once when it is shown again - so coming back to the page is never stale. */
function whileVisible(fn, ms){
  setInterval(() => { if (!document.hidden) fn(); }, ms);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) fn();
  });
}

function drawAuto(state, live){
  /* A pill, not a sentence: the word, and a number when there is one. The
     sentence it used to print lives in the bubble - hover it at a desk, tap it
     on a phone - exactly as the Live chip beside it works. */
  const bar = document.getElementById("autobar");
  const says = document.getElementById("autosays");
  if (!bar || !says) return;
  const busy = (live || []).filter(j => j.by === "automation");
  bar.classList.toggle("busy", busy.length > 0);
  bar.classList.toggle("on", !busy.length && !!(state && state.on));
  let word, tip;
  if (busy.length){
    word = `<b>Running</b>${busy.length > 1 ? ` <span>${busy.length}</span>` : ""}`;
    tip = "Automation is running " + busy.map(j => j.title).join(", ") + " now.";
  } else if (!state){
    word = "<b>?</b>";
    tip = "The app did not answer. It may be restarting.";
  } else if (!state.on){
    const dsm = (state.by_dsm || []).length;
    word = "<b>Off</b>";
    tip = S.automationOff
      + (dsm ? " " + say("automationByDsm", {n: dsm}) : "");
  } else {
    const next = state.next_in == null ? null : Math.max(0, state.next_in);
    const soon = next == null ? "" : (next < 60 ? next + "s" : Math.round(next / 60) + "m");
    word = `<b>On</b>${soon ? ` <span>${soon}</span>` : ""}`;
    tip = "Automation is on: " + ((state.flows || []).join(", ") || "its flows")
      + (next == null ? `, every ${state.every_minutes} min.`
                      : `. Next look in ${soon}.`);
  }
  says.innerHTML = word;
  const hint = matchMedia("(hover: hover)").matches
    ? " Click to open Automation." : " Open it from the menu.";
  bar.setAttribute("data-tip", tip + hint);
  bar.removeAttribute("title");
  if (TIPFOR === bar) showTip(bar, TIPHOW);
}

async function checkHealth(){
  try{
    const r = await fetch("api/health?t=" + Date.now(), {cache: "no-store"});
    showHealth(await r.json(), true);
  }catch(e){ showHealth(null, false); }
}

/* ----------------------------------------------------------------- the drawer

   Thirteen features in a horizontal scroller is a list you have to swipe
   through to read and cannot see your place in. On a phone the sidebar is a
   drawer instead: off screen until asked for, full height, one tap to anywhere,
   and it closes the moment you pick something - a menu you have to dismiss
   yourself is a menu that covers the thing you just opened. */

function openDrawer(){
  document.body.classList.add("drawer");
  drawNotice();
}

function closeDrawer(){ document.body.classList.remove("drawer"); }

/* THE ONE BREAKPOINT. The stylesheets' @media rules use the same number
   (tests/test_design.py holds them together): 720 here and 860 there left a
   window where the rail was a drawer and the guide placed its spots for a
   desk. 860 is where the rail folds away, so it is where a phone starts. */
const PHONE_MAX = 860;
function isPhone(){ return matchMedia(`(max-width:${PHONE_MAX}px)`).matches; }

function toggleDrawer(){
  if (document.body.classList.contains("drawer")) closeDrawer();
  else openDrawer();
}

/* ------------------------------------------------------------ the families

   Five headings over the features, so you can tell which of them is a thing
   you do on day one. The rail and the Tools screen draw them; the server says
   which feature is under which, so one table decides it. */

let FAMILIES = [];
let SETTINGS_TASKS = [];
/* The features pinned to the top level of the rail. Five screens and
   forty-eight features is the right shape for a library and the wrong one for
   the two things somebody does every day. */
let PINNED = [];
/* The NAS-only tools a copy on a PC leaves off the page (empty on the NAS),
   named once in Setup so they do not just vanish. */
let NAS_ONLY = [];

async function boot(){
  THEME = readTheme();
  themeButton();
  keepShell();
  bindTips();
  document.getElementById("menu").innerHTML = icon("menu");
  document.getElementById("menu").onclick = toggleDrawer;
  document.getElementById("scrim").onclick = closeDrawer;
  addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
  /* It reads as a button and it is shaped like one, so it opens Automation
     wherever you are. It used to do that only where there was a mouse - on a
     phone a tap showed a bubble and nothing else, which is a dead control. The
     bubble is still there on hover; `data-tipnoclick` keeps the tip engine from
     also toggling it under the tab you have just been moved to. */
  document.getElementById("autobar").onclick = () => {
    hideTip();
    show("automation");
    closeDrawer();
  };
  const bye = document.getElementById("quit");
  if (bye){
    bye.innerHTML = icon("cross") + "<span>Quit</span>";
    bye.onclick = async () => {
      const yes = await askSure({
        title: "Stop Photo Manager on this PC?",
        body: S.quitBody,
        yes: "Stop it"});
      if (!yes) return;
      try{
        await fetch("api/quit", {method: "POST",
          headers: {"Content-Type": "application/json"}, body: "{}"});
      }catch(e){}
      document.body.innerHTML = `<div class="card" style="margin:60px auto;
        max-width:420px;text-align:center">
        <b>Photo Manager has stopped.</b>
        <div class="note" style="margin-top:8px">Start it again from the Start
          menu, then reload this page.</div></div>`;
    };
  }
  const out = document.getElementById("signout");
  out.innerHTML = icon("lock") + "<span>Sign out</span>";
  out.onclick = async () => {
    try{ await fetch("api/logout", {method: "POST",
                                    headers: {"Content-Type": "application/json"},
                                    body: "{}"}); }catch(e){}
    location.replace(location.pathname);
  };
  document.getElementById("reload").innerHTML = icon("again") + "<span>Reload page</span>";
  document.getElementById("reload").onclick = () => {
    /* A plain reload can still be answered from cache. Changing the address
       cannot be - and the app ignores the query, so it is the same page. */
    location.replace(location.pathname + "?t=" + Date.now() + location.hash);
  };
  checkHealth();
  whileVisible(checkHealth, 5000);
  pollJobs();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollJobs();
  });
  const info = await (await fetch("api/tasks?t=" + Date.now(),
                                  {cache: "no-store"})).json();
  TREES = info.trees || {};
  takeSettings(info);
  watchPaths();
  showHealth(info, true);
  TASKS = info.tasks;
  FAMILIES = info.families || [];
  SETTINGS_TASKS = info.settings_tasks || [];
  PINNED = info.pinned || [];
  NAS_ONLY = info.nas_only || [];
  /* The ones that are not steps in any workflow get a place in the header
     rather than a line in the sidebar. A list of twenty features with "what
     happened last week" among them reads as twenty steps, nineteen of which
     you do and one of which you go and look at. */
  document.getElementById("apart").innerHTML =
    TASKS.filter(t => !t.parent && t.hidden).map(t =>
      `<button type="button" class="apart" data-t="${t.name}"
         title="${esc(t.summary)}">${icon(t.icon)}<span>${esc(t.title)}</span></button>`
    ).join("");
  document.querySelectorAll("#apart button").forEach(b =>
    b.onclick = () => show(b.dataset.t));
  addEventListener("hashchange", () => {
    const want = location.hash.slice(1);
    if (!want) return;
    if (want !== (CURRENT && CURRENT.name)) show(want);
  });
  /* Read BEFORE show(), because show() writes the tab into the address - so
     asking afterwards always finds one. An address that ARRIVED with a tab in
     it lands where it says: a link you followed on purpose. */
  const asked = location.hash.slice(1);
  /* A new install has no library, and nothing works until it does - so it
     opens on the checklist, which says exactly that and what else is missing. */
  const fresh = !asked && !TREES.library && TASKS.some(t => t.name === "checklist");
  show(asked || (fresh ? "checklist" : TASKS[0]?.name));
}

/* ------------------------------------------------------------------ the form */


/* ------------------------------------------------------------ folder patterns */

function patKeptHtml(name, kept){
  if (!kept.length) return "";
  return `<span class="note">Kept:</span> ` + kept.map(k =>
    `<span class="patchip"><button type="button" class="patuse"
        title="${esc(k.pattern)}" onclick="patUse('${name}', this.title)">${esc(k.name)}</button
      ><button type="button" class="patx" aria-label="Forget ${esc(k.name)}"
        onclick="patForget('${name}', '${quoted(k.name)}')">${icon("cross")}</button></span>`
  ).join("");
}

function patInsert(name, v){
  const box = document.getElementById("o_" + name);
  if (!box) return;
  const at = box.selectionStart ?? box.value.length, end = box.selectionEnd ?? at;
  const put = "{" + v + "}";
  box.value = box.value.slice(0, at) + put + box.value.slice(end);
  box.focus();
  box.setSelectionRange(at + put.length, at + put.length);
  patCheck(name);
}

function patUse(name, pattern){
  const box = document.getElementById("o_" + name);
  if (box){ box.value = pattern; patCheck(name); }
}

let PATTIMER = 0;
function patCheck(name){
  clearTimeout(PATTIMER);
  PATTIMER = setTimeout(async () => {
    const box = document.getElementById("o_" + name);
    const said = document.getElementById("px_" + name);
    if (!box || !said) return;
    try{
      const got = await (await fetch("api/pattern?p=" + encodeURIComponent(box.value))).json();
      said.classList.toggle("bad", !!got.problem);
      said.innerHTML = got.problem ? esc(got.problem)
        : `Makes <b>${esc(got.example).split("/").join(" <span>/</span> ")}</b>`
          + (got.place ? ` <span class="note">- needs a location on the photo</span>` : "");
    }catch(e){}
  }, 180);
}

async function patSend(name, body){
  const r = await fetch("api/patterns", {method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const got = await r.json();
  const said = document.getElementById("px_" + name);
  if (got.error){ if (said){ said.classList.add("bad"); said.textContent = got.error; } return; }
  document.getElementById("pk_" + name).innerHTML = patKeptHtml(name, got.kept);
  // and the dropdown above offers them straight away
  const sel = document.getElementById("o_shape");
  if (sel){
    sel.querySelectorAll('option[value^="saved:"]').forEach(o => o.remove());
    let grp = sel.querySelector('optgroup[label="Kept"]');
    if (!grp){
      grp = document.createElement("optgroup"); grp.label = "Kept";
      const own = sel.querySelector('option[value="custom"]');
      sel.insertBefore(grp, own ? own.parentElement.tagName === "OPTGROUP" ? own.parentElement : own : null);
    }
    got.kept.forEach(k => {
      const o = document.createElement("option");
      o.value = "saved:" + k.name; o.textContent = k.name + "  -  " + k.label;
      grp.appendChild(o);
    });
    if (!got.kept.length) grp.remove();
  }
  if (said && body.name){
    said.classList.remove("bad"); said.textContent = `Kept as "${body.name}".`;
    setTimeout(() => patCheck(name), 1600);
  }
}

function patKeep(name){
  const box = document.getElementById("o_" + name);
  const nm = document.getElementById("pn_" + name);
  if (box && nm) patSend(name, {name: nm.value, pattern: box.value}).then(() => { nm.value = ""; });
}

function patForget(name, which){ patSend(name, {forget: which}); }

function control(o){
  /* Every option in its own wrapper, so one of them can be greyed out without
     the fieldset around it going grey too. That matters exactly once - the
     Automation tab, whose steps lock while the loop is running - and a wrapper
     is cheaper than the special case. */
  return `<div class="opt" id="w_${o.name}">${controlBody(o)}</div>`;
}

function controlBody(o){
  const id = "o_" + o.name;
  const info = o.help
    ? `<button class="info" type="button" aria-label="What this does"
        data-tip="${esc(o.help)}">i</button>` : "";
  /* Where the value in the box actually came from - not merely where it could
     have come from. Labelling a remembered path "(from Setup)" is how Setup
     showing an empty box looks like the app losing it. */
  const said = {setup: "from Setup", recent: "last used"}[o.from] || "";
  const from = (said && CURRENT && CURRENT.name !== "setup")
    ? ` <span class="fromsetup">(${said})</span>` : "";
  const help = "";          // the help is a bubble now, not a panel

  if (o.kind === "flag")
    return `<div class="row-flag"><input type="checkbox" id="${id}" ${o.default ? "checked" : ""}>
            <span class="lab"><label for="${id}" style="margin:0">${esc(o.label)}</label>${info}</span>
            </div>${help}`;

  let field;
  if (o.kind === "pattern"){
    /* A pattern, typed - with every variable a tap away, what it makes shown
       as you type, and a name to keep it under. */
    const vars = (o.variables || []).map(v =>
      `<button type="button" class="patvar" title="${esc(v.label)} - e.g. ${esc(v.example)}"
         onclick="patInsert('${o.name}','${v.name}')">{${v.name}}</button>`).join("");
    return `<div class="lab"><label for="${id}" style="margin:0">${esc(o.label)}</label>${info}</div>
      <input type="text" id="${id}" class="patbox" value="${esc(o.default ?? "")}"
        spellcheck="false" autocomplete="off" autocapitalize="off"
        oninput="patCheck('${o.name}')">
      <div class="patex" id="px_${o.name}"></div>
      <div class="patvars">${vars}</div>
      <div class="patkeep">
        <input type="text" id="pn_${o.name}" placeholder="Name to keep it under">
        <button type="button" class="ghost" onclick="patKeep('${o.name}')">Keep</button>
      </div>
      <div class="patkept" id="pk_${o.name}">${patKeptHtml(o.name, o.kept || [])}</div>`;
  }
  if (o.kind === "choice" && o.tabs){
    /* A view of the same answer, not a setting - so it is a row of tabs and
       picking one looks again immediately. A dropdown hides the options you did
       not pick and makes comparing them a three-click job. */
    return `<div class="lab"><label style="margin:0">${esc(o.label)}</label>${info}</div>
      ${help}
      <input type="hidden" id="${id}" value="${esc(o.default ?? "")}">
      <div class="viewtabs" id="t_${o.name}">` + o.choices.map(c =>
        `<button type="button" class="${c.value == o.default ? "on" : ""}"
           data-v="${esc(c.value)}"
           onclick="pickTab('${o.name}','${quoted(c.value)}')"
           >${esc(c.label)}</button>`).join("") + `</div>`;
  }
  if (o.kind === "choice"){
    /* Grouped under their own headings when the task named any, so a long list
       of ways to do one thing reads as two short lists. */
    const one = c => `<option value="${esc(c.value)}"
        ${c.value == o.default ? "selected" : ""}>${esc(c.label)}</option>`;
    let body = "", head = null;
    for (const c of o.choices){
      const name = c.group || "";
      if (name !== head){
        if (head) body += `</optgroup>`;
        if (name) body += `<optgroup label="${esc(name)}">`;
        head = name;
      }
      body += one(c);
    }
    if (head) body += `</optgroup>`;
    field = `<select id="${id}">${body}</select>`;
  }
  else if (o.kind === "number")
    field = `<input type="number" id="${id}" value="${esc(o.default)}"
       ${o.min != null ? `min="${o.min}"` : ""} ${o.max != null ? `max="${o.max}"` : ""}>`;
  else if (o.kind === "folder" && o.many)
    /* Several folders in one run. Same hidden-field-and-chips shape as an
       exclusion list, so everything downstream stays plain text - but still a
       folder box, so it is fenced, followed and remembered like one. */
    field = `<input type="hidden" id="${id}" value="${esc(o.default ?? "")}">
      <div class="chips" id="c_${o.name}"></div>
      <button type="button" class="ghost" onclick="browse('${o.name}', true)">
        ${icon("folder")} Add a folder</button>`;
  else if (o.kind === "folder")
    field = `<div class="withbtn"><input type="text" id="${id}" value="${esc(o.default ?? "")}"
       placeholder="a folder path">
       <button type="button" class="ghost" onclick="browse('${o.name}')">${icon("folder")} Browse</button></div>`;
  else if (o.kind === "file")
    /* A file box had no Browse at all, so the three places that want one - the
       photograph whose real time you know, the place-name dumps - were the only
       boxes in the app where you had to type a full path from memory. */
    field = `<div class="withbtn"><input type="text" id="${id}" value="${esc(o.default ?? "")}"
       placeholder="a file path">
       <button type="button" class="ghost" onclick="browse('${o.name}', false,
         '${quoted((o.suffixes || []).join(","))}')">${icon("folder")} Browse</button></div>`;
  else if (o.kind === "folders")
    /* Several folders, held in one hidden field so everything downstream stays
       plain text, and drawn as chips you can remove one at a time. Typed paths
       are how a folder you meant to leave out gets scanned anyway - a name that
       matches nothing looks exactly like one that matches nothing on purpose. */
    field = `<input type="hidden" id="${id}" value="${esc(o.default ?? "")}">
      <div class="chips" id="c_${o.name}"></div>
      <button type="button" class="ghost" onclick="browse('${o.name}', true)">
        ${icon("folder")} Add a folder</button>`;
  else if (o.kind === "secret")
    /* Never carries a value in, and never sends one back into the form. The
       browser is told what it is so its password manager can offer to keep it -
       which is the difference between a lock people use and one they turn off
       after a fortnight. */
    field = `<input type="password" id="${id}" value=""
       autocomplete="new-password" placeholder="not shown">`;
  else
    field = `<input type="text" id="${id}" value="${esc(o.default ?? "")}">`;

  return `<div class="lab"><label for="${id}" style="margin:0">${esc(o.label)}</label>${info}${from}</div>
          ${field}${help}`;
}

/* ------------------------------------------------------------- the help bubble

   One element, moved to whichever (i) is being asked about, so the page does
   not carry a hidden panel per option. Bound by DELEGATION on the document:
   forms here are redrawn constantly - every tab switch, every plan, every
   redraw of the flow editor - and anything that binds listeners to the buttons
   themselves has to remember to rebind, which is a thing that gets forgotten
   once and then silently half-works.

   Hover on a mouse, tap on a touch screen, and focus for a keyboard. Three ways
   in because a bubble you can only hover is a bubble that does not exist on a
   phone, and one you can only tap is one that fights a mouse. */

let TIPFOR = null, TIPHOW = "";

function tipBox(){
  let el = document.getElementById("tip");
  if (!el){
    el = document.createElement("div");
    el.id = "tip";
    el.hidden = true;
    document.body.appendChild(el);
  }
  return el;
}

function showTip(btn, how){
  const text = btn && btn.getAttribute("data-tip");
  if (!text) return;
  const el = tipBox();
  el.textContent = text;
  el.hidden = false;
  el.classList.remove("on");
  // Measure, then place: the width is not known until the text is in it.
  const b = btn.getBoundingClientRect();
  const w = el.offsetWidth, h = el.offsetHeight;
  const pad = 10;
  let left = b.left + b.width / 2 - w / 2;
  /* Clamped, so a bubble beside the last control on the right can never stick
     off the edge - which on a phone would make the whole page scroll sideways
     for ever after. */
  left = Math.max(pad, Math.min(left, innerWidth - w - pad));
  let top = b.bottom + 8;
  if (top + h > innerHeight - pad) top = Math.max(pad, b.top - h - 8);
  el.style.left = left + "px";
  el.style.top = top + "px";
  el.classList.add("on");
  btn.classList.add("tipon");
  TIPFOR = btn;
  TIPHOW = how || "";
}

function hideTip(){
  const el = document.getElementById("tip");
  if (el){ el.classList.remove("on"); el.hidden = true; }
  if (TIPFOR) TIPFOR.classList.remove("tipon");
  TIPFOR = null;
  TIPHOW = "";
}

function bindTips(){
  /* Once only. Every listener below is delegated on [data-tip], so a button
     drawn later is already covered; a second binding doubled every handler,
     and two click handlers toggling the same bubble shut it in one tap. */
  if (bindTips.bound) return;
  bindTips.bound = true;
  /* HOVER is a mouse thing, and only a mouse thing.
     A tap fires pointerover, pointerout and click in one gesture, so a bubble
     that opened on pointerover would then be toggled shut by the click - the
     button appearing not to work at all. So on a touch screen the tap alone
     opens and closes it, and the hover handlers ignore anything that is not a
     mouse. */
  document.addEventListener("pointerover", e => {
    if (e.pointerType && e.pointerType !== "mouse") return;
    const btn = e.target.closest && e.target.closest("[data-tip]");
    if (btn && btn !== TIPFOR) showTip(btn, "hover");
  });
  document.addEventListener("pointerout", e => {
    if (e.pointerType && e.pointerType !== "mouse") return;
    const btn = e.target.closest && e.target.closest("[data-tip]");
    /* Moving INTO a child fires pointerout on the parent - that is what this
       event means, unlike pointerleave. The (i) buttons have nothing inside
       them so it never showed; a chart bar has a label, a track and a number,
       and the bubble opened and shut again in the same gesture. */
    if (btn && btn === TIPFOR
        && !(e.relatedTarget && btn.contains(e.relatedTarget))) hideTip();
  });
  document.addEventListener("click", e => {
    const btn = e.target.closest && e.target.closest("[data-tip]");
    /* A chart mark that carries a search does that when you click it. Toggling
       a bubble on top of the tab it has just moved you to would be noise. */
    if (btn && (btn.closest("[data-ask]") || btn.hasAttribute("data-tipnoclick"))){
      hideTip(); return;
    }
    if (btn){
      e.preventDefault();
      /* A second TAP closes it; the focus that tapping the button also caused
         must not. Without remembering how it opened, a tap focuses the button,
         the focus opens the bubble, and the click that follows in the same
         gesture reads it as already open and shuts it again - one tap, nothing
         visible, a button that appears dead. */
      if (btn === TIPFOR && TIPHOW === "click") hideTip();
      else showTip(btn, "click");
      return;
    }
    hideTip();                         // anywhere else closes it
  });
  document.addEventListener("focusin", e => {
    const btn = e.target.closest && e.target.closest("[data-tip]");
    if (btn) showTip(btn, "focus"); else if (TIPFOR) hideTip();
  });
  addEventListener("keydown", e => { if (e.key === "Escape") hideTip(); });
  addEventListener("scroll", hideTip, true);
  addEventListener("resize", hideTip);
}

function group(g, fold, flat, open){
  /* A whole group of advanced settings folds away under its own name. A group
     that MIXES them shows the plain ones and folds the rest under "More" -
     otherwise marking one option advanced inside a normal group did nothing at
     all, and the form filled up with settings nobody changes.

     `flat` is for a group that is already INSIDE the one Advanced disclosure:
     everything in it is advanced by definition, and a fold inside a fold is a
     setting two clicks deep that nobody will ever find again. */
  const plain = flat ? g.options : g.options.filter(o => !o.advanced);
  const extra = flat ? [] : g.options.filter(o => o.advanced);

  if (!flat && (g.advanced || (!plain.length && extra.length && g.name)))
    return g.name
      ? `<details class="fold"><summary>${esc(g.name)}</summary>
           <div>${g.options.map(control).join("")}</div></details>`
      : moreFold(g.options.length, g.options.map(control).join(""), "");

  let body = plain.map(control).join("");
  if (extra.length)
    body += moreFold(extra.length, extra.map(control).join(""),
                     ' style="margin-bottom:4px"');
  if (!g.name) return body;
  /* A tab that says so starts each group folded. Search is twenty-two boxes
     over six groups, which on a phone is a column you scroll past to reach the
     button; folded it is six lines you can read. What is folded is named and
     counted, and a group carrying a value opens itself (`foldSettle`), so this
     can never hide something that is in force. */
  if (fold)
    return `<details class="fold gfold" data-g="${esc(g.name)}"${open ? " open" : ""}>
      <summary>${swatch(g.name)}${esc(g.name)}<span class="gcount"></span></summary>
      <div>${body}</div></details>`;
  /* A group that IS a colour wears it. "What does red mean to you" over five
     identical grey boxes is a page you have to read to use; with the colours on
     it you find the row you meant without reading anything. */
  const tint = tintOf(g.name);
  return `<fieldset${tint ? ` class="tinted t-${tint}"` : ""}>
    <legend>${swatch(g.name)}${esc(g.name)}</legend>${body}</fieldset>`;
}

/* The five colours this app knows, by the words it writes into a file. Matched
   on the GROUP name, so nothing has to be declared twice: the colour settings
   name their groups Red, Yellow, Green, Blue, Purple because that is what they
   are about. */
const TINTS = ["red", "yellow", "green", "blue", "purple"];

function tintOf(name){
  const low = String(name || "").trim().toLowerCase();
  return TINTS.indexOf(low) >= 0 ? low : "";
}

function swatch(name){
  const tint = tintOf(name);
  return tint ? `<span class="cswatch c-${tint}" aria-hidden="true"></span>` : "";
}

/* One Advanced, not seven.
   Every feature here has a handful of settings that matter and a handful that
   are there because somebody's library needs them, and the second lot were
   folded away one group at a time - so a form could show five collapsed boxes
   named More, Limits, What to do with RAWs, and you still had to open each to
   find out whether any of it concerned you. They are one disclosure now, named
   and counted, and what is left above it is the decision you came to make. */
function formGroups(t){
  const plain = t.groups.filter(g => !g.advanced);
  const extra = t.groups.filter(g => g.advanced);
  /* A long form starts with its groups folded, all but the first: that is
     where the folder is, and a form whose folder is behind a closed heading
     reads as a form with no folder. When the first group has no name its boxes
     are not folded at all, which comes to the same thing. The Advanced ones
     stay under the one Advanced, folded or not. */
  const body = t.fold_groups
    ? plain.map((g, i) => group(g, true, false, i === 0)).join("")
    : plain.map(g => group(g, false)).join("");
  if (!extra.length) return body;
  const n = extra.reduce((k, g) => k + g.options.length, 0);
  return body + moreFold(n, extra.map(g => group(g, false, true)).join(""), "adv");
}

/* ONE FOLD for settings that are there when you need them. Setup said "More",
   every other form "Advanced · 3 settings", and the two sat side by side in
   different case; now both are "More settings (3)", in sentence case like
   every other fold row. */
function moreFold(n, inside, how){
  /* "adv" is the form's one fold under everything else, which the page finds
     by its id; any other is a fold inside a group. */
  const head = how === "adv" ? `<details class="fold adv" id="advanced">`
                             : `<details class="fold"${how || ""}>`;
  return head + `
    <summary>More settings<span class="gcount"> (${num(n)})</span></summary>
    <div>${inside}</div></details>`;
}

function foldSettle(){
  /* Open the groups that are carrying something, and say how much each holds.
     Run after the boxes are filled - which is the whole point: it is what is IN
     them, not what they were declared as, that decides.

     "Carrying something" is a box that no longer says what the form opened
     with. On Search every box opens empty, so that is any box filled in; on
     By date half of them open with a number in, and counting those would open
     every group on the way in and fold nothing. */
  const declared = {};
  for (const o of (CURRENT && CURRENT.options) || []) declared["o_" + o.name] = o;
  document.querySelectorAll("#form details.gfold").forEach(d => {
    let set = 0;
    d.querySelectorAll("input,select,textarea").forEach(el => {
      const o = declared[el.id];
      if (o){ if (movedFrom(el, o)) set++; }
      else if (el.type === "checkbox" || el.type === "radio"){ if (el.checked) set++; }
      else if (el.tagName === "SELECT"){
        if (el.value && el.selectedIndex > 0) set++;
      } else if (String(el.value || "").trim()) set++;
    });
    const tag = d.querySelector(".gcount");
    if (tag) tag.textContent = set ? ` \u00b7 ${set} set` : "";
    d.classList.toggle("has", !!set);
    if (set) d.open = true;
  });
}

/* Has this box been changed from the value the form opened it with? Numbers
   compare as numbers, so 5 drawn as "5" and declared as 5.0 is not a change. */
function movedFrom(el, o){
  if (o.kind === "flag") return el.checked !== !!o.default;
  const now = String(el.value == null ? "" : el.value).trim();
  const was = String(o.default == null ? "" : o.default).trim();
  if (now === was) return false;
  if (now !== "" && was !== "" && !isNaN(now) && !isNaN(was))
    return Number(now) !== Number(was);
  return true;
}

/* ---------------------------------------------------- the same shape every time

   Every feature here is the same four steps - set it up, look at what it would
   do, let it do it, read what happened - and until now you could only tell
   which one you were on by what happened to be on the screen. A strip at the
   top says it out loud, which costs one line and answers "did I already press
   the button" without scrolling.

   Drawn only for a feature that WRITES. A tab that reports has two steps, and
   four boxes with two of them permanently grey is furniture. */
const STEPS = ["Set it up", "Check the list", "Apply", "What happened"];

/* ONE WORD PER IDEA, in one place.

   The same act had four names depending on which screen you were on: "Show me
   what would happen", "Have a look", "Go ahead", "Look again". Each reads well
   on its own and together they teach that this app has several kinds of button
   doing several kinds of thing - which it has not. A person should learn the
   word once.

       CHECK    make the list of what would happen. Named after step two, so
                the button and the strip above it say the same thing.
       APPLY    do exactly that list. Always carries the real verb and the
                count - "Move 412 files" - because a button that says "Apply"
                and moves four hundred files has not told you anything.
       AGAIN    make the list again, after something has changed.
       RUN      only automation, which is the one thing here that is not a
                plan you read first.
       MORE     only an overflow menu. Never a feature, never an action.
       DONE     leave a mode you are in (selecting, arranging).
       BACK     return to where you were.

   Anything that wants a different word needs a reason that survives being
   asked "and what does the other one mean, then?". */
const WORDS = {
  check: "Check the list",
  again: "Check again",
  apply: "Apply",
  run: "Run",
  more: "More",
  done: "Done",
  back: "Back",
};

function stepStrip(t){
  if (!t.writes || t.settings) return "";
  return `<ol class="steps" id="steps" data-at="1">` + STEPS.map((w, i) =>
    `<li data-s="${i + 1}"><b>${i + 1}</b><span>${esc(w)}</span></li>`).join("")
    + `</ol>`;
}

function setStep(n){
  const strip = document.getElementById("steps");
  if (!strip) return;
  strip.dataset.at = n;
  strip.querySelectorAll("li").forEach(li => {
    const at = +li.dataset.s;
    li.classList.toggle("now", at === n);
    li.classList.toggle("done", at < n);
  });
}

/* Editors a library piece adds for a tab of its own: `TAB_EDITORS.name =
   start`, and the tab draws <div id="tabedit"> and calls start() once it is
   on the page. Growing the list above for every new editor is how this file
   got to eight thousand lines. */
const TAB_EDITORS = {};

function show(name){
  const wanted = byName(name);
  if (!wanted) return;
  /* Arranging is a mode you leave when you leave the tab. Coming back to the
     Library half an hour later and finding every widget wearing a delete cross
     is a page that looks like it is mid-edit when you were only looking. */
  if (!CURRENT || CURRENT.name !== name) ARRANGING = false;
  if (CURRENT && CURRENT.name !== name) keepWhereYouWere();
  CURRENT = wanted;
  /* The address says which feature is open, but it does NOT add a step to the
     browser's history: the trail does that, once per move (`trailPush`), and
     two sources of history entries meant one press of the browser's Back went
     two places. A link with #name in it still lands on that feature - that is
     read at boot, not from here. */
  try{
    history.replaceState(history.state, "",
                         location.pathname + location.search + "#" + wanted.name);
  }catch(e){ location.hash = wanted.name; }
  const box = SEEN[name] || {};
  PLAN = box.plan || null;

  const root = wanted.parent ? byName(wanted.parent) : wanted;
  document.querySelectorAll("#apart button").forEach(b =>
    b.classList.toggle("on", b.dataset.t === root.name));
  /* Looking at the runs IS reading them. Clearing on the Automation tab itself
     would mean the mark disappears when you go to change a setting, which is
     not the same thing as having read what happened. */
  if (wanted.name === "autoruns") markAutoSeen();
  clearFinished(wanted.name);
  if (HEALTH) showHealth(HEALTH, true);

  /* No tab row. Each tool is a page of its own, and the tools beside it -
     the rest of its group, as arranged on All tools - are listed down the
     right by drawToolSide (library/js/22-tool-side.js), drawn after this. */

  /* A settings tab SAVES. Everything else shows what would happen and waits for
     Go ahead, which is right for moving four hundred photographs and absurd for
     writing down where your library is - and it meant a path typed and then
     walked away from was never saved at all, silently. */
  const buttons = wanted.settings
    ? `<button id="save">${icon("again")} Save</button>`
      + (wanted.writes
         ? `<button id="go" class="ghost">${esc(wanted.run_label
              || WORDS.check)}</button>` : "")
    : `<button id="go">${esc(wanted.run_label || WORDS.check)}</button>`;

  /* Named here rather than left implicit: a form that silently refuses to be
     typed into is a form that looks broken. The line only exists on a tab that
     has something to lock, and lockLocked() shows or hides it. */
  const locknote = wanted.options.some(o => o.needs_off)
    ? `<div class="note" id="lockednote" hidden>${icon("lock")}
         <span>These settings are locked because it is running in the
         background. Turn the switch off to change them - a pass firing half way
         through your edits is how a loop ends up running settings nobody
         chose.</span></div>` : "";

  /* On a PC the NAS tab is not drawn, and the server did not send its tools.
     Setup says so in one line, so nobody goes looking for them. */
  const nasnote = wanted.name === "setup" && NAS_ONLY.length
    ? `<div class="note" id="nasonly">${icon("nas")}<span>Reindex and
         Permissions are NAS-only, so they are left out on a PC. The command
         line still runs them.</span></div>` : "";

  /* An editor belongs to the TAB, not to a plan: a tab whose whole purpose is
     the editor must not make you press "Have a look" to see it. */
  const editor = wanted.editor === "files" ? `<div id="fileman"></div>`
              : wanted.editor === "search" ? `<div id="searchbar"></div>`
              : wanted.editor === "cameras" ? `<div id="camerabar"></div>`
              : wanted.editor === "rename" ? `<div id="renamer"></div>`
              : wanted.editor === "flows" ? `<div id="flowedit"></div>`
              : wanted.editor === "flowsummary" ? `<div id="flowsum"></div>`
              : TAB_EDITORS[wanted.editor] ? `<div id="tabedit"></div>` : "";
  document.getElementById("form").innerHTML =
    /* The sentence about what a feature does is in the bubble beside its
       name, not printed under it. It was the first thing on every screen and
       the least useful after the first time: you read it once, and then it was
       a line of prose pushing the controls down on every visit. */
    `<h2>${icon(wanted.icon)}${esc(wanted.title)}
       ${wanted.summary ? `<button class="info" type="button"
          aria-label="What this does" data-tip="${esc(wanted.summary)}">i</button>`
          : ""}
       <button class="info pinbtn${PINNED.indexOf(wanted.name) >= 0 ? " on" : ""}"
         type="button" onclick="pinToggle('${quoted(wanted.name)}')"
         data-tip="${PINNED.indexOf(wanted.name) >= 0
           ? S.pinnedTip
           : "Put this on the main list, beside Home and Photos"}"
         aria-label="Pin to the main list">${icon("pin")}</button>
       ${wanted.settings ? '<span class="tag">settings</span>'
         : (wanted.writes || wanted.name === "files" || TAB_EDITORS[wanted.editor] ? ""
            : '<span class="tag">only ever reports</span>')}</h2>
     ${stepStrip(wanted)}
     ${editor}
     ${locknote}
     ${nasnote}
     ${/* THE EXPLORER IS NOT A PLAN.

           Under the file manager sat the ordinary feature form: a box repeating
           the folder the crumbs already name, two checkboxes, and a "Check the
           list" button whose whole answer was a count of what is in the folder -
           which is the line above the listing. Pressing it was a step that
           produced something you were already looking at.

           The boxes themselves stay in the page, because the manager reads them
           when it copies and deletes; they are reachable from the View menu,
           where everything else about how this tab behaves lives. */
       wanted.editor === "files"
         ? `<div hidden>${formGroups(wanted)}</div>`
         : `${formGroups(wanted)}
            <div class="act">${buttons}<span class="note" id="saidsaved"></span></div>`}
     <div class="note" id="followed" style="margin-top:8px"></div>`;
  for (const o of wanted.options) if (o.kind === "pattern") patCheck(o.name);
  const go = document.getElementById("go");
  if (go) go.onclick = run;
  const sv = document.getElementById("save");
  if (sv) sv.onclick = save;
  if (wanted.editor === "files") startFiles();
  if (wanted.editor === "rename") startRename();
  if (wanted.editor === "search") startSearch();
  if (wanted.editor === "cameras") startCameras();
  if (TAB_EDITORS[wanted.editor]) TAB_EDITORS[wanted.editor]();
  /* A tab that IS the thing it shows: there is nothing to fill in and nothing
     to decide, so making you press "Have a look" at an empty form to see your
     own settings would be a step that exists for the machine. */
  if (wanted.editor === "bands")
    setTimeout(() => { const b = document.getElementById("go"); if (b) b.click(); }, 0);
  if (wanted.editor === "flows"){ FLOWS = null; loadFlows(); }
  if (wanted.editor === "flowsummary"){
    loadSummary();
    /* Picking a different flow redraws the picture at once rather than after a
       plan - choosing from a dropdown and seeing last flow's chain is the kind
       of small lie that makes a page feel untrustworthy. */
    const which = document.getElementById("o_which");
    if (which) which.addEventListener("change", drawSummary);
  }

  // whatever was typed here before the tab was left, back in the boxes
  for (const o of wanted.options){
    if (!box.values || !(o.name in box.values)) continue;
    const el = document.getElementById("o_" + o.name);
    if (!el) continue;
    if (o.kind === "flag") el.checked = !!box.values[o.name];
    else el.value = box.values[o.name];
  }

  /* A chooser that knows the pattern behind each of its choices drives the
     box beside it, both ways: pick a ready-made shape and the box shows what it
     actually does; type in the box and the chooser says "your own". The box
     used to appear only once you had found "Write my own pattern..." at the
     bottom of a dropdown, which is a field hidden inside a menu. */
  for (const o of wanted.options){
    if (!o.patterns || !Object.keys(o.patterns).length) continue;
    const pick = document.getElementById("o_" + o.name);
    const box = document.getElementById("o_pattern");
    if (!pick || !box) continue;
    pick.addEventListener("change", () => {
      const said = o.patterns[pick.value];
      if (said) box.value = said;
      box.dispatchEvent(new Event("input", {bubbles: true}));
      if (typeof patCheck === "function") patCheck("pattern");
    });
    box.addEventListener("input", () => {
      // Only when it stops matching the shape that is chosen - so merely
      // looking at the box does not quietly change what you picked.
      if (box.value.trim() && box.value.trim() !== (o.patterns[pick.value] || "").trim()
          && [...pick.options].some(x => x.value === "custom"))
        pick.value = "custom";
    });
  }

  if (wanted.fold_groups){
    foldSettle();
    // and again whenever a box changes, so the count beside a folded group is
    // never one edit behind what is in it
    const form = document.getElementById("form");
    /* In the CAPTURE phase. `new Event("input")` does not bubble unless whoever
       made it said so, and half the app fills a box and fires exactly that - so
       a listener on the form itself simply never ran. A capture listener on an
       ancestor is called for a non-bubbling event too. */
    /* Once: #form outlives every tab drawn into it, and fifteen tabs fold now,
       so a listener per visit would pile up a foldSettle per tab opened. */
    if (form && !form.dataset.folds){
      form.dataset.folds = "1";
      form.addEventListener("input", () => foldSettle(), true);
    }
  }

  typedIn.clear();
  for (const o of wanted.options){
    if (o.kind === "folders" || (o.kind === "folder" && o.many)) drawChips(o.name);
    // a switch that gates other settings re-locks them the moment it moves
    const gate = document.getElementById("o_" + o.name);
    if (gate && (o.kind === "flag" || o.kind === "choice"))
      gate.addEventListener("change", lockLocked);
  }
  lockLocked();
  const from = document.getElementById("o_folder");
  if (from){
    from.addEventListener("input", followTrees);
    from.addEventListener("change", followTrees);
  }
  const mir = document.getElementById("o_mirror");
  if (mir) mir.addEventListener("change", greyDestinations);
  for (const o of wanted.options){
    if (!o.tree) continue;
    const el = document.getElementById("o_" + o.name);
    // typing in a tree box by hand stops it following - a box that overwrites
    // what you just typed is worse than one that never helped
    if (el) el.addEventListener("input", () => typedIn.add(o.name));
  }
  greyDestinations();

  folded.clear();
  if (box.folded) box.folded.forEach(f => folded.add(f));
  document.getElementById("out").innerHTML = box.out || "";
  setStep(box.out ? 2 : 1);
  if (box.out){
    // the restored HTML is inert until its buttons are wired up again
    if (PLAN && PLAN.tree && PLAN.tree.length) drawTree(PLAN.tree);
    const go = document.getElementById("doit");
    if (go) go.onclick = apply;
    const again = document.getElementById("again");
    if (again) again.onclick = run;
    const stop = document.getElementById("stop");
    if (stop) stop.onclick = askToStop;
    // a run that finished while you were on another tab: the card is still
    // saying "Working...", so finish it now rather than leaving it lying
    if (box.done && document.getElementById("apply")) finish(box.done);
    else if (WATCH && WATCH.task === name && !poller) poller = setInterval(poll, 400);
  }
  if (box.pending){
    // a scan that finished while you were elsewhere, drawn now rather than lost
    PLAN = box.pending;
    box.pending = null;
    render(PLAN);
  }
}

/* --------------------------------------------------------------- folder lists */

function chosenList(name){
  const el = document.getElementById("o_" + name);
  return String(el && el.value || "").split("\n").map(x => x.trim()).filter(Boolean);
}

function drawChips(name, empty){
  const box = document.getElementById("c_" + name);
  if (!box) return;
  const list = chosenList(name);
  box.innerHTML = list.length
    ? list.map((p, i) => `<span class="chip">${icon("folder")}<span>${esc(p)}</span>
        <button type="button" title="Remove" onclick="dropChip('${name}',${i})">
        \u00d7</button></span>`).join("")
    : `<span class="note">${esc(empty || emptyChipText(name))}</span>`;
}

function emptyChipText(name){
  const o = (CURRENT && CURRENT.options || []).find(x => x.name === name);
  return (o && o.kind === "folder")
    ? S.foldersNoneYet
    : S.skipNone;
}

function addChip(name, path){
  const list = chosenList(name);
  if (path && !list.includes(path)) list.push(path);
  document.getElementById("o_" + name).value = list.join("\n");
  drawChips(name);
  if (name === "folder") followTrees();
}

function dropChip(name, i){
  const list = chosenList(name);
  list.splice(i, 1);
  document.getElementById("o_" + name).value = list.join("\n");
  drawChips(name);
  if (name === "folder") followTrees();
}

function pickTab(name, value){
  const box = document.getElementById("o_" + name);
  if (!box) return;
  box.value = value;
  for (const b of document.querySelectorAll("#t_" + name + " button"))
    b.classList.toggle("on", b.dataset.v === value);
  lockLocked();
  if (PLAN || (SEEN[CURRENT.name] || {}).out) run();
}

function values(){
  const v = {};
  for (const o of CURRENT.options){
    const el = document.getElementById("o_" + o.name);
    if (!el) continue;
    v[o.name] = o.kind === "flag" ? el.checked : el.value;
  }
  return v;
}

/* --------------------------------------------------------------- seeing a photo

   Reading a list of file names and deciding whether to cull them is a guess.
   Seeing the photo is not, and it is the one thing a preview could not do.

   A browser cannot open a folder on your machine - nothing on a web page is
   allowed to, and it is the same rule that stops any other site rifling through
   your disk. So the folder is offered as a path to copy instead, which is what
   File Station and Explorer both take. */

/* Anything a thumbnail can be made of - RAWs and video too, when Synology
   Photos has made one. */
const SHOWABLE = /\.(jpe?g|png|webp|gif|tiff?|heic|heif|bmp|rw2|arw|dng|cr2|cr3|nef|orf|raf|mp4|mov|mts|m4v)$/i;
const VIEWABLE = /\.(jpe?g|png|webp|gif)$/i;

/* Every thumbnail address carries a stamp that changes whenever anything is
   re-read. A picture is cached hard - by the browser, and by the worker when
   this is installed on a phone - and its address does not otherwise change
   when the file behind it does, so an edited or replaced photo went on
   showing the old one with no way to clear it from here. */
/* THE ADDRESS OF A PICTURE MUST NOT CHANGE JUST BECAUSE THE PAGE RELOADED.

   This was `Date.now()` at the top of every page load, which put a new number
   on the end of every thumbnail address - so a browser that had been told it
   could keep them for a day never used one of them. A screenful of two hundred
   and forty tiles was two hundred and forty requests to the NAS for pictures
   the browser already had, every single time the page opened.

   It is now remembered, and it changes when Refresh says the pictures may have
   changed. Where the file's own date is known - the grid, an album cover, the
   explorer - that is used instead, which is better still: a photograph that has
   actually been edited gets a new address the moment it is read again. */
let PICV = (function(){
  try{
    const kept = localStorage.getItem("pm-picv");
    if (kept) return kept;
    const now = String(Date.now());
    localStorage.setItem("pm-picv", now);
    return now;
  }catch(e){ return "1"; }
})();
function freshPics(){
  PICV = String(Date.now());
  try{ localStorage.setItem("pm-picv", PICV); }catch(e){}
  /* The worker keeps thumbnails by address; with a new stamp every one of
     them is an address nothing will ask for again, so they go now. */
  try{
    const sw = navigator.serviceWorker && navigator.serviceWorker.controller;
    if (sw) sw.postMessage("forget-pics");
  }catch(e){}
}
function thumbSrc(path, size, when){
  return "api/thumb?s=" + (size || "s") + "&path=" + encodeURIComponent(path)
    + "&v=" + (when ? Math.round(when) : PICV);
}
let SKIPPEDPICS = [];
function peekSkipped(path){ return peek(path, SKIPPEDPICS); }
/* ------------------------------------------------------------------ the viewer

   One photo, full screen, and everything you do to a photo while looking at
   it: stars, a colour, tags, delete. Built for a thumb first.

   - The stars sit ON the picture, big enough to hit. Tapping the star you
     already gave takes it off again.
   - Colour and Tags are menus that open from the bottom - on a phone as a sheet
     your thumb reaches, on a desk as a popover.
   - Swipe left and right for the next photo, down to close, up for tags. A tap
     on the picture hides everything but the picture.
   - Keys at a desk: arrows, 0-5 stars, 6-9 colours (as Lightroom), T tags,
     Delete, Esc.

   Every change shows at once and is written behind it. If the NAS says no, it
   goes back and says why. Delete goes to the share's Recycle Bin and offers
   Undo for a few seconds - no "are you sure", because it is not final. */

const VIEW = {list: [], at: -1, items: {}, vocab: [], colours: [], busy: 0,
              chrome: true, undo: null, toastTimer: 0, shot: {}};
const COLOUR_KEYS = {"6": "red", "7": "yellow", "8": "green", "9": "blue"};

/* Space plays and pauses, because that is what space does in every player
   anybody has used. The arrows still move between photographs rather than
   seeking: this is a library with clips in it, not a video editor, and a left
   arrow that sometimes changes photograph and sometimes rewinds four seconds is
   worse than either. The clip's own bar scrubs. */
function clipKey(key){
  const vid = document.getElementById("vvid");
  if (!vid || vid.hidden || !vid.src) return false;
  if (key !== " " && key !== "Spacebar") return false;
  if (vid.paused) vid.play().catch(() => {}); else vid.pause();
  return true;
}

function viewItem(path){
  if (!VIEW.items[path])
    VIEW.items[path] = {path: path, name: basename(path), stars: 0, colour: "",
                        tags: [], fresh: false};
  return VIEW.items[path];
}

/* What can carry a mark. A clip can: nothing is written into it, a sidecar is
   written beside it, exactly as a negative has always been. */
function editable(path){
  return /\.(jpe?g|png|webp|tiff?|heic|heif|rw2|arw|dng|cr2|cr3|nef|orf|raf)$/i.test(path)
      || /\.(mp4|mov|mts|m2ts|m4v|avi|webm|mkv|3gp|wmv|mpe?g)$/i.test(path);
}

function peek(path, list){
  VIEW.list = (Array.isArray(list) && list.length) ? list.slice() : [path];
  VIEW.at = Math.max(0, VIEW.list.indexOf(path));
  if (!document.getElementById("viewer")){
    overlaySaved();
    viewerBuild();
    VIEW.unhold = holdFocus(document.getElementById("viewer"),
                            document.getElementById("vclose"));
  }
  document.body.classList.add("viewing");
  VIEW.chrome = true;
  viewerShow(0);
  return false;
}

/* Focus that goes into a dialog stays in it, and goes back where it was when
   the dialog closes. Without the first, Tab walked out from under the viewer
   into the grid behind it, where nothing can be seen; without the second,
   closing it left the keyboard at the top of the page, a screen away from the
   photograph it was on. Returns the function that lets go. */
function holdFocus(box, first){
  const was = document.activeElement;
  const key = e => {
    if (e.key !== "Tab" || !box.isConnected) return;
    const all = [...box.querySelectorAll(
        'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')]
      .filter(el => !el.disabled && !el.hidden && el.getClientRects().length);
    if (!all.length) return;
    const a = all[0], z = all[all.length - 1], at = document.activeElement;
    if (e.shiftKey && (at === a || !box.contains(at))){ e.preventDefault(); z.focus(); }
    else if (!e.shiftKey && (at === z || !box.contains(at))){ e.preventDefault(); a.focus(); }
  };
  document.addEventListener("keydown", key, true);
  if (first && first.focus) first.focus();
  return () => {
    document.removeEventListener("keydown", key, true);
    if (was && was.isConnected && was.focus && was !== document.body) was.focus();
  };
}

function viewerBuild(){
  const stars = [1, 2, 3, 4, 5].map(n =>
    `<button type="button" class="vstar" data-n="${n}" aria-label="${n} star${n > 1 ? "s" : ""}">★</button>`).join("");
  document.body.insertAdjacentHTML("beforeend", `
  <div id="viewer" class="viewer chrome" role="dialog" aria-modal="true" aria-label="Photo">
    <div class="vstage" id="vstage">
      <img id="vimg" alt="" draggable="false">
      <video id="vvid" hidden controls preload="metadata" playsinline></video>
      <div class="vnopic" id="vnopic" hidden>${esc(S.noPreview)}</div>
    </div>
    <div class="vhist" id="vhist" hidden>
      <canvas id="vhistc" width="256" height="110" aria-label="Histogram"></canvas>
      <div class="vhistfoot"><span id="vhistmode">RGB + luminance</span>
        <span id="vhistclip"></span></div>
    </div>
    <div class="vshot" id="vshot" hidden></div>
    <div class="vzoom" id="vzoom" hidden>100%</div>
    <div class="vtop">
      <button type="button" class="vbtn" id="vclose" aria-label="Close">${icon("cross")}</button>
      <div class="vtitle"><div id="vname"></div><div class="vdim" id="vcount"></div></div>
      <button type="button" class="vbtn" id="vshotb" aria-label="Exposure details"
        title="How it was exposed${KEYS.info ? ` (${KEYS.info.toUpperCase()})` : ""}"
        >${icon("info")}</button>
      <button type="button" class="vbtn" id="vhistb" aria-label="Histogram"
        title="Histogram${KEYS.histogram ? ` (${KEYS.histogram.toUpperCase()})` : ""}"
        >${icon("hist")}</button>
      <button type="button" class="vbtn" id="vfullb" aria-label="Full size"
        title="Show the file itself rather than a preview of it"
        >${icon("expand-all")}</button>
      <div class="vmenu">
        <button type="button" class="vbtn" id="vmore" aria-label="More">⋯</button>
        <div class="vpop vright" id="vmorepop" hidden></div>
      </div>
      <button type="button" class="vbtn vdanger" id="vdel" aria-label="Delete" title="Delete (Del)">${icon("trash")}</button>
    </div>
    <button type="button" class="vnav vprev" id="vprev" aria-label="Previous">${icon("back")}</button>
    <button type="button" class="vnav vnext" id="vnext" aria-label="Next">${icon("forward")}</button>
    <div class="vbottom" id="vbottom">
      <div class="vstars" id="vstars">${stars}</div>
      <div class="vrow">
        <div class="vmenu">
          <button type="button" class="vpill" id="vcolbtn"><span class="cdot" id="vcoldot"></span>
            <span id="vcolname">Colour</span><span class="vcaret">${icon("expand-one")}</span></button>
          <div class="vpop" id="vcolpop" hidden></div>
        </div>
        <div class="vmenu">
          <button type="button" class="vpill" id="vtagbtn">${icon("tag")}
            <span id="vtagname">Tags</span><span class="vcaret">${icon("expand-one")}</span></button>
          <div class="vpop vtags" id="vtagpop" hidden>
            <input id="vtagin" type="text" placeholder="Find or add a tag" autocomplete="off"
                   enterkeyhint="done">
            <div id="vtaglist" class="vtaglist"></div>
          </div>
        </div>
      </div>
      <div class="vchips" id="vchips"></div>
    </div>
  </div>`);

  const $ = id => document.getElementById(id);
  $("vclose").onclick = viewerClose;
  $("vprev").onclick = () => viewerStep(-1);
  $("vnext").onclick = () => viewerStep(1);
  $("vdel").onclick = viewerDelete;
  $("vmore").onclick = e => { e.stopPropagation(); viewerMenu("vmorepop"); };
  $("vshotb").onclick = e => { e.stopPropagation(); overlayToggle("shot"); };
  $("vhistb").onclick = e => { e.stopPropagation(); overlayToggle("hist"); };
  $("vfullb").onclick = e => { e.stopPropagation(); fullToggle(); };
  /* Pressing the histogram itself changes what it draws - the three channels
     are for spotting one of them clipping, the luminance for reading the
     exposure, and which you want changes with the photograph in front of you. */
  $("vhist").onclick = e => { e.stopPropagation(); histMode(); };
  $("vimg").addEventListener("load", () => drawHistogram());
  $("vcolbtn").onclick = e => { e.stopPropagation(); viewerMenu("vcolpop"); };
  $("vtagbtn").onclick = e => { e.stopPropagation(); viewerMenu("vtagpop"); };
  $("vstars").onclick = e => {
    const b = e.target.closest(".vstar");
    if (b) viewerStars(+b.dataset.n);
  };
  $("vtagin").oninput = () => drawTagList();
  $("vtagin").onkeydown = e => {
    if (e.key === "Enter"){
      e.preventDefault();
      const word = $("vtagin").value.trim();
      if (word){ viewerTag(word, true); $("vtagin").value = ""; drawTagList(); }
    }
    e.stopPropagation();
  };
  document.querySelectorAll("#viewer .vpop").forEach(p =>
    p.addEventListener("click", e => e.stopPropagation()));
  $("viewer").addEventListener("click", e => {
    if (!e.target.closest(".vmenu")) viewerMenu("");
  });
  viewerGestures($("vstage"));
}

function viewerMenu(id){
  /* The viewer may have gone. Pressing the X closes it, and the same click then
     carries on up to the viewer's own listener - which is on the element that
     has just been removed. It threw there, which in the console looks like the
     viewer failed to close rather than like it closed twice. */
  if (!document.getElementById("viewer")) return;
  document.querySelectorAll("#viewer .vpop").forEach(p => {
    const open = p.id === id && p.hidden;
    p.hidden = !open;
    if (open){
      if (p.id === "vcolpop") drawColours();
      if (p.id === "vtagpop"){
        drawTagList();
        const box = document.getElementById("vtagin");
        box.value = "";
        /* A phone's keyboard would cover the list; open it only where there
           is a real keyboard. */
        if (matchMedia("(pointer: fine)").matches) setTimeout(() => box.focus(), 30);
      }
      if (p.id === "vmorepop") drawMore();
    }
  });
  document.getElementById("viewer").classList.toggle("menuopen", !!id &&
    !document.getElementById(id)?.hidden);
}

function viewerClose(){
  stopClip();                       // nothing goes on playing behind the grid
  const v = document.getElementById("viewer");
  if (v) v.remove();
  document.body.classList.remove("viewing");
  if (VIEW.unhold){ const let_go = VIEW.unhold; VIEW.unhold = null; let_go(); }
  /* The toast is NOT cancelled here, and that is a real bug fixed: deleting the
     last photograph closes the viewer, and closing it used to clear the timer
     that hides the "Deleted - Undo" line. So the one toast you most want to be
     able to act on was the one that never went away. It lives on the page, not
     in the viewer, and it can see itself out. */
}

function viewerPath(){ return VIEW.list[VIEW.at] || ""; }

/* ---- the file itself, not a picture of it

   The viewer has always shown a 2,000px preview. That is the right default -
   it arrives at once over a phone connection and it is what a library is for -
   but it is the wrong thing entirely when the question is "is this sharp".
   Zooming into a preview magnifies the preview.

   So it is a switch, and the switch STAYS ON: deciding frame by frame which
   one you are looking at is the state nobody can hold, and culling for focus
   means going through forty frames at full size, not one. It says which it is
   showing while the full-size file is on its way, because a 25MB file over
   wifi is a second or two of looking at the preview wondering if it worked. */
function wantsFull(){
  try{ return localStorage.getItem("pm-full") === "yes"; }catch(e){ return false; }
}

/* A RAW has no picture a browser can open - the preview IS the only picture of
   it there is - and a clip is streamed either way. */
const FULLSIZE = /\.(jpe?g|png|webp|tiff?|heic|heif)$/i;

function canFull(path){ return FULLSIZE.test(path || ""); }

function fullToggle(on){
  const want = on === undefined ? !wantsFull() : !!on;
  try{ localStorage.setItem("pm-full", want ? "yes" : "no"); }catch(e){}
  toast(want ? S.fullOn : S.fullOff, 4000);
  viewerFullDraw();
  viewerShow(0);
}

/* The file itself, fetched once and swapped in under whatever is on screen.

   Called by the switch and by zooming past what a preview holds - the same
   job either way, so it is in one place and it never fetches the same file
   twice. */
function wantBigger(){
  const path = viewerPath();
  if (!path || !canFull(path)) return;
  const img = document.getElementById("vimg");
  if (!img || img.dataset.full === path) return;
  img.dataset.full = path;
  const big = new Image();
  big.onload = () => {
    if (viewerPath() !== path) return;
    img.src = big.src;
    viewerFullDraw();
  };
  big.onerror = () => { if (img.dataset.full === path) img.dataset.full = ""; };
  big.src = "api/file?path=" + encodeURIComponent(path);
}

function viewerFullDraw(){
  const b = document.getElementById("vfullb");
  if (!b) return;
  const path = viewerPath();
  const on = wantsFull() && canFull(path);
  b.classList.toggle("on", on);
  b.disabled = !canFull(path) && !wantsFull();
  const here = document.getElementById("vimg");
  const arrived = here && here.dataset.full === path;
  b.title = !canFull(path)
    ? "Only a preview can be made of this one"
    : (arrived ? S.fullShownTip
       : wantsFull() ? "Fetching the file itself..."
                     : "Show the file itself rather than a preview of it");
}

/* A CLIP IS NOT A PICTURE OF A CLIP.

   The viewer showed a video's thumbnail: a still frame, with the play triangle
   drawn on the tile, and nothing happened when you pressed it. It plays now -
   streamed, so it starts at once and can be scrubbed - and where a browser
   genuinely cannot decode the format (MTS and AVI are what cameras write and
   browsers have never played) it says so in those words and offers the file
   instead of showing a black rectangle. */
const PLAYABLE = /\.(mp4|m4v|mov|webm|ogv)$/i;
const NOTPLAYABLE = /\.(mts|m2ts|avi|wmv|mpe?g|3gp|mkv|flv)$/i;

function isClip(path){ return PLAYABLE.test(path) || NOTPLAYABLE.test(path); }

/* Why this clip will not play, as a sentence, or "" when it will.

   ASKED BEFORE LOADING, not after failing. A browser that cannot decode a
   format shows a black rectangle and reports nothing for a second or two
   first - and a black rectangle is indistinguishable from a broken app. The
   browser already knows what it can decode; this asks it. */
const CODECS = {mp4: 'video/mp4; codecs="avc1.42E01E"', m4v: 'video/mp4',
                mov: 'video/quicktime', webm: 'video/webm', ogv: 'video/ogg'};

function cannotPlay(path){
  const ext = (path.split(".").pop() || "").toLowerCase();
  if (NOTPLAYABLE.test(path))
    return say("notPlayable", {ext: ext.toUpperCase()});
  try{
    const probe = document.createElement("video");
    const said = probe.canPlayType(CODECS[ext] || "video/mp4");
    if (said === "")
      return say("cannotPlayType", {ext: ext.toUpperCase()});
  }catch(e){ return ""; }
  return "";
}

function stopClip(){
  const vid = document.getElementById("vvid");
  if (!vid) return;
  try{ vid.pause(); }catch(e){}
  vid.removeAttribute("src");
  try{ vid.load(); }catch(e){}
  vid.hidden = true;
}

async function viewerShow(dir){
  const path = viewerPath();
  const img = document.getElementById("vimg");
  const none = document.getElementById("vnopic");
  const vid = document.getElementById("vvid");
  if (!path){ viewerClose(); return; }
  none.hidden = true;
  // Whatever was playing stops the moment you move on. A clip still running
  // under the next photograph is the kind of thing that makes an app feel
  // haunted.
  stopClip();
  if (isClip(path)){
    img.hidden = true;
    const why = cannotPlay(path);
    if (!why){
      vid.hidden = false;
      vid.poster = thumbSrc(path, "l");
      vid.src = "api/video?path=" + encodeURIComponent(path);
      vid.onerror = () => {
        stopClip();
        none.hidden = false;
        none.textContent = S.couldNotPlay;
      };
    } else {
      none.hidden = false;
      none.textContent = why;
    }
  } else {
    img.hidden = false;
    img.onerror = () => { img.hidden = true; none.hidden = false;
                          none.textContent = S.noPreview; };
    img.className = dir > 0 ? "in-right" : dir < 0 ? "in-left" : "in";
    img.style.transform = "";
    /* The preview first, so there is a picture on screen immediately, and the
       file itself over the top of it when it arrives. A blank frame for two
       seconds reads as the app having lost the photograph. */
    img.dataset.full = "";
    img.src = thumbSrc(path, "l");
    if (wantsFull()) wantBigger();
    void img.offsetWidth;
    img.classList.add("settled");
  }
  // A new photograph starts fitted to the screen. Keeping the zoom from the
  // last one lands you in the top-left corner of a frame you have not seen.
  ZOOM.at = 1; ZOOM.x = ZOOM.y = 0;
  zoomDraw();
  document.getElementById("vname").textContent = basename(path);
  document.getElementById("vcount").textContent =
    VIEW.list.length > 1 ? `${VIEW.at + 1} of ${VIEW.list.length}` : "";
  const many = VIEW.list.length > 1;
  document.getElementById("vprev").hidden = !many;
  document.getElementById("vnext").hidden = !many;
  const can = editable(path);
  document.getElementById("vbottom").hidden = !can;
  viewerMenu("");
  viewerFullDraw();
  viewerDraw();
  overlayDraw();
  // the neighbours, so the next swipe is already there
  for (const k of [1, -1]){
    const n = VIEW.list[(VIEW.at + k + VIEW.list.length) % VIEW.list.length];
    if (n && n !== path) (new Image()).src = thumbSrc(n, "l");
  }
  if (can){
    try{
      const got = await (await fetch("api/photo?path=" + encodeURIComponent(path))).json();
      if (got.error) return;
      const it = viewItem(path);
      it.stars = got.stars; it.colour = got.colour; it.tags = got.tags; it.fresh = true;
      VIEW.vocab = got.vocab || VIEW.vocab;
      VIEW.colours = got.colours || VIEW.colours;
      VIEW.shot = VIEW.shot || {};
      if (got.shot) VIEW.shot[path] = got.shot;
      if (viewerPath() === path){ viewerDraw(); drawShot(); }
    }catch(e){}
  }
}

function viewerStep(by){
  if (VIEW.list.length < 2) return;
  VIEW.at = (VIEW.at + by + VIEW.list.length) % VIEW.list.length;
  viewerShow(by);
}

function colourName(c){
  const d = (VIEW.colours || []).find(x => x.colour === c);
  const word = c ? c[0].toUpperCase() + c.slice(1) : "";
  return d && d.name ? `${d.name}` : word;
}

function viewerDraw(){
  const it = viewItem(viewerPath());
  document.querySelectorAll("#vstars .vstar").forEach(b =>
    b.classList.toggle("on", +b.dataset.n <= (it.stars || 0)));
  const dot = document.getElementById("vcoldot");
  dot.className = "cdot" + (it.colour ? " c-" + it.colour : " c-none");
  document.getElementById("vcolname").textContent = it.colour ? colourName(it.colour) : "Colour";
  const n = (it.tags || []).length;
  document.getElementById("vtagname").textContent = n ? `Tags (${n})` : "Tags";
  document.getElementById("vchips").innerHTML = (it.tags || []).map(t =>
    `<button type="button" class="vchip" data-t="${esc(t)}" title="Remove">${esc(t)} ${icon("cross")}</button>`).join("");
  document.querySelectorAll("#vchips .vchip").forEach(b =>
    b.onclick = e => { e.stopPropagation(); viewerTag(b.dataset.t, false); });
  if (!document.getElementById("vtagpop").hidden) drawTagList();
  if (!document.getElementById("vcolpop").hidden) drawColours();
  tileRefresh(it);
}

/* ------------------------------------------------- the two overlays

   A photograph on screen answers "is this the one". It does not answer "is it
   exposed right" or "what was I shooting at" - and those are the two questions
   you actually have while looking, which is why every camera puts a histogram
   and a line of numbers on the back of itself.

   Both are drawn OVER the picture and both are switches: press once and they
   stay on for the next photograph and the next session, press again and they
   are gone. Nothing is computed while they are off.

   The histogram is read from the picture on screen - the 1,280px preview the
   viewer already loaded, not the original - which is exact enough to read an
   exposure and costs the NAS nothing. For a RAW that preview is the JPEG the
   camera embedded, so the curve is the camera's rendering rather than the
   sensor data; said in the corner rather than left to be assumed. */

const OVER = {hist: false, shot: false, mode: 0};
const HISTMODES = [["both", "RGB + luminance"], ["lum", "Luminance"],
                   ["rgb", "RGB"]];

function overlaySaved(){
  try{
    const kept = JSON.parse(localStorage.getItem("pm_overlay") || "{}") || {};
    OVER.hist = !!kept.hist; OVER.shot = !!kept.shot;
    OVER.mode = Math.max(0, Math.min(HISTMODES.length - 1, kept.mode | 0));
  }catch(e){}
}

function overlayKeep(){
  try{ localStorage.setItem("pm_overlay", JSON.stringify(OVER)); }catch(e){}
}

function overlayToggle(which){
  OVER[which] = !OVER[which];
  overlayKeep();
  overlayDraw();
}

function histMode(){
  OVER.mode = (OVER.mode + 1) % HISTMODES.length;
  overlayKeep();
  drawHistogram();
}

function overlayDraw(){
  const hist = document.getElementById("vhist");
  const shot = document.getElementById("vshot");
  if (!hist || !shot) return;
  /* A RAW gets both: the viewer is showing the JPEG the camera embedded in it,
     which is a real picture to measure and carries the same EXIF. A video gets
     neither - there is no frame here to count, and a shutter speed for a clip
     would be a different thing wearing the same word. */
  const path = viewerPath();
  const still = SHOWABLE.test(path) && !isClip(path);
  hist.hidden = !(OVER.hist && still);
  shot.hidden = !(OVER.shot && still);
  // on a phone the histogram drops below the shot strip when both are on
  document.getElementById("viewer").classList.toggle("shotoff", shot.hidden);
  const hb = document.getElementById("vhistb");
  const sb = document.getElementById("vshotb");
  if (hb) hb.classList.toggle("on", OVER.hist);
  if (sb) sb.classList.toggle("on", OVER.shot);
  /* DISABLED, not hidden. A clip has no exposure to read and no histogram to
     draw - but a button that vanishes teaches that the app is different on
     different photographs, and a person then wonders where it went. It stays,
     greyed, and says why. */
  for (const b of [hb, sb]){
    if (!b) continue;
    b.disabled = !still;
    b.title = still ? (b.id === "vhistb" ? "Histogram" : "How it was exposed")
                    : S.videoNoExposure;
  }
  drawShot();
  drawHistogram();
  overlayStack();
}

function overlayStack(){
  /* On a phone they share the top of the screen, and the shot strip is two
     lines or three depending on what the file carries - so where the histogram
     starts is measured rather than guessed at in the stylesheet. */
  const hist = document.getElementById("vhist");
  const shot = document.getElementById("vshot");
  if (!hist || !shot) return;
  if (!isPhone() || hist.hidden || shot.hidden){ hist.style.top = ""; return; }
  hist.style.top = (shot.offsetTop + shot.offsetHeight + 8) + "px";
}

addEventListener("resize", () => { if (document.getElementById("viewer")) overlayStack(); });

/* ---- how it was exposed */

function shotLine(s){
  /* The four numbers, in the order a camera says them, and only the ones the
     file actually carries. A line reading "- mm - f/- ISO -" tells you nothing
     except that this app likes dashes. */
  if (!s) return "";
  const bits = [];
  if (s.focal) bits.push(`${(+s.focal).toFixed(0)}mm`
    + (s.focal35 && Math.round(s.focal35) !== Math.round(s.focal)
       ? ` <span class="vdim">(${Math.round(s.focal35)}mm eq)</span>` : ""));
  if (s.shutter) bits.push(esc(s.shutter));
  if (s.fnumber) bits.push(`f/${(+s.fnumber).toFixed(1).replace(/\.0$/, "")}`);
  if (s.iso) bits.push(`ISO ${s.iso}`);
  return bits.join(" <span class=\"vsep\">\u00b7</span> ");
}

function drawShot(){
  const box = document.getElementById("vshot");
  if (!box || box.hidden) return;
  const s = (VIEW.shot || {})[viewerPath()];
  if (!s){ box.innerHTML = `<div class="vdim">reading...</div>`; return; }
  const line = shotLine(s);
  const rest = [s.camera, s.lens, s.taken].filter(Boolean).map(esc).join(
    " <span class=\"vsep\">\u00b7</span> ");
  const before = box.offsetHeight;
  box.innerHTML = (line ? `<div class="vshotline">${line}</div>` : "")
    + (rest ? `<div class="vdim vshotrest">${rest}</div>` : "")
    + (line || rest ? "" : `<div class="vdim">nothing in this file says how it was taken</div>`)
    + (s.ev !== null && s.ev !== undefined && s.ev !== 0
       ? `<div class="vdim vshotrest">exposure compensation ${s.ev > 0 ? "+" : ""}${s.ev} EV</div>`
       : "");
  if (box.offsetHeight !== before) overlayStack();
}

/* ---- the histogram */

let HISTAT = "";

function drawHistogram(){
  const box = document.getElementById("vhist");
  const canvas = document.getElementById("vhistc");
  if (!box || !canvas || box.hidden) return;
  const img = document.getElementById("vimg");
  if (!img || !img.complete || !img.naturalWidth){ HISTAT = ""; return; }
  const path = viewerPath();
  const bins = histogramOf(img, path);
  if (!bins) return;
  paintHistogram(canvas, bins);
  const mode = HISTMODES[OVER.mode];
  document.getElementById("vhistmode").textContent = mode[1];
  const clip = [];
  if (bins.dark > 0.002) clip.push(`${Math.round(bins.dark * 100)}% black`);
  if (bins.light > 0.002) clip.push(`${Math.round(bins.light * 100)}% white`);
  if (bins.raw) clip.push("from the embedded JPEG");
  document.getElementById("vhistclip").textContent = clip.join(" \u00b7 ");
}

const HISTCACHE = {};

function histogramOf(img, path){
  /* Counted once per photograph and kept: paging back and forth through a
     shoot must not recount the same picture every time. */
  if (HISTCACHE[path]) return HISTCACHE[path];
  const wide = 320;
  const tall = Math.max(1, Math.round(wide * img.naturalHeight / img.naturalWidth));
  const off = document.createElement("canvas");
  off.width = wide; off.height = tall;
  const ctx = off.getContext("2d", {willReadFrequently: true});
  let data;
  try{
    ctx.drawImage(img, 0, 0, wide, tall);
    data = ctx.getImageData(0, 0, wide, tall).data;
  }catch(e){ return null; }          // a tainted canvas: no histogram, no crash
  const r = new Uint32Array(256), g = new Uint32Array(256), b = new Uint32Array(256);
  const l = new Uint32Array(256);
  let dark = 0, light = 0, n = 0;
  for (let i = 0; i < data.length; i += 4){
    const R = data[i], G = data[i + 1], B = data[i + 2];
    r[R]++; g[G]++; b[B]++;
    // Rec. 709 luminance - what the eye weighs, not the average of three
    // numbers, which makes every blue sky look darker than it is.
    const Y = (0.2126 * R + 0.7152 * G + 0.0722 * B) | 0;
    l[Y]++;
    if (R <= 1 && G <= 1 && B <= 1) dark++;
    if (R >= 254 && G >= 254 && B >= 254) light++;
    n++;
  }
  const out = {r: r, g: g, b: b, l: l, dark: dark / n, light: light / n,
               raw: /\.(rw2|arw|dng|cr2|cr3|nef|orf|raf)$/i.test(path)};
  HISTCACHE[path] = out;
  const keys = Object.keys(HISTCACHE);
  if (keys.length > 60) delete HISTCACHE[keys[0]];
  return out;
}

function paintHistogram(canvas, bins){
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const mode = HISTMODES[OVER.mode][0];
  /* Scaled to the tallest bin of whatever is being drawn, ignoring the two
     ends: one blown sky or one black frame edge is a spike ten times
     everything else, and scaling to it flattens the picture's whole curve to
     nothing. */
  const peak = list => {
    let top = 1;
    for (let i = 2; i < 254; i++) if (list[i] > top) top = list[i];
    return top;
  };
  const line = (list, colour, fill) => {
    const top = peak(list);
    ctx.beginPath();
    ctx.moveTo(0, H);
    for (let i = 0; i < 256; i++){
      const y = H - Math.min(1, list[i] / top) * (H - 2);
      ctx.lineTo(i * W / 255, y);
    }
    ctx.lineTo(W, H);
    if (fill){ ctx.fillStyle = fill; ctx.fill(); }
    ctx.strokeStyle = colour; ctx.lineWidth = 1; ctx.stroke();
  };
  if (mode === "lum" || mode === "both")
    line(bins.l, "rgba(255,255,255,.75)", "rgba(255,255,255,.22)");
  if (mode === "rgb" || mode === "both"){
    ctx.globalCompositeOperation = "screen";
    line(bins.r, "rgba(255,90,90,.95)", mode === "rgb" ? "rgba(255,60,60,.28)" : "");
    line(bins.g, "rgba(90,235,120,.95)", mode === "rgb" ? "rgba(60,235,90,.28)" : "");
    line(bins.b, "rgba(110,150,255,.95)", mode === "rgb" ? "rgba(80,130,255,.28)" : "");
    ctx.globalCompositeOperation = "source-over";
  }
  // the two ends, so clipping is visible rather than only counted
  if (bins.dark > 0.002){ ctx.fillStyle = "rgba(120,170,255,.9)"; ctx.fillRect(0, 0, 3, H); }
  if (bins.light > 0.002){ ctx.fillStyle = "rgba(255,190,90,.9)"; ctx.fillRect(W - 3, 0, 3, H); }
}

function drawColours(){
  const it = viewItem(viewerPath());
  const pop = document.getElementById("vcolpop");
  const list = (VIEW.colours.length ? VIEW.colours
                : ["red", "yellow", "green", "blue", "purple"].map(c => ({colour: c, name: ""})));
  pop.innerHTML = list.map((c, i) => `
    <button type="button" class="vopt${it.colour === c.colour ? " on" : ""}" data-c="${c.colour}">
      <span class="cdot c-${c.colour}"></span><span class="vgrow">${esc(colourName(c.colour))}</span>
      ${i < 4 ? `<kbd>${i + 6}</kbd>` : ""}</button>`).join("")
    + `<button type="button" class="vopt${it.colour ? "" : " on"}" data-c="">
      <span class="cdot c-none"></span><span class="vgrow">No colour</span></button>`;
  pop.querySelectorAll(".vopt").forEach(b => b.onclick = () => {
    viewerColour(b.dataset.c, true);
    viewerMenu("");
  });
}

function drawTagList(){
  const it = viewItem(viewerPath());
  const box = document.getElementById("vtagin");
  const q = (box.value || "").trim().toLowerCase();
  const have = new Set((it.tags || []).map(t => t.toLowerCase()));
  const words = [];
  for (const w of [].concat(it.tags || [], VIEW.vocab || [])){
    if (!words.some(x => x.toLowerCase() === w.toLowerCase())) words.push(w);
  }
  const shown = words.filter(w => !q || w.toLowerCase().includes(q)).slice(0, 60);
  let h = "";
  if (q && !words.some(w => w.toLowerCase() === q))
    h += `<button type="button" class="vopt vadd" data-w="${esc(box.value.trim())}">
      <span class="vplus">+</span><span class="vgrow">Add “${esc(box.value.trim())}”</span></button>`;
  h += shown.map(w => `<button type="button" class="vopt${have.has(w.toLowerCase()) ? " on" : ""}"
      data-w="${esc(w)}"><span class="vcheck">${have.has(w.toLowerCase()) ? "✓" : ""}</span>
      <span class="vgrow">${esc(w)}</span></button>`).join("");
  if (!h) h = `<div class="vdim" style="padding:10px 12px">Type a word to add it.</div>`;
  const list = document.getElementById("vtaglist");
  list.innerHTML = h;
  list.querySelectorAll(".vopt").forEach(b => b.onclick = () => {
    const w = b.dataset.w;
    const on = have.has(w.toLowerCase());
    viewerTag(w, !on);
    box.value = "";
    drawTagList();
  });
}

/* ---- the things you can do to the one photograph you are looking at

   Stars, a colour and tags were already here, because those are the marks you
   make while looking. Everything else meant closing the viewer, finding the
   folder again in another tab, and running a whole-folder feature over forty
   photographs to fix the one you were looking at - which is how a person
   decides not to bother. So: the actions that make sense for ONE shot happen
   here, and the ones that only make sense for a folder open that folder with
   it already filled in. */

function drawMore(){
  const path = viewerPath();
  const q = quoted(path);
  const about = VABOUT[path];
  document.getElementById("vmorepop").innerHTML =
    `<div class="vhead">${esc(S.viewerThisPhoto)}</div>`
    + (VIEWABLE.test(path) ? `<a class="vopt" target="_blank" rel="noopener"
       href="api/file?path=${encodeURIComponent(path)}"
       ><span class="vgrow">Open full size</span></a>` : "")
    + `<a class="vopt" href="api/download?path=${encodeURIComponent(path)}"
       ><span class="vgrow">Save to this device</span></a>
       <button type="button" class="vopt" onclick="viewerAbout('${q}')"
         ><span class="vgrow">What it is</span></button>
       <button type="button" class="vopt" onclick="viewerRename('${q}')"
         ><span class="vgrow">Rename it</span>
          <span class="vdim">+ RAW</span></button>
       <button type="button" class="vopt" onclick="viewerUnlocate('${q}')"
         ><span class="vgrow">Remove location</span>
          <span class="vdim">${about ? (about.located ? "has one" : "none") : ""}</span></button>
       <button type="button" class="vopt" onclick="copyPath('${q}')" id="copyb">
         <span class="vgrow">Copy folder path</span></button>
       <div class="vhead">The folder it is in</div>
       <button type="button" class="vopt" onclick="viewerInFiles('${q}')"
         ><span class="vgrow">Show it in File explorer</span></button>
       <button type="button" class="vopt" onclick="viewerUseIn(event, '${q}')"
         ><span class="vgrow">Use the folder in...</span></button>`
    + (about ? aboutHtml(about) : "")
    + `<div class="vdim vpath">${esc(path)}</div>
       <div class="vdim vkeys">Keys: ← → · 0-5 stars · 6-9 colour · T tags · Del</div>`;
}

const VABOUT = {};

function aboutHtml(a){
  const line = (label, value) => value
    ? `<div class="vfact"><span>${esc(label)}</span><b>${esc(value)}</b></div>` : "";
  return `<div class="vhead">What it is</div><div class="vfacts">`
    + line("Taken", a.taken || "nothing in the file says")
    + line("Camera", a.camera)
    + (a.model && a.model !== a.camera ? line("It writes", a.model) : "")
    + line("Lens", a.lens)
    + line("Size", fmSize(a.bytes))
    + line("Location", a.located ? `${a.lat}, ${a.lon}` : "none on it")
    + line("Sidecar", a.sidecar ? "one beside it" : "")
    + ((a.copies || []).length
       ? a.copies.map(c => `<div class="vfact"><span>${
           esc(c.kind === "raw" ? S.copyRaw : "Copy")}</span>
           <b title="${esc(c.path)}">${esc(c.name)} - ${fmSize(c.bytes)}</b></div>`).join("")
       : `<div class="vfact"><span>Copies</span><b>none in the other trees</b></div>`)
    + `</div>`;
}

async function viewerAbout(path){
  if (VABOUT[path]){ drawMore(); return; }
  try{
    const got = await (await fetch("api/photo-about?path="
      + encodeURIComponent(path))).json();
    if (got.error){ toast(got.error, 5000); return; }
    VABOUT[path] = got;
  }catch(e){ toast("that could not be read", 4000); return; }
  drawMore();
  /* The popup scrolls, and the facts land at the bottom of it - which looks
     exactly like nothing happening. */
  const facts = document.querySelector("#vmorepop .vfacts");
  if (facts) facts.scrollIntoView({block: "nearest"});
}

async function viewerUnlocate(path){
  const ok = await askSure({
    title: "Remove the location?",
    body: S.unlocateBody,
    yes: "Remove it"});
  if (!ok) return;
  const got = await viewerSend({do: "unlocate", path: path});
  if (!got) return;
  delete VABOUT[path];
  toast(got.taken ? say("unlocated", {n: got.taken})
                  : "There was no location on it", 4000);
  drawMore();
}

async function viewerRename(path){
  /* The app's own dialog, like every other question it asks. The browser's
     prompt() freezes the page, cannot be styled, and on a phone reads as an
     error - and this was the last place still using one. */
  const name = await fmAsk({title: S.renamePhoto,
                            value: basename(path), yes: "Rename"});
  if (!name) return;
  const got = await viewerSend({do: "rename", path: path, name: name});
  if (!got || !got.path) return;
  /* The viewer is holding a path that does not exist any more, so the list it
     is paging through has to be corrected too - otherwise Next walks into a
     file that was just renamed out from under it. */
  const at = VIEW.list.indexOf(path);
  if (at >= 0) VIEW.list[at] = got.path;
  if (VIEW.items[path]){
    VIEW.items[got.path] = Object.assign({}, VIEW.items[path],
      {path: got.path, name: basename(got.path)});
    delete VIEW.items[path];
  }
  delete VABOUT[path];
  toast(got.sidecars ? say("renamedWithSidecars", {n: got.sidecars}) : "Renamed", 3000);
  viewerShow(0);
  if (document.getElementById("fileman")) fmRefresh();
}

function viewerInFiles(path){
  /* Close the viewer and stand in its folder with the photograph picked -
     which is what "show me where this is" means everywhere else. */
  const folder = path.replace(/[\\/][^\\/]*$/, "");
  viewerClose();
  show("files");
  setTimeout(() => { fmGo(0, folder).then(() => fmToggle(0, path, true)); }, 60);
}

function viewerUseIn(ev, path){
  const folder = path.replace(/[\\/][^\\/]*$/, "");
  /* Measured BEFORE the viewer goes. The row this was clicked on lives inside
     the viewer, so once it is removed the node is detached, every edge of it
     reads zero, and the menu landed in the top-left corner behind the header. */
  const on = ev.target && ev.target.closest
    ? (ev.target.closest("button,a,.vopt,[role=button]") || ev.target) : ev.target;
  const at = on && on.getBoundingClientRect ? on.getBoundingClientRect() : null;
  viewerClose();
  const rect = at && at.width + at.height > 0
    ? at : {left: 16, top: 90, bottom: 110, width: 1, height: 1};
  workOn({preventDefault(){}, target: {getBoundingClientRect: () => rect}}, folder);
}

/* ---- writing */

async function viewerSend(body, it, undoTo){
  VIEW.busy++;
  document.getElementById("viewer")?.classList.add("saving");
  try{
    const r = await fetch("api/photo", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const got = await r.json();
    if (!r.ok || got.error) throw new Error(got.error || "it did not save");
    if (it && got.path){
      it.stars = got.stars; it.colour = got.colour; it.tags = got.tags;
      if (viewerPath() === got.path) viewerDraw(); else tileRefresh(it);
      if (got.failed && got.failed.length) toast("Saved, but: " + got.failed[0]);
      else if (got.copies > 1) toast(`Saved to ${got.copies} copies`, 1400);
    }
    return got;
  }catch(e){
    if (it && undoTo){ Object.assign(it, undoTo); if (viewerPath() === it.path) viewerDraw(); }
    toast("Not saved - " + e.message, 5000);
    return null;
  }finally{
    VIEW.busy--;
    if (!VIEW.busy) document.getElementById("viewer")?.classList.remove("saving");
  }
}

function viewerStars(n){
  const path = viewerPath();
  if (!editable(path)) return;
  const it = viewItem(path);
  const was = {stars: it.stars};
  it.stars = (it.stars === n) ? 0 : n;
  viewerDraw();
  const s = document.querySelector(`#vstars .vstar[data-n="${Math.max(1, n)}"]`);
  if (s){ s.classList.remove("pop"); void s.offsetWidth; s.classList.add("pop"); }
  viewerSend({do: "stars", path: path, value: it.stars}, it, was);
}

function viewerColour(c, fromMenu){
  const path = viewerPath();
  if (!editable(path)) return;
  const it = viewItem(path);
  const was = {colour: it.colour};
  it.colour = (!fromMenu && it.colour === c) ? "" : c;
  viewerDraw();
  viewerSend({do: "colour", path: path, value: it.colour}, it, was);
}

function viewerTag(word, on){
  const path = viewerPath();
  if (!editable(path) || !word) return;
  const it = viewItem(path);
  const was = {tags: (it.tags || []).slice()};
  const lower = word.toLowerCase();
  it.tags = (it.tags || []).filter(t => t.toLowerCase() !== lower);
  if (on) it.tags.push(word);
  if (on && !VIEW.vocab.some(v => v.toLowerCase() === lower)) VIEW.vocab.unshift(word);
  viewerDraw();
  viewerSend({do: on ? "tag" : "untag", path: path, value: word}, it, was);
}

async function viewerDelete(){
  const path = viewerPath();
  if (!path) return;
  const at = VIEW.at;
  const img = document.getElementById("vimg");
  img.classList.add("gone");
  const got = await viewerSend({do: "delete", path: path}, null, null);
  img.classList.remove("gone");
  if (!got) return;
  VIEW.list.splice(at, 1);
  tileRemove(path);
  const moves = got.moves || [];
  toast(moves.length > 1 ? say("deletedWithOthers", {n: moves.length - 1}) : S.deletedOne,
        8000, "Undo", async () => {
    const back = await fetch("api/photo", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({do: "undo", moves: moves})});
    const said = await back.json().catch(() => ({}));
    VIEW.list.splice(Math.min(at, VIEW.list.length), 0, path);
    toast(said.restored ? "Put back" : "Could not put it back", 2500);
    if (document.getElementById("viewer")){ VIEW.at = Math.min(at, VIEW.list.length - 1); viewerShow(0); }
  });
  if (!VIEW.list.length){ viewerClose(); return; }
  VIEW.at = Math.min(at, VIEW.list.length - 1);
  viewerShow(1);
}

function toast(text, ms, action, fn){
  /* One line, top centre, with at most one thing to press. It lives on the
     page rather than inside the viewer, because the file manager needs to be
     able to offer Undo when no photo is open. */
  let t = document.getElementById("vtoast");
  if (!t){
    t = document.createElement("div");
    t.id = "vtoast";
    t.className = "vtoast pagetoast";
    t.hidden = true;
    document.body.appendChild(t);
  }
  clearTimeout(VIEW.toastTimer);
  t.innerHTML = `<span>${esc(text)}</span>` +
    (action ? `<button type="button" id="vtoastgo">${esc(action)}</button>` : "");
  t.hidden = false;
  t.classList.remove("show"); void t.offsetWidth; t.classList.add("show");
  if (action) document.getElementById("vtoastgo").onclick = e => {
    e.stopPropagation(); t.hidden = true; fn();
  };
  VIEW.toastTimer = setTimeout(() => { t.hidden = true; }, ms || 2500);
}

/* ---- what is behind the viewer keeps up

   Stars, a colour or a tag set in the viewer has to show in the listing the
   moment you close it. There is one listing now - the file manager - so the
   marks it holds are corrected in place, and a photo put aside is dropped from
   the pane rather than left as a name with nothing behind it. */

function tileRefresh(it){
  FM.panes.forEach(pane => {
    if (pane.marks && pane.marks[it.path])
      pane.marks[it.path] = {stars: it.stars || 0, colour: it.colour || "",
                             tags: it.tags || []};
  });
  if (document.getElementById("fileman")) drawFiles();
}

function tileRemove(path){
  FM.panes.forEach(pane => {
    if (!pane.data) return;
    pane.data.files = (pane.data.files || []).filter(x => x.path !== path);
    pane.sel = pane.sel.filter(x => x !== path);
    if (pane.marks) delete pane.marks[path];
  });
  if (document.getElementById("fileman")) drawFiles();
}

/* ---------------------------------------------------------------- closer in

   "SHOW ME THE FILE ITSELF" MEANT NOTHING WITHOUT THIS.

   3.5.1 added a switch that fetched the original instead of the 2,000px
   preview. It worked, and it changed not one visible pixel - because the
   viewer fits the picture to the screen either way, so the twenty-four
   megapixels and the two were the same number of pixels on the glass. The
   switch was answering a question nobody could see.

   The question is "is this one sharp", and the only way to ask it is to get
   closer than the screen. So: the wheel zooms, two fingers pinch, a double
   press goes to actual size and back, and dragging a zoomed photograph moves
   it rather than turning the page.

   And the file itself is fetched the moment you go past what the preview can
   show, whether or not the switch is on - because at that point a preview
   magnified is a blurred preview, which looks like a photograph that is out of
   focus. That is the one wrong answer this screen must never give. */
const ZOOM = {at: 1, x: 0, y: 0, max: 8};

function zoomed(){ return ZOOM.at > 1.01; }

function zoomDraw(){
  const i = document.getElementById("vimg");
  if (!i) return;
  i.style.transform = zoomed()
    ? `translate(${ZOOM.x}px, ${ZOOM.y}px) scale(${ZOOM.at})` : "";
  i.style.cursor = zoomed() ? "grab" : "";
  const v = document.getElementById("viewer");
  if (v) v.classList.toggle("zoomed", zoomed());
  const said = document.getElementById("vzoom");
  if (said){
    said.hidden = !zoomed();
    said.textContent = Math.round(ZOOM.at * 100) + "%";
  }
}

function zoomHold(){
  /* Kept inside its own edges: a photograph dragged off the screen entirely is
     a photograph you have to guess your way back to. */
  const i = document.getElementById("vimg");
  if (!i) return;
  const r = i.getBoundingClientRect();
  const over = (r.width * 1 - i.clientWidth) / 2;
  const overY = (r.height * 1 - i.clientHeight) / 2;
  ZOOM.x = Math.max(-Math.abs(over), Math.min(Math.abs(over), ZOOM.x));
  ZOOM.y = Math.max(-Math.abs(overY), Math.min(Math.abs(overY), ZOOM.y));
}

function zoomTo(want, atX, atY){
  const i = document.getElementById("vimg");
  if (!i || isClip(viewerPath())) return;
  const was = ZOOM.at;
  ZOOM.at = Math.max(1, Math.min(ZOOM.max, want));
  if (ZOOM.at <= 1.01){ ZOOM.at = 1; ZOOM.x = ZOOM.y = 0; }
  else if (atX !== undefined){
    // Zoom towards the pointer, not towards the middle: zooming to the middle
    // means hunting for the corner you were looking at.
    const box = i.getBoundingClientRect();
    const mx = atX - (box.left + box.width / 2);
    const my = atY - (box.top + box.height / 2);
    const by = ZOOM.at / was;
    ZOOM.x = (ZOOM.x - mx) * by + mx;
    ZOOM.y = (ZOOM.y - my) * by + my;
  }
  zoomHold();
  zoomDraw();
  // Past what a preview holds, the preview is not good enough to answer the
  // question being asked of it.
  if (zoomed()) wantBigger();
}

function zoomReset(){ ZOOM.at = 1; ZOOM.x = ZOOM.y = 0; zoomDraw(); }

function zoomFlip(atX, atY){
  if (zoomed()) zoomReset(); else zoomTo(2.5, atX, atY);
}

/* ---- gestures */

function viewerGestures(stage){
  let sx = 0, sy = 0, st = 0, dx = 0, dy = 0, down = false, lastTap = 0;
  let zx = 0, zy = 0, pinch = 0, pinchAt = 1;
  const touching = new Map();
  const img = () => document.getElementById("vimg");

  const gap = () => {
    const [a, b] = [...touching.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  stage.addEventListener("wheel", e => {
    if (isClip(viewerPath())) return;
    e.preventDefault();
    // A notch is 100 or 120 and a trackpad sends threes - the same lesson the
    // map learned. Scale by a ratio rather than by the number.
    zoomTo(ZOOM.at * Math.pow(1.0022, -e.deltaY), e.clientX, e.clientY);
  }, {passive: false});

  stage.addEventListener("pointerdown", e => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    touching.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (touching.size === 2){ pinch = gap(); pinchAt = ZOOM.at; down = false; return; }
    down = true; sx = e.clientX; sy = e.clientY; st = Date.now(); dx = dy = 0;
    zx = ZOOM.x; zy = ZOOM.y;
    try{ stage.setPointerCapture(e.pointerId); }catch(err){}
    img().style.transition = "none";
  });
  stage.addEventListener("pointermove", e => {
    if (touching.has(e.pointerId)) touching.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (touching.size === 2 && pinch){
      const now = gap();
      if (now > 0) zoomTo(pinchAt * (now / pinch));
      return;
    }
    if (!down) return;
    dx = e.clientX - sx; dy = e.clientY - sy;
    const i = img();
    /* ZOOMED IN, A DRAG MOVES THE PHOTOGRAPH. Turning the page while somebody
       is looking at one corner of a frame is the wrong answer to the same
       gesture. */
    if (zoomed()){
      ZOOM.x = zx + dx; ZOOM.y = zy + dy;
      zoomHold(); zoomDraw();
      return;
    }
    if (Math.abs(dx) > Math.abs(dy)){
      if (VIEW.list.length > 1) i.style.transform = `translateX(${dx}px)`;
    } else if (dy > 0){
      i.style.transform = `translateY(${dy}px) scale(${Math.max(.85, 1 - dy / 1200)})`;
      document.getElementById("viewer").style.setProperty("--vfade",Math.max(.35, 1 - dy / 500));
    }
  });
  const end = (e) => {
    if (e && e.pointerId !== undefined) touching.delete(e.pointerId);
    if (touching.size < 2) pinch = 0;
    if (!down) return;
    down = false;
    const i = img();
    i.style.transition = "";
    if (zoomed()){
      document.getElementById("viewer")?.style.removeProperty("--vfade");
      const quick = Date.now() - st < 300;
      if (quick && Math.abs(dx) < 8 && Math.abs(dy) < 8){
        const now = Date.now();
        if (now - lastTap < 280){ lastTap = 0; zoomFlip(sx, sy); return; }
        lastTap = now;
      }
      zoomDraw();
      return;
    }
    document.getElementById("viewer")?.style.removeProperty("--vfade");
    const quick = Date.now() - st < 300;
    const ax = Math.abs(dx), ay = Math.abs(dy);
    if (ax > 60 && ax > ay && VIEW.list.length > 1){
      i.style.transform = `translateX(${dx > 0 ? 110 : -110}vw)`;
      setTimeout(() => viewerStep(dx > 0 ? -1 : 1), 140);
      return;
    }
    if (dy > 90 && ay > ax){ viewerClose(); return; }
    if (dy < -70 && ay > ax && editable(viewerPath())){
      i.style.transform = ""; VIEW.chrome = true; chromeSet(); viewerMenu("vtagpop"); return;
    }
    i.style.transform = "";
    if (quick && ax < 8 && ay < 8){
      const now = Date.now();
      if (now - lastTap < 280){ lastTap = 0; zoomFlip(sx, sy); return; }
      lastTap = now;
      setTimeout(() => {
        if (lastTap !== now) return;
        const menu = document.querySelector("#viewer .vpop:not([hidden])");
        if (menu){ viewerMenu(""); return; }
        VIEW.chrome = !VIEW.chrome; chromeSet();
      }, 200);
    }
  };
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
}

function chromeSet(){
  document.getElementById("viewer")?.classList.toggle("chrome", VIEW.chrome);
}

addEventListener("keydown", e => {
  if (!document.getElementById("viewer")) return;
  if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  const k = e.key;
  if (clipKey(k)){ e.preventDefault(); return; }
  if (k === "ArrowRight"){ viewerStep(1); }
  else if (k === "ArrowLeft"){ viewerStep(-1); }
  else if (k === "Escape"){
    if (document.querySelector("#viewer .vpop:not([hidden])")) viewerMenu("");
    else viewerClose();
  }
  /* Pressing the same key again takes it off. `viewerStars` has always
     toggled; the handler was guarding it with "only if it is not already that",
     so three stars on a three-star photograph did nothing - which reads as a
     key that has stopped working rather than as one that has nothing to do. */
  else if (/^[0-5]$/.test(k)){ const it = viewItem(viewerPath());
    if (+k === 0){ if (it.stars) viewerStars(it.stars); } else viewerStars(+k); }
  else if (COLOUR_KEYS[k]) viewerColour(COLOUR_KEYS[k], false);
  else if (k === "t" || k === "T") viewerMenu("vtagpop");
  else if (e.shiftKey && QUICKTAGS.length && /^[1-5]$/.test(quickSlot(e))){
    quickTag(+quickSlot(e));
  }
  else if (k === "+" || k === "=") zoomTo(ZOOM.at * 1.4);
  else if (k === "-" || k === "_") zoomTo(ZOOM.at / 1.4);
  else if (k === "f" || k === "F") zoomReset();
  else if (k === "o" || k === "O") fullToggle();
  else if (k === "d" || k === "D"){
    if (typeof infoOpen === "function")
      infoOpen(!document.getElementById("viewer").classList.contains("withinfo"));
  }
  else if (k === "?") shortcutCard();
  else if (KEYS.histogram && k.toLowerCase() === KEYS.histogram) overlayToggle("hist");
  else if (KEYS.info && k.toLowerCase() === KEYS.info) overlayToggle("shot");
  else if (k === "Delete" || k === "Backspace") viewerDelete();
  else return;
  e.preventDefault();
});

/* WHICH NUMBER WAS HELD WITH SHIFT.

   `e.key` on a shifted number is the symbol the layout puts there - ! on a UK
   or US board, " on a Swedish one, & on a French one. `e.code` is the KEY, and
   it is the same key on every layout. */
function quickSlot(e){
  const m = /^Digit([1-9])$/.exec(e.code || "");
  return m ? m[1] : "";
}

function quickTag(n){
  const word = QUICKTAGS[n - 1];
  if (!word || !editable(viewerPath())) return;
  const it = viewItem(viewerPath());
  const has = (it.tags || []).some(t => t.toLowerCase() === word.toLowerCase());
  viewerTag(word, !has);
  toast((has ? "Took off " : "Put on ") + word, 1600);
}

/* The list, over whatever you are looking at. Built from the one table, so a
   key that is added and not written down here cannot happen. */
function shortcutCard(){
  const had = document.getElementById("keyscard");
  if (had){ keysClose(); return; }
  const rows = shortcutRows();
  const groups = [];
  for (const [group, key, said] of rows){
    let box = groups.find(g => g[0] === group);
    if (!box){ box = [group, []]; groups.push(box); }
    box[1].push([key, said]);
  }
  const wrap = document.createElement("div");
  wrap.id = "keyscard";
  wrap.className = "sure";
  /* A dialog like the others: it says so, Escape closes it, and its Close
     sits at the top where a phone that scrolls the card still shows it. */
  wrap.innerHTML = `<div class="surebox keyscard" role="dialog" aria-modal="true"
    aria-labelledby="keyshead"><div class="keystop"><h3 id="keyshead">Keys</h3>
      <button type="button" class="ghost" id="keysclose"
        onclick="keysClose()">Close</button></div>
    ${groups.map(([group, keys]) => `<div class="keygroup"><b>${esc(group)}</b>
      ${keys.map(([key, said]) => `<div class="keyrow"><kbd>${esc(key)}</kbd>
        <span>${esc(said)}</span></div>`).join("")}</div>`).join("")}
    <div class="note">The three you can change, and your quick tags, are in
      Setup under "Keys".</div></div>`;
  wrap.onclick = e => { if (e.target === wrap) keysClose(); };
  wrap.onkeydown = e => {
    if (e.key === "Escape"){ e.stopPropagation(); keysClose(); }
  };
  document.body.appendChild(wrap);
  KEYSHOLD = holdFocus(wrap, document.getElementById("keysclose"));
}

let KEYSHOLD = null;
function keysClose(){
  const card = document.getElementById("keyscard");
  if (card) card.remove();
  if (KEYSHOLD){ const let_go = KEYSHOLD; KEYSHOLD = null; let_go(); }
}

/* Hovering a thumbnail in a table shows it bigger beside the pointer - on a
   mouse only; a finger taps it instead and gets the full view. */
(function(){
  let box = null;
  const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (!fine) return;
  document.addEventListener("mouseover", e => {
    const t = e.target;
    if (!(t instanceof HTMLImageElement) || !t.classList.contains("th")) return;
    if (!box){
      box = document.createElement("img");
      box.id = "hoverpeek"; box.alt = "";
      document.body.appendChild(box);
    }
    box.src = thumbSrc(t.dataset.p || "", "m");
    box.hidden = false;
    const r = t.getBoundingClientRect();
    const left = r.right + 12 + 420 > innerWidth ? Math.max(8, r.left - 432) : r.right + 12;
    box.style.left = left + "px";
    box.style.top = Math.max(8, Math.min(innerHeight - 330, r.top - 140)) + "px";
  });
  document.addEventListener("mouseout", e => {
    if (box && e.target.classList && e.target.classList.contains("th")) box.hidden = true;
  });
})();

async function copyPath(path){
  const cut = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  const folder = cut > 0 ? path.slice(0, cut) : path;
  const b = document.getElementById("copyb");
  try{
    await navigator.clipboard.writeText(folder);
    if (b) b.textContent = "Copied";
  }catch(e){
    // no clipboard (an http page on some browsers): show it to select by hand
    const box = document.getElementById("peekpath");
    if (box) box.textContent = folder;
    if (b) b.textContent = "Select it above";
  }
}

/* ------------------------------------------------------------ picking a folder */

async function browseTo(then, start){
  /* The same picker, handing the folder it chose to a function instead of
     writing it into an option box. The flow editor is not a generated form, so
     it has no option box to write into - and a second folder picker would be a
     second place for the allowed-roots marking and the system-folder fold to
     drift out of step. */
  pickThen = then;
  picking = "";
  pickAdds = false;
  pickFiles = "";
  pickedFile = "";
  pickWhy = "";
  return openPick(start || "");
}

async function browse(option, adding, suffixes){
  pickThen = null;
  picking = option;
  pickAdds = !!adding;
  pickFiles = suffixes || "";
  pickedFile = "";
  const box = document.getElementById("o_" + option);
  /* Which box you are filling in, at the top of the picker. The picker is a
     panel that covers the form it was opened from, so by the time you are three
     folders deep the only thing telling you WHICH of a task's four folder boxes
     you are choosing for is your memory of pressing the button. */
  const o = (CURRENT && CURRENT.options || []).find(x => x.name === option);
  pickWhy = o ? o.label : "";
  const start = pickAdds ? (chosenList(option).slice(-1)[0] || "") : box.value;
  return openPick(start);
}

async function openPick(start){
  document.body.insertAdjacentHTML("beforeend",
    `<div class="veil" id="veil"><div class="pick">
       <h3>Choose a ${pickFiles ? "file" : "folder"}${pickWhy
         ? ` <span class="pickwhy">for ${esc(pickWhy)}</span>` : ""}</h3>
       <div class="at" id="pickat">looking...</div>
       <div class="at warn" id="pickwarn" style="display:none"></div>
       <ul id="picklist"></ul>
       <div class="foot">
         <button class="ghost" onclick="closePick()">Cancel</button>
         <button onclick="usePick()" id="usepick">Use this ${
           pickFiles ? "file" : "folder"}</button>
       </div></div></div>`);
  document.getElementById("veil").onclick = e => {
    if (e.target.id === "veil") closePick();
  };
  await listDir(start);
}

let pickAt = "", pickOk = true, pickAdds = false;
let pickFiles = "", pickedFile = "", pickThen = null, pickWhy = "";

async function listDir(path){
  let d;
  try{
    d = await (await fetch("api/browse?path=" + encodeURIComponent(path || "")
                           + (pickFiles ? "&files=" + encodeURIComponent(pickFiles)
                                        : ""))).json();
  }catch(e){
    /* Saying nothing here is what made a click on a drive look dead. */
    const at = document.getElementById("pickat");
    if (at){ at.textContent = "Could not reach the app to list that folder."; at.className = "at bad"; }
    return;
  }
  pickAt = d.path || "";
  pickOk = d.allowed !== false;
  const at = document.getElementById("pickat");
  at.textContent = d.error ? d.error : (pickAt || "This machine");
  at.className = "at" + (d.error ? " bad" : "");
  /* The whole machine is listed, but a folder no task would accept says so here
     rather than being hidden - "no folders found" for a machine full of them is
     the failure this replaced. */
  const warn = document.getElementById("pickwarn");
  warn.textContent = d.outside || "";
  warn.style.display = d.outside ? "" : "none";
  const go = f => `<li><button class="${f.allowed === false ? "off" : ""}"
      onclick="listDir('${quoted(f.path)}')">
      ${icon("folder")} <span>${esc(f.name)}</span></button></li>`;
  const rows = [];
  if (d.parent != null)
    rows.push(`<li><button onclick="listDir('${quoted(d.parent)}')">
      ${icon("folder")} <span>.. up one level</span></button></li>`);

  /* The container's own operating system sits at the top of the tree - a dozen
     folders that are never anybody's photos, in front of the two that are. They
     are not hidden, because a folder you cannot see is a folder you cannot rule
     out; they are moved out of the way and counted. */
  const yours  = (d.folders || []).filter(f => !f.system);
  const system = (d.folders || []).filter(f => f.system);
  yours.forEach(f => rows.push(go(f)));
  if (!yours.length && !system.length)
    rows.push(`<li><div class="note" style="padding:12px 16px">
      No folders inside this one.</div></li>`);
  if (system.length)
    rows.push(`<li><details class="sysfold"><summary>${system.length} system folder${
      system.length === 1 ? "" : "s"} - this container's own, not your photos</summary>
      <ul>${system.map(go).join("")}</ul></details></li>`);
  /* The files, when a file is what is wanted. Chosen by clicking, and the
     button then says which one - a picker that lists files and still hands back
     the folder is a picker that wastes your time twice. */
  (d.files || []).forEach(f => rows.push(
    `<li><button class="afile ${f.path === pickedFile ? "chosen" : ""}"
       onclick="chooseFile('${quoted(f.path)}')">
       ${icon("inbox")} <span>${esc(f.name)}</span></button></li>`));
  document.getElementById("picklist").innerHTML = rows.join("");
  pickedFile = "";
  const use = document.getElementById("usepick");
  if (use && pickFiles) use.textContent = "Choose a file above";
}

function chooseFile(path){
  pickedFile = path;
  document.querySelectorAll("#picklist .afile").forEach(b =>
    b.classList.toggle("chosen", b.textContent.trim() ===
                       String(path).split(/[\\/]/).pop()));
  const use = document.getElementById("usepick");
  if (use) use.textContent = "Use " + String(path).split(/[\\/]/).pop();
}

function usePick(){
  if (pickThen){
    if (pickAt){ const f = pickThen; pickThen = null; f(pickAt); }
    closePick();
    return;
  }
  if (pickFiles){
    if (!pickedFile) return;                 // nothing chosen yet
    document.getElementById("o_" + picking).value = pickedFile;
    typedIn.add(picking);
    closePick();
    return;
  }
  if (pickAt){
    if (pickAdds){
      addChip(picking, pickAt);
    } else {
      document.getElementById("o_" + picking).value = pickAt;
      if (picking !== "folder") typedIn.add(picking);
      else followTrees();
    }
  }
  closePick();
}
function closePick(){
  const v = document.getElementById("veil");
  if (v) v.remove();
}

async function save(){
  const btn = document.getElementById("save");
  const said = document.getElementById("saidsaved");
  if (btn) btn.disabled = true;
  if (said) said.textContent = "saving...";
  let got = {};
  try{
    const r = await fetch("api/save", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({task: CURRENT.name, options: values()})});
    got = await r.json();
  }catch(e){ got = {error: String(e)}; }
  if (btn) btn.disabled = false;
  if (said)
    said.textContent = got.saved ? "Saved." :
      (got.blocked ? S.notSaved : (got.error ? "Failed." : ""));
  PLAN = got;
  if (SEEN[CURRENT.name]) SEEN[CURRENT.name].plan = got;
  render(got);
  /* Every other tab starts its boxes from these, so they have to be re-read
     rather than left as they were when the page loaded - otherwise Setup says
     one thing and the form beside it opens with the old value. */
  if (got.saved) await refreshTasks();
  lockLocked();
}

async function refreshTasks(){
  try{
    const info = await (await fetch("api/tasks?t=" + Date.now(),
                                    {cache: "no-store"})).json();
    const was = TASKS, wasRoots = ROOTS;
    TASKS = info.tasks || TASKS;
    TREES = info.trees || TREES;
    takeSettings(info);
    /* Every copy the page keeps of a setting follows it - the forms already
       opened, Photos, the shortened paths (library/js/19-settings-followed.js). */
    if (typeof followSettings === "function") followSettings(was, wasRoots);
  }catch(e){}
}

/* The settings that ride along with the task list, read the same way when the
   page opens and whenever the settings change under it. */
function takeSettings(info){
  if (info.keys) KEYS = {info: String(info.keys.info || "").toLowerCase(),
                         histogram: String(info.keys.histogram || "").toLowerCase()};
  QUICKTAGS = (info.keys && info.keys.quick_tags) || [];
  ROOTS = info.tree_roots || [];
  if (typeof SETTINGS_STAMP !== "undefined" && info.settings)
    SETTINGS_STAMP = info.settings;
}

function lockLocked(){
  /* An option that names a switch which must be OFF is greyed out while that
     switch is on. Changing the steps of a loop WHILE it is looping is a
     question nobody wants to think about, and a form that allows it will be
     half-changed when the next pass fires. */
  if (!CURRENT) return;
  for (const o of CURRENT.options){
    if (!o.needs_off) continue;
    const gate = document.getElementById("o_" + o.needs_off);
    const el = document.getElementById("o_" + o.name);
    if (!gate || !el) continue;
    const locked = !!gate.checked;
    el.disabled = locked;
    const row = el.closest(".opt") || el.parentElement;
    if (row){
      row.classList.toggle("locked", locked);
      // a Browse button beside a locked box is still a way to change it
      row.querySelectorAll("button").forEach(b => {
        if (!b.classList.contains("info")) b.disabled = locked;
      });
    }
  }
  for (const o of CURRENT.options){
    if (!o.only_when) continue;
    const [gate, want] = o.only_when.split("=");
    const g = document.getElementById("o_" + gate);
    const row = document.getElementById("w_" + o.name);
    if (g && row) row.hidden = g.value !== want;
  }
  const note = document.getElementById("lockednote");
  if (note){
    const gate = document.getElementById("o_auto_on");
    note.hidden = !(gate && gate.checked);
  }
}

/* --------------------------------------------------------------- plan + apply */

async function run(){
  const btn = document.getElementById("go");
  const was = btn.textContent;
  const task = CURRENT.name;
  btn.disabled = true; btn.textContent = "Looking...";
  const out = document.getElementById("out");
  out.innerHTML = `<div class="card"><b>Looking...</b>
    <div class="bar"><i id="lookfill"></i></div>
    <div class="note" id="looknote">reading</div>
    <div class="mono" id="looknow"></div>
    ${CURRENT.watchable
      ? `<div class="act" style="margin-top:12px">
           <button class="danger" id="lookstop">Stop</button></div>` : ""}</div>`;
  try{
    const r = await fetch("api/plan", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({task: task, options: values()})});
    const started = await r.json();
    if (!started.id){ PLAN = started; render(started); return; }
    pollJobs();

    const stopLook = document.getElementById("lookstop");
    if (stopLook) stopLook.onclick = () => {
      stopLook.disabled = true;
      fetch("api/cancel", {method:"POST", headers:{"Content-Type":"application/json"},
                           body: JSON.stringify({id: started.id})});
    };

    /* Waiting on the job rather than on the request. A scan of the whole
       library is work - it reads the front of every JPEG over SMB - and a page
       that holds one HTTP connection open for two minutes cannot show progress,
       cannot be cancelled, and looks hung. */
    const plan = await waitForPlan(started.id, task);
    if (plan === null) return;                  // the tab moved on; it is stored
    PLAN = plan;
    if (CURRENT && CURRENT.name === task) render(plan);
  }catch(e){
    out.innerHTML = `<div class="card bad">Could not reach the app: ${esc(e)}</div>`;
  }finally{
    btn.disabled = false; btn.textContent = was;
  }
}

/* How many polls in a row may go unanswered before the card says so. Retrying
   in silence was right for a blip on the Wi-Fi and wrong for an app that had
   stopped: the bar simply sat there, which reads as "it does nothing". */
const UNANSWERED = 20;

function notAnswering(where){
  const el = document.getElementById(where);
  if (el) el.textContent = S.notAnswering;
}

async function waitForPlan(id, task){
  let missed = 0;
  for(;;){
    await new Promise(r => setTimeout(r, 350));
    let s;
    try{ s = await (await fetch("api/progress?id=" + encodeURIComponent(id))).json(); }
    catch(e){
      if (++missed >= UNANSWERED && CURRENT && CURRENT.name === task)
        notAnswering("looknote");
      continue;
    }
    missed = 0;
    const here = CURRENT && CURRENT.name === task;
    if (s.phase === "planning"){
      const fill = here && document.getElementById("lookfill");
      if (fill){
        fill.style.width = (s.total ? Math.round(100 * s.done / s.total) : 0) + "%";
        document.getElementById("looknote").textContent =
          s.total ? `${s.done} of ${s.total}` : "reading";
        document.getElementById("looknow").textContent = s.now || "";
      }
      continue;
    }
    if (s.error){
      const box = {error: s.error};
      if (here) render(box); else stash(task, box);
      return null;
    }
    if (!here){ stash(task, s.plan); return null; }
    return s.plan;
  }
}

/* A scan that finishes while you are on another tab is not thrown away. */
function stash(task, plan){
  const box = SEEN[task] || (SEEN[task] = {});
  box.plan = plan;
  box.out = null;
  box.pending = plan;
}

/* ---------------------------------------------------------------- results

   Three complaints about this table, all the same complaint really: it made
   you read where a plain look should have been enough.

   - Every row repeated the same long shared prefix, so the part that
     differed - the only part worth reading - was pushed off to the right.
   - "was 3 stars, now 5" was a sentence per row, so comparing forty of them
     meant reading forty sentences instead of glancing down a column.
   - The rows came in whatever order the disk gave them up, and the one you
     wanted was somewhere in nine hundred.                                  */

let ROWSORT = {col: -1, dir: 1};

/* ---- how many rows of a plan are drawn

   A plan can hold twenty thousand rows now, and a table of twenty thousand
   rows - each with a thumbnail waiting to load - is a page that takes a
   breath before every click. So the table is drawn a few hundred rows at a
   time, in the order asked for, and the rest are a press away. The count in
   the heading is always the whole number: what is drawn is paced, what was
   found is not. The window belongs to the plan on screen and starts again
   when a different one arrives, which is why it is keyed on the object. */
const ROWPAGE = 500;
let ROWSHOWN = {of: null, n: ROWPAGE};

function rowsWindow(p, body){
  if (ROWSHOWN.of !== p) ROWSHOWN = {of: p, n: ROWPAGE};
  return body.slice(0, ROWSHOWN.n);
}

function rowsMore(n){
  const box = document.querySelector("#out .scroll");
  const was = box ? box.scrollTop : 0;
  ROWSHOWN.n = n ? ROWSHOWN.n + n : Infinity;
  if (PLAN) render(PLAN);
  const now = document.querySelector("#out .scroll");
  if (now && was) now.scrollTop = was;
}

function rowsMoreHtml(drawn, whole){
  if (drawn >= whole) return "";
  const left = whole - drawn;
  return `<div class="act rowsmore" style="margin-top:8px">
    <button type="button" class="ghost" onclick="rowsMore(${ROWPAGE})"
      >Show the next ${num(Math.min(ROWPAGE, left))}</button>
    <button type="button" class="ghost" onclick="rowsMore(0)"
      >Show all ${num(whole)}</button>
    <span class="note">${num(drawn)} of ${num(whole)} drawn</span></div>`;
}

function sep(path){ return path.indexOf("\\") >= 0 && path.indexOf("/") < 0 ? "\\" : "/"; }

function commonRoot(paths){
  /* The longest folder every one of these paths sits under.

     Compared SEGMENT by segment, never as text: `Photos` and `Photos Raw`
     share eight characters and share no folder at all, and trimming by
     characters would print `Raw/2022/Spain` as if it were inside the library. */
  const real = paths.filter(Boolean);
  if (real.length < 2) return "";
  const cut = p => p.split(/[\\/]/).filter((x, i) => x !== "" || i === 0);
  let parts = cut(real[0]);
  for (const one of real.slice(1)){
    const bits = cut(one);
    let n = 0;
    while (n < parts.length && n < bits.length &&
           parts[n].toLowerCase() === bits[n].toLowerCase()) n++;
    parts = parts.slice(0, n);
    if (parts.length < 2) return "";
  }
  return parts.join(sep(real[0]));
}

function trimTo(path, root){
  if (!path || !root) return path || "";
  if (path.length === root.length) return ".";
  const rest = path.slice(root.length);
  return rest.replace(/^[\\/]+/, "");
}

function sortValue(text){
  /* Numbers sort as numbers, everything else as text. "1.2 MB" against "900 KB"
     read as text puts the smaller one first, confidently. */
  const t = String(text == null ? "" : text).trim();
  const m = t.match(/^(-?[\d.,]+)\s*(kb|mb|gb|px|star)?/i);
  if (m && m[1].replace(/[.,]/g, "").length){
    let n = parseFloat(m[1].replace(/,/g, ""));
    const unit = (m[2] || "").toLowerCase();
    if (unit === "kb") n *= 1e3;
    if (unit === "mb") n *= 1e6;
    if (unit === "gb") n *= 1e9;
    if (!isNaN(n)) return n;
  }
  return t.toLowerCase();
}

function sortRows(col){
  ROWSORT = (ROWSORT.col === col) ? {col: col, dir: -ROWSORT.dir}
                                  : {col: col, dir: 1};
  if (PLAN) render(PLAN);
}

function rowCells(p, r, root){
  /* One row, as the cells under the headings - the name, whatever the task
     split out, then where it came from and where it goes. */
  const moves = p.rows.some(x => x.target);
  const from = folderOf(r.source), to = folderOf(r.target);
  const middle = (r.cells && r.cells.length) ? r.cells.slice()
                                             : [r.detail || ""];
  const place = moves
    ? [trimTo(from, root), (to === from ? "the same folder" : trimTo(to, root))
        + (r.target && basename(r.target) !== r.name ? "  " + basename(r.target) : "")]
    : [trimTo(r.source, root)];
  return [r.name].concat(middle, place);
}

function picksCard(p){
  /* The names a plan chose, in boxes you can type over.

     A place sort works out a town per photograph and then commits to it in a
     folder name. "Marrakesh" when you would have written "Marrakech" is not
     worth a bug report and is worth fixing once, here, before anything moves -
     so the list is editable and the change goes back into the option the task
     named, which is a plain text box you can also keep in Setup. */
  const k = p.picks;
  let h = `<div class="card"><b>${esc(k.title || "What it chose")}</b>
    <span class="note">(${k.items.length})</span>`;
  if (k.note) h += `<div class="note" style="margin-top:4px">${esc(k.note)}</div>`;
  h += `<div class="scroll" style="margin-top:10px"><table id="pickbody">`
    + k.items.map((it, i) => `<tr>
        <td class="note">${esc(it.name)}</td>
        <td class="note">${it.count == null ? "" : say("pickPhotos", {n: it.count})}</td>
        <td><input id="pk${i}" data-was="${esc(it.name)}" value="${esc(it.name)}"
                   style="width:100%"></td></tr>`).join("")
    + `</table></div>
    <div class="act" style="margin-top:10px">
      <button onclick="usePicks('${quoted(k.option)}')">Use these names</button>
      <span class="note">Looks again with the names above.</span>
    </div></div>`;
  return h;
}

function usePicks(option){
  /* Write the changed names into the task's own option and look again.

     Only the ones that CHANGED: a rename list holding forty lines that say
     "Rome = Rome" is a list nobody will read next month, and it would quietly
     freeze names that should follow the table when it is next imported. */
  const box = document.getElementById("o_" + option);
  if (!box) return;
  const lines = [];
  document.querySelectorAll("#pickbody input").forEach(el => {
    const was = el.getAttribute("data-was") || "";
    const now = (el.value || "").trim();
    if (now && now !== was) lines.push(was + " = " + now);
  });
  const had = (box.value || "").split("\n").filter(x => x.trim() &&
      !lines.some(l => l.split("=")[0].trim().toLowerCase() ===
                       x.split("=")[0].trim().toLowerCase()));
  box.value = had.concat(lines).join("\n");
  box.dispatchEvent(new Event("input"));
  const go = document.getElementById("go");
  if (go) go.click();
}

/* A row's own button: open that feature with that option already filled in.
   The row knows which feature and which option (`Row.act`), so this does not
   need to know anything about History, or about the next task that wants one. */
function rowAct(act){
  if (!act || !act.task) return;
  if (typeof openFeature === "function") openFeature(act.task); else show(act.task);
  setTimeout(() => {
    const box = document.getElementById("o_" + act.option);
    if (box){
      box.value = act.value;
      box.dispatchEvent(new Event("input", {bubbles: true}));
      box.dispatchEvent(new Event("change", {bubbles: true}));
    }
    const go = document.getElementById("go");
    if (go) go.click();
  }, 80);
}

function rowHtml(p, item, head, moves, cls){
  const r = item.r, i = item.i, cells = item.cells;
  const look = SHOWABLE.test(r.source);
  const q = quoted(r.source);
  const name = look
    ? `<img class="th" loading="lazy" alt="" data-p="${esc(r.source)}"
         src="${thumbSrc(r.source, "s")}"
         onclick="return peek('${q}')" onerror="this.remove()"
       ><a href="#" class="fgo" onclick="return peek('${q}')">${esc(r.name)}</a>`
    : esc(r.name);
  /* Every cell carries its column's name. On a wide screen that is invisible;
     on a phone the table becomes one card per row and the name is what makes a
     value readable - seven columns in 390 pixels is four characters each, and
     the heading is a mile above whatever you are looking at. */
  let tds = `<td data-h="${esc(head[0] || "")}"
      ><span class="rowmark" id="m${i}"></span>${name}</td>`;
  for (let n = 1; n < head.length; n++){
    const value = cells[n] == null ? "" : cells[n];
    const last = (n >= head.length - (moves ? 2 : 1));
    const full = last ? (n === head.length - 1 && moves ? folderOf(r.target)
                                                        : folderOf(r.source)) : "";
    const same = value === "the same folder";
    tds += `<td data-h="${esc(head[n] || "")}" class="${last ? "note" : ""}"${
           full ? ` title="${esc(full)}"` : ""}>`
         + (same ? `<span class="same">${esc(value)}</span>` : esc(value))
         + `</td>`;
  }
  if (head[head.length - 1] === "" && head.length > 1){
    const a = r.act || {};
    tds += `<td class="rowact">` + (a.label
      ? `<button type="button" class="fchip" onclick="rowAct(${
          esc(JSON.stringify(a)).replace(/"/g, "&quot;")})">${esc(a.label)}</button>`
      : "") + `</td>`;
  }
  return `<tr id="r${i}" class="${r.approximate ? "approx" : ""} ${cls || ""}"
    ${cls ? "hidden" : ""}>${tds}</tr>`;
}

function groupHead(g, n, count, head){
  /* One heading over the rows it gathers, closed.

     Four hundred duplicate files are not four hundred decisions - they are this
     folder against that one, a dozen times over. The heading is where that is
     visible and where the judgement can be overruled, so what it says has to be
     enough to decide on without opening it: both folders, how big each one is,
     and why this one won. */
  const acts = (g.actions || []).map(a =>
    `<button class="ghost gact" title="${esc(a.help || "")}"
       onclick="groupAction('${quoted(a.option)}', '${quoted(String(a.value))}', event)"
       >${esc(a.label)}</button>`).join(" ");
  let tds = `<td data-h=""><span class="gtwist" id="gt${n}">${icon("forward")}</span>${esc(g.label || "")}
      <span class="gcount">(${count})</span>`
    + (g.note ? `<span class="gnote">${esc(g.note)}</span>` : "") + `</td>`;
  const cells = g.cells || [];
  for (let c = 1; c < head.length; c++){
    const last = (c === head.length - 1);
    tds += `<td data-h="${esc(head[c] || "")}" class="note${last ? " gacts" : ""}"
      >${esc(cells[c - 1] == null ? "" : cells[c - 1])}`
         + (last && acts ? `<div>${acts}</div>` : "") + `</td>`;
  }
  return `<tr class="ghead" onclick="toggleGroup(${n})">${tds}</tr>`;
}

function toggleGroup(n){
  const twist = document.getElementById("gt" + n);
  const rows = document.querySelectorAll("tr.g" + n);
  const opening = rows.length ? rows[0].hasAttribute("hidden") : false;
  rows.forEach(tr => { if (opening) tr.removeAttribute("hidden");
                       else tr.setAttribute("hidden", ""); });
  if (twist) twist.innerHTML = icon(opening ? "expand-one" : "forward");
}

function groupAction(option, value, ev){
  /* A heading's button writes into one of the task's own options and looks
     again. Nothing here decides anything itself: the app made a choice by a
     stated rule, and this is how you tell it a different folder wins - without
     retyping a path, and leaving a setting you can see rather than a hidden
     override the next run would forget. */
  if (ev) ev.stopPropagation();
  const box = document.getElementById("o_" + option);
  if (!box) return;
  const o = (CURRENT && CURRENT.options || []).find(x => x.name === option);
  if (o && (o.kind === "folders" || (o.kind === "folder" && o.many)))
    addChip(option, value);
  else { box.value = value; box.dispatchEvent(new Event("input")); }
  const go = document.getElementById("go");
  if (go) go.click();
}


function rowsCard(p){
  const moves = p.rows.some(r => r.target);
  let head = (p.columns && p.columns.length) ? p.columns.slice()
             : (moves ? ["File", "What happens", "From", "To"]
                      : ["File", "Detail", "Where"]);
  /* A task that named its own columns names the middle ones only - where a
     file came FROM and where it goes are this table's, not the task's, and
     asking every task to remember them is asking for a table whose last two
     headings are wrong on the day somebody forgets. */
  const named = (p.columns && p.columns.length);
  if (named) head = head.concat(moves ? ["From", "To"] : ["Where"]);
  /* A column for the buttons, only when some row actually has one. */
  const acts = p.rows.some(r => r.act && r.act.label);
  if (acts) head = head.concat([""]);

  const root = commonRoot([].concat(
    p.rows.map(r => folderOf(r.source)), p.rows.map(r => folderOf(r.target))));

  const body = p.rows.map((r, i) => ({r: r, i: i, cells: rowCells(p, r, root)}));
  if (ROWSORT.col >= 0){
    const c = ROWSORT.col, dir = ROWSORT.dir;
    body.sort((a, b) => {
      const x = sortValue(a.cells[c]), y = sortValue(b.cells[c]);
      if (x < y) return -dir;
      if (x > y) return dir;
      return a.i - b.i;                 /* stable: equal rows keep plan order */
    });
  }

  const arrow = n => ROWSORT.col === n
    ? icon(ROWSORT.dir > 0 ? "collapse-one" : "expand-one") : "";
  let h = `<div class="card"><b>${p.writes ? "What would happen" : "What it found"}</b>
    <span class="note">(${p.rows.length})</span>`;
  if (root) h += `<div class="note rootline">everything below
    <code>${esc(root)}</code></div>`;
  const groups = Array.isArray(p.groups) ? p.groups : [];
  if (groups.length) h += `<div class="note" style="margin-top:4px">${
    esc(say("planHeadings", {n: groups.length}))}</div>`;
  /* `stack` is what the phone stylesheet turns into one card per row, and it
     is put on here rather than in the CSS because only this knows how many
     columns there are: a two-column table is perfectly readable on a phone and
     turning it into cards would make it longer for no gain. */
  h += `<div class="scroll" style="margin-top:10px"><table${
        head.length > 2 ? ' class="stack"' : ""}><tr>`
    + head.map((c, n) => `<th class="sortable" onclick="sortRows(${n})"
         title="Sort by ${esc(c)}">${esc(c)}${arrow(n)}</th>`).join("")
    + `</tr>`;

  const seen = rowsWindow(p, body);
  if (!groups.length){
    h += seen.map(item => rowHtml(p, item, head, moves, "")).join("");
    return h + `</table></div>${rowsMoreHtml(seen.length, body.length)}</div>`;
  }

  /* Grouped. The headings keep the order the task put them in - it sorted them
     by what matters, usually how much is at stake - and a sort you ask for
     reorders the files INSIDE each heading. Rows belonging to no heading, or to
     one that is not listed, are drawn plainly at the end rather than dropped:
     losing a row from a list of what would happen is the one thing this table
     must never do. */
  const held = {};
  groups.forEach(g => { held[g.key] = []; });
  const loose = [];
  seen.forEach(item => {
    const key = item.r.group || "";
    if (key && held[key]) held[key].push(item); else loose.push(item);
  });
  groups.forEach((g, n) => {
    const mine = held[g.key] || [];
    h += groupHead(g, n, mine.length, head);
    h += mine.map(item => rowHtml(p, item, head, moves, "g" + n)).join("");
  });
  h += loose.map(item => rowHtml(p, item, head, moves, "")).join("");
  return h + `</table></div>${rowsMoreHtml(seen.length, body.length)}</div>`;
}

/* Nothing to do is not the same as nothing to say: the stats under it are what
   it looked at, and they stay. This is the sentence on top of them. */
function nothingDoing(p){
  if (p.blocked || p.error) return false;
  if (p.rows.length || (p.tree || []).length) return false;
  if (p.charts && (p.charts.tiles || p.charts.charts || p.charts.cross)) return false;
  if (p.picks && p.picks.items && p.picks.items.length) return false;
  if (p.editor) return false;                 // a tab that IS an editor
  if (Array.isArray(p.points) && p.points.length) return false;
  return true;
}

function nothingCard(p){
  const im = p.impact || {};
  const where = im.from ? shortText(im.from) : "";
  /* A tab that only reports has not failed to do anything - it has looked. */
  const head = p.writes ? "Nothing to do" : "Nothing found";
  const why = p.writes ? "found nothing it needs to change"
                       : "found nothing to report";
  return `<div class="card"><b class="good">${icon("check")} ${head}</b>
    <div class="note" style="margin-top:6px">${where
      ? `It read ${esc(where)} and ${why}.`
      : `It ${why}.`}
      ${p.writes ? "Nothing was written." : ""}</div></div>`;
}

/* --------------------------------------------------- what is about to happen

   The page asked you to approve four hundred rows and never said the sentence
   that would let you check them: WHAT is being done, to HOW MANY, out of WHERE,
   into WHERE, and whether it can be undone. Every one of those facts already
   existed - the task knows its verb, the plan knows its rows, the boxes hold
   the folders - they were simply never put side by side, so the only way to
   know what the button did was to read the table and infer it.

   And the button said "Go ahead with these 184" on every tab in the app, which
   is the one place the missing word belongs. */

function opWords(p){
  const im = p.impact || {};
  const n = im.count == null ? p.rows.length : im.count;
  if (!im.verb) return `${WORDS.apply} to these ${num(n)}`;
  /* Some things do not come in a quantity. "Set the password" counts one row
     because every plan counts its rows, and "Set the password 1 password" is
     what naming the unit anyway would read as - so a task with no unit gets
     its verb and nothing else. */
  if (!im.unit) return im.verb;
  return `${im.verb} ${num(n)} ${im.unit}`;
}

function changingCard(p){
  const im = p.impact || {};
  const n = im.count == null ? p.rows.length : im.count;
  const high = im.risk === "high";
  /* The operation is one line printed at the size of the decision it is
     (4.0): "Move 412 files", the count in big numerals on the same baseline.
     With nothing to count it stays the first row of the facts. */
  const big = im.unit ? `<p class="ckcount"><span class="sronly">Operation: </span><span
      class="ckv">${esc(im.verb || "Change")}</span> <span class="ckn">${num(n)}</span> <span
      class="cku">${esc(im.unit)}</span></p>` : "";
  let rows = im.unit ? "" : `<div>Operation</div><div><b>${esc(im.verb || "Change")}</b></div>`;
  if (im.from) rows += `<div>Out of</div><div class="mono">${esc(shortText(im.from))}</div>`;
  for (const w of (im.into || []))
    rows += `<div>${esc(w.label)}</div><div class="mono">${esc(shortText(w.path))}</div>`;
  /* Reversibility in the task's own words, or nothing. A generic "you can
     always put them back" printed over something irreversible would be worse
     than the silence it replaced. */
  if (im.undo) rows += `<div>Afterwards</div><div>${esc(im.undo)}</div>`;
  return `<div class="card${high ? " risky" : ""}" id="apply">
    <b class="ckhead">${high ? icon("warn") + " " : ""}Nothing has been written yet.</b>
    ${big}
    ${rows ? `<div class="changing">${rows}</div>` : ""}
    <div class="note" style="margin:10px 0 12px">
      ${esc(S.applyNote)}</div>
    <div class="act"><button id="doit"${high ? ' class="danger"' : ''}
      >${esc(opWords(p))}</button></div></div>`;
}

/* A second place to say yes, for the things that cannot be taken back. Not
   "Are you sure?" - that asks you to confirm a question you have not been told
   the answer to. This names the operation, the number, where it happens, and
   what the task itself says about putting it back. */
async function sureAbout(p){
  const im = p.impact || {};
  if (im.risk !== "high") return true;
  const n = im.count == null ? p.rows.length : im.count;
  const where = [im.from].concat((im.into || []).map(w => w.path))
    .filter(Boolean).map(shortText);
  return askSure({
    title: im.unit ? `${im.verb || "Change"} ${num(n)} ${im.unit}?`
                   : `${im.verb || WORDS.apply}?`,
    body: (where.length ? `In ${where.join(" and ")}. ` : "")
          + (im.undo || "This cannot be undone."),
    yes: opWords(p)});
}

function render(p){
  const out = document.getElementById("out");
  /* Whatever comes back is drawn as a plan, so it has to BE one. A response
     that was refused before it began carries no rows and no stats, and reaching
     for .length on those is how a message about the folder it refused became a
     TypeError about reading 'length'. */
  p = p || {};
  for (const list of ["stats", "notes", "rows", "skipped", "errors", "columns",
                      "groups", "acts"])
    if (!Array.isArray(p[list])) p[list] = [];
  let h = "";
  if (p.error){ out.innerHTML = `<div class="card"><b class="bad">Something went wrong</b>
    <pre>${esc(p.error)}</pre></div>`; return; }
  if (p.blocked)
    h += `<div class="card"><b class="bad">Cannot run</b>
          <div style="margin-top:4px">${esc(p.blocked)}</div></div>`;

  /* The pictures first. Numbers you can see the shape of belong above the list
     of numbers you have to read, not under the table at the bottom of the
     page - that is the difference between a dashboard and an appendix. */
  if (p.charts && (p.charts.tiles || p.charts.charts || p.charts.cross))
    h += chartsCard(p);

  if (p.stats.length || p.notes.length){
    h += `<div class="card"><div class="stats">` +
      p.stats.map(s => `<div>${esc(s[0])}</div><div>${esc(s[1])}</div>`).join("") + `</div>`;
    if (p.notes.length) h += `<div class="note" style="margin-top:12px">` +
      p.notes.map(n => `<div style="margin-bottom:3px">${esc(n)}</div>`).join("") + `</div>`;
    h += `</div>`;
  }

  /* The plan's own buttons: things you do FROM this list rather than to one row
     of it. Same machinery as a row's button - open that feature with that one
     option filled in - so nothing here knows what History is. */
  if (Array.isArray(p.acts) && p.acts.length)
    h += `<div class="card"><div class="act">` + p.acts.map(a =>
      `<button type="button" class="ghost" title="${esc(a.help || "")}"
         onclick="rowAct(${esc(JSON.stringify(a)).replace(/"/g, "&quot;")})"
         >${esc(a.label || "")}</button>`).join("") + `</div></div>`;

  if (p.picks && p.picks.items && p.picks.items.length) h += picksCard(p);
  if (Array.isArray(p.points) && p.points.length) h += mapCard(p.points);
  if (p.tree && p.tree.length) h += treeCard(p);

  /* A few tabs are an editor rather than a list of things that happened. They
     say so in `p.editor`, which is the task's own word for which one it wants -
     the page does not guess from the task name. */
  const EDITORS = {cameras: camerasCard, bands: bandsCard, boards: boardsCard};
  if (EDITORS[p.editor]) h += EDITORS[p.editor](p);
  else if (p.rows.length) h += rowsCard(p);
  if (p.task === "search" && p.rows.length) h += foundCard(p);
  if (p.skipped.length){
    /* "Left alone - no capture time" is a list of names until you can see
       which photographs they are. The ones that ARE photographs get their
       thumbnail and open in the viewer, exactly like the table above. */
    SKIPPEDPICS = p.skipped.map(s => String(s[0])).filter(x => SHOWABLE.test(x));
    /* "Left alone" is right for a task that acts and says what it did not
       touch. On a tab that only reports, it said nothing at all - the Library
       used it for stranded RAW folders - so a task may name its own list. */
    const sktitle = (p.data && p.data.skipped_title) || "Left alone";
    const sknote = (p.data && p.data.skipped_note) || "and why";
    h += `<div class="card"><b>${esc(sktitle)}</b> <span class="note">(${p.skipped.length}) - ${esc(sknote)}</span>
      <div class="scroll" style="margin-top:10px"><table>` +
      p.skipped.map(s => {
        const path = String(s[0]);
        const look = SHOWABLE.test(path);
        const q = quoted(path);
        return `<tr><td>${look
          ? `<img class="th" loading="lazy" alt="" data-p="${esc(path)}"
               src="${thumbSrc(path, "s")}" onclick="return peekSkipped('${q}')"
               onerror="this.remove()"
             ><a href="#" class="fgo" onclick="return peekSkipped('${q}')"
             >${esc(basename(path))}</a>`
          : esc(basename(path) || path)}</td>
        <td class="note">${esc(s[1])}</td></tr>`;
      }).join("") +
      `</table></div></div>`;
  }
  if (p.errors.length){
    h += `<div class="card"><b class="bad">Could not be read</b>
      <div class="scroll" style="margin-top:10px"><pre>` +
      p.errors.map(esc).join("\n") + `</pre></div></div>`;
  }
  if (p.writes && p.rows.length && p.id && !p.blocked) h += changingCard(p);
  /* A plan that found nothing said so only in the arithmetic: a stats grid of
     zeroes, no table, and nothing anywhere on the screen using the word
     nothing. You pressed the button, the page changed almost not at all, and
     the only honest reading of that was that it had broken. Said first,
     because it is the answer - the numbers underneath are the working. */
  if (nothingDoing(p)) h = nothingCard(p) + h;
  out.innerHTML = h;
  setStep(p.blocked || p.error ? 1 : 2);
  if (Array.isArray(p.points) && p.points.length) drawMap(p.points);
  if (CURRENT && SEEN[CURRENT.name]) SEEN[CURRENT.name].done = null;
  if (p.tree && p.tree.length) drawTree(p.tree);
  const go = document.getElementById("doit");
  if (go) go.onclick = apply;
}

/* ------------------------------------------------------- a flow, as a picture */

/* One drawing, used on both tabs, because two pictures of one flow is two
   pictures that will disagree. The blocks come from the server (`diagram()` in
   app/tasks/flows.py) so the Automation tab and the Flows tab cannot differ
   about what a flow is.

   Why a diagram at all: a list of steps with a summary above it reads as a SET,
   and the one property of a flow that is easy to get wrong is its ORDER. Steps
   run in order inside one pass and a step that writes makes the next one run
   straight away, so a step placed before the one that feeds it does its work an
   interval late, for ever, and nothing on a list says so. Arrows do. */

function flowDiagram(flow, opts){
  opts = opts || {};
  const blocks = flow.diagram || [];
  if (!blocks.length)
    return `<div class="note">No steps yet.</div>`;
  const chain = blocks.map((b, i) => flowBlock(b, i === blocks.length - 1))
    .join("");
  return `<div class="chain"${opts.id ? ` id="${esc(opts.id)}"` : ""}>${chain}</div>`;
}

function flowBlock(b, last){
  /* Each block says four things, and each of them is something you would
     otherwise have to open a step to find out: what it is, what it watches,
     whether it runs or only reports, and whether anything is waiting on it. */
  const state = b.missing ? "gone"
              : !b.on ? "off"
              : !b.ready ? "unset"
              : b.waiting ? "waiting"
              : b.do === "run" ? "runs" : "reports";
  const says = {
    gone: "no such tool", off: "switched off", unset: "tree not set up",
    waiting: b.waiting + " waiting", runs: "runs", reports: "just tells you",
  }[state];
  const tip = `${b.title} - watches ${b.watches || "nothing"}`
    + (b.last ? `, last ran ${b.last}` : ", never run")
    + (b.said ? ` (${b.said})` : "");
  return `<div class="blk ${state}" title="${esc(tip)}">
      <span class="blkn">${b.n}</span>
      <span class="blkname">${icon(b.icon)}<span>${esc(b.title)}</span></span>
      <span class="blkwatch">${esc(b.watches || "-")}</span>
      <span class="blkdo">${esc(says)}${b.overrides
        ? ` &middot; ${b.overrides} set here` : ""}</span>
    </div>` + (last ? "" : `<span class="blkarrow" aria-hidden="true">&#8594;</span>`);
}

async function loadSummary(){
  /* The Automation tab shows the SAME picture the Flows tab draws, from the
     same data, because two pictures of one flow is two pictures that will come
     to disagree. */
  if (!FLOWS){
    try{
      const got = await (await fetch("api/flows?t=" + Date.now(),
                                     {cache: "no-store"})).json();
      FLOWS = got.flows || [];
      FLOWCAT = got.catalogue || [];
      FLOWMETA = {fired_by: got.fired_by || [], do: got.do || []};
    }catch(e){ FLOWS = []; }
  }
  drawSummary();
}

function drawSummary(){
  /* Every flow, each with its own switch, not one picked from a list: "what
     runs by itself on this NAS" is one question, and a dropdown made it a
     question you had to ask once per flow. */
  const box = document.getElementById("flowsum");
  if (!box) return;
  if (!(FLOWS || []).length){ box.innerHTML = `<div class="note">No flows yet.
    <a href="#flows">Build one on the Flows tab.</a></div>`; return; }
  box.innerHTML = FLOWS.map(f => {
    const left = (f.exclude || []).length;
    const dsm = f.fired_by === "dsm";
    const folded = flowFolded(f.id);
    return `<div class="sumflow${folded ? " folded" : ""}">
      <div class="sumhead">
        <button type="button" class="ghost fold" onclick="toggleFlowFold('${quoted(f.id)}', drawSummary)"
          aria-label="${folded ? "Show" : "Hide"} this flow">${icon(folded ? "forward" : "expand-one")}</button>
        <b>${esc(f.name)}</b>${flowLight(f)}
        <span class="note">${say("flowSteps", {n: f.steps.length})}, every ${f.every} min${
          left ? ", " + say("foldersLeftOut", {n: left}) : ""}</span>
        <span class="stepacts">
          ${dsm ? `<span class="note">DSM fires it</span>`
            : `<label class="switch" title="Run this flow by itself">
                 <input type="checkbox" ${f.on ? "checked" : ""}
                   onchange="flipFlow('${quoted(f.id)}', this)"><span></span>
                 <em>${f.on ? "On" : "Off"}</em></label>`}
          <button class="ghost" onclick="runOne('${quoted(f.id)}')">${icon("play")} Run now</button>
          <button class="ghost" onclick="show('flows')">Edit</button>
        </span>
      </div>
      ${folded ? "" : flowDiagram(f)}
    </div>`;
  }).join("");
}

function runOne(id){
  const which = document.getElementById("o_which");
  if (which) which.value = id;
  const go = document.getElementById("go");
  if (go) go.click();
}

async function flipFlow(id, box){
  /* Turning a flow on is the one switch in this app that makes things happen
     while nobody is looking - so it asks, and says what it is agreeing to. */
  const f = (FLOWS || []).find(x => x.id === id);
  if (!f){ box.checked = !box.checked; return; }
  const on = box.checked;
  const moving = f.steps.filter(st => st.do === "run")
    .map(st => (byName(st.task) || {}).title || st.task);
  const ok = await askSure(on
    ? {title: `Turn on "${f.name}"?`,
       body: `It will look for changes every ${f.every} min and run by itself.`
         + (moving.length ? ` Steps set to run, not just report: ${moving.join(", ")}.` : ""),
       yes: "Turn it on"}
    : {title: `Turn off "${f.name}"?`,
       body: "Nothing in it will run by itself until you turn it back on. A pass "
           + "already running finishes first.",
       yes: "Turn it off"});
  if (!ok){ box.checked = !on; return; }
  f.on = on;
  await saveFlows();
  drawSummary();
}

function askSure(o){
  /* A small dialog of our own, not the browser's confirm(): that one freezes
     the page, cannot be styled, and on a phone looks like an error. */
  return new Promise(done => {
    const wrap = document.createElement("div");
    wrap.className = "sure";
    wrap.innerHTML = `<div class="surebox" role="alertdialog" aria-modal="true">
        <h3>${esc(o.title)}</h3><p>${esc(o.body || "")}</p>
        <div class="act"><button type="button" class="ghost" data-a="0">Cancel</button>
        <button type="button" data-a="1">${esc(o.yes || "Yes")}</button></div></div>`;
    let unhold = null;
    const end = v => {
      wrap.remove(); removeEventListener("keydown", key);
      if (unhold) unhold();
      done(v);
    };
    const key = e => { if (e.key === "Escape") end(false); };
    wrap.onclick = e => {
      if (e.target === wrap) end(false);
      const b = e.target.closest("button[data-a]");
      if (b) end(b.dataset.a === "1");
    };
    addEventListener("keydown", key);
    document.body.appendChild(wrap);
    unhold = holdFocus(wrap, wrap.querySelector('button[data-a="1"]'));
  });
}

/* A whole flow folded down to its name - remembered in this browser. With
   three or four flows open the one you are editing was a long scroll away. */
function flowFolded(id){
  try{ return (JSON.parse(localStorage.getItem("pm_flowfold") || "{}") || {})[id]; }
  catch(e){ return false; }
}
function setFlowFold(id, on){
  let all = {};
  try{ all = JSON.parse(localStorage.getItem("pm_flowfold") || "{}") || {}; }catch(e){}
  if (on) all[id] = 1; else delete all[id];
  try{ localStorage.setItem("pm_flowfold", JSON.stringify(all)); }catch(e){}
}
function toggleFlowFold(id, redraw){
  setFlowFold(id, !flowFolded(id));
  (redraw || drawFlows)();
}
function foldAllFlows(on){
  (FLOWS || []).forEach(f => setFlowFold(f.id, on));
  drawFlows();
}

function flowLight(flow){
  /* Running or not, at a glance - and "not" has three different reasons that
     are worth telling apart: switched off, left to DSM, or on but with nothing
     to run. A light that says "off" for all three is a light you have to go and
     investigate anyway. */
  const dsm = flow.fired_by === "dsm";
  const live = (RUNNING_NOW || []).some(j => j.by === "automation");
  const state = live && flow.on ? "busy" : dsm ? "dsm" : flow.on ? "on" : "off";
  const word = {busy: S.flowBusy, dsm: S.flowDsm, on: S.flowOn, off: S.flowOff}[state];
  const tip = {
    busy: "A pass is running now.",
    dsm: S.flowDsmTip,
    on: "Runs by itself every " + flow.every + " minutes.",
    off: "Nothing happens unless you press Run.",
  }[state];
  return `<span class="flight ${state}" title="${esc(tip)}"
    ><span class="fdot"></span>${word}</span>`;
}

/* ------------------------------------------------- installed on a phone

   Three things turn this page into something that behaves like an app: a
   worker that keeps the shell and the thumbnails, and a notification when a
   run you started finishes while you are somewhere else.

   Both need a SECURE page - https, or localhost. On a plain http address the
   browser refuses them, so each is asked for only when it can work and the
   app says why in Setup rather than failing quietly. */

function appish(){
  return matchMedia("(display-mode: standalone)").matches
    || navigator.standalone === true;
}

function keepShell(){
  if (!("serviceWorker" in navigator) || !isSecureContext) return;
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

/* ---- telling you a run finished, when you are not looking at it */

function noticeWanted(){
  try{ return localStorage.getItem("pm_notice") === "yes"; }catch(e){ return false; }
}

async function askNotice(on){
  if (!on){
    try{ localStorage.setItem("pm_notice", "no"); }catch(e){}
    drawNotice();
    return;
  }
  if (!("Notification" in window) || !isSecureContext){
    toast(S.needsHttps, 6000);
    drawNotice();
    return;
  }
  let how = Notification.permission;
  if (how === "default") how = await Notification.requestPermission();
  try{ localStorage.setItem("pm_notice", how === "granted" ? "yes" : "no"); }catch(e){}
  if (how !== "granted") toast("The browser said no to notifications", 4000);
  drawNotice();
}

function drawNotice(){
  const box = document.getElementById("noticeon");
  if (box) box.checked = noticeWanted() && ("Notification" in window)
    && Notification.permission === "granted";
}

function tellMe(f){
  /* One line, from the page you are not looking at. Nothing is sent anywhere:
     this is the browser's own notification, raised by the page itself. */
  if (!noticeWanted() || !("Notification" in window)) return;
  if (Notification.permission !== "granted" || !document.hidden) return;
  try{
    const n = new Notification(f.failed ? `${f.title}: ${f.failed} failed`
                                        : `${f.title} - ${f.planned ? "ready to look at" : "done"}`,
      {body: "Photo Manager", tag: "pm-" + f.task, icon: "icon-192.png"});
    n.onclick = () => { window.focus(); show(f.go); n.close(); };
  }catch(e){}
}

/* ------------------------------------------------------------ the file manager

   Two panes at a desk, one on a phone. Picking files is the whole gesture, so
   everything else follows from a selection: copy, move, rename, delete,
   download - and a photograph opens in the same viewer the Photos tab uses.

   Nothing here plans first. You have already said which files by picking them,
   and the safety is in the operations instead: a taken name becomes `_1` rather
   than overwriting, delete means the Recycle Bin and offers Undo, and a move
   carries the RAW and the preview with it so the trees stay mirrored. */

const FM = {
  panes: [{path: "", data: null, sel: [], view: "list", sort: "name", busy: false,
           find: "", anchor: ""},
          {path: "", data: null, sel: [], view: "list", sort: "name", busy: false,
           find: "", anchor: ""}],
  at: 0, two: false, hidden: false, deep: false, clip: null, job: null,
  poll: 0, tick: 0,
  /* ---- 3.5: browse, then select, then act

     Every action this screen can perform used to sit in one row under the
     listing, lit up whether or not it had anything to work on, and a press on
     a file meant "tick it" - so opening a folder was a double press, which on
     a phone is a press that does nothing. Twenty-two buttons, three of them
     destructive, before you had chosen a single file.

     The order is now the one a person actually works in. BROWSE: one press
     opens, which is what one press does in every file manager there is.
     SELECT: a mode you turn on, or a modifier-press, or a long press on a
     phone. ACT: a bar that is not there until something is picked, and then
     says how many and what will happen to them. */
  picking: false,      // the Select mode: a press ticks rather than opens
  info: false,         // the panel on the right, about what is picked
  open: false,         // the folder's own figures, unfolded
  sheet: null,         // "where do these go" - a place, not a second pane
  about: {},           // what has been read about a file, kept per path
};

function fmSaved(){
  try{ return JSON.parse(localStorage.getItem("pm_files") || "{}") || {}; }
  catch(e){ return {}; }
}
function fmKeep(){
  try{
    localStorage.setItem("pm_files", JSON.stringify({
      two: FM.two, hidden: FM.hidden, deep: FM.deep, sort: FM.panes[0].sort,
      view: FM.panes[0].view, right: FM.panes[1].path, info: FM.info}));
  }catch(e){}
}

async function startFiles(){
  const was = fmSaved();
  FM.two = !!was.two && !isPhone();
  FM.hidden = !!was.hidden;
  FM.deep = !!was.deep;
  FM.info = !!was.info && !isPhone();
  FM.picking = false;
  FM.panes.forEach(p => { p.sel = []; p.find = ""; p.anchor = ""; });
  FM.panes[0].view = was.view || "list";
  FM.panes[1].view = was.view || "list";
  FM.panes[0].sort = was.sort || "name";
  FM.panes[1].sort = was.sort || "name";
  const box = document.getElementById("o_folder");
  FM.panes[0].path = (box && box.value.trim()) || "";
  FM.panes[1].path = was.right || "";
  drawFiles();
  await fmGo(0, FM.panes[0].path);
  if (FM.two) await fmGo(1, FM.panes[1].path || FM.panes[0].path);
}

/* THE LAST FOLDER YOU ASKED FOR IS THE ONE THAT WINS, NOT THE LAST TO ANSWER.

   Two reads of two different folders can be in the air at once - opening the
   explorer at a folder starts one while the tab's own first read is still
   running, and on a sleeping NAS the first can land second. The pane then shows
   a folder nobody asked for, with the address bar saying something else.

   Each read carries a number. An answer whose number is no longer the pane's
   newest is thrown away: it is not wrong, it is just late. */
let FMASK = 0;

async function fmGo(n, path){
  const pane = FM.panes[n];
  const mine = pane.asked = ++FMASK;
  pane.busy = true;
  drawFiles();
  try{
    const url = "api/files?t=" + Date.now() + "&hidden=" + (FM.hidden ? 1 : 0)
      + "&deep=" + (FM.deep ? 1 : 0)
      + (path ? "&path=" + encodeURIComponent(path) : "");
    const got = await (await fetch(url, {cache: "no-store"})).json();
    if (pane.asked !== mine) return;          // something newer is on its way
    if (got.error){ pane.error = got.error; }
    else {
      /* Reading the SAME folder again keeps what you had picked - pressing
         Refresh, or coming back to this tab, used to throw the selection away
         and there is nothing to be gained by that. A different folder starts
         clean, because a path picked in one folder means nothing in another. */
      pane.found = null;
      const same = got.path === pane.path;
      const there = {};
      (got.folders || []).concat(got.files || []).forEach(x => { there[x.path] = 1; });
      pane.error = ""; pane.data = got; pane.path = got.path;
      pane.sel = same ? pane.sel.filter(x => there[x]) : [];
      if (!same) pane.shown = 0;
      pane.status = null; pane.marks = null; pane.read = Date.now();
    }
  }catch(e){
    if (pane.asked !== mine) return;
    pane.error = "could not read that folder";
  }
  if (pane.asked !== mine) return;
  pane.busy = false;
  if (n === 0){
    const box = document.getElementById("o_folder");
    if (box && pane.path){ box.value = pane.path; box.dispatchEvent(new Event("input")); }
  }
  fmKeep();
  drawFiles();
  if (!pane.error){ fmStatus(n); fmMarks(n); fmTick(); }
}

/* ---- keeping up with the folder

   The pane used to be a photograph of the folder taken when you opened it. A
   copy finishing elsewhere, a phone dropping a file in, your own job moving
   things - none of it reached the screen, and Refresh looked broken because the
   names were right and the pictures were the browser's old ones.

   Two halves to the fix. The address of a thumbnail now carries the time on the
   file, so a changed file is a different picture as far as the cache is
   concerned. And the folder is read again quietly every few seconds while you
   are looking at it: same signature, nothing happens; different, the listing is
   replaced and what you had picked is kept where it still exists. */

function fmSign(d){
  if (!d) return "";
  return (d.folders || []).concat(d.files || []).map(
    x => x.name + ":" + (x.size || 0) + ":" + Math.round(x.when || 0)).join("|");
}

async function fmPeek(n){
  const pane = FM.panes[n];
  if (!pane.path || pane.busy || !pane.data) return;
  const path = pane.path;
  let got;
  try{
    got = await (await fetch("api/files?t=" + Date.now() + "&hidden="
      + (FM.hidden ? 1 : 0) + "&deep=" + (FM.deep ? 1 : 0)
      + "&path=" + encodeURIComponent(path), {cache: "no-store"})).json();
  }catch(e){ return; }
  if (got.error || got.path !== pane.path || pane.busy) return;
  pane.read = Date.now();
  if (fmSign(got) === fmSign(pane.data)) return;
  const there = {};
  (got.folders || []).concat(got.files || []).forEach(x => { there[x.path] = 1; });
  pane.data = got;
  pane.sel = pane.sel.filter(x => there[x]);
  pane.marks = null;
  freshPics();
  drawFiles();
  fmStatus(n);
  fmMarks(n);
}

function fmWatching(){
  return CURRENT && CURRENT.editor === "files" && !document.hidden
    && document.getElementById("fileman");
}

function fmTick(){
  if (FM.tick) return;
  FM.tick = setInterval(() => {
    if (!fmWatching()) return;
    (FM.two ? [0, 1] : [FM.at]).forEach(fmPeek);
  }, 5000);
}

document.addEventListener("visibilitychange", () => {
  if (fmWatching()) (FM.two ? [0, 1] : [FM.at]).forEach(fmPeek);
});
addEventListener("focus", () => {
  if (fmWatching()) (FM.two ? [0, 1] : [FM.at]).forEach(fmPeek);
});

/* ---- stars, colour and tags, in the listing itself

   There used to be a Photos tab that did nothing else: a grid of thumbnails
   with the marks under them. Everything it had is here now, so it is one place
   instead of two. Read after the names, like the dashboard is. */

async function fmMarks(n){
  const pane = FM.panes[n];
  const path = pane.path;
  if (!path) return;
  if (!(pane.data && (pane.data.files || []).some(fmShowable))) return;
  try{
    const got = await (await fetch("api/photo-marks?path="
      + encodeURIComponent(path) + "&deep=" + (FM.deep ? 1 : 0))).json();
    if (FM.panes[n].path !== path) return;
    pane.marks = got.error ? {} : (got.marks || {});
  }catch(e){ pane.marks = {}; }
  drawFiles();
}

/* ---- what a folder weighs

   A listing cannot say a folder's size without walking it, and walking every
   folder before showing any names would make the manager feel broken for the
   sake of a number you usually do not want. So each folder's size is a small
   button, and what it reads is kept for the rest of the session. */

const FMWEIGH = {};

function fmWeighHtml(n, x){
  const got = FMWEIGH[x.path];
  if (got === "reading") return `<span class="fmweigh">reading...</span>`;
  if (got && got.bytes !== undefined)
    return `<span class="fmweigh done" title="${esc(fmWeighWhy(got))}"
      >${fmSize(got.bytes) || "empty"}</span>`;
  const q = quoted(x.path);
  return `<button class="fmweigh ask" title="Read how much is in this folder"
    onclick="event.stopPropagation(); fmWeigh(${n}, '${q}')">size?</button>`;
}

function fmWeighWhy(got){
  const inside = got.bytes - got.here;
  return say("weighed", {files: got.files, folders: got.folders + 1})
    + (inside > 0 ? ", " + say("weighedSplit", {here: fmSize(got.here),
                                                below: fmSize(inside)}) : "");
}

async function fmWeigh(n, path){
  if (FMWEIGH[path] === "reading") return;
  FMWEIGH[path] = "reading";
  drawFiles();
  try{
    const got = await (await fetch("api/folder-size?path="
      + encodeURIComponent(path))).json();
    FMWEIGH[path] = got.error ? null : got;
    if (got.error) toast(got.error, 5000);
  }catch(e){ FMWEIGH[path] = null; toast("that folder could not be read", 4000); }
  drawFiles();
}

async function fmWeighAll(n){
  /* Every folder in the pane, one after another rather than all at once: a NAS
     asked for thirty walks in parallel answers all of them slowly. */
  const pane = FM.panes[n];
  const here = pane.path;
  for (const f of (pane.data ? pane.data.folders : [])){
    if (FM.panes[n].path !== here) return;
    if (!FMWEIGH[f.path]) await fmWeigh(n, f.path);
  }
}

function fmMark(n, x){
  const m = FM.panes[n].marks;
  return (m && m[x.path]) || null;
}

function fmMarkHtml(m){
  if (!m) return "";
  let h = "";
  if (m.colour) h += `<span class="cdot c-${esc(m.colour)}" title="${esc(m.colour)}"></span>`;
  if (m.stars) h += `<span class="fmstars">${"\u2605".repeat(Math.min(5, m.stars))}</span>`;
  if (m.tags && m.tags.length)
    h += `<span class="fmtags">${esc(m.tags.slice(0, 3).join(", "))}</span>`;
  return h;
}

/* ---- what order

   The server hands them back by name, folders first. Sorting is the page's job
   because Stars is something only the page knows, and because a folder stays at
   the top whatever you sort by. */

function fmOrder(n, rows){
  const pane = FM.panes[n];
  const how = pane.sort || "name";
  const key = {
    name: x => [0, (x.name || "").toLowerCase()],
    when: x => [-(x.when || 0), (x.name || "").toLowerCase()],
    size: x => [-(x.size || 0), (x.name || "").toLowerCase()],
    stars: x => [-(((fmMark(n, x) || {}).stars) || 0), (x.name || "").toLowerCase()],
  }[how] || (x => [0, (x.name || "").toLowerCase()]);
  const out = rows.slice();
  out.sort((a, b) => {
    if ((a.kind === "folder") !== (b.kind === "folder")) return a.kind === "folder" ? -1 : 1;
    const ka = key(a), kb = key(b);
    for (let i = 0; i < ka.length; i++){
      if (ka[i] < kb[i]) return -1;
      if (ka[i] > kb[i]) return 1;
    }
    return 0;
  });
  return out;
}

function fmPane(){ return FM.panes[FM.at]; }
function fmOther(){ return FM.panes[FM.at ? 0 : 1]; }

function fmSelected(n){
  const pane = FM.panes[n === undefined ? FM.at : n];
  return pane.sel.slice();
}

function fmToggle(n, path, on){
  const pane = FM.panes[n];
  const at = pane.sel.indexOf(path);
  const want = on === undefined ? at < 0 : on;
  if (want && at < 0) pane.sel.push(path);
  if (!want && at >= 0) pane.sel.splice(at, 1);
  pane.anchor = path;
  FM.at = n;
  /* Picking one thing IS turning picking on - otherwise a tick pressed on a
     row leaves the screen in a state where the next press opens something. */
  if (pane.sel.length) FM.picking = true;
  drawFiles();
  fmAbout();
}

function fmPick(n, how, text){
  const pane = FM.panes[n];
  const all = (pane.data ? pane.data.files : []).concat(pane.data ? pane.data.folders : []);
  const is = {
    all: () => true,
    none: () => false,
    jpeg: x => x.kind === "jpeg",
    raw: x => x.kind === "raw",
    video: x => x.kind === "video",
    folders: x => x.kind === "folder",
    name: x => text && x.name.toLowerCase().includes(text.toLowerCase()),
  }[how] || (() => false);
  pane.sel = all.filter(is).map(x => x.path);
  FM.at = n;
  drawFiles();
}

function fmSize(n){
  if (!n) return "";
  if (n >= 1e9) return (n / 1e9).toFixed(2) + " GB";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + " MB";
  if (n >= 1e3) return Math.round(n / 1e3) + " KB";
  return n + " B";
}

function fmWhen(t){ return dayTime(t); }

function fmIcon(x){
  if (x.kind === "folder") return icon("folder");
  if (x.kind === "video") return icon("film");
  if (x.kind === "raw") return icon("layers");
  if (x.kind === "jpeg" || x.kind === "image") return icon("image");
  return icon("copy");
}

/* Has a picture that can be drawn of it - a thumbnail in the listing. */
function fmShowable(x){ return x.kind === "jpeg" || x.kind === "image" || x.kind === "raw"; }

/* OPENS IN THE VIEWER, which is not the same question. The viewer has played
   clips since 3.4 - it was only this listing that still treated a video as a
   row with nothing behind it, so pressing one in the explorer did nothing at
   all while pressing the same file on the Photos screen played it. */
function fmViewable(x){ return fmShowable(x) || x.kind === "video"; }

function fmOpen(n, x){
  if (x.kind === "folder"){ fmGo(n, x.path); return; }
  const pane = FM.panes[n];
  /* The viewer pages in the order you are looking at, not the order the server
     happened to answer in - otherwise Next goes somewhere the screen does not. */
  const shots = fmOrder(n, (pane.data.files || []).filter(fmViewable)).map(f => f.path);
  if (shots.includes(x.path)){ peek(x.path, shots); return; }
  toast("There is nothing to show of that file - Save to this device opens it "
        + "in something that can", 4500);
}

/* ---- drawing */

/* EVERY redraw rebuilds the listing, and a rebuilt listing starts at the top.

   Picking the fortieth file in a folder therefore scrolled you back to the
   first one, every single time - which makes picking forty files impossible
   rather than merely annoying. The scroll position belongs to the folder you
   are looking at, not to the HTML that happens to be drawing it. */
function fmScrollNow(){
  const out = [];
  document.querySelectorAll("#fileman .fmlist,#fileman .fmgrid").forEach(
    el => out.push(el.scrollTop));
  return out;
}

function fmScrollBack(was){
  if (!was || !was.length) return;
  document.querySelectorAll("#fileman .fmlist,#fileman .fmgrid").forEach(
    (el, i) => { if (was[i]) el.scrollTop = was[i]; });
}

function drawFiles(){
  const box = document.getElementById("fileman");
  if (!box) return;
  const was = fmScrollNow();
  const panes = FM.two ? [0, 1] : [FM.at];
  box.innerHTML = `<div class="fmbody${FM.info ? " sided" : ""}">
      <div class="fmwrap${FM.two ? " two" : ""}">`
    + panes.map(fmPaneHtml).join("") + `</div>`
    + (FM.info ? fmInfoHtml() : "") + `</div>`
    + fmActHtml() + fmJobHtml();
  fmScrollBack(was);
  box.querySelectorAll("[data-pane]").forEach(el =>
    el.addEventListener("scroll", fmNearEnd, {passive: true}));
  fmSheetDraw();
}

function fmHere(n){
  if (FM.at === n) return;
  FM.at = n;
  drawFiles();
}

/* The one bar at the top of a pane: where you are, what you are looking for,
   and the two menus that hold everything that is not an action on a file.
   Nothing here is destructive and nothing here is disabled waiting for a
   selection - that is the bar at the bottom, and it only exists when there is
   something to act on. */
function fmTopHtml(n){
  const pane = FM.panes[n];
  const d = pane.data;
  const up = (d && d.parent) || "";
  const crumbs = (d && d.crumbs) || [];
  const stop = "event.stopPropagation(); ";
  return `<div class="fmtop">
    <button class="ghost" ${up ? "" : "disabled"} title="Up one folder"
      onclick="${stop}fmGo(${n}, '${quoted(up)}')">${icon("back")}</button>
    <div class="fmwhere">` + (pane.found
      ? `<span class="fmchip">${icon("find")} ${pane.found.length} found</span>
         <button class="quiet" onclick="${stop}fmLeaveFound(${n})"
           title="Leave the results and open a folder again">Leave the results</button>`
      : crumbs.slice(-4).map((c, i, a) =>
          `<button class="crumb${i === a.length - 1 ? " on" : ""}"
             onclick="${stop}fmGo(${n}, '${quoted(c.path)}')"
             >${esc(shortText(c.name))}</button>`).join(`<span class="sep">/</span>`))
   + `</div>
    <input class="fmsearch" type="search" placeholder="Search"
      aria-label="Search this folder by name" value="${esc(pane.find || "")}"
      onclick="${stop}" oninput="fmFind(${n}, this.value)">
    <button class="ghost" title="How to show what is in here"
      onclick="${stop}fmViewMenu(${n}, event)">${icon("grid")} View</button>
    <button class="ghost" title="Everything else this folder can do"
      onclick="${stop}fmMoreMenu(${n}, event)">${icon("menu")} More</button>
    <button class="fchip${FM.picking ? " on" : ""}"
      title="${FM.picking ? "Back to opening things with one press"
                          : "Pick several, then choose what happens to them"}"
      onclick="${stop}fmPicking(!FM.picking)">${icon("select")} Select</button>
  </div>`;
}

function fmPaneHtml(n){
  const pane = FM.panes[n];
  const d = pane.data;
  const live = n === FM.at || !FM.two;
  let h = `<div class="fmpane${live ? " on" : ""}${FM.picking ? " picking" : ""}"
    onclick="fmHere(${n})">` + fmTopHtml(n);
  /* A results pane is not a folder, so the folder dashboard has nothing to
     say about it - and left there it reads "reading what is in here..." for
     ever. What it says instead is where the matches came from. */
  h += pane.found ? fmFoundHtml(pane) : fmHealthHtml(n);
  if (pane.error) h += `<div class="fmempty bad">${esc(pane.error)}</div>`;
  else if (!d) h += `<div class="fmempty">Reading...</div>`;
  else {
    const rows = fmRows(n);
    const shown = fmShown(n, rows);
    if (!rows.length) h += fmNothingHtml(n);
    else if (pane.view === "grid") h += fmGrid(n, shown);
    else h += fmList(n, shown);
    h += fmMoreHtml(n, shown.length, rows.length);
    h += `<div class="fmfoot"><span class="note">${[
        say("nFolders", {n: d.folders.length}),
        say(d.deep ? "nPhotosBelow" : "nFiles", {n: d.files.length}),
        fmSize(d.size)].filter(Boolean).join(", ")}${
        d.capped ? " - the first of them only" : ""}${
        pane.find ? ` - ${rows.length} match "${esc(pane.find)}"` : ""}${
        shown.length < rows.length ? ` - ${num(shown.length)} drawn so far` : ""}</span>
      <span class="note">read ${pane.read ? clock(pane.read / 1000) : "..."}</span></div>`;
  }
  return h + `</div>`;
}

/* ---- how many of them are drawn

   A listing is drawn whole on every pick, which is right for a folder of two
   hundred and a page that stops answering for a search of six thousand. So a
   pane draws a few hundred rows, the next few hundred arrive when you reach
   the bottom or press for them, and everything that is not drawing - the
   counts, Select everything, the viewer's order - still works on the whole
   list. The window is the pane's and starts again in a different folder. */
const FM_PAGE = 400;

function fmShown(n, rows){
  const pane = FM.panes[n];
  if (!pane.shown) pane.shown = FM_PAGE;
  return rows.slice(0, pane.shown);
}

function fmMore(n, all){
  const pane = FM.panes[n];
  pane.shown = all ? Infinity : (pane.shown || FM_PAGE) + FM_PAGE;
  drawFiles();
}

function fmMoreHtml(n, drawn, whole){
  if (drawn >= whole) return "";
  return `<div class="act fmmore">
    <button type="button" class="ghost" onclick="event.stopPropagation(); fmMore(${n})"
      >Show the next ${num(Math.min(FM_PAGE, whole - drawn))}</button>
    <button type="button" class="ghost" onclick="event.stopPropagation(); fmMore(${n}, true)"
      >Show all ${num(whole)}</button>
    <span class="note">${num(drawn)} of ${num(whole)} drawn</span></div>`;
}

/* Reaching the bottom of the list asks for the next page by itself, so a
   wheel or a finger never meets a button. */
function fmNearEnd(e){
  const el = e.currentTarget;
  const n = +el.dataset.pane;
  const pane = FM.panes[n];
  if (!pane || !pane.data) return;
  /* A list that has just been replaced, or is not on screen, measures as
     nothing tall - and nothing tall is always "at the bottom". */
  if (!el.isConnected || !el.clientHeight) return;
  if (el.scrollTop + el.clientHeight < el.scrollHeight - 240) return;
  if (fmRows(n).length <= (pane.shown || FM_PAGE)) return;
  fmMore(n);
}

/* What is on screen: the folder, in the order asked for, narrowed by the
   search box. One function, so the listing, the footer count and "Select
   everything" can never disagree about what "everything" is. */
function fmRows(n){
  const pane = FM.panes[n];
  const d = pane.data;
  if (!d) return [];
  let rows = fmOrder(n, (d.folders || []).concat(d.files || []));
  const want = String(pane.find || "").trim().toLowerCase();
  if (want) rows = rows.filter(x => x.name.toLowerCase().includes(want));
  return rows;
}

function fmFind(n, text){
  FM.panes[n].find = text || "";
  const pane = FM.panes[n];
  /* Narrowing the list must not leave things picked that are no longer on
     screen - "Delete 12" with four of them invisible is the worst kind of
     surprise. */
  const there = {};
  fmRows(n).forEach(x => { there[x.path] = 1; });
  pane.sel = pane.sel.filter(p => there[p]);
  const box = document.querySelector(`.fmpane${n === FM.at ? ".on" : ""} .fmsearch`);
  drawFiles();
  const now = document.querySelector(".fmpane.on .fmsearch");
  if (now && box){ now.focus(); now.setSelectionRange(now.value.length, now.value.length); }
}

function fmNothingHtml(n){
  const pane = FM.panes[n];
  if (pane.find)
    return nothingHere({icon: "find", title: "Nothing by that name",
      said: `Nothing in this folder is called "${pane.find}".`,
      acts: [{label: "Clear the search", go: `fmFind(${n}, '')`}]});
  return nothingHere({icon: "folder", title: "Nothing in this folder",
    said: "No files and no folders in here" + (FM.hidden ? "." : " that are not hidden."),
    acts: [{label: "New folder", go: "fmNewFolder()"},
           {label: "Up one folder",
            go: `fmGo(${n}, '${quoted((pane.data && pane.data.parent) || "")}')`}]});
}

function fmFoundHtml(pane){
  const files = (pane.data && pane.data.files) || [];
  const folders = new Set(files.map(f => f.folder || "").filter(Boolean));
  const chip = t => `<span class="fmchip">${t}</span>`;
  return `<div class="fmstat">`
    + chip(say("nFiles", {n: files.length}))
    + chip(say("fromFolders", {n: folders.size}))
    + chip(fmSize(files.reduce((n, f) => n + (f.size || 0), 0)))
    + `<span class="note">everything above works on these, wherever they
        are</span></div>`;
}

/* ---- the folder's own state, as ONE line

   It was eleven chips in a row - "128 photos", "14 RAW", "1.2 GB", "128
   rated", "116 placed", "12 with no date", "9 without a preview" - above every
   listing, all the same size and all the same weight, so the one that said
   something was wrong looked exactly like the seven that said everything was
   fine. A person reads that row once and never again.

   One line now: a light, the size of the place, and the first thing that is
   actually wrong. The eleven chips are still there, behind a press, for when
   the answer is the question. */
function fmVerdict(st, kids){
  if (!st || st.error) return null;
  const bad = [];
  if (st.photos){
    if (st.undated) bad.push(`${st.undated} with no date`);
    const noPlace = st.photos - st.located;
    if (noPlace) bad.push(`${noPlace} with no place`);
    const noPrev = st.photos - st.with_preview;
    if (noPrev) bad.push(`${noPrev} without a preview`);
    if (st.with_raw && st.photos - st.with_raw)
      bad.push(`${st.photos - st.with_raw} without a RAW`);
  }
  const parts = [];
  if (kids) parts.push(`${kids} folder${kids === 1 ? "" : "s"}`);
  if (st.photos) parts.push(`${st.photos} photo${st.photos === 1 ? "" : "s"}`);
  if (st.raws) parts.push(`${st.raws} RAW`);
  if (st.videos) parts.push(`${st.videos} video`);
  if (st.size) parts.push(fmSize(st.size));
  return {how: bad.length ? "warn" : "good", said: parts.join(" · ") || "nothing in here",
          wrong: bad};
}

function fmHealthHtml(n){
  const st = FM.panes[n].status;
  if (!st) return `<div class="fmhealth"><span class="note">Reading what is in here...</span></div>`;
  if (st.error) return "";
  const d = FM.panes[n].data;
  const v = fmVerdict(st, ((d && d.folders) || []).length);
  return `<div class="fmhealth">
    <span class="light ${v.how}" aria-hidden="true"></span>
    <span class="hsaid">${esc(v.said)}</span>
    ${v.wrong.length ? `<span class="hwrong">${esc(v.wrong[0])}${
        v.wrong.length > 1 ? ` and ${v.wrong.length - 1} more` : ""}</span>` : ""}
    <button class="quiet" onclick="event.stopPropagation(); fmOpenHealth(!FM.open)"
      title="Every figure this folder has">${FM.open ? "Hide the figures" : "All the figures"}</button>
  </div>` + (FM.open ? fmStatusHtml(n) : "");
}

function fmOpenHealth(on){
  FM.open = !!on;
  drawFiles();
}

function fmStatusHtml(n){
  /* The dashboard for the folder you are standing in. Loaded after the listing
     rather than with it: the names are instant and this reads headers, and a
     manager that waits for the slow half before showing anything is a manager
     that feels broken. */
  const st = FM.panes[n].status;
  if (!st) return `<div class="fmstat"><span class="note">reading what is in here...</span></div>`;
  if (st.error) return "";
  const chip = (text, cls) => `<span class="fmchip${cls ? " " + cls : ""}">${text}</span>`;
  let h = `<div class="fmstat">`;
  if (st.photos) h += chip(`${st.photos} photo${st.photos === 1 ? "" : "s"}`);
  if (st.raws) h += chip(`${st.raws} RAW`);
  if (st.videos) h += chip(`${st.videos} video`);
  if (st.size) h += chip(fmSize(st.size));
  if (st.photos){
    h += chip(`${st.rated} rated`, st.rated === st.photos ? "good" : "");
    h += chip(`${st.located} placed`, st.located === st.photos ? "good"
      : st.located ? "" : "warn");
    if (st.undated) h += chip(`${st.undated} with no date`, "warn");
    if (st.tagged) h += chip(`${st.tagged} tagged`);
    const noRaw = st.photos - st.with_raw, noPrev = st.photos - st.with_preview;
    if (noRaw && st.with_raw) h += chip(`${noRaw} without a RAW`, "warn");
    if (noPrev) h += chip(`${noPrev} without a preview`, noPrev === st.photos ? "" : "warn");
  }
  if (st.capped) h += chip("first 3,000 only");
  return h + `</div>`;
}

async function fmStatus(n){
  const pane = FM.panes[n];
  const path = pane.path;
  if (!path) return;
  try{
    const got = await (await fetch("api/folder-status?path=" + encodeURIComponent(path))).json();
    if (FM.panes[n].path !== path) return;       // moved on while it was reading
    pane.status = got;
  }catch(e){ pane.status = {error: 1}; }
  drawFiles();
}

/* ---- one press

   A press used to tick the row. Opening a folder was a DOUBLE press, which a
   phone does not have and a tablet does badly, so on a touch screen the only
   way into a folder was the name itself - a target four millimetres tall. Not
   one file manager in the world works that way.

   One press opens. Picking is a mode you turn on (Select), a modifier-press
   for a desk, or a long press for a finger. Shift extends from the last one
   you touched, because picking forty files one at a time is not picking. */
function fmRowClick(n, path, ev){
  const pane = FM.panes[n];
  FM.at = n;
  if (ev && ev.shiftKey && pane.anchor){ fmRange(n, pane.anchor, path); return; }
  if (FM.picking || (ev && (ev.metaKey || ev.ctrlKey))){
    pane.anchor = path;
    fmToggle(n, path);
    return;
  }
  const rows = fmRows(n);
  const x = rows.find(r => r.path === path);
  if (x) fmOpen(n, x);
}

function fmRange(n, from, to){
  const pane = FM.panes[n];
  const rows = fmRows(n).map(r => r.path);
  let a = rows.indexOf(from), b = rows.indexOf(to);
  if (a < 0 || b < 0) return fmToggle(n, to);
  if (a > b){ const t = a; a = b; b = t; }
  const want = rows.slice(a, b + 1);
  pane.sel = pane.sel.concat(want.filter(p => !pane.sel.includes(p)));
  pane.anchor = to;
  if (!FM.picking && pane.sel.length) FM.picking = true;
  drawFiles();
}

/* A finger has no right button and no Ctrl key. Holding still for half a
   second is what it has instead, and it is what every phone gallery uses. */
function fmHold(n, path, ev){
  const pane = FM.panes[n];
  clearTimeout(FM.held);
  FM.held = setTimeout(() => {
    FM.picking = true;
    pane.anchor = path;
    if (!pane.sel.includes(path)) pane.sel.push(path);
    FM.at = n;
    if (navigator.vibrate) try{ navigator.vibrate(12); }catch(e){}
    drawFiles();
  }, 500);
}

function fmLetGo(){ clearTimeout(FM.held); }

function fmPicking(on){
  FM.picking = !!on;
  if (!FM.picking) FM.panes.forEach(p => { p.sel = []; p.anchor = ""; });
  drawFiles();
}

function fmClearSel(){
  FM.panes.forEach(p => { p.sel = []; p.anchor = ""; });
  FM.picking = false;
  drawFiles();
}

function fmTouchBits(n, q){
  return `onpointerdown="fmHold(${n},'${q}',event)" onpointerup="fmLetGo()"
    onpointercancel="fmLetGo()" onpointermove="fmLetGo()"`;
}

function fmList(n, rows){
  const pane = FM.panes[n];
  const picked = new Set(pane.sel);
  return `<div class="fmlist" data-pane="${n}">` + rows.map(x => {
    const on = picked.has(x.path);
    const q = quoted(x.path);
    return `<div class="fmrow${on ? " on" : ""}" onclick="fmRowClick(${n},'${q}',event)"
        ${fmTouchBits(n, q)} title="${esc(x.name)}">
      <span class="tick" onclick="event.stopPropagation(); fmToggle(${n},'${q}')"
        role="checkbox" aria-checked="${on}" aria-label="Pick ${esc(x.name)}"
        >${icon("check")}</span>
      ${fmShowable(x) ? `<img class="th" loading="lazy" alt="" data-p="${esc(x.path)}"
          src="${thumbSrc(x.path, "s", x.when)}"
          onerror="this.replaceWith(Object.assign(document.createElement('span'),
            {className:'fmic'}))">` : `<span class="fmic">${fmIcon(x)}</span>`}
      <span class="fmname">${esc(x.name)}</span>
      <span class="fmmarks">${fmMarkHtml(fmMark(n, x))}</span>
      <span class="note fmsize">${x.kind === "folder"
        ? fmWeighHtml(n, x) : fmSize(x.size)}</span>
      <span class="note fmwhen">${fmWhen(x.when)}</span>
    </div>`;
  }).join("") + `</div>`;
}

/* HOW TALL A PICTURE BOX IS, AS A NUMBER, ON THE ELEMENT ITSELF.

   This has now been wrong twice. The box took its height from `aspect-ratio`,
   which came out as nothing and left eighty rounded bars twenty pixels tall;
   it was then given an `aspect-ratio` and a `min-height` in the stylesheet, and
   it was STILL nothing on the machine it mattered on.

   So it is not a stylesheet question any more. The height is written onto each
   box as an inline style, which no rule, no cascade order and no engine's
   opinion about aspect ratios inside flex containers can disagree with. One
   number, computed in one place, used by the box and by the picture in it. */
function fmTileHigh(){ return isPhone() ? 96 : 126; }

function fmGrid(n, rows){
  const pane = FM.panes[n];
  const high = fmTileHigh();
  const picked = new Set(pane.sel);
  return `<div class="grid fmgrid" data-pane="${n}">` + rows.map(x => {
    const on = picked.has(x.path);
    const q = quoted(x.path);
    return `<figure class="tile${on ? " on" : ""}" onclick="fmRowClick(${n},'${q}',event)"
        ${fmTouchBits(n, q)} title="${esc(x.name)}"
        style="min-height:${high + 42}px">
      <div class="pic" style="height:${high}px;min-height:${high}px;flex:0 0 ${high}px">${
        fmShowable(x)
        ? `<img loading="lazy" alt="" style="height:${high}px" src="${thumbSrc(x.path, "s", x.when)}"
             onerror="this.replaceWith(Object.assign(document.createElement('span'),
               {className:'nopic', textContent:'no preview'}))">`
        : `<span class="fmbig">${fmIcon(x)}</span>`}
        <span class="tick" onclick="event.stopPropagation(); fmToggle(${n},'${q}')"
          role="checkbox" aria-checked="${on}" aria-label="Pick ${esc(x.name)}"
          >${icon("check")}</span></div>
      <figcaption><div class="gname">${esc(x.name)}</div>
        <div class="gtags">${fmMarkHtml(fmMark(n, x))
          || (x.kind === "folder" ? fmWeighHtml(n, x) : fmSize(x.size))}</div></figcaption>
    </figure>`;
  }).join("") + `</div>`;
}

/* ---- the act bar

   Every action lived in one row under the listing: twenty-two buttons, three
   of them destructive, sitting there greyed out before a single file had been
   chosen. A row like that is read as decoration - you stop seeing it - and the
   one thing it has to do, which is tell you what is about to happen to the
   forty files you just picked, it could not do at all.

   It now exists only when something is picked, it says how many, and the
   dangerous one is the only one wearing the destructive role. Everything that
   is about the FOLDER rather than about a selection moved into the two menus
   at the top, where nothing is ever disabled. */
function fmActHtml(){
  const sel = fmSelected();
  if (!sel.length) return "";
  const one = sel.length === 1;
  const kind = fmKindOf(sel);
  return `<div class="fmact">
    <span class="fmcount">${sel.length} ${kind} picked</span>
    <button class="pillbtn" onclick="fmSheetOpen(false)"
      title="${esc(S.copyTip)}"
      >${icon("copy")} Copy to...</button>
    <button class="pillbtn" onclick="fmSheetOpen(true)"
      title="${esc(S.moveTip)}"
      >${icon("send")} Move to...</button>
    <button class="pillbtn" ${one ? "" : "disabled"} onclick="fmRename()"
      title="Give this one a new name, with its RAW and preview">Rename</button>
    <button class="pillbtn" onclick="fmUse(event)"
      title="Open what is picked in another tool">${icon("play")} Use in</button>
    <button class="pillbtn" onclick="fmActMore(event)"
      title="Download, copy the paths, the clipboard">${icon("menu")} More</button>
    <button class="danger" onclick="fmDelete()"
      title="${esc(S.recycleTip)}"
      >${icon("trash")} Delete</button>
    <button class="quiet" onclick="fmClearSel()">Clear</button>
  </div>`;
}

function fmKindOf(sel){
  const pane = fmPane();
  const folders = ((pane.data && pane.data.folders) || []).map(f => f.path);
  const dirs = sel.filter(p => folders.includes(p)).length;
  if (dirs === sel.length) return sel.length === 1 ? "folder" : "folders";
  if (!dirs) return sel.length === 1 ? "file" : "files";
  return "things";
}

function fmActMore(ev){
  const sel = fmSelected();
  const clip = FM.clip;
  const rows = [
    ["download", "Save to this device", sel.length === 1],
    ["paths", "Copy the paths", true],
    ["copy", "Copy (and Paste elsewhere)", true],
    ["cut", "Cut (and Paste elsewhere)", true],
    ["paste", `Paste${clip ? ` ${clip.paths.length} here` : " here"}`,
     !!(clip && clip.paths.length)],
    ["send", `Move to the other pane`, FM.two],
    ["sendcopy", `Copy to the other pane`, FM.two],
  ].filter(r => r[2]);
  pageMenu(ev, rows.map(([k, label]) =>
    `<button type="button" class="vopt" data-k="${k}">${esc(label)}</button>`).join(""),
    b => fmActDo(b.dataset.k));
}

function fmActDo(what){
  closePageMenu();
  if (what === "download") return fmDownload();
  if (what === "paths") return fmCopyPaths();
  if (what === "copy") return fmClip("copy");
  if (what === "cut") return fmClip("cut");
  if (what === "paste") return fmPaste();
  if (what === "send") return fmSend(true);
  if (what === "sendcopy") return fmSend(false);
}

async function fmCopyPaths(){
  const text = fmSelected().join("\n");
  try{ await navigator.clipboard.writeText(text); toast("Paths copied"); }
  catch(e){ toast(S.copyRefused, 4000); }
}

/* ---- the two menus at the top

   What used to be nine checkboxes and four "... ▾" buttons spread across two
   rows. Nothing in either of them is ever disabled, because neither is about a
   selection: one is how to LOOK at the folder, the other is what to DO with
   the folder itself. */
function fmViewMenu(n, ev){
  const pane = FM.panes[n];
  const tick = on => on ? icon("check") : `<span class="vgap"></span>`;
  const rows = [
    ["list", `${tick(pane.view === "list")} As a list`],
    ["grid", `${tick(pane.view === "grid")} ${esc(S.viewGrid)}`],
    ["-", ""],
    ["sort", `${icon("expand-all")} Order: ${fmSortName(pane.sort)}`],
    ["two", `${tick(FM.two)} Split view`],
    ["info", `${tick(FM.info)} Details panel`],
    ["-", ""],
    ["hidden", `${tick(FM.hidden)} Hidden folders`],
    ["deep", `${tick(FM.deep)} Photos below too`],
    ["-", ""],
    /* What goes with a file when it is moved, copied or deleted. The one thing
       this manager does that File Station cannot, so it belongs where you can
       see what it is set to - not in a form under the listing. */
    ["raws", `${tick(fmOpts().raw)} RAW files follow`],
    ["previews", `${tick(fmOpts().prev)} Previews follow`],
  ];
  pageMenu(ev, rows.map(([k, label]) => k === "-"
    ? `<div class="mline"></div>`
    : `<button type="button" class="vopt" data-k="${k}">${label}</button>`).join(""),
    b => fmViewDo(n, b.dataset.k, ev));
}

/* A row that opens ANOTHER menu returns false, which tells pageMenu not to
   close what it has just opened - the menu machinery closes the old one on its
   own when the new one is made. Without it the second menu appeared and
   vanished in the same frame. */
function fmViewDo(n, what, ev){
  const pane = FM.panes[n];
  if (what === "sort"){ fmSortMenu(n, ev); return false; }
  closePageMenu();
  if (what === "list" || what === "grid"){
    pane.view = what; FM.panes[n ? 0 : 1].view = what; fmKeep(); return drawFiles();
  }
  if (what === "two") return fmTwo(!FM.two);
  if (what === "info"){ FM.info = !FM.info; fmKeep(); drawFiles(); return fmAbout(); }
  if (what === "hidden") return fmHidden(!FM.hidden);
  if (what === "deep") return fmDeep(!FM.deep);
  if (what === "raws" || what === "previews"){
    const box = document.getElementById(
      what === "raws" ? "o_with_raw" : "o_with_previews");
    if (box){
      box.checked = !box.checked;
      box.dispatchEvent(new Event("change", {bubbles: true}));
      toast(`${what === "raws" ? "RAWs" : "Previews"} `
            + (box.checked ? "follow what you move" : "stay where they are"), 2600);
    }
    return drawFiles();
  }
}

function fmSortName(key){
  const row = FMSORTS.find(s => s[0] === key);
  return row ? row[1] : "Name";
}

function fmMoreMenu(n, ev){
  const rows = [
    ["new", `${icon("folder")} New folder`],
    ["select", `${icon("select")} Select everything`],
    ["pick", `${icon("find")} Select by kind...`],
    ["-", ""],
    ["sizes", `${icon("layers")} Read every folder size`],
    ["renames", `${icon("type")} Rename many`],
    ["use", `${icon("play")} Use this folder in...`],
    ["-", ""],
    ["places", `${icon("tree")} Go to a set-up folder`],
    ["refresh", `${icon("refresh")} Read this folder again`],
  ];
  pageMenu(ev, rows.map(([k, label]) => k === "-"
    ? `<div class="mline"></div>`
    : `<button type="button" class="vopt" data-k="${k}">${label}</button>`).join(""),
    b => fmMoreDo(n, b.dataset.k, ev));
}

function fmMoreDo(n, what, ev){
  if (what === "pick"){ fmPickMenu(ev); return false; }
  if (what === "places"){ fmPlaces(n, ev); return false; }
  if (what === "use"){ fmUse(ev); return false; }
  closePageMenu();
  if (what === "new") return fmNewFolder();
  if (what === "select"){ FM.picking = true; return fmPick(n, "all"); }
  if (what === "sizes") return fmWeighAll(n);
  if (what === "renames") return fmPowerRename();
  if (what === "refresh"){
    freshPics();
    const pane = FM.panes[n];
    return pane.found ? fmShowFound(pane.found) : fmGo(n, pane.path);
  }
}

/* ---- where do these go

   Copy and Cut are half a sentence and the other half is WHERE. The old answer
   was a second pane: it opened itself, took half the screen, and on a phone it
   did not exist at all - so a phone got "copied - now open a folder and press
   Paste", which is a two-screen instruction for one thought.

   This is the other half of the sentence, as a place you walk into and press
   once. The same sheet on a phone and on a desk. The split view is still there
   for people who want it; it is now a choice in the View menu rather than the
   only way to move a file. */
function fmSheetOpen(move){
  const sel = fmSelected();
  if (!sel.length) return;
  FM.sheet = {paths: sel, move: !!move, at: fmPane().path, data: null, busy: true,
              kind: fmKindOf(sel)};
  drawFiles();
  fmSheetGo(fmPane().path);
}

function fmSheetClose(){
  FM.sheet = null;
  const box = document.getElementById("fmsheet");
  if (box) box.remove();
}

async function fmSheetGo(path){
  if (!FM.sheet) return;
  FM.sheet.at = path;
  FM.sheet.busy = true;
  fmSheetDraw();
  try{
    const got = await (await fetch("api/files?hidden=" + (FM.hidden ? 1 : 0)
      + (path ? "&path=" + encodeURIComponent(path) : ""), {cache: "no-store"})).json();
    if (!FM.sheet) return;
    FM.sheet.data = got.error ? null : got;
    FM.sheet.error = got.error || "";
    if (!got.error) FM.sheet.at = got.path;
  }catch(e){ if (FM.sheet) FM.sheet.error = "could not read that folder"; }
  if (FM.sheet) FM.sheet.busy = false;
  fmSheetDraw();
}

async function fmSheetNew(){
  if (!FM.sheet) return;
  const name = await fmAsk({title: "New folder", value: "", yes: "Make it"});
  if (!name || !FM.sheet) return;
  const got = await fmPost({do: "mkdir", into: FM.sheet.at, name: name});
  if (got) fmSheetGo(FM.sheet.at);
}

async function fmSheetDo(){
  const sheet = FM.sheet;
  if (!sheet) return;
  const into = sheet.at;
  const paths = sheet.paths;
  const move = sheet.move;
  if (paths.some(p => into === p || into.startsWith(p + "/") || into.startsWith(p + "\\"))){
    toast("A folder cannot go inside itself", 4000);
    return;
  }
  fmSheetClose();
  await fmRun(paths, into, move);
}

function fmSheetDraw(){
  const sheet = FM.sheet;
  let box = document.getElementById("fmsheet");
  if (!sheet){ if (box) box.remove(); return; }
  if (!box){
    box = document.createElement("div");
    box.id = "fmsheet";
    box.className = "sure";
    box.onclick = e => { if (e.target === box) fmSheetClose(); };
    document.body.appendChild(box);
  }
  const d = sheet.data;
  const crumbs = (d && d.crumbs) || [];
  const folders = (d && d.folders) || [];
  const here = crumbs.length ? crumbs[crumbs.length - 1].name : "...";
  box.innerHTML = `<div class="surebox sheet">
    <h3>${sheet.move ? "Move" : "Copy"} ${num(sheet.paths.length)} ${
      esc(sheet.kind || S.items)}: where to?</h3>
    <div class="sheettop">
      <button class="ghost" ${d && d.parent ? "" : "disabled"} title="Up one folder"
        onclick="fmSheetGo('${quoted((d && d.parent) || "")}')">${icon("back")}</button>
      <div class="fmwhere">${crumbs.slice(-4).map((c, i, a) =>
        `<button class="crumb${i === a.length - 1 ? " on" : ""}"
           onclick="fmSheetGo('${quoted(c.path)}')">${esc(shortText(c.name))}</button>`)
        .join(`<span class="sep">/</span>`)}</div>
      <button class="ghost" onclick="fmSheetNew()">${icon("folder")} New folder</button>
    </div>
    <div class="sheetlist">${sheet.busy ? `<div class="fmempty">Reading...</div>`
      : sheet.error ? `<div class="fmempty bad">${esc(sheet.error)}</div>`
      : folders.length ? folders.map(f =>
          `<button type="button" class="sheetrow" onclick="fmSheetGo('${quoted(f.path)}')">
             <span class="fmic">${icon("folder")}</span>
             <span class="sname">${esc(f.name)}</span>
             <span class="note">open</span></button>`).join("")
      : `<div class="fmempty">No folders in here - ${sheet.move ? "move" : "copy"}
           them in anyway, or make one.</div>`}</div>
    <div class="act">
      <button class="ghost" onclick="fmSheetClose()">Cancel</button>
      <button ${sheet.busy || sheet.error ? "disabled" : ""} onclick="fmSheetDo()"
        >${sheet.move ? "Move" : "Copy"} into ${esc(shortText(here))}</button>
    </div>
  </div>`;
}

/* ---- the panel on the right

   "Which of these is the one with no location" was a question you answered by
   opening each file in the viewer and coming back. The facts were already
   being read for the marks; this is them, written out, for whatever is picked. */
function fmInfoHtml(){
  const sel = fmSelected();
  const pane = fmPane();
  if (!sel.length)
    return `<aside class="fminfo"><div class="ihead">Details</div>
      <div class="note">Pick something and what is known about it appears here.</div>
      </aside>`;
  if (sel.length > 1){
    const rows = fmRows(FM.at).filter(x => sel.includes(x.path));
    const bytes = rows.reduce((n, x) => n + (x.size || 0), 0);
    return `<aside class="fminfo"><div class="ihead">${sel.length} picked</div>
      <div class="ifact"><span>Together</span><b>${fmSize(bytes)}</b></div>
      <div class="ifact"><span>Folders</span><b>${rows.filter(
        x => x.kind === "folder").length}</b></div>
      <div class="ifact"><span>Files</span><b>${rows.filter(
        x => x.kind !== "folder").length}</b></div></aside>`;
  }
  const path = sel[0];
  const x = fmRows(FM.at).find(r => r.path === path) || {name: basename(path)};
  const a = FM.about[path];
  const fact = (label, value) => value
    ? `<div class="ifact"><span>${esc(label)}</span><b>${esc(String(value))}</b></div>` : "";
  return `<aside class="fminfo">
    <div class="ihead">${esc(x.name)}</div>
    ${fmShowable(x) ? `<img class="ipic" alt="" src="${thumbSrc(path, "m", x.when)}"
       onerror="this.remove()">` : ""}
    ${fact("Kind", x.kind === "folder" ? "Folder" : String(x.kind || "file").toUpperCase())}
    ${x.kind === "folder" ? "" : fact("Size", fmSize(x.size))}
    ${fact("Changed", x.when ? fmWhen(x.when) : "")}
    ${a ? fact("Taken", a.taken ? a.taken.replace("T", " ").slice(0, 16) : "no date on it")
        + fact("Camera", a.camera) + fact("Lens", a.lens)
        + fact("Where", a.located ? `${a.lat}, ${a.lon}` : "no location")
        + fact("Beside it", (a.copies || []).map(c => c.name).join(", ")
            || "nothing in the other trees")
      : (x.kind === "folder" ? "" : `<div class="note">Reading...</div>`)}
    <div class="iact">
      ${fmViewable(x) ? `<button class="ghost" onclick="fmOpen(${FM.at}, ${
        esc(JSON.stringify(x)).replace(/"/g, "&quot;")})">${icon("image")} Look at it</button>`
        : ""}
      <button class="ghost" onclick="fmRename()">Rename</button>
    </div>
  </aside>`;
}

async function fmAbout(){
  if (!FM.info) return;
  const sel = fmSelected();
  if (sel.length !== 1) return;
  const path = sel[0];
  if (FM.about[path]) return;
  const x = fmRows(FM.at).find(r => r.path === path);
  if (!x || x.kind === "folder") return;
  try{
    const got = await (await fetch("api/photo-about?path="
      + encodeURIComponent(path))).json();
    if (got.error) return;
    FM.about[path] = got;
  }catch(e){ return; }
  if (FM.info) drawFiles();
}

function fmJobHtml(){
  const j = FM.job;
  if (!j) return "";
  const pct = j.total ? Math.round(100 * j.done / j.total) : 0;
  return `<div class="fmjob">
    <span class="jname">${j.move ? "Moving" : "Copying"} ${j.done} of ${j.total}</span>
    <span class="jbar"><i style="width:${pct}%"></i></span>
    <span class="jnow">${esc(j.now || "")}</span>
    <button class="ghost" onclick="fmStop()">Stop</button></div>`;
}

function fmTwo(on){
  FM.two = !!on; fmKeep(); drawFiles();
  if (on && !FM.panes[1].data) fmGo(1, FM.panes[1].path || FM.panes[0].path);
}
function fmHidden(on){
  FM.hidden = !!on; fmKeep();
  FM.panes.forEach((p, n) => { if (p.data) fmGo(n, p.path); });
}
function fmDeep(on){
  /* "Include subfolders", which the Photos tab had and this did not. Folders
     are still listed, so you can keep walking in; the files become every
     photograph below here, named by the way down to them. */
  FM.deep = !!on; fmKeep();
  FM.panes.forEach((p, n) => { if (p.data) fmGo(n, p.path); });
}

const TREE_WORDS = {
  library: S.treeLibrary,
  raw: S.treeRaw,
  previews: S.treePreviews,
  video: S.treeVideo,
  develop: "the working set you edit in Lightroom",
  inbox: "where finished edits come back to",
};

function fmPlaces(n, ev){
  /* A row of chips called RAWs and Previews, beside the folder you are
     standing in, reads as something to press rather than somewhere to go -
     and pressing one silently moved the pane. So they are a menu now, each
     with a line saying what that tree is for. */
  const pane = FM.panes[n];
  const roots = (pane.data && pane.data.roots) || [];
  fmMenu(ev, roots.map(r =>
    `<button type="button" class="vopt" data-p="${esc(r.path)}" ${r.there ? "" : "disabled"}>
       <span class="vgrow"><b>${esc(r.name)}</b>
         <span class="note">${esc(TREE_WORDS[r.key] || "")}${r.there ? "" : " - not set up"}</span>
       </span>${pane.path === r.path ? "<span class=\"vcheck\">✓</span>" : ""}</button>`).join("")
    || `<div class="vdim" style="padding:10px 12px">No trees are set up yet - Setup.</div>`,
    b => fmGo(n, b.dataset.p));
}

const FMSORTS = [["name", "Name"], ["when", "Date on the file"],
                 ["size", "Size"], ["stars", "Stars"]];

function fmSortMenu(n, ev){
  const pane = FM.panes[n];
  fmMenu(ev, FMSORTS.map(([k, label]) =>
    `<button type="button" class="vopt" data-k="${k}"><span class="vgrow">${label}</span>
       ${(pane.sort || "name") === k ? "<span class=\"vcheck\">✓</span>" : ""}</button>`).join(""),
    b => { FM.panes.forEach(p => { p.sort = b.dataset.k; }); fmKeep(); drawFiles(); });
}

/* ------------------------------------------------------------ the page menu

   Every "\u25be" on the page - Go to, Sort, Pick, Columns, the value pickers -
   opens through here. There used to be two near-copies of this function, each
   positioning and dismissing itself a little differently, and both of them
   borrowed the viewer's dark popup for their looks.

   One box, one place that decides where it goes, one way of shutting it. The
   sheet of glass behind it is not decoration: on iOS a tap on plain background
   does not reliably reach a document click listener, so a menu that listened
   only for that could be opened and then not closed. */
let PMENU = null;

function closePageMenu(){
  if (!PMENU) return;
  const gone = PMENU;
  PMENU = null;
  gone.box.remove();
  if (gone.scrim) gone.scrim.remove();
  document.removeEventListener("keydown", gone.away);
}

function pageMenu(ev, html, hit){
  closePageMenu();
  if (typeof closeMenu === "function") closeMenu();     // never two at once
  /* The anchor is read here, at the top, on purpose. A caller that fetched
     something first has lost ev.currentTarget by the time it gets here, and one
     that closed the viewer first is measuring a node no longer in the page -
     which is how a menu ended up in the top-left corner behind the header. */
  const from = (ev && (ev.currentTarget || ev.target)) || null;
  const btn = from && from.closest
    ? (from.closest("button,a,[role=button]") || from) : from;
  const scrim = document.createElement("div");
  scrim.id = "menuscrim";
  scrim.onclick = closePageMenu;
  const box = document.createElement("div");
  box.className = "pmenu";
  /* Plain buttons in a box, said plainly. role="menu" promised arrow keys and
     menuitems that were never there, so a screen reader announced a menu and
     then found ordinary buttons in it. */
  box.innerHTML = html;
  box.onclick = e => {
    const b = e.target.closest("button[data-p], button[data-k], button[data-w]");
    if (b && !b.disabled && hit(b) !== false) closePageMenu();
  };
  document.body.appendChild(scrim);
  document.body.appendChild(box);
  // Measure, then place: the width is not known until the content is in it.
  const at = btn && btn.getBoundingClientRect ? btn.getBoundingClientRect() : null;
  if (at && at.width + at.height > 0){
    const w = box.offsetWidth, h = box.offsetHeight;
    box.style.left = Math.max(8, Math.min(innerWidth - w - 8, at.left)) + "px";
    box.style.top = (at.bottom + 6 + h > innerHeight - 8 && at.top - h - 6 > 8
                     ? at.top - h - 6 : at.bottom + 6) + "px";
  } else {
    box.style.left = "8px";
    box.style.top = "72px";
  }
  const away = e => { if (e.key === "Escape"){ e.stopPropagation(); closePageMenu(); } };
  document.addEventListener("keydown", away);
  PMENU = {box: box, scrim: scrim, away: away};
  return box;
}

function fmMenu(ev, html, pick){
  return pageMenu(ev, html, pick);
}

function fmPickMenu(ev){
  const n = FM.at;
  const menu = [["all", "Everything"], ["none", "Nothing"], ["folders", "Folders"],
                ["jpeg", "JPEGs"], ["raw", "RAWs"], ["video", "Video"]];
  const box = pageMenu(ev, menu.map(([k, label]) =>
    `<button type="button" class="vopt" data-k="${k}"><span class="vgrow">${label}</span></button>`).join("")
    + `<div class="fmfind"><input type="text" placeholder="Name holds..." id="fmfind"></div>`,
    b => { fmPick(n, b.dataset.k); });
  box.querySelector("#fmfind").onkeydown = e => {
    if (e.key === "Enter"){ fmPick(n, "name", e.target.value); closePageMenu(); }
  };
}

function fmUse(ev){
  /* The whole point of standing in a folder: you can see that Spain is half
     geotagged, and the next thing you want is to geotag Spain - not to
     remember its path and type it into another tab. One picked folder wins
     over the one you are in, because picking it is the more specific thing
     you did. */
  const sel = fmSelected();
  const pane = fmPane();
  const folders = (pane.data ? pane.data.folders : []).filter(f => sel.includes(f.path));
  workOn(ev, folders.length === 1 ? folders[0].path : pane.path);
}

function fmPowerRename(){
  /* What is picked comes with you - the table opens on those folders rather
     than on whatever the rename tab was last pointed at. */
  goWith("rename", fmPane().path);
}

function fmClip(mode){
  /* Copy and Cut are half a sentence and the other half is WHERE. "Copy to..."
     asks for that half straight away; this is the other way of saying it, for
     people who think in clipboards - so it no longer forces a second pane open
     to make its point. */
  FM.clip = {mode: mode, paths: fmSelected(), from: fmPane().path};
  toast(`${FM.clip.paths.length} ${mode === "cut" ? "cut" : "copied"}`
        + " - open where they go, then Paste from More", 3600);
  drawFiles();
}

async function fmSend(move){
  const to = fmOther().path;
  if (!to) return;
  await fmRun(fmSelected(), to, move);
}

async function fmPaste(){
  if (!FM.clip || !FM.clip.paths.length) return;
  const clip = FM.clip;
  await fmRun(clip.paths, fmPane().path, clip.mode === "cut");
  if (clip.mode === "cut") FM.clip = null;
  drawFiles();
}

async function fmRun(paths, into, move){
  const opts = fmOpts();
  const r = await fetch("api/files", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({do: move ? "move" : "copy", paths: paths, into: into,
                          with_raw: opts.raw, with_previews: opts.prev})});
  const got = await r.json();
  if (got.error){ toast(got.error, 6000); return; }
  FM.job = Object.assign({move: move, done: 0, total: got.total, now: ""}, got.state || {});
  drawFiles();
  clearInterval(FM.poll);
  FM.poll = setInterval(() => fmWatch(got.id), 500);
}

async function fmWatch(id){
  try{
    const st = await (await fetch("api/files/progress?id=" + id)).json();
    if (st.error){ clearInterval(FM.poll); FM.job = null; drawFiles(); return; }
    FM.job = st;
    if (st.finished){
      clearInterval(FM.poll);
      FM.job = null;
      const res = st.result || {};
      const moves = res.moves || [];
      const said = say(st.move ? "movedFiles" : "copiedFiles", {n: res.done || 0})
        + (res.renamed ? `, ${res.renamed} renamed to keep a name free` : "")
        + (res.failed ? `, ${res.failed} failed` : "");
      if (st.move && moves.length)
        toast(said, 9000, "Undo", async () => {
          const back = await (await fetch("api/files", {method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({do: "undo", moves: moves})})).json();
          toast(`${back.restored || 0} put back`, 3000);
          fmRefresh();
        });
      else toast(said, 5000);
      if ((res.errors || []).length) toast(res.errors[0], 8000);
      fmRefresh();
    } else drawFiles();
  }catch(e){}
}

function fmStop(){
  if (!FM.job) return;
  fetch("api/files", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({do: "cancel", id: FM.job.id})});
}

function fmRefresh(){
  FM.panes.forEach((p, n) => {
    if (!p.data) return;
    if (p.found) fmShowFound(p.found); else fmGo(n, p.path);
  });
}

function fmLeaveFound(n){
  /* Out of the results and back into a folder. The set is dropped rather than
     kept in the background: a pane that still remembers a search you have
     walked away from is a Refresh that goes somewhere you did not expect. */
  const pane = FM.panes[n];
  pane.found = null;
  fmGo(n, pane.path || (FM.panes[n ? 0 : 1].path || ""));
}

function fmOpts(){
  const raw = document.getElementById("o_with_raw");
  const prev = document.getElementById("o_with_previews");
  return {raw: raw ? raw.checked : true, prev: prev ? prev.checked : true};
}

async function fmAsk(o){
  /* A one-line answer - a name, mostly - in the same small dialog the rest of
     the app asks its questions in. */
  return new Promise(done => {
    const wrap = document.createElement("div");
    wrap.className = "sure";
    wrap.innerHTML = `<div class="surebox" role="dialog" aria-modal="true"
      aria-labelledby="askhead"><h3 id="askhead">${esc(o.title)}</h3>
      <input type="text" id="askbox" value="${esc(o.value || "")}" autocomplete="off"
        aria-labelledby="askhead">
      <div class="act"><button class="ghost" data-a="0">Cancel</button>
      <button data-a="1">${esc(o.yes || "OK")}</button></div></div>`;
    const box = () => wrap.querySelector("#askbox");
    let unhold = null;
    const end = v => { wrap.remove(); if (unhold) unhold(); done(v); };
    wrap.onclick = e => {
      if (e.target === wrap) end(null);
      const b = e.target.closest("button[data-a]");
      if (b) end(b.dataset.a === "1" ? box().value.trim() : null);
    };
    wrap.onkeydown = e => {
      if (e.key === "Enter") end(box().value.trim());
      if (e.key === "Escape") end(null);
    };
    document.body.appendChild(wrap);
    unhold = holdFocus(wrap, box());
    box().select();
  });
}

async function fmNewFolder(){
  const name = await fmAsk({title: "New folder", value: "", yes: "Make it"});
  if (!name) return;
  const got = await fmPost({do: "mkdir", into: fmPane().path, name: name});
  if (got) fmGo(FM.at, fmPane().path);
}

async function fmRename(){
  /* What is picked, or - when nothing is - the folder you are standing in.
     Renaming the folder you are IN is the common case the old one could not
     do at all: it only ever looked at the selection, so the answer to "rename
     this folder" was to walk out of it, find it in the list and pick it. */
  const pane = fmPane();
  const path = fmSelected()[0] || pane.path;
  if (!path) return;
  const here = path === pane.path;
  const was = path.split(/[\\/]/).pop();
  const name = await fmAsk({title: here ? `Rename this folder` : "Rename",
                            value: was, yes: "Rename"});
  if (!name || name === was) return;
  const got = await fmPost({do: "rename", path: path, name: name});
  if (!got) return;                      // fmPost has already said why
  toast(got.sidecars ? say("renamedWithSidecars", {n: got.sidecars}) : "Renamed", 3000);
  /* The thing that was picked no longer exists under that name, and a pane
     standing in a folder that has just been renamed must follow it rather than
     read a path that is gone. */
  pane.sel = [];
  pane.anchor = "";
  FM.picking = false;
  fmGo(FM.at, here ? (got.path || pane.path) : pane.path);
}

function fmDownload(){
  const path = fmSelected()[0];
  if (!path) return;
  const a = document.createElement("a");
  a.href = "api/download?path=" + encodeURIComponent(path);
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function fmDelete(){
  const sel = fmSelected();
  /* A folder goes through Delete folder, not straight to the Recycle Bin from
     here. That feature takes the folder's twins in the RAW, previews and video
     trees with it and shows the plan first; deleting it from here left those
     behind, still full, with nothing pointing at them. Files are unchanged. */
  const pane = fmPane();
  const folders = (pane.data ? pane.data.folders : [])
    .filter(f => sel.includes(f.path)).map(f => f.path);
  if (folders.length){
    if (folders.length < sel.length)
      toast("Folders are deleted through Delete folder. The files you picked "
            + "were left as they are.", 7000);
    openFeature("delfolder", {folders: folders});
    return;
  }
  const opts = fmOpts();
  const ok = await askSure({
    title: say("deleteItems", {n: sel.length}),
    body: "They go to the share's Recycle Bin, and you can put them back from "
        + "here or from File Station."
        + (opts.raw || opts.prev ? " Matching RAWs and previews go too." : ""),
    yes: "Delete"});
  if (!ok) return;
  const got = await fmPost({do: "delete", paths: sel, into: fmPane().path,
                            with_raw: opts.raw, with_previews: opts.prev});
  if (!got) return;
  toast(`${got.done} moved to the Recycle Bin`, 9000, "Undo", async () => {
    const back = await fmPost({do: "undo", moves: got.moves});
    toast(`${(back || {}).restored || 0} put back`, 3000);
    fmRefresh();
  });
  fmRefresh();
}

async function fmPost(body){
  try{
    const r = await fetch("api/files", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const got = await r.json();
    if (got.error){ toast(got.error, 6000); return null; }
    return got;
  }catch(e){ toast("that did not reach the app", 5000); return null; }
}

/* ---------------------------------------------------- the power rename table

   Every folder in a table, its name in a box. The mess this is for: a library
   grown over years holds `2022-04-12`, `12 April 2022`, `April 12` and `spain
   trip 2` side by side. One at a time that is thirty dialogs and you lose track
   of what you decided halfway down.

   Nothing is written until Rename is pressed. The bulk tools above the table
   FILL THE BOXES rather than doing anything - so what is about to be written is
   on the screen, in the rows it affects, before it happens. Every check comes
   back from the server as you type: two rows meeting on one name, and a name
   already taken by something not in the table, are the two that actually happen
   and neither is visible from inside a single row. */

const RN = {
  folder: "", depth: 1, start: 0, rows: [], names: {}, was: {}, picked: [],
  problems: {}, ready: 0, busy: false, error: "", moves: null, timer: 0,
  find: "", put: "", matchcase: false,
};

async function startRename(){
  /* It opens on what you had picked in Files - the whole reason this sits
     beside the manager rather than somewhere on its own. */
  const box = document.getElementById("o_folder");
  RN.folder = (box && box.value.trim()) || RN.folder;
  const depth = document.getElementById("o_depth");
  RN.depth = depth ? Math.max(0, parseInt(depth.value || "1", 10) || 0) : 1;
  const from = document.getElementById("o_start");
  RN.start = from ? Math.max(0, parseInt(from.value || "0", 10) || 0) : 0;
  RN.picked = (FM.panes[FM.at].sel || []).slice();
  await rnLoad();
}

function rnParams(){
  let url = "api/rename-list?depth=" + RN.depth + "&start=" + RN.start
    + "&path=" + encodeURIComponent(RN.folder);
  RN.picked.forEach(p => { url += "&picked=" + encodeURIComponent(p); });
  return url;
}

async function rnLoad(){
  RN.busy = true; RN.error = ""; rnDraw();
  try{
    const got = await (await fetch(rnParams(), {cache: "no-store"})).json();
    if (got.error){ RN.error = got.error; RN.rows = []; }
    else {
      RN.rows = got.rows || [];
      RN.folder = got.folder || RN.folder;
      RN.capped = !!got.capped;
      RN.kept = got.kept || [];
      RN.from_picked = !!got.from_picked;
      RN.names = {}; RN.was = {};
      RN.rows.forEach(r => { RN.names[r.path] = r.name; RN.was[r.path] = r.name; });
      RN.problems = {}; RN.moves = null;
    }
  }catch(e){ RN.error = "the table could not be read"; RN.rows = []; }
  RN.busy = false; rnDraw();
  rnCheckSoon();
}

/* ---- what is wrong with it, from the server, while you type */

function rnCheckSoon(){
  clearTimeout(RN.timer);
  RN.timer = setTimeout(rnCheck, 400);
}

async function rnCheck(){
  if (!RN.rows.length) return;
  const got = await rnPost({do: "check", rows: rnWanted()}, true);
  if (!got) return;
  RN.problems = {};
  (got.rows || []).forEach(r => { if (r.problem) RN.problems[r.path] = r.problem; });
  RN.ready = got.ready || 0;
  rnDraw();
}

function rnWanted(){
  return RN.rows.map(r => ({path: r.path, name: RN.names[r.path]}));
}

function rnChanged(){
  return RN.rows.filter(r => RN.names[r.path] !== RN.was[r.path]);
}

/* ---- typing */

function rnType(path, value){
  RN.names[path] = value;
  const cell = document.querySelector(`.rnrow[data-p="${CSS.escape(path)}"]`);
  if (cell) cell.classList.toggle("edited", value !== RN.was[path]);
  rnFoot();
  rnCheckSoon();
}

function rnReset(path){
  RN.names[path] = RN.was[path];
  rnDraw(); rnCheckSoon();
}

function rnResetAll(){
  RN.rows.forEach(r => { RN.names[r.path] = RN.was[r.path]; });
  RN.problems = {}; rnDraw(); rnCheckSoon();
}

/* ---- the bulk tools: each one fills the boxes, nothing writes */

function rnWhich(){
  /* Picked rows if any are ticked, otherwise every row. A tool that silently
     did all thirty when you meant these four is the whole danger here. */
  const on = RN.rows.filter(r => r.on);
  return on.length ? on : RN.rows;
}

function rnSwap(){
  const find = (document.getElementById("rnfind") || {}).value || "";
  const put = (document.getElementById("rnput") || {}).value || "";
  const cased = !!(document.getElementById("rncase") || {}).checked;
  if (!find){ toast("Type what to look for", 3000); return; }
  let hit = 0;
  rnWhich().forEach(r => {
    const now = RN.names[r.path] || "";
    const next = rnReplace(now, find, put, cased);
    if (next !== now){ RN.names[r.path] = next; hit++; }
  });
  toast(hit ? say("rnChanged", {n: hit}) : "nothing matched", 4000);
  rnDraw(); rnCheckSoon();
}

function rnReplace(name, find, put, cased){
  if (cased) return name.split(find).join(put);
  let out = "", at = 0;
  const low = name.toLowerCase(), lf = find.toLowerCase();
  for (;;){
    const hit = low.indexOf(lf, at);
    if (hit < 0) return out + name.slice(at);
    out += name.slice(at, hit) + put;
    at = hit + find.length;
  }
}

function rnCase(how){
  rnWhich().forEach(r => {
    const now = RN.names[r.path] || "";
    RN.names[r.path] = how === "lower" ? now.toLowerCase()
      : how === "upper" ? now.toUpperCase()
      : how === "tidy" ? now.replace(/[ \t]+/g, " ").replace(/_{2,}/g, "_").trim().replace(/^[-_ ]+|[-_ ]+$/g, "")
      : how === "unnumber" ? (now.replace(/^[\s\-_.]*\d+[\s\-_.]+/, "") || now)
      : now.replace(/[A-Za-z][A-Za-z']*/g, w => w[0].toUpperCase() + w.slice(1));
  });
  rnDraw(); rnCheckSoon();
}

function rnNumber(){
  const start = parseInt((document.getElementById("rnstart") || {}).value || "1", 10) || 1;
  const width = Math.max(1, Math.min(6,
    parseInt((document.getElementById("rnwidth") || {}).value || "2", 10) || 2));
  const end = !!(document.getElementById("rnatend") || {}).checked;
  const sep = (document.getElementById("rnsep") || {}).value;
  const gap = sep === undefined ? " - " : sep;
  rnWhich().forEach((r, n) => {
    const num = String(start + n).padStart(width, "0");
    const now = RN.names[r.path] || "";
    RN.names[r.path] = end ? now + gap + num : num + gap + now;
  });
  rnDraw(); rnCheckSoon();
}

async function rnPattern(){
  const pick = document.getElementById("rnpat");
  const pattern = pick ? pick.value : "";
  if (!pattern){ toast("Choose a pattern", 3000); return; }
  const rows = rnWhich().filter(r => r.kind === "folder");
  if (!rows.length){ toast("Patterns name folders, and none are picked", 4000); return; }
  toast(S.patternReading, 2500);
  const got = await rnPost({do: "pattern", pattern: pattern,
                            rows: rows.map(r => ({path: r.path, name: RN.names[r.path]}))});
  if (!got) return;
  let hit = 0, kept = 0;
  (got.names || []).forEach((name, n) => {
    const r = rows[n];
    if (!r) return;
    if (name && name !== RN.names[r.path]){ RN.names[r.path] = name; hit++; }
    else if (name === RN.was[r.path]) kept++;
  });
  toast(hit ? `${hit} named by the pattern`
            : S.rnNoNames,
        5000);
  rnDraw(); rnCheckSoon();
}

/* ---- doing it */

async function rnApply(){
  const doing = rnChanged();
  if (!doing.length){ toast("No names have been changed", 3000); return; }
  const bad = doing.filter(r => RN.problems[r.path]);
  if (bad.length){
    toast(say("rnBad", {n: bad.length}), 6000);
    return;
  }
  const raw = (document.getElementById("o_with_raw") || {}).checked;
  const prev = (document.getElementById("o_with_previews") || {}).checked;
  const ok = await askSure({
    title: `Rename ${doing.length}?`,
    body: say("rnBody", {n: doing.length})
      + (raw || prev ? ", and the matching folders in the other trees change with them" : "")
      + S.rnBodyEnd,
    yes: "Rename"});
  if (!ok) return;
  RN.busy = true; rnDraw();
  const got = await rnPost({do: "apply", rows: rnWanted(),
                            with_raw: !!raw, with_previews: !!prev});
  RN.busy = false;
  if (!got){ rnDraw(); return; }
  RN.moves = got.moves || null;
  const said = `${got.renamed} renamed`
    + (got.mirrored ? `, ${got.mirrored} in the other trees` : "")
    + (got.failed && got.failed.length ? `, ${got.failed.length} could not be` : "");
  toast(said, 12000, "Undo", async () => {
    const back = await rnPost({do: "undo", moves: got.moves});
    toast(`${(back || {}).restored || 0} put back`, 4000);
    rnLoad();
  });
  (got.failed || []).slice(0, 4).forEach((line, n) =>
    setTimeout(() => toast(line, 9000), 400 * (n + 1)));
  await rnLoad();
  if (document.getElementById("fileman")) freshPics();
}

async function rnPost(body, quiet){
  try{
    const r = await fetch("api/rename", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const got = await r.json();
    if (got.error){ if (!quiet) toast(got.error, 7000); return null; }
    return got;
  }catch(e){ if (!quiet) toast("that did not reach the app", 5000); return null; }
}

/* ---- drawing */

/* Which folder the table is OF, chosen here rather than in the form above it.
   "Pick one folder and rename what is beneath it" was possible and nobody could
   find it: the box was a scroll away under the editor, and the only controls in
   the editor itself were how DEEP to go from wherever it already was. */
function rnCrumbs(){
  const sep = RN.folder.indexOf("\\") >= 0 && RN.folder.indexOf("/") < 0 ? "\\" : "/";
  /* Each crumb's folder is counted from the END of the real path. Counting from
     the start went wrong twice: a Windows path has no empty first piece the way
     a path on the NAS does, so every crumb opened the folder below the one it
     named; and once the shared start of the library was trimmed from the
     labels, the labels and the paths no longer lined up at all. */
  const parts = RN.folder.replace(/[\\/]+$/, "").split(/[\\/]/);
  const upTo = n => {
    const p = parts.slice(0, n).join(sep);
    // "C:" alone is "wherever C: was last", not the top of the drive.
    return /^[A-Za-z]:$/.test(p) ? p + sep : (p || sep);
  };
  const named = parts.map((b, i) => i).filter(i => parts[i]);
  const shown = (shortText(RN.folder) || RN.folder).split(/[\\/]/).filter(Boolean).length;
  const keep = named.slice(-Math.max(1, Math.min(3, shown)));
  let out = shown > keep.length ? `<span class="note">...</span>` : "";
  keep.forEach((at, i) => {
    out += `<button class="rncrumb${i === keep.length - 1 ? " on" : ""}"
      onclick="rnGo('${quoted(upTo(at + 1))}')">${esc(parts[at])}</button>`;
  });
  // Not up to the very top of the container: that is its own system, not photos.
  const up = parts.length > 1 ? upTo(parts.length - 1) : "";
  return `<span class="rnpath">${up && up !== "/"
    ? `<button class="rncrumb" title="Up one"
        onclick="rnGo('${quoted(up)}')">\u2191</button>` : ""}
    ${out}</span>`;
}

function rnGo(path){
  if (!path) return;
  RN.folder = path;
  RN.picked = [];
  const box = document.getElementById("o_folder");
  if (box){ box.value = path; box.dispatchEvent(new Event("input", {bubbles: true})); }
  rnLoad();
}

function rnInto(path){ rnGo(path); }

function rnBrowse(){ browseTo(path => rnGo(path), RN.folder); }

function rnDepth(n){
  RN.depth = n;
  const box = document.getElementById("o_depth");
  if (box){ box.value = String(n); box.dispatchEvent(new Event("input")); }
  rnLoad();
}

function rnStart(n){
  /* Which level the table begins at. On a library of twelve years, "every
     folder" is a table nobody can use - and the only thing that made it
     usable before was a depth, which still started at the top. */
  RN.start = Math.max(0, n);
  const box = document.getElementById("o_start");
  if (box){ box.value = String(RN.start); box.dispatchEvent(new Event("input")); }
  rnLoad();
}

function rnTick(path, on){
  const row = RN.rows.find(r => r.path === path);
  if (row) row.on = !!on;
  rnDraw();
}

function rnTickAll(on){
  RN.rows.forEach(r => { r.on = !!on; });
  rnDraw();
}

function rnDraw(){
  const box = document.getElementById("renamer");
  if (!box) return;
  const changed = rnChanged().length;
  const bad = RN.rows.filter(r => RN.problems[r.path]).length;
  const picked = RN.rows.filter(r => r.on).length;
  const kept = (RN.kept || []).map(p =>
    `<option value="${esc(p.pattern)}">${esc(p.name)}</option>`).join("");
  let h = `<div class="rnwrap">
    <div class="rnwhere">
      <span class="note">Renaming what is inside</span>
      ${rnCrumbs()}
      <button class="ghost" onclick="rnBrowse()">${icon("folder")} Choose a folder</button>
    </div>
    <div class="rntop">
      <span class="note">${RN.from_picked
        ? `${RN.rows.length} from what you picked in File explorer`
        : `${say("rnFolders", {n: RN.rows.length})} ${RN.start ? say("rnLevels", {n: RN.start})
            : "in"} <code>${esc(shortText(basename(RN.folder) || RN.folder))}</code>`}</span>
      <span class="rngroup">Start at level:
        ${[[0, "here"], [1, "1 down"], [2, "2 down"], [3, "3 down"]].map(([n, label]) =>
          `<button class="ghost${RN.start === n ? " on" : ""}"
             onclick="rnStart(${n})">${label}</button>`).join("")}</span>
      <span class="rngroup">Levels to list:
        ${[[1, "1"], [2, "2"], [3, "3"], [0, "All"]].map(([d, label]) =>
          `<button class="ghost${RN.depth === d ? " on" : ""}"
             onclick="rnDepth(${d})">${label}</button>`).join("")}</span>
      <button class="ghost" onclick="rnLoad()">${icon("refresh")} Read again</button>
      ${RN.from_picked
        ? `<button class="ghost" onclick="RN.picked=[]; rnLoad()"
             title="List everything in the folder instead">Whole folder instead</button>`
        : ((FM.panes[FM.at].sel || []).length
          ? `<button class="ghost" onclick="RN.picked=FM.panes[FM.at].sel.slice(); rnLoad()"
               >Use the ${FM.panes[FM.at].sel.length} picked in File explorer</button>` : "")}
      <button class="ghost" ${changed ? "" : "disabled"} onclick="rnResetAll()"
        >Put every name back</button>
    </div>`;

  h += `<div class="rntools">
    <div class="rntool">
      <b>Find and replace</b>
      <div class="rnline">
        <input id="rnfind" placeholder="look for" aria-label="Look for"
          value="${esc(RN.find)}" oninput="RN.find=this.value">
        <input id="rnput" placeholder="put instead" aria-label="Put instead"
          value="${esc(RN.put)}" oninput="RN.put=this.value">
        <button class="ghost" onclick="rnSwap()">Replace</button>
      </div>
      <label class="fmcheck"><input type="checkbox" id="rncase"
        ${RN.matchcase ? "checked" : ""} onchange="RN.matchcase=this.checked">
        Match capitals</label>
    </div>
    <div class="rntool">
      <b>Name by a pattern</b>
      <div class="rnline">
        <select id="rnpat" aria-label="Pattern">
          <option value="">choose...</option>
          <option value="{year} {monthname}">2022 April</option>
          <option value="{year} {hmonthname}">2022 Ramadhan</option>
          <option value="{year}-{month}">2022-04</option>
          <option value="{date}">2022-04-12</option>
          <option value="{range}">12-14 April 2022</option>
          <option value="{camera}">GH4</option>
          ${kept}
        </select>
        <button class="ghost" onclick="rnPattern()">Fill in</button>
      </div>
      <span class="note">${esc(S.patternNote)}</span>
    </div>
    <div class="rntool">
      <b>Numbering</b>
      <div class="rnline">
        <input id="rnstart" type="number" value="1" min="0" style="width:4.5rem"
          aria-label="Start at">
        <input id="rnwidth" type="number" value="2" min="1" max="6" style="width:4rem"
          aria-label="Digits">
        <input id="rnsep" value=" - " style="width:4rem" aria-label="Between">
        <button class="ghost" onclick="rnNumber()">Add</button>
      </div>
      <label class="fmcheck"><input type="checkbox" id="rnatend"> At the end</label>
    </div>
    <div class="rntool">
      <b>Case and spacing</b>
      <div class="rnline wrap">
        <button class="ghost" onclick="rnCase('title')">Title Case</button>
        <button class="ghost" onclick="rnCase('lower')">lower</button>
        <button class="ghost" onclick="rnCase('upper')">UPPER</button>
        <button class="ghost" onclick="rnCase('tidy')">Tidy spaces</button>
        <button class="ghost" onclick="rnCase('unnumber')">Drop leading number</button>
      </div>
    </div>
  </div>`;

  if (picked) h += `<div class="note rnscope">${esc(say("rnTicked", {n: picked}))}</div>`;

  if (RN.error) h += `<div class="fmempty bad">${esc(RN.error)}</div>`;
  else if (RN.busy && !RN.rows.length) h += `<div class="fmempty">reading...</div>`;
  else if (!RN.rows.length) h += `<div class="fmempty">No folders in there.</div>`;
  else {
    h += `<div class="scroll"><table class="rntable"><tr>
      <th><input type="checkbox" onchange="rnTickAll(this.checked)"
        aria-label="Tick every row"></th>
      <th>Name now</th><th>Rename to</th><th>What is wrong</th></tr>`;
    h += RN.rows.map(r => {
      const q = quoted(r.path);
      const why = RN.problems[r.path] || "";
      const edited = RN.names[r.path] !== RN.was[r.path];
      return `<tr class="rnrow${edited ? " edited" : ""}${why ? " bad" : ""}"
          data-p="${esc(r.path)}">
        <td><input type="checkbox" ${r.on ? "checked" : ""}
          onchange="rnTick('${q}', this.checked)" aria-label="Pick ${esc(r.name)}"></td>
        <td class="rnwas" style="padding-left:${6 + 14 * (r.depth || 0)}px">
          <span class="rnic">${icon(r.kind === "folder" ? "folder" : "image")}</span>
          <span class="rnold">${esc(r.name)}</span>
          ${r.holds ? `<span class="note">(${r.holds} inside)</span>` : ""}
          ${r.kind === "folder" ? `<button class="rnin" title="Rename what is
            inside this one instead" onclick="rnInto('${q}')">\u203a</button>` : ""}</td>
        <td><input class="rnbox" value="${esc(RN.names[r.path] || "")}"
          spellcheck="false" aria-label="New name for ${esc(r.name)}"
          oninput="rnType('${q}', this.value)"></td>
        <td class="note rnwhy">${why ? esc(why)
          : edited ? `<button class="ghost" onclick="rnReset('${q}')">put back</button>`
          : ""}</td></tr>`;
    }).join("") + `</table></div>`;
    if (RN.capped) h += `<div class="note">The first ${RN.rows.length} only -
      go a level shallower, or start further in.</div>`;
  }

  h += `<div class="rnbar">
    <span class="note" id="rnfoot"></span>
    <button ${changed && !bad && !RN.busy ? "" : "disabled"} onclick="rnApply()"
      >Rename ${changed || ""}</button>
  </div></div>`;
  box.innerHTML = h;
  rnFoot();
}

function rnFoot(){
  const foot = document.getElementById("rnfoot");
  if (!foot) return;
  const changed = rnChanged().length;
  const bad = RN.rows.filter(r => RN.problems[r.path]).length;
  foot.textContent = !changed ? S.rnNothing
    : bad ? say("rnSome", {changed, bad})
    : `${changed} ready. Nothing has been written.`;
  const go = foot.parentElement && foot.parentElement.querySelector("button");
  if (go) go.disabled = !changed || !!bad || RN.busy;
}

/* The paths a search found, held here rather than written into the buttons:
   six thousand paths serialised into two onclick attributes was half a
   megabyte of HTML the browser had to parse before the card could be read. */
let FOUND = [];

function foundCard(p){
  /* What a list of matches is FOR. Looking through them is the viewer, which
     the thumbnails above already do; the other half is doing something to the
     set - and that is the file manager, so the set goes there whole rather
     than being written down and typed in again. */
  FOUND = p.rows.map(r => r.source).filter(Boolean);
  const paths = FOUND;
  return `<div class="card">
    <b>${num(paths.length)} found</b>
    <span class="note">- and nothing has been written</span>
    <div class="act" style="margin-top:10px">
      <button class="ghost" onclick="foundToFiles(FOUND)"
        >${icon("folder")} Send these to Files</button>
      <button class="ghost" onclick="peekFound(FOUND.filter(x => SHOWABLE.test(x)))"
        >${icon("grid")} Look through them</button>
      ${typeof showInPhotosButton === "function" ? showInPhotosButton() : ""}
    </div>
    <div class="note" style="margin-top:8px">In Files they arrive as one
      listing, whatever folders they are in - copy, move, download and delete
      all work on exactly that set.</div>
  </div>`;
}

function peekFound(paths){
  if (!paths.length){ toast("None of those can be shown", 3000); return; }
  peek(paths[0], paths);
}

/* ---------------------------------------------------------------- the charts

   Drawn here, in SVG, from numbers the plan already worked out - no library,
   nothing fetched, and they survive the app being offline on a phone.

   Three shapes and no more, each picked by what the numbers are FOR:

   * a stat tile for a headline number, because a one-bar bar chart is not a
     chart;
   * bars for magnitude along one ordered axis, in one hue, more-is-darker -
     the safe default, and hard to misread;
   * a donut for part-to-whole with a handful of slices, in the fixed
     categorical order so a camera keeps its colour whatever else is on screen.

   Every one of them carries its numbers as text as well. Three of the light
   slots sit under 3:1 against white, and a reader who cannot separate two hues
   must still be able to read the chart - so the colour is never the only thing
   saying what a slice is. */

const CHARTC = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];

function num(n){ return (+n || 0).toLocaleString(); }

/* "12 photographs", "1 folder": the one way the page counts things. "(s)" was
   in seventeen places, and it reads as a form rather than as a sentence. */
function count(n, one, many){
  n = +n || 0;
  return `${num(n)} ${n === 1 ? one : (many || one + "s")}`;
}

function clip(text, most){
  /* A label that does not fit is cut, never wrapped: a chart whose rows are
     two lines tall on some names and one on others is a chart with a ragged
     baseline, and the whole name is on the mark's tooltip anyway. */
  text = String(text === undefined || text === null ? "" : text);
  return text.length > most ? text.slice(0, most - 1) + "\u2026" : text;
}

function share(part, whole){
  if (!whole) return "";
  const pct = 100 * part / whole;
  return pct >= 9.5 ? Math.round(pct) + "%"
       : pct >= 0.95 ? pct.toFixed(1) + "%" : "<1%";
}

/* Which charts have been opened out. A chart shows its biggest few and keeps
   the rest folded, because eight is where colours stop being tellable apart -
   but the folded ones are HERE, in the same payload, so opening is instant and
   nothing has to be fetched to find out what "everything else" was. */
const CHARTOPEN = {};

function chartKey(one){ return (one.title || "") + "/" + (one.dim || ""); }

function chartShown(one){
  const rows = one.rows || [];
  const show = one.show || 8;
  if (CHARTOPEN[chartKey(one)] || rows.length <= show)
    return {rows: rows, folded: 0, whole: rows};
  /* The tail keeps its members rather than becoming a number: the fold is a
     row that says how many and, on hover, which. */
  const head = rows.slice(0, show - 1);
  const tail = rows.slice(show - 1);
  const rest = ["everything else", tail.reduce((n, r) => n + r[1], 0),
                tail.reduce((n, r) => n + r[2], 0), {},
                tail.map(r => r[0])];
  return {rows: head.concat([rest]), folded: tail.length, whole: rows};
}

function chartFold(key){
  CHARTOPEN[key] = !CHARTOPEN[key];
  boardsRedraw();
}

function foldButton(one, shown){
  const more = (one.more || 0);
  if (!shown.folded && !CHARTOPEN[chartKey(one)]) return "";
  const key = quoted(chartKey(one));
  return `<button class="ghost cmore" onclick="chartFold('${key}')">${
    CHARTOPEN[chartKey(one)]
      ? "show the biggest few"
      : `show all ${(one.rows || []).length}`}</button>`
    + (more ? `<span class="note"> (${more} more are not counted here)</span>` : "");
}

function rowTip(row, said, whole){
  /* What a mark says on hover: what it is, how many, its share - and, for a
     folded tail, the names inside it, which is the whole complaint about
     "everything else" answered. */
  const inside = row[4] && row[4].length
    ? " \u2014 " + row[4].slice(0, 12).join(", ")
      + (row[4].length > 12 ? `, and ${row[4].length - 12} more` : "")
    : "";
  return `${row[0]}: ${said}${whole ? " \u00b7 " + share(row[1], whole) : ""}${inside}`
    + (row[3] && Object.keys(row[3]).length ? " \u00b7 click to list them"
       : isFold(row) ? " \u00b7 click to show them all" : "");
}

/* A folded tail is many buckets, so no one search lists it. Pressing it opens
   the chart out instead, and every row it held can then be pressed on its own -
   "everything else" that does nothing when pressed reads as a broken row. */
function isFold(row){ return !!(row && row[4] && row[4].length); }

function foldAttr(one, row){
  if (!isFold(row)) return "";
  return ` data-fold="${esc(chartKey(one))}" data-tipnoclick role="button"`
    + ` tabindex="0" title="Show them all"`;
}

document.addEventListener("click", e => {
  const at = e.target.closest ? e.target.closest("[data-fold]") : null;
  if (at) chartFold(at.dataset.fold);
});

/* ---- a bucket, as a search

   The point of a chart of a library is the photographs behind it. Every bucket
   carries the search that means it - worked out where the buckets are defined,
   not guessed here - so pressing "2020" leaves the dashboard and lists those
   files, and pressing "not said" lists the files that do not say. A bucket no
   search can say (a month, a weekday) has no link rather than a link that
   lands somewhere else, and a folded tail opens out so each of its rows can be
   pressed instead. */

function askOf(row){
  return row && row[3] && Object.keys(row[3]).length ? row[3] : null;
}

function searchFor(ask, where){
  if (!ask) return;
  /* The folders the chart counted, carried across. Without this a chart of one
     shoot led to a search of the whole library: the bar said "4 in 2013 in
     Spain" and the table that opened said 60, which makes the chart look wrong
     when it was the search that had quietly widened. */
  const folders = (where && where.length) ? where.join("\n") : "";
  show("search");
  setTimeout(() => {
    if (folders){
      const box = document.getElementById("o_folders");
      if (box){
        box.value = folders;
        box.dispatchEvent(new Event("input"));
        box.dispatchEvent(new Event("change"));
        if (typeof drawChips === "function") drawChips("folders");
      }
    }
    searchFill(ask);
    const go = document.getElementById("go");
    if (go) go.click();
  }, 90);
}

/* The folders the chart on screen counted. On Home that is the index's
   roots - the library and the video tree - and not whatever plan the Library
   tab last drew; a search of the library alone said 5,000 where Home had said
   6,000, because the thousand clips lived in the other tree. */
function chartFolders(){
  if (typeof SCREEN !== "undefined" && SCREEN === "home")
    return (typeof SUMS !== "undefined" && SUMS && SUMS.folders) || [];
  return (PLAN && PLAN.charts && PLAN.charts.folders) || [];
}

function askAttr(row){
  const ask = askOf(row);
  return ask ? ` data-ask="${esc(JSON.stringify(ask))}"` : "";
}

document.addEventListener("click", e => {
  const at = e.target.closest ? e.target.closest("[data-ask]") : null;
  if (!at) return;
  try{
    searchFor(JSON.parse(at.dataset.ask), chartFolders());
  }catch(err){}
});

/* ---- the dashboard, as you arranged it

   Which widgets appear is a list of names kept per arrangement, and Arrange is
   the mode where you edit that list in the place where you can see it. Every
   change saves straight away: a dashboard with an unsaved state is a dashboard
   you have to remember to press something on. */

let ARRANGING = false;

function boardBar(c){
  if (!c || !c.boards || !c.boards.length) return "";
  const many = c.boards.length > 1;
  return `<div class="boardbar">
    ${many ? `<span class="note">Showing</span>
      <select id="boardpick" aria-label="Which arrangement"
        onchange="boardDo({do:'show', board:this.value})">`
      + c.boards.map(n => `<option${n === c.board ? " selected" : ""}
          >${esc(n)}</option>`).join("") + `</select>` : ""}
    <button type="button" id="boardarrange" class="ghost${ARRANGING ? " on" : ""}"
      onclick="arrangeToggle()">${icon("grid")}
      <span>${ARRANGING ? "Done arranging" : "Arrange"}</span></button>
    ${ARRANGING ? `<button type="button" class="ghost" onclick="boardAdd()"
        >${icon("copy")}<span>Copy to a new one</span></button>
      <button type="button" class="ghost" onclick="boardDo({do:'reset'})"
        >${icon("again")}<span>Put it back as it was</span></button>` : ""}
  </div>`;
}

/* Whatever is on screen. The dashboard is on two screens now - Home, counted
   from the index, and the Library tab, which has a plan - and the arranging
   only knew about the second. On Home it re-rendered a plan that was not
   there, into a panel that was not on screen, and then asked a "Show me what
   would happen" button that does not exist there to press itself. So every
   button on the Arrange bar did nothing at all. */
function boardsRedraw(){
  if (typeof SCREEN !== "undefined" && SCREEN === "home"){
    SUMS = null;
    if (typeof drawHomeScreen === "function") return drawHomeScreen();
  }
  const go = document.getElementById("go");
  if (go) return go.click();
  if (PLAN) render(PLAN);
}

function arrangeToggle(){
  ARRANGING = !ARRANGING;
  if (typeof SCREEN !== "undefined" && SCREEN === "home"){
    SUMS = null;
    drawHomeScreen();
  } else if (PLAN) render(PLAN);
  if (ARRANGING) toast(S.arrangeTip, 4000);
}

async function boardDo(body){
  try{
    const r = await fetch("api/boards", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)});
    const got = await r.json();
    if (got.error){ toast(got.error, 5000); return; }
    boardsRedraw();                               // read it again, new shape
  }catch(e){ toast("that did not reach the app", 4000); }
}

async function boardAdd(){
  const name = await fmAsk({title: "What should this arrangement be called?",
                            value: "", yes: "Make it"});
  if (!name) return;
  boardDo({do: "add", name: name, like: (PLAN.charts || {}).board || ""});
}

function boardNames(){
  /* The list the server is told, in the order it is drawn. Read back off the
     page rather than kept in a variable, so what is saved is what you can see -
     there is no second copy of the order to fall out of step. */
  return [...document.querySelectorAll("[data-widget]")]
    .map(el => el.dataset.widget).filter(Boolean);
}

const wkind = name => String(name || "").split(":")[0];

function widgetMove(name, by){
  /* Within its own kind. The tiles are drawn in a row, the meters under them
     and the charts in a grid below, so moving a chart "above" the last meter
     would change the saved list and change nothing you can see - an arrow that
     appears to do nothing is worse than no arrow. */
  const on = boardNames();
  const mine = on.filter(n => wkind(n) === wkind(name));
  const at = mine.indexOf(name);
  if (at < 0 || at + by < 0 || at + by >= mine.length) return;
  const swap = mine[at + by];
  const i = on.indexOf(name), j = on.indexOf(swap);
  on[i] = swap; on[j] = name;
  boardDo({do: "keep", widgets: on});
}

function widgetEnds(name){
  /* Whether this one is already first or last of its kind, so the arrow that
     cannot go anywhere is shown as unavailable rather than silently ignored. */
  const mine = boardNames().filter(n => wkind(n) === wkind(name));
  const at = mine.indexOf(name);
  return [at <= 0, at < 0 || at >= mine.length - 1];
}

function widgetOff(name){
  boardDo({do: "keep", widgets: boardNames().filter(n => n !== name)});
}

function widgetOn(name){
  boardDo({do: "keep", widgets: boardNames().concat([name])});
}

function widgetTools(name, title){
  if (!ARRANGING || !name) return "";
  return `<div class="wtools" role="group" aria-label="Arrange ${esc(title || "")}">
    <button type="button" class="wbtn wup" title="Earlier"
      onclick="widgetMove('${quoted(name)}',-1)">\u2191</button>
    <button type="button" class="wbtn wdown" title="Later"
      onclick="widgetMove('${quoted(name)}',1)">\u2193</button>
    <button type="button" class="wbtn wdrop" title="Take it off the dashboard"
      onclick="widgetOff('${quoted(name)}')">\u00d7</button></div>`;
}

function arrangeEnds(){
  // after the page is drawn, because it counts what is on it
  if (!ARRANGING) return;
  document.querySelectorAll("[data-widget]").forEach(el => {
    const [first, last] = widgetEnds(el.dataset.widget);
    const up = el.querySelector(".wup"), down = el.querySelector(".wdown");
    if (up) up.disabled = first;
    if (down) down.disabled = last;
  });
}

function addWidgets(c){
  /* What is NOT on it. A dashboard editor that only lets you remove things is
     an editor you can only make worse with. */
  const off = (c.widgets || []).filter(w => !w.on);
  if (!ARRANGING) return "";
  if (!off.length) return `<div class="card"><b>Everything is on this one</b>
    <div class="note">There is nothing left to add.</div></div>`;
  return `<div class="card"><b>Not on this arrangement</b>
    <span class="note">- ${off.length} more to choose from</span>
    <div class="offlist">` + off.map(w =>
      `<button type="button" class="offw" onclick="widgetOn('${quoted(w.name)}')"
        data-tip="${esc(w.about || w.title)}">
        <span class="offplus">+</span>
        <span class="offname">${esc(w.title)}</span>
        <span class="offkind">${esc(w.kind)}</span></button>`).join("")
    + `</div></div>`;
}

function chartsCard(p){
  const c = p.charts || {};
  let h = boardBar(c);
  if (c.tiles && c.tiles.length){
    h += `<div class="card${ARRANGING ? " arranging" : ""}">
      <b>The library at a glance</b>
      <div class="tiles">` + c.tiles.map(t =>
        `<div class="tile2" data-widget="${esc(t.widget || "")}">
          ${widgetTools(t.widget, t.label)}
          <div class="tval">${esc(t.value)}</div>
          <div class="tlab">${esc(t.label)}</div>
          <div class="tnote" title="${esc(t.note || "")}">${esc(t.note || "")}</div>
        </div>`).join("") + `</div>`;
    if (c.done && c.done.length) h += metersHtml(c.done);
    h += `</div>`;
  } else if (c.done && c.done.length){
    h += `<div class="card${ARRANGING ? " arranging" : ""}">` + metersHtml(c.done)
      + `</div>`;
  }
  if (c.cross) h += heatCard(c.cross);
  if (c.charts && c.charts.length){
    h += `<div class="card${ARRANGING ? " arranging" : ""}">
      <b>${c.cross ? "Each on its own" : "What is in it"}</b>
      <div class="charts">`
      + c.charts.map(one => (one.kind === "donut" ? donutHtml(one) : barsHtml(one)))
        .join("")
      + `</div></div>`;
  }
  h += addWidgets(c);
  if (ARRANGING) setTimeout(arrangeEnds, 0);
  return h;
}

function metersHtml(done){
  /* How far along each job is, against the same track - a share of a whole is
     a meter, not a pie of two slices. */
  return `<div class="meters">` + done.map(([label, part, whole, widget]) => {
    const pct = whole ? Math.max(0, Math.min(100, 100 * part / whole)) : 0;
    return `<div class="meter" data-widget="${esc(widget || "")}"
      data-tip="${esc(label)}: ${num(part)} of ${num(whole)}">
      ${widgetTools(widget, label)}
      <div class="mtop"><span>${esc(label)}</span>
        <b>${share(part, whole) || "-"} <span class="note">${num(part)}/${num(whole)}</span></b></div>
      <div class="mtrack"><i class="mfill" style="width:${pct.toFixed(1)}%"></i></div>
    </div>`;
  }).join("") + `</div>`;
}

function barsHtml(one){
  /* Plain HTML rather than SVG. An SVG scaled to the width of its card scales
     its type with it, so the same chart had 40px numbers beside 11px labels
     depending on how wide the column happened to be. Divs do not do that.

     Horizontal, because the labels are words - "f/16 and smaller" turned on its
     side is a chart nobody reads. One hue, and the number printed at the end of
     every bar rather than an axis to measure against. */
  const shown = chartShown(one);
  const rows = shown.rows;
  const bytes = one.unit === "bytes";
  const most = Math.max(1, ...rows.map(r => bytes ? r[2] : r[1]));
  const whole = shown.whole.reduce((n, r) => n + (bytes ? r[2] : r[1]), 0);
  const body = rows.map(r => {
    const value = bytes ? r[2] : r[1];
    const said = bytes ? fmSize(value) : num(value);
    const ask = askOf(r);
    return `<div class="brow${ask || isFold(r) ? " go" : ""}"${askAttr(r)}${foldAttr(one, r)}
      data-tip="${esc(rowTip(r, said, whole))}"
      ${ask ? `role="button" tabindex="0" title="List these in Search"` : ""}>
      <span class="blab">${esc(clip(r[0], 20))}</span>
      <span class="btrack"><i class="bfill" style="width:${
        (100 * value / most).toFixed(1)}%"></i></span>
      <b class="bval">${esc(said)}</b></div>`;
  }).join("");
  return `<div class="chart" data-widget="${esc(one.widget || "")}">${widgetTools(one.widget, one.title)}<h4>${esc(one.title)}</h4>
    ${one.note ? `<div class="cnote">${esc(one.note)}</div>` : ""}
    <div class="bars">${body}</div>
    ${foldButton(one, shown)}</div>`;
}

function donutHtml(one){
  /* Part-to-whole, with the slices in the fixed colour order and a legend that
     carries the numbers. Capped before it gets here: past eight slices the
     ninth colour is one a colour-blind reader cannot tell from an earlier one,
     so the tail arrives already folded into "everything else". */
  const shown = chartShown(one);
  /* Opened out, a donut becomes bars: past eight slices the ninth colour is one
     a colour-blind reader cannot tell from an earlier one, so "show all" is a
     change of form rather than more hues. */
  if (CHARTOPEN[chartKey(one)] && shown.rows.length > 8) return barsHtml(one);
  const rows = shown.rows.slice(0, 8);
  const bytes = one.unit === "bytes";
  const whole = rows.reduce((n, r) => n + (bytes ? r[2] : r[1]), 0) || 1;
  const R = 42, r0 = 26, C = 50;
  let at = -Math.PI / 2;
  /* One slice is the whole ring, and an arc whose start and end are the same
     point draws nothing at all - which is why a library with one camera in it
     had a legend and an empty hole where the chart should be. A circle with a
     thick stroke IS that ring. */
  const only = rows.length === 1 && !(one.more || 0) ? rows[0] : null;
  if (only){
    const value = bytes ? only[2] : only[1];
    return `<div class="chart" data-widget="${esc(one.widget || "")}">${widgetTools(one.widget, one.title)}<h4>${esc(one.title)}</h4>
      ${one.note ? `<div class="cnote">${esc(one.note)}</div>` : ""}
      <svg viewBox="0 0 100 100" style="max-width:190px;margin:0 auto"
        role="img" aria-label="${esc(one.title)}">
        <circle cx="50" cy="50" r="${(R + r0) / 2}" fill="none"
          stroke="var(${CHARTC[0]})" stroke-width="${R - r0}"
          data-tip="${esc(only[0])}: ${esc(bytes ? fmSize(value) : num(value))} \u00b7 all of it"/>
        <text class="cvalue" x="50" y="50" text-anchor="middle"
          style="font-size:9px">${esc(bytes ? fmSize(value) : num(value))}</text>
        <text class="ctext" x="50" y="59" text-anchor="middle"
          style="font-size:6px">${esc(bytes ? "in all" : (one.unit || "photos"))}</text>
      </svg>
      <div class="clegend"><span title="${esc(only[0])}"><i class="cdotc"
        style="background:var(${CHARTC[0]})"></i>
        ${esc(clip(only[0], 18))} <b>${esc(bytes ? fmSize(value) : num(value))}</b>
        <span class="cshare">all of them</span></span></div>
      ${foldButton(one, shown)}</div>`;
  }
  const arcs = rows.map((row, i) => {
    const value = bytes ? row[2] : row[1];
    let sweep = 2 * Math.PI * value / whole;
    if (sweep <= 0) return "";
    // a 2px gap between neighbours, so two slices never melt into one shape
    const gap = rows.length > 1 ? Math.min(0.06, sweep / 4) : 0;
    const a = at + gap / 2, b = at + sweep - gap / 2;
    at += sweep;
    const big = (b - a) > Math.PI ? 1 : 0;
    const pt = (rad, radius) => [C + radius * Math.cos(rad), C + radius * Math.sin(rad)];
    const [x1, y1] = pt(a, R), [x2, y2] = pt(b, R);
    const [x3, y3] = pt(b, r0), [x4, y4] = pt(a, r0);
    return `<path class="cbar${askOf(row) || isFold(row) ? " go" : ""}"
      fill="var(${CHARTC[i % 8]})"${askAttr(row)}${foldAttr(one, row)}
      data-tip="${esc(rowTip(row, bytes ? fmSize(value) : num(value), whole))}"
      d="M${x1.toFixed(2)} ${y1.toFixed(2)} A${R} ${R} 0 ${big} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}
         L${x3.toFixed(2)} ${y3.toFixed(2)} A${r0} ${r0} 0 ${big} 0 ${x4.toFixed(2)} ${y4.toFixed(2)} Z"/>`;
  }).join("");
  const middle = bytes ? fmSize(whole) : num(whole);
  const under = bytes ? "in all" : (one.unit || "photos");
  return `<div class="chart" data-widget="${esc(one.widget || "")}">${widgetTools(one.widget, one.title)}<h4>${esc(one.title)}</h4>
    ${one.note ? `<div class="cnote">${esc(one.note)}</div>` : ""}
    <svg viewBox="0 0 100 100" style="max-width:190px;margin:0 auto"
      role="img" aria-label="${esc(one.title)}">${arcs}
      <text class="cvalue" x="50" y="50" text-anchor="middle"
        style="font-size:9px">${esc(middle)}</text>
      <text class="ctext" x="50" y="59" text-anchor="middle"
        style="font-size:6px">${esc(under)}</text></svg>
    <div class="clegend">` + rows.map((row, i) => {
      const value = bytes ? row[2] : row[1];
      return `<span class="${askOf(row) || isFold(row) ? "go" : ""}"${askAttr(row)}${foldAttr(one, row)}
        data-tip="${esc(rowTip(row, bytes ? fmSize(value) : num(value), whole))}"
        ><i class="cdotc" style="background:var(${CHARTC[i % 8]})"></i>
        ${esc(clip(row[0], 18))} <b>${esc(bytes ? fmSize(value) : num(value))}</b>
        <span class="cshare">${share(value, whole)}</span></span>`;
    }).join("") + `</div>
    ${foldButton(one, shown)}</div>`;
}

function heatCard(cross){
  /* Two axes at once. One hue, light to dark, because the thing being read is
     magnitude - and the numbers are printed in the cells as well, so the shade
     is a way of seeing the shape rather than the only way of reading it. */
  const grid = cross.grid || [];
  const most = cross.most || Math.max(1, ...grid.map(r => Math.max(...r)));
  const step = v => {
    if (!v) return "zero";
    const n = Math.min(7, Math.max(1, Math.ceil(7 * v / most)));
    return "q" + n;
  };
  let h = `<div class="card"><b>${esc(cross.down_label)} against ${
    esc(cross.across_label)}</b>
    <span class="note">- ${esc(S.crossEach)}</span>
    <div class="heatwrap" style="margin-top:10px"><table class="heat">
      <tr><th></th>` + (cross.cols || []).map(c =>
        `<th title="${esc(c)}">${esc(clip(c, 12))}</th>`).join("") + `</tr>`;
  (cross.rows || []).forEach((name, i) => {
    h += `<tr><th class="down" title="${esc(name)}">${esc(clip(name, 18))}</th>`
      + (grid[i] || []).map((v, j) => {
        const cls = step(v);
        const dark = cls !== "zero" && +cls.slice(1) >= 5;
        /* A cell is both edges at once, so it lists exactly the photographs it
           drew - the two searches merged, and no link at all when either edge
           is something Search has no box for. */
        const a = (cross.row_asks || [])[i], b2 = (cross.col_asks || [])[j];
        const both = v && a && b2 && Object.keys(a).length && Object.keys(b2).length
          ? Object.assign({}, a, b2) : null;
        /* Both edges "not said" is both facts missing, not the second one
           written over the first. */
        if (both && a.missing && b2.missing && a.missing !== b2.missing)
          both.missing = a.missing + "," + b2.missing;
        return `<td><span class="cell ${cls === "zero" ? "zero" : ""}${dark ? " on" : ""}${
            both ? " go" : ""}"
          style="${cls === "zero" ? "" : `background:var(--${cls})`}"
          ${both ? `data-ask="${esc(JSON.stringify(both))}"` : ""}
          data-tip="${esc(name)} \u00b7 ${esc(cross.cols[j])}: ${num(v)}${
            both ? " \u00b7 click to list them" : ""}"
          >${v ? num(v) : "\u00b7"}</span></td>`;
      }).join("") + `</tr>`;
  });
  h += `</table></div>
    <div class="heatkey">fewer
      ${[1, 2, 3, 4, 5, 6, 7].map(n => `<i style="background:var(--q${n})"></i>`).join("")}
      more <span style="margin-left:8px">- ${num(most)} in the busiest cell</span>
    </div></div>`;
  return h;
}

/* Charts say what a mark is through the same `data-tip` the rest of the page
   uses. There used to be a second engine here, bound to the same attribute, so
   every bar and slice opened TWO bubbles at once - one beside the pointer and
   one under the mark. One engine, one bubble. */

/* ------------------------------------------------------- what a camera is called

   A phone writes an order code - `SM-G991B`, `iPhone14,2` - and three phones in
   a library make a chart legend nobody can read. So every camera the library
   contains gets a box, and what you type in it is what the app calls that
   camera everywhere afterwards.

   It is a display name. Nothing is written to a photograph, the code in the
   file is untouched, and a search by either the code or the name finds the
   same photographs. */

function startCameras(){
  const box = document.getElementById("camerabar");
  if (box) box.innerHTML = `<div class="kept">
    <b>Camera names</b>
    <span class="note">Press "Check the list" to name the cameras in your library,
      then type what you call each one. Saved as you type.</span></div>`;
}

function camerasCard(p){
  return `<div class="card"><b>Cameras in the library</b>
    <span class="note">- what the file says, and what you call it</span>
    <div class="scroll" style="margin-top:10px"><table>
      <tr><th>What the file says</th><th>Called</th><th>Where the name
        came from</th><th class="num">Photos</th></tr>`
    /* From the row's own columns, not from anything extra the plan attached:
       what a plan hands the page is name and cells, and a card that needs more
       than that is a card that breaks the day the plan is trimmed. */
    + p.rows.map(r => {
      const code = r.name || "";
      const q = quoted(code);
      return `<tr><td><code>${esc(code)}</code></td>
        <td><input class="camname" value="${esc(r.cells[0] || "")}"
          data-model="${esc(code)}" spellcheck="false"
          aria-label="What ${esc(code)} is called"
          onchange="cameraName('${q}', this.value, this)"></td>
        <td class="note camhow">${esc(r.cells[1] || "")}</td>
        <td class="num">${esc(r.cells[2] || "")}</td></tr>`;
    }).join("")
    + `</table></div>
    <div class="note" style="margin-top:8px">Emptying a box puts the code back.
      A guess comes from a short table inside this app - it is far from
      complete and it can be wrong, which is why the code stays beside it.</div>
    </div>`;
}

/* ------------------------------------------------- where the brackets fall

   A set of bands is a small table, and the honest way to edit a small table is
   to show it as text. Refused whole or kept whole: half a table would put
   photographs in the wrong bracket and the chart would still look reasonable,
   which is the worst way to be wrong. */

function bandsCard(p){
  const sets = ((p.data || {}).sets) || [];
  if (!sets.length) return "";
  return `<div class="card"><b>Where the brackets fall</b>
    <span class="note">- one band per line, written 'name = up to'</span>
    <div class="bandsets" style="margin-top:10px">` + sets.map(one => `
      <div class="bandset" data-set="${esc(one.set)}">
        <h4>${esc(one.title)}</h4>
        <div class="bandhow">${esc(one.unit)} \u00b7 <span class="bhow">${
          one.how === "yours" ? "you set these" : "as this app comes"}</span></div>
        <div class="note" style="margin-top:4px">${esc(one.about)}</div>
        <textarea spellcheck="false" aria-label="${esc(one.title)} bands"
          >${esc(one.text)}</textarea>
        <div class="bandacts">
          <button type="button" onclick="bandsSave('${quoted(one.set)}', this)"
            >Keep these</button>
          <button type="button" class="ghost"
            onclick="bandsReset('${quoted(one.set)}', this)">Put the built-in ones back</button>
          <span class="bandwhy"></span>
        </div>
      </div>`).join("") + `</div>
    <div class="note" style="margin-top:10px">A value belongs to the first band
      whose number it is under, so the numbers have to climb. The last line
      catches everything above it, whichever number is against it. Shutter speeds
      may be written as fractions.</div>
    <div class="note">${esc(S.bandsNote)}</div>
  </div>`;
}

async function bandsSend(set, box, body){
  const why = box.closest(".bandset").querySelector(".bandwhy");
  try{
    const r = await fetch("api/bands", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign({set: set}, body))});
    const got = await r.json();
    if (got.error){ why.className = "bandwhy"; why.textContent = got.error; return; }
    const card = box.closest(".bandset");
    card.querySelector("textarea").value = got.text;
    card.querySelector(".bhow").textContent =
      got.how === "yours" ? "you set these" : "as this app comes";
    why.className = "bandwhy good";
    why.textContent = S.bandsKept;
  }catch(e){ why.className = "bandwhy"; why.textContent = "that did not reach the app"; }
}

function bandsSave(set, box){
  bandsSend(set, box, {text: box.closest(".bandset").querySelector("textarea").value});
}

function bandsReset(set, box){ bandsSend(set, box, {reset: true}); }

/* ------------------------------------------- the dashboard arrangements

   Named here, arranged on the Library itself - which is the only place you can
   see what an arrangement actually looks like. */

function boardsCard(p){
  const d = p.data || {};
  const each = d.each || [];
  if (!each.length) return "";
  return `<div class="card"><b>Arrangements of the Library dashboard</b>
    <span class="note">- ${each.length} of them</span>
    <div style="margin-top:8px">` + each.map(one => `
      <div class="brdrow">
        <span class="brdname">${esc(one.board)}</span>
        ${one.now ? `<span class="brdnow">showing now</span>` : ""}
        <span class="brdwhat">${esc((one.widgets || []).join(", ") || "nothing on it")}</span>
        ${one.now ? "" : `<button type="button" class="ghost"
          onclick="boardsDo({do:'show', board:'${quoted(one.board)}'})">Show this one</button>`}
        <button type="button" class="ghost"
          onclick="boardsCopy('${quoted(one.board)}')">Copy</button>
        ${one.builtin ? `<button type="button" class="ghost"
            onclick="boardsDo({do:'reset', board:'${quoted(one.board)}'})"
            >Put it back</button>`
          : `<button type="button" class="ghost"
              onclick="boardsRename('${quoted(one.board)}')">Rename</button>
            <button type="button" class="ghost"
              onclick="boardsDrop('${quoted(one.board)}')">Delete</button>`}
      </div>`).join("") + `</div>
    <div class="note" style="margin-top:10px">Open the Library and press
      <b>Arrange</b> to choose what is on one. Whatever you do there is saved
      into the arrangement that is showing.</div>
  </div>`;
}

async function boardsDo(body){
  try{
    const r = await fetch("api/boards", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)});
    const got = await r.json();
    if (got.error){ toast(got.error, 5000); return; }
    document.getElementById("go").click();
  }catch(e){ toast("that did not reach the app", 4000); }
}

async function boardsCopy(from){
  const name = await fmAsk({title: "What should the copy be called?",
                            value: from + " (copy)", yes: "Copy it"});
  if (name) boardsDo({do: "add", name: name, like: from});
}

async function boardsRename(was){
  const name = await fmAsk({title: "Call it what?", value: was, yes: "Rename"});
  if (name && name !== was) boardsDo({do: "rename", board: was, name: name});
}

async function boardsDrop(name){
  const yes = await askSure({title: `Delete the arrangement "${name}"?`,
    body: S.homeResetBody,
    yes: "Delete it"});
  if (yes) boardsDo({do: "drop", board: name});
}

async function cameraName(model, name, box){
  try{
    const r = await fetch("api/cameras", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({model: model, name: name})});
    const got = await r.json();
    if (got.error){ toast(got.error, 5000); return; }
    const cell = box.closest("tr").querySelector(".camhow");
    if (cell) cell.textContent = got.how === "yours" ? "you named it"
      : got.how === "guessed" ? "a guess by this app" : "the code itself";
    if (!name && box) box.value = got.label.replace(/\s*\(.*\)$/, "");
    toast(name ? `Called ${name} from now on` : "Back to the code", 2500);
  }catch(e){ toast("that did not reach the app", 4000); }
}

/* ------------------------------------------------- searches kept by name

   A search is eight boxes on a good day - "wide, on the GH4, with no location"
   is three of them and a tick - and retyping that every month is how a feature
   gets used twice and then forgotten. So a search can be kept by name and comes
   back by pressing it.

   Pressing one FILLS THE BOXES rather than running something of its own. What
   runs is always what the form says: a saved search that ran from somewhere
   else, while the form on screen said something different, would be a bug
   nobody could see. */

let KEPTSEARCH = [];

const SEARCHKEYS = ["kinds", "name", "since", "until", "camera", "lens",
  "focal_from", "focal_to", "focal35", "f_from", "f_to", "iso_from", "iso_to",
  "faster_than", "slower_than", "stars_from", "stars_to", "colour", "tags",
  "all_tags", "located", "missing"];

/* ---- the boxes that should have been lists

   Typing a camera's name from memory is how you search a library that says
   `DMC-GH4` for `GH5`, get nothing, and conclude there is nothing there. So
   the boxes that hold a NAME - camera, lens, tag - carry a picker beside them
   that asks the library what it actually contains, spelled its way, with how
   many of each. Still a text box, because a part of a name is a perfectly good
   search and a list of forty lenses is not something to scroll on a phone. */

const PICKABLE = [["camera", "Camera"], ["lens", "Lens"], ["tag", "Tag"]];
const PICKED = {};

function searchPickers(){
  for (const [dim, label] of PICKABLE){
    const box = document.getElementById("o_" + (dim === "tag" ? "tags" : dim));
    if (!box || box.dataset.picker) continue;
    box.dataset.picker = "1";
    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "ghost pickbtn";
    pick.title = `What ${label.toLowerCase()}s are in the library`;
    pick.innerHTML = `${icon("find")} Pick \u25be`;
    pick.onclick = ev => pickValues(dim, box, ev);
    const row = document.createElement("div");
    row.className = "pickrow";
    box.parentNode.insertBefore(row, box);
    row.appendChild(box);
    row.appendChild(pick);
  }
}

async function pickValues(dim, box, ev){
  ev.preventDefault();
  ev.stopPropagation();
  /* Kept before the await. `currentTarget` is null once the event has been
     handed back, so anchoring after the fetch put the menu against whichever
     glyph inside the button happened to be tapped - or against nothing. */
  const from = {currentTarget: ev.currentTarget || ev.target};
  if (!PICKED[dim]){
    toast("Reading what is in the library...", 1800);
    let url = "api/values?dim=" + encodeURIComponent(dim);
    const where = document.getElementById("o_folders");
    if (where && where.value.trim())
      for (const line of where.value.split("\n"))
        if (line.trim()) url += "&path=" + encodeURIComponent(line.trim());
    try{
      const got = await (await fetch(url)).json();
      if (got.error){ toast(got.error, 5000); return; }
      PICKED[dim] = got.values || [];
    }catch(e){ toast("that could not be read", 4000); return; }
  }
  const values = PICKED[dim];
  if (!values.length){ toast("Nothing in the library says one", 3500); return; }
  fmMenu(from, values.slice(0, 60).map(v =>
    `<button type="button" class="vopt" data-w="${esc(v.name)}">
       <span class="vgrow">${esc(v.name)}</span>
       <span class="vdim">${num(v.photos)}</span></button>`).join("")
    + (values.length > 60
       ? `<div class="mnote">${esc(say("moreValues", {n: values.length - 60}))}</div>`
       : ""),
    b => {
      /* Tags add up rather than replace: "street, night" is a real search and
         picking the second one should not throw the first away. */
      /* The menu shows "Lumix GH5 (DC-GH5)" so you can see which body it is;
         the box gets the name alone, because the whole label is neither the
         code in the file nor the name, and would match nothing. */
      const picked = String(b.dataset.w).replace(/\s*\([^()]*\)\s*$/, "").trim()
        || b.dataset.w;
      if (dim === "tag" && box.value.trim())
        box.value = box.value.trim().replace(/,\s*$/, "") + ", " + picked;
      else box.value = picked;
      box.dispatchEvent(new Event("input"));
      box.focus();
    });
}

async function startSearch(){
  drawSearchBar();
  searchPickers();
  try{
    const got = await (await fetch("api/searches")).json();
    KEPTSEARCH = got.kept || [];
  }catch(e){ KEPTSEARCH = []; }
  drawSearchBar();
}

function searchNow(){
  /* What the boxes say, as a search. Flags come back as booleans, everything
     else as the text typed - the server settles the shapes, in one place. */
  const out = {};
  for (const key of SEARCHKEYS){
    const el = document.getElementById("o_" + key);
    if (!el) continue;
    if (el.type === "checkbox"){ if (el.checked) out[key] = true; }
    else if (String(el.value || "").trim()) out[key] = el.value.trim();
  }
  return out;
}

function searchFill(ask){
  for (const key of SEARCHKEYS){
    const el = document.getElementById("o_" + key);
    if (!el) continue;
    const value = (ask || {})[key];
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value === undefined || value === null ? "" : String(value);
    el.dispatchEvent(new Event("input"));
    el.dispatchEvent(new Event("change"));
  }
  /* Whatever this filled in has to be on screen, not behind a folded heading:
     a search that says "3 set" and shows you nothing is a search you cannot
     check before you run it. */
  foldSettle();
  toast(S.filledIn, 2600);
}

function drawSearchBar(){
  const box = document.getElementById("searchbar");
  if (!box) return;
  box.innerHTML = `<div class="kept">
    <b>Kept searches</b>
    ${KEPTSEARCH.length
      ? KEPTSEARCH.map(k => `<span class="keptone">
          <button type="button" class="ghost" onclick="searchFill(${
            esc(JSON.stringify(k.ask)).replace(/"/g, "&quot;")})"
            title="${esc(searchWords(k.ask))}">${esc(k.name)}</button>
          <button type="button" class="keptx" title="Forget this one"
            onclick="searchForget('${quoted(k.name)}')"
            >\u00d7</button></span>`).join("")
      : `<span class="note">${esc(S.searchesNone)}</span>`}
    <button type="button" class="ghost keptadd" onclick="searchKeep()"
      >${icon("check")} Keep what is below</button>
  </div>
  <div class="note" id="searchreads">${esc(READS_INDEX)}</div>`;
}

function searchWords(ask){
  const out = [];
  for (const [k, v] of Object.entries(ask || {}))
    out.push(`${k.replace(/_/g, " ")}: ${v === true ? "yes" : v}`);
  return out.join(", ") || "everything";
}

async function searchKeep(){
  const ask = searchNow();
  if (!Object.keys(ask).length){
    toast("Fill in at least one box first", 3000);
    return;
  }
  const name = await fmAsk({title: "Keep this search as", value: "",
                            yes: "Keep it"});
  if (!name) return;
  const got = await searchSend({name: name, ask: ask});
  if (got) toast(`Kept as ${name}`, 2500);
}

async function searchForget(name){
  await searchSend({forget: name});
}

async function searchSend(body){
  try{
    const r = await fetch("api/searches", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const got = await r.json();
    if (got.error){ toast(got.error, 5000); return null; }
    KEPTSEARCH = got.kept || [];
    drawSearchBar();
    return got;
  }catch(e){ toast("that did not reach the app", 4000); return null; }
}

/* ---- and what the matches can be handed to

   The manager is built around one folder at a time, which is the right shape
   for moving things about and the wrong shape for "these forty, wherever they
   are". So a search can hand it a SET: the same rows, the same buttons, and no
   folder above them. */

async function foundToFiles(paths){
  if (!paths.length){ toast("Nothing to send", 2500); return; }
  show("files");
  await fmShowFound(paths);
}

/* The set claims the pane the way a folder read does (`fmGo`): with a number,
   so that whichever read answers last cannot win if it was asked first.
   Opening the Files tab starts a read of the library folder, and this used to
   land on top of it with no number of its own - so on a big library the
   folder came back a second later, replaced the matches, and the six thousand
   you had searched for became every photograph you own. */
async function fmShowFound(paths){
  const pane = FM.panes[FM.at];
  const mine = pane.asked = ++FMASK;
  pane.busy = true; drawFiles();
  try{
    const r = await fetch("api/files-of", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({paths: paths})});
    const got = await r.json();
    if (pane.asked !== mine) return;          // something newer is on its way
    if (got.error){ pane.error = got.error; }
    else {
      pane.error = ""; pane.data = got; pane.path = ""; pane.sel = [];
      pane.found = paths.slice(); pane.status = null; pane.marks = null;
      pane.shown = 0;
      pane.read = Date.now();
      if (got.missing) toast(`${got.missing} of them are not there any more`, 5000);
    }
  }catch(e){
    if (pane.asked !== mine) return;
    pane.error = "those files could not be read";
  }
  pane.busy = false;
  drawFiles();
}

/* ------------------------------------------------------------- the flow editor */

/* A flow is a variable number of steps, each carrying the settings of a
   different feature, so it cannot be a list of options declared once at import
   time the way every other form here is. This is the one hand-written editor in
   the app, and it earns that by being the thing the user asked for: pick a
   feature from a dropdown, then another, then configure each one.

   Everything it draws still comes from the same `describe()` the generic form
   uses, so a feature gains a new option and it appears here too. */

let FLOWS = null;
let FLOWCAT = [];
let FLOWMETA = {fired_by: [], do: []};
let FLOWOPEN = {};          // which steps are expanded, by step id

async function loadFlows(){
  try{
    const got = await (await fetch("api/flows?t=" + Date.now(),
                                   {cache: "no-store"})).json();
    FLOWS = got.flows || [];
    FLOWCAT = got.catalogue || [];
    FLOWMETA = {fired_by: got.fired_by || [], do: got.do || []};
  }catch(e){ FLOWS = []; }
  drawFlows();
}

function flowSaid(text, bad){
  const el = document.getElementById("flowsaid");
  if (el){ el.textContent = text || ""; el.classList.toggle("bad", !!bad); }
}

async function saveFlows(){
  flowSaid("saving...");
  let got = {};
  try{
    const r = await fetch("api/flows", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({flows: FLOWS})});
    got = await r.json();
  }catch(e){ got = {error: String(e)}; }
  if (got.saved){
    FLOWS = got.flows || FLOWS;
    flowSaid("Saved.");
    drawFlows();
    /* The Automation tab's dropdown is built from the flows, so it has to be
       re-read - otherwise a flow you just made is not there to choose. */
    await refreshTasks();
  } else {
    flowSaid(got.error || "Could not save.", true);
  }
}

function drawFlows(){
  const box = document.getElementById("flowedit");
  if (!box) return;
  if (!FLOWS){ box.innerHTML = `<div class="card note">reading...</div>`; return; }
  let h = FLOWS.length > 1 ? `<div class="flowfoldall">
      <button class="ghost" onclick="foldAllFlows(true)">Fold all flows</button>
      <button class="ghost" onclick="foldAllFlows(false)">Open all flows</button></div>` : "";
  FLOWS.forEach((f, i) => { h += flowCard(f, i); });
  h += `<div class="card"><div class="act">
      <button id="addflow" class="ghost">${icon("auto")} Add a flow</button>
      <button id="saveflows">${icon("again")} Save flows</button>
      <span class="note" id="flowsaid"></span></div>
      <div class="note" style="margin-top:8px">${esc(S.flowsNote)}</div></div>`;
  box.innerHTML = h;
  const add = document.getElementById("addflow");
  if (add) add.onclick = addFlow;
  const save = document.getElementById("saveflows");
  if (save) save.onclick = saveFlows;
}


async function flipInEditor(i, box){
  const f = FLOWS[i];
  const on = box.checked;
  const ok = await askSure(on
    ? {title: `Let "${f.name}" run by itself?`,
       body: `Once saved, it looks for changes every ${f.every} min and runs on its own.`,
       yes: "Yes"}
    : {title: `Stop "${f.name}" running by itself?`, body: "Once saved.", yes: "Yes"});
  if (!ok){ box.checked = !on; return; }
  flowSet(i, "on", on);
}

function flowCard(f, i){
  const byDsm = f.fired_by === "dsm";
  const folded = flowFolded(f.id);
  let h = `<div class="card${folded ? " flowfolded" : ""}">
    <div class="lab" style="gap:10px">
      <button type="button" class="ghost fold" onclick="toggleFlowFold('${quoted(f.id)}')"
        aria-label="${folded ? "Open" : "Fold"} this flow"
        title="${folded ? "Open" : "Fold"} this flow">${icon(folded ? "forward" : "expand-one")}</button>
      <input type="text" value="${esc(f.name)}" style="max-width:20em"
        oninput="flowSet(${i},'name',this.value)">
      ${flowLight(f)}
      <button onclick="runFlow('${quoted(f.id)}')"
        title="Run one pass of this flow now">${icon("play")} Run</button>
      <button class="ghost" onclick="dropFlow(${i})" title="Remove this flow"
        >Remove</button>
      ${folded ? `<span class="note">${say("flowSteps", {n: f.steps.length})}${f.on ? ", on" : ""}</span>` : ""}
    </div>`;
  if (folded) return h + `</div>`;
  h += `
    ${flowDiagram(f)}
    <div class="row-flag" style="margin-top:10px">
      <input type="checkbox" id="fon${i}" ${f.on ? "checked" : ""}
        onchange="flipInEditor(${i}, this)">
      <span class="lab"><label for="fon${i}" style="margin:0">Run this flow by
        itself</label></span>
    </div>
    <div class="lab" style="margin-top:8px">Look for changes every</div>
    <input type="number" min="1" max="1440" value="${esc(f.every)}"
      style="max-width:8em" oninput="flowSet(${i},'every',this.value)">
    <div class="lab" style="margin-top:8px">Fired by</div>
    <select onchange="flowSet(${i},'fired_by',this.value)">` +
    (FLOWMETA.fired_by || []).map(o =>
      `<option value="${esc(o[0])}" ${o[0] === f.fired_by ? "selected" : ""}
        >${esc(o[1])}</option>`).join("") + `</select>`;
  if (byDsm)
    h += `<div class="note" style="margin-top:10px">This app will not fire it.
      In DSM: Control Panel &gt; Task Scheduler &gt; Create &gt; Scheduled Task
      &gt; User-defined script, run as root, and paste:
      <div class="mono" style="margin-top:6px;user-select:all">${esc(f.command)}</div>
      The name comes from this container's own hostname, which is usually right -
      check it against Container Manager if the scheduler says "No such
      container". A schedule of every 30 minutes costs almost nothing when
      nothing has changed: the step still checks first.</div>`;
  h += `<div class="lab" style="margin-top:12px">Folders this flow leaves alone
      <span class="fromsetup">(added to the list in Setup, not replacing it)</span>
    </div>
    <div class="chips" id="fex${i}">` +
    (f.exclude || []).map((x, k) =>
      `<span class="chip">${esc(x)}<button type="button"
         onclick="dropExclude(${i},${k})" title="Stop leaving this out"
         >${icon("cross")}</button></span>`).join("") +
    `</div>
    <button type="button" class="ghost" onclick="addExclude(${i})"
      ${flowLocked(f) ? "disabled" : ""}>${icon("folder")} Leave a folder out</button>
    <div class="row-flag" style="margin-top:10px">
      <input type="checkbox" id="fdeep${i}" ${f.deep ? "checked" : ""}
        onchange="flowSet(${i},'deep',this.checked)">
      <span class="lab"><label for="fdeep${i}" style="margin:0">Notice edits
        inside files, not just files coming and going</label></span>
    </div>`;
  (f.trouble || []).forEach(t => {
    h += `<div class="note" style="margin-top:8px">${esc(t)}</div>`;
  });

  /* A flow that is running has its steps locked, exactly as the old Automation
     tab locked its settings. The whole flow is written in one go and read in
     one go, so a half-changed flow cannot actually be run - but a form you can
     edit while it is firing invites you to wonder which version just ran, and
     "turn it off to change it" is a shorter answer than that. */
  if (flowLocked(f))
    h += `<div class="note" id="flowlocked${i}" style="margin-top:10px">
      ${icon("lock")} <span>These steps are locked because this flow is running
      by itself. Turn it off above to change them.</span></div>`;

  h += `<div class="steprow" style="margin-top:14px">
      <b style="font-size:13px">Steps</b>
      <span class="note">in the order the work happens</span>
      <span class="stepacts">
        <button class="ghost" onclick="openAll(${i}, true)">Expand all</button>
        <button class="ghost" onclick="openAll(${i}, false)">Collapse all</button>
      </span>
    </div>
    <div style="margin-top:4px">`;
  if (!f.steps.length)
    h += `<div class="note">No steps yet. Add one below - the order is the
      order the work happens.</div>`;
  f.steps.forEach((s, j) => { h += stepCard(f, i, s, j); });
  h += `</div>
    <div class="act" style="margin-top:10px">
      <select id="pick${i}"${flowLocked(f) ? " disabled" : ""}>` +
      FLOWCAT.map(c => `<option value="${esc(c.name)}">${esc(c.title)}</option>`)
        .join("") + `</select>
      <button class="ghost" onclick="addStep(${i})"
        ${flowLocked(f) ? "disabled" : ""}>Add this step</button>
    </div></div>`;
  return h;
}

function flowLocked(f){
  return !!(f && f.on && f.fired_by !== "dsm");
}

function stepCard(f, i, s, j){
  const open = !!FLOWOPEN[s.id];
  const lock = flowLocked(f) ? " disabled" : "";
  const cat = FLOWCAT.find(c => c.name === s.task) || {};
  const over = Object.keys(s.opts || {}).length;
  let h = `<div class="stepcard${s.on ? "" : " off"}">
    <div class="steprow">
      <span class="stepn">${j + 1}</span>
      <span class="steptitle">${esc(s.title)}${s.missing
        ? ` <span class="bad">(no such tool any more)</span>` : ""}</span>
      <span class="note">watches ${esc(s.watches_label || "-")}${
        s.watches_path ? "" : " - not set up in Setup"}</span>
      <span class="stepacts">
        <button class="ghost" onclick="moveStep(${i},${j},-1)"
          ${j === 0 || lock ? "disabled" : ""}
          title="Earlier in the chain">&#9650;</button>
        <button class="ghost" onclick="moveStep(${i},${j},1)"
          ${j === f.steps.length - 1 || lock ? "disabled" : ""}
          title="Later in the chain">&#9660;</button>
        <button class="ghost" onclick="openStep('${quoted(s.id)}')"
          >${open ? "Hide" : "Settings"}${over ? ` (${over})` : ""}</button>
        <button class="ghost" onclick="dropStep(${i},${j})"${lock}>Remove</button>
      </span>
    </div>
    <div class="steprow" style="margin-top:6px">
      <label class="note"><input type="checkbox" ${s.on ? "checked" : ""}${lock}
        onchange="stepSet(${i},${j},'on',this.checked)"> on</label>
      <select onchange="stepSet(${i},${j},'do',this.value)"${lock}>` +
      (FLOWMETA.do || []).map(o => `<option value="${esc(o[0])}"
        ${o[0] === s.do ? "selected" : ""}>${esc(o[1])}</option>`).join("") +
      `</select>
      ${cat.summary ? `<button class="info" type="button"
        aria-label="What this step does" data-tip="${esc(cat.summary)}">i</button>`
        : ""}
    </div>`;
  if (open) h += stepSettings(i, s, j, !!lock);
  h += `</div>`;
  return h;
}

function stepSettings(i, s, j, lock){
  /* Every option of that feature, with the value it would use and where that
     value came from. The point is that nothing is invisible: the fault this
     replaces was a threshold typed on a tab that was not the threshold running
     in the background, with neither end saying so. */
  const cat = FLOWCAT.find(c => c.name === s.task);
  if (!cat) return `<div class="note">Nothing is known about this tool.</div>`;
  let h = `<div class="stepopts">`;
  cat.options.forEach(o => {
    const eff = (s.effective || {})[o.name] || {};
    const mine = Object.prototype.hasOwnProperty.call(s.opts || {}, o.name);
    const value = mine ? s.opts[o.name] : eff.value;
    const came = mine ? "set on this step"
                      : (eff.from === "setup" ? "from Setup" : "the default");
    h += `<div class="stepopt">
      <div class="lab"><label style="margin:0">${esc(o.label)}</label>
        <span class="fromsetup">(${came})</span>
        ${mine ? `<button class="ghost" onclick="clearOpt(${i},${j},'${quoted(o.name)}')"
             >use Setup</button>` : ""}</div>`;
    const off = lock ? " disabled" : "";
    if (o.kind === "flag")
      h += `<input type="checkbox" ${value ? "checked" : ""}${off}
             onchange="setOpt(${i},${j},'${quoted(o.name)}',this.checked)">`;
    else if (o.kind === "choice")
      h += `<select${off} onchange="setOpt(${i},${j},'${quoted(o.name)}',this.value)">` +
        (o.choices || []).map(c => `<option value="${esc(c.value)}"
          ${String(c.value) === String(value) ? "selected" : ""}
          >${esc(c.label)}</option>`).join("") + `</select>`;
    else if (o.kind === "number")
      h += `<input type="number" value="${esc(value == null ? "" : value)}"${off}
             onchange="setOpt(${i},${j},'${quoted(o.name)}',this.value)">`;
    else
      h += `<input type="text" value="${esc(value == null ? "" : value)}"${off}
             onchange="setOpt(${i},${j},'${quoted(o.name)}',this.value)">`;
    // the same bubble the rest of the app uses, rather than a wall of prose
    // under every one of a step's fifteen settings
    h += `</div>`;
  });
  h += `</div>`;
  return h;
}

/* -------------------------------------------------------------- editing it */

function flowSet(i, key, value){
  if (!FLOWS || !FLOWS[i]) return;
  FLOWS[i][key] = (key === "every") ? Math.max(1, parseInt(value, 10) || 15)
                                    : value;
  if (key === "fired_by" || key === "on") drawFlows();
}

function stepSet(i, j, key, value){
  const s = FLOWS[i] && FLOWS[i].steps[j];
  if (!s) return;
  s[key] = value;
  drawFlows();
}

function setOpt(i, j, name, value){
  const s = FLOWS[i] && FLOWS[i].steps[j];
  if (!s) return;
  s.opts = s.opts || {};
  s.opts[name] = value;
  /* Not redrawn: the box you are typing into would lose the caret. The label
     above it is one redraw behind until something else redraws, which is a
     smaller lie than a form that fights you. */
}

function clearOpt(i, j, name){
  const s = FLOWS[i] && FLOWS[i].steps[j];
  if (!s || !s.opts) return;
  delete s.opts[name];
  drawFlows();
}

function openStep(id){
  FLOWOPEN[id] = !FLOWOPEN[id];
  drawFlows();
}

function openAll(i, open){
  /* All of them at once. Opening six steps one at a time to compare a threshold
     across them is the kind of chore that makes people stop checking. */
  (FLOWS[i].steps || []).forEach(s => { FLOWOPEN[s.id] = !!open; });
  drawFlows();
}

function addExclude(i){
  browseTo(path => {
    const list = FLOWS[i].exclude || (FLOWS[i].exclude = []);
    if (!list.includes(path)) list.push(path);
    drawFlows();
  }, (FLOWS[i].exclude || []).slice(-1)[0] || "");
}

function dropExclude(i, k){
  (FLOWS[i].exclude || []).splice(k, 1);
  drawFlows();
}

async function runFlow(id){
  /* Straight to the Automation tab with this flow chosen, and press its button.
     Not a second way of running a flow - the SAME one, because two code paths
     would mean the thing you pressed here is not the thing that runs at four in
     the morning, which is the rule the whole automation is built on. */
  await show("automation");
  const box = document.getElementById("o_which");
  if (box){ box.value = id; box.dispatchEvent(new Event("change")); }
  const go = document.getElementById("go");
  if (go) go.click();
}

function moveStep(i, j, by){
  /* One place at a time, because the order IS the chain: steps run in order
     inside one pass and a step that writes makes the next one run straight
     away. Dragging would be prettier and this is the thing you actually do. */
  const steps = FLOWS[i].steps;
  const to = j + by;
  if (to < 0 || to >= steps.length) return;
  const one = steps.splice(j, 1)[0];
  steps.splice(to, 0, one);
  drawFlows();
}

function addStep(i){
  const pick = document.getElementById("pick" + i);
  if (!pick) return;
  const cat = FLOWCAT.find(c => c.name === pick.value);
  if (!cat) return;
  FLOWS[i].steps.push({
    id: "", task: cat.name, on: true,
    /* A step that WRITES starts as "just tell me". Adding a feature to a flow
       from a dropdown and having it start moving photographs on the next pass
       is not a thing anybody should be able to do by accident. */
    do: cat.writes ? "report" : "run",
    watch: "", opts: {}, title: cat.title,
    watches: cat.watches, watches_label: cat.watches_label,
    watches_path: cat.watches_path, effective: {}, missing: false});
  drawFlows();
}

function dropStep(i, j){
  FLOWS[i].steps.splice(j, 1);
  drawFlows();
}

function addFlow(){
  FLOWS.push({id: "", name: "New flow", on: false, every: 15, deep: true,
              fired_by: "app", steps: [], command: "", trouble: []});
  drawFlows();
}

async function dropFlow(i){
  const f = FLOWS[i];
  if (f && f.steps.length && !await askSure({
      title: `Remove "${f.name}"?`,
      body: say("flowRemove", {n: f.steps.length}),
      yes: "Remove"})) return;
  FLOWS.splice(i, 1);
  drawFlows();
}

/* ------------------------------------------------------------- the folder tree */

/* What each column means. The mark is one of all / some / none / empty, and
   "some" is the one that earns the display: a half-finished shoot must not look
   like a finished one. */
const MARKS = [
  ["separated", "\u2702", "RAWs out",  "RAWs separated out of the library", "unpair"],
  ["video",     "\u25b6", "Video out", "video moved into the video tree",    "videos"],
  ["located",   "\u25c9", "Location",  "photos carrying a location",        "geotag"],
  ["rated",     "\u2605", "Rated",     "photos with a star rating",         "ratings"],
  ["dated",     "\u23f1", "Dated",     "photos with a capture time in them", "retime"],
  ["previews",  "\u25a3", "Previews",  "previews made",                     "previews"],
  ["culled",    "\u2715", "Aside",     S.asideTip,                           "cull"],
  ["readable",  "\u2713", "Readable",  S.readableTip, ""],
];

/* Which columns are on, remembered in this browser.

   Nine columns is the right number to HAVE and the wrong number to look at:
   the week you are geotagging, four of them are noise. So each one can be put
   away, and what you put away stays away - it is a view, and a view you have to
   set up again every time is one you stop using. */
const COLUMNS = [
  ["photos", "Photos", 1],
  ["raws", "RAWs", 1],
  ["size", "Size", 0],
  ["span", "Dates covered", 0],
].concat(MARKS.map(m => [m[0], m[2], 1]));

let COLSON = null;

function colsOn(){
  if (COLSON) return COLSON;
  let kept = {};
  try{ kept = JSON.parse(localStorage.getItem("pm_cols") || "{}") || {}; }
  catch(e){ kept = {}; }
  COLSON = {};
  COLUMNS.forEach(([key, , on]) => {
    COLSON[key] = key in kept ? !!kept[key] : !!on;
  });
  return COLSON;
}

function colToggle(key, on){
  colsOn()[key] = !!on;
  try{ localStorage.setItem("pm_cols", JSON.stringify(COLSON)); }catch(e){}
  // The home screen draws this same table over the index, and it has no plan
  // to re-render - so it says so for itself.
  if (typeof boardTreeRedraw === "function") boardTreeRedraw();
  if (PLAN && PLAN.tree) render(PLAN);
}

function colMenu(ev){
  const on = colsOn();
  fmMenu(ev, COLUMNS.map(([key, label]) =>
    `<button type="button" class="vopt" data-w="${key}"><span class="vgrow">${esc(label)}</span>
       ${on[key] ? "<span class=\"vcheck\">\u2713</span>" : ""}</button>`).join(""),
    b => colToggle(b.dataset.w, !on[b.dataset.w]));
}

function shownMarks(){
  const on = colsOn();
  return MARKS.filter(m => on[m[0]]);
}

const folded = new Set();

function treeCard(p){
  let h = `<div class="card"><b>The library</b>
    <span class="note">(${p.tree.length} folders)</span>
    <span class="twists">
      <button title="Which columns to show" onclick="colMenu(event)"
        class="colpick">${icon("layers")} Columns \u25be</button>
      <button title="Collapse everything" onclick="depthTo(0)">${icon("collapse-all")}</button>
      <button title="One level less" onclick="depthBy(-1)">${icon("collapse-one")}</button>
      <button title="One level more" onclick="depthBy(1)">${icon("expand-one")}</button>
      <button title="Expand everything" onclick="depthTo(99)">${icon("expand-all")}</button>
    </span>
    <div class="scroll" style="margin-top:10px"><table class="tree">
      <thead><tr><th>Folder</th>`
    + (colsOn().photos ? `<th class="num">Photos</th>` : "")
    + (colsOn().raws ? `<th class="num">RAWs</th>` : "")
    + (colsOn().size ? `<th class="num" title="Everything this folder costs, across the library, RAW, previews and video trees">Size</th>` : "")
    + (colsOn().span ? `<th title="${esc(S.spanTip)}">Dates covered</th>` : "")
    + shownMarks().map(m => `<th title="${esc(m[3])}">${esc(m[2])}</th>`).join("")
    + `</tr></thead><tbody id="treebody"></tbody></table></div>
    <div class="legend">
      <span><span class="pip all">&nbsp;</span> all of them</span>
      <span><span class="pip some">&nbsp;</span> some - unfinished</span>
      <span><span class="pip none">&nbsp;</span> none</span>
      <span>click a folder for the list of tools - or a mark to go straight
        to the one that changes it</span>
      <span class="faded">faded rows are only holding up the ones that matched</span>
    </div></div>`;
  return h;
}

/* The row above a row, worked out from the paths.

   Everything about drawing a tree - what indents how far, what has an arrow,
   what a folded folder hides - used to be arithmetic on a `depth` number and an
   assumption that rows arrive parent-first. Both are things that can drift out
   of step with the actual hierarchy, and when they do the tree does not look
   wrong: it looks like folding is broken, because a folder sits there with a
   closed arrow and every child still on screen.

   Paths cannot drift. They ARE the hierarchy. */

function cutLast(path){
  const at = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return at > 0 ? path.slice(0, at) : "";
}

function family(nodes){
  const present = new Set(nodes.map(n => n.path));
  const parent = new Map();
  for (const n of nodes){
    let up = cutLast(n.path);
    while (up && !present.has(up)) up = cutLast(up);
    parent.set(n.path, present.has(up) ? up : null);
  }
  const hasKids = new Set();
  for (const up of parent.values()) if (up) hasKids.add(up);

  const level = new Map();
  for (const n of nodes){
    let d = 0, up = parent.get(n.path);
    const seen = new Set([n.path]);
    while (up && !seen.has(up)){ seen.add(up); d += 1; up = parent.get(up); }
    level.set(n.path, d);
  }
  return {parent, hasKids, level};
}

function drawTree(nodes){
  const body = document.getElementById("treebody");
  if (!body) return;
  TREENOW = Array.isArray(nodes) ? nodes : [];

  const {parent, hasKids, level} = family(nodes);

  // hidden because an ancestor is folded - walked up, never inferred
  const hidden = new Set();
  if (folded.size)
    for (const n of nodes){
      let up = parent.get(n.path);
      const seen = new Set();
      while (up && !seen.has(up)){
        if (folded.has(up)){ hidden.add(n.path); break; }
        seen.add(up);
        up = parent.get(up);
      }
    }

  let shownDepth = 0;
  const rows = [];
  for (const n of nodes){
    if (hidden.has(n.path)) continue;
    const shut = folded.has(n.path);
    const depth = level.get(n.path) || 0;
    shownDepth = Math.max(shownDepth, depth);

    const twist = !hasKids.has(n.path)
      ? `<span class="leafpad"></span>`
      : `<span class="twist" onclick="fold('${quoted(n.path)}')">${shut ? "\u25b8" : "\u25be"}</span>`;

    const safe = quoted(n.path);
    /* Guide lines, one per level. Sixteen pixels of indent and nothing else is
       not enough to see which folder a folder is under - deep shoots read as
       siblings of the years above them, which is how a folder that is plainly
       inside another one looks orphaned. */
    const rail = depth
      ? `background-image:repeating-linear-gradient(to right,var(--line) 0 1px,`
        + `transparent 1px 20px);background-position:13px 0;background-repeat:no-repeat;`
        + `background-size:${depth * 20}px 100%;`
      : "";
    rows.push(`<tr class="${n.matched === false ? "scaffold" : ""}">
      <td style="padding-left:${8 + depth * 20}px;${rail}">
        <span class="fname">${twist}${icon("folder")}<a href="#" class="fgo ${n.leaf ? "" : "branch"}"
          onclick="return workOn(event,'${safe}')">${esc(n.name)}</a></span></td>
      ${colsOn().photos ? `<td class="num">${n.photos ? `<b>${n.photos}</b>` : "-"}</td>` : ""}
      ${colsOn().raws ? `<td class="num">${n.raws_here
          ? `<b style="color:var(--warn)">${n.raws_here} here</b>`
          : (n.raws_apart ? n.raws_apart : "-")}</td>` : ""}
      ${colsOn().size ? `<td class="num" title="${esc(sizeWhy(n))}">${
          n.bytes ? fmSize(n.bytes) : "-"}</td>` : ""}
      ${colsOn().span ? `<td class="note">${esc(span(n))}</td>` : ""}`
      /* The mark is the shortcut. You spot that Italy is half geotagged, and
         the next thing you want is to geotag Italy - so the icon that told you
         is the thing you press, and it opens that feature with the folder
         already in the box. Reading and acting in the same gesture. */
      + shownMarks().map(m => {
          const state = (n.marks || {})[m[0]] || "empty";
          const what = byName(m[4]);
          const title = (state === "empty" ? "nothing to say"
                          : `${state} - ${m[2]}` + countFor(n, m[0]))
            + (what ? `\nclick to open ${what.title} for this folder` : "");
          if (!what)
            return `<td><span class="pip ${state}" title="${esc(title)}">${m[1]}</span></td>`;
          return `<td><button class="pip ${state}" title="${esc(title)}"
            onclick="goWith('${m[4]}','${safe}')">${m[1]}</button></td>`;
        }).join("")
      + `</tr>`);
  }
  body.innerHTML = rows.join("");
  drawnDepth = shownDepth;

  /* A button that would do nothing says so, rather than being pressed twice and
     called broken. Everything is already open, or already shut. */
  const anyFolded = nodes.some(n => hasKids.has(n.path) && folded.has(n.path));
  const anyOpen = nodes.some(n => hasKids.has(n.path) && !folded.has(n.path));
  /* By what each one SAYS, not by where it sits. Counting along the row broke
     the moment a button was added to the front of it - and broke silently,
     disabling whichever button happened to be in that position. */
  const set = (title, on) => {
    const b = document.querySelector(`.twists button[title="${title}"]`);
    if (b) b.disabled = !on;
  };
  set("Collapse everything", anyOpen);
  set("One level less", anyOpen);
  set("One level more", anyFolded);
  set("Expand everything", anyFolded);
}

function countFor(n, key){
  if (key === "video")     return ` (${n.videos_here || 0} here, ${n.videos_apart || 0} apart)`;
  if (key === "rated")     return ` (${n.rated} of ${n.photos})`;
  if (key === "located")   return ` (${n.located} of ${n.photos})`;
  if (key === "dated")     return ` (${n.dated || 0} of ${n.photos})`;
  if (key === "previews")  return ` (${n.previews} of ${n.photos})`;
  if (key === "culled")    return ` (${n.culled})`;
  if (key === "readable")  return n.unreadable ? ` (${n.unreadable} could not be read)` : "";
  if (key === "separated") return ` (${n.raws_apart} out, ${n.raws_here} still here)`;
  return "";
}

function sizeWhy(n){
  /* The number is the whole shoot - the photographs, their negatives, the
     previews, the clips and whatever has been put aside from it. Said in the
     tooltip, because one number with four things in it is worth explaining. */
  const parts = [];
  if (n.own_bytes) parts.push(`${fmSize(n.own_bytes)} here`);
  const rest = (n.bytes || 0) - (n.own_bytes || 0);
  if (rest > 0) parts.push(`${fmSize(rest)} in the other trees`);
  return parts.join(", ") || "nothing in here";
}

function span(n){
  const first = (n.first_taken || "").slice(0, 10);
  const last = (n.last_taken || "").slice(0, 10);
  if (!first) return "-";
  return first === last ? first : `${first} to ${last}`;
}

/* Clicking a folder is the point of the whole view: you spot that Italy is half
   geotagged, and the next thing you want is to geotag Italy - not to remember
   its path, switch tab and type it in. */
function workOn(ev, path){
  /* Every feature that takes a folder, which is most of them. Flat, that was a
     list of thirty-odd on a menu that could not scroll - on a phone the bottom
     of it simply did not exist. So: the features first, and the tabs under one
     appear when you open it. Two taps to anywhere, and the first tap is a list
     short enough to read. */
  ev.preventDefault();
  closeMenu();
  if (typeof closePageMenu === "function") closePageMenu();   // never two at once
  const usable = t => t.name !== CURRENT.name && t.options.some(o => o.name === "folder");
  const tops = TASKS.filter(t => !t.parent);
  const menu = document.createElement("div");
  menu.className = "fmenu";
  menu.id = "fmenu";
  const q = quoted(path);

  let h = `<div class="mpath">${esc(path)}</div><div class="fmenulist">`;
  /* Looking at it is a thing you do with a folder too, and it is the first one
     anybody wants: you spot a half-rated shoot and the next move is to SEE it.
     Only where there is a grid to show it in. */
  if (typeof showFolder === "function" && typeof shellOn === "function" && shellOn())
    h += `<button class="tier1" onclick="showFolder('${q}')"
      >${icon("photos")}<span>${esc(S.showPhotos)}</span></button>`;
  let any = 0;
  for (const top of tops){
    const kids = TASKS.filter(t => t.parent === top.name && usable(t));
    const self = usable(top);
    if (!self && !kids.length) continue;
    any++;
    const open = MENUOPEN === top.name;
    if (!kids.length){
      h += `<button class="tier1" onclick="goWith('${top.name}','${q}')"
        >${icon(top.icon)}<span>${esc(top.title)}</span></button>`;
      continue;
    }
    h += `<button class="tier1" onclick="menuOpen('${top.name}','${q}', event)"
      >${icon(top.icon)}<span>${esc(top.title)}</span>
      <span class="twisty">${kids.length + (self ? 1 : 0)} ${open ? "\u25be" : "\u25b8"}</span></button>`;
    if (!open) continue;
    if (self)
      h += `<button class="tier2" onclick="goWith('${top.name}','${q}')"
        >${icon(top.icon)}<span>${esc(top.tab || top.title)}</span></button>`;
    h += kids.map(t => `<button class="tier2" onclick="goWith('${t.name}','${q}')"
      >${icon(t.icon)}<span>${esc(t.tab || t.title)}</span></button>`).join("");
  }
  h += `</div>`;
  if (!any) h += `<div class="mnote">Nothing else takes a folder.</div>`;
  menu.innerHTML = h;

  /* The button, not whatever was under the finger. A tap on the glyph inside
     "Use in \u25be" made ev.target the <svg>, and the menu hung off the icon. */
  const on = ev.target && ev.target.closest
    ? (ev.target.closest("button,a,[role=button]") || ev.target) : ev.target;
  const at = on.getBoundingClientRect();
  menu.style.left = (at.left + window.scrollX) + "px";
  menu.style.visibility = "hidden";
  menu.style.top = (at.bottom + window.scrollY + 4) + "px";
  document.body.appendChild(menu);
  // flip it above the row when it would hang off the bottom of the window
  if (at.bottom + menu.offsetHeight + 12 > window.innerHeight)
    menu.style.top = Math.max(window.scrollY + 8,
      at.top + window.scrollY - menu.offsetHeight - 4) + "px";
  // and back from the right edge when it would hang off the side
  const wide = menu.offsetWidth;
  if (at.left + wide + 12 > window.innerWidth)
    menu.style.left = Math.max(8, window.innerWidth - wide - 12) + window.scrollX + "px";
  menu.style.visibility = "visible";
  /* Kept in DOCUMENT coordinates. They used to be viewport ones, and opening a
     tier after scrolling re-added the scroll a second time, so the menu jumped
     by however far the page had moved. */
  MENUAT = {x: at.left + window.scrollX, y: at.bottom + window.scrollY,
            top: at.top + window.scrollY, path: path};
  /* Same sheet of glass as the page menus: a tap on empty background does not
     reliably reach a document click listener on iOS. */
  const scrim = document.createElement("div");
  scrim.id = "menuscrim";
  scrim.onclick = () => closeMenu();
  document.body.appendChild(scrim);
  if (MENUAWAY) document.removeEventListener("click", MENUAWAY);
  MENUAWAY = () => closeMenu();
  setTimeout(() => document.addEventListener("click", MENUAWAY), 0);
  if (MENUKEY) document.removeEventListener("keydown", MENUKEY);
  MENUKEY = e => { if (e.key === "Escape"){ e.stopPropagation(); closeMenu(); } };
  document.addEventListener("keydown", MENUKEY);
  return false;
}

let MENUAWAY = null, MENUKEY = null;

let MENUOPEN = "", MENUAT = null;

function menuOpen(name, path, ev){
  /* Opening one closes the last: the menu is a list you read, and two open
     features is most of a phone screen of tabs you were not looking for. */
  ev.stopPropagation();
  MENUOPEN = MENUOPEN === name ? "" : name;
  const was = MENUAT;
  closeMenu();
  // back to viewport coordinates, because that is what workOn measures in
  workOn({preventDefault(){}, target: {getBoundingClientRect: () =>
    ({left: was.x - window.scrollX, bottom: was.y - window.scrollY,
      top: was.top - window.scrollY})}}, was.path);
}

function closeMenu(){
  const m = document.getElementById("fmenu");
  if (m) m.remove();
  const g = document.getElementById("menuscrim");
  if (g) g.remove();
  if (MENUAWAY){ document.removeEventListener("click", MENUAWAY); MENUAWAY = null; }
  if (MENUKEY){ document.removeEventListener("keydown", MENUKEY); MENUKEY = null; }
}

function goWith(task, path){
  closeMenu();
  show(task);
  const el = document.getElementById("o_folder");
  if (!el) return;
  /* `show` above has already cleared the typed-in memory, which is what makes
     the tree boxes follow this new folder rather than staying pointed at last
     week's shoot. Stated because it is not obvious from here, and because a
     future `show` that returns early for the tab you are already on would break
     this quietly. */
  el.value = path;
  el.focus();
  el.scrollIntoView({block: "center"});
  followTrees();
  /* An editor tab read the box while `show` was drawing it, which was before
     this line put the new folder in it. Reading it again is the whole difference
     between "Use in > Power rename" listing this folder and listing last
     week's. */
  if (task === "rename") startRename();
  if (task === "files") startFiles();
  /* Whatever that tab was showing was about a DIFFERENT folder. Leaving it up
     beside a box that now says something else is how you read last week's
     answer as this one. */
  const box = SEEN[task];
  if (box && box.out){ box.out = ""; box.plan = null; box.done = null; }
  PLAN = null;
  document.getElementById("out").innerHTML =
    `<div class="card note">Ready for <b>${esc(path)}</b> - press the button above
     to see what would happen. Nothing has been read yet.</div>`;
}

/* THE TREE ON SCREEN, whosever it is.

   Folding used to redraw `PLAN.tree` - the tree belonging to the feature whose
   plan was last made. That is right on the Library tab and wrong everywhere
   else: the same table draws the folder board on Home, where there is no plan
   at all, so collapsing a level there either threw or redrew Home with some
   other feature's rows. The table remembers what it last drew instead. */
let TREENOW = [];

function fold(path){
  if (folded.has(path)) folded.delete(path); else folded.add(path);
  drawTree(TREENOW.length ? TREENOW : ((PLAN && PLAN.tree) || []));
}

/* Open to a DEPTH rather than opening one folder at a time.
   A library is years over shoots: "show me the years" and "show me everything"
   are the two things anybody actually wants, and clicking twelve twists to get
   either is why nobody uses a tree view twice.

   How deep the tree looks RIGHT NOW - the deepest row actually drawn.
   Stepping by absolute depth was the mistake: in a tree where one branch runs
   three levels deeper than the rest, "one level less" folded that single branch
   and nothing else, so the button looked broken. Stepping by what is on screen
   always changes what is on screen. */
let drawnDepth = 0;

function depthTo(want){
  const nodes = TREENOW.length ? TREENOW : ((PLAN && PLAN.tree) || []);
  if (!nodes.length) return;
  const {level} = family(nodes);
  folded.clear();
  for (const n of nodes)
    if ((level.get(n.path) || 0) >= want) folded.add(n.path);
  drawTree(nodes);
}

function depthBy(step){
  depthTo(Math.max(0, drawnDepth + step));
}



function stopPolling(){ if (poller){ clearInterval(poller); poller = null; } }

async function askToStop(){
  const b = document.getElementById("stop");
  if (b) b.disabled = true;
  if (!WATCH) return;
  await fetch("api/cancel", {method:"POST",
    headers:{"Content-Type":"application/json"}, body: JSON.stringify({id: WATCH.id})});
}

async function apply(){
  if (!await sureAbout(PLAN || {})) return;
  setStep(3);
  const card = document.getElementById("apply");
  card.innerHTML = `<b>Working...</b>
    <div class="bar"><i id="fill"></i></div>
    <div class="note" id="pnote">starting</div>
    <div class="mono" id="pnow"></div>
    <div class="act" style="margin-top:12px">
      <button class="danger" id="stop">Stop after the current file</button></div>`;
  document.getElementById("stop").onclick = askToStop;
  WATCH = {task: CURRENT.name, id: PLAN.id};
  const r = await fetch("api/apply", {method:"POST",
    headers:{"Content-Type":"application/json"}, body: JSON.stringify({id: PLAN.id})});
  const first = await r.json();
  if (first.error){ card.innerHTML = `<b class="bad">Could not start</b>
    <pre>${esc(first.error)}</pre>`; return; }
  poller = setInterval(poll, 400);
  poll();
  pollJobs();           // something is running now: the bar asks quickly again
}

let POLLMISSED = 0;

async function poll(){
  if (!WATCH) return stopPolling();
  let s;
  try{ s = await (await fetch("api/progress?id=" + encodeURIComponent(WATCH.id))).json(); }
  catch(e){
    if (++POLLMISSED >= UNANSWERED && CURRENT && WATCH && CURRENT.name === WATCH.task)
      notAnswering("pnote");
    return;
  }
  POLLMISSED = 0;

  /* The run belongs to a task, not to whatever is on screen. Look at another
     tab while it works and it keeps working; the numbers are simply not drawn
     until you come back, and a run that finishes while you are away is waiting
     for you when you return rather than having quietly vanished. */
  const here = CURRENT && CURRENT.name === WATCH.task;
  const fill = here ? document.getElementById("fill") : null;
  if (fill){
    fill.style.width = (s.total ? Math.round(100 * s.done / s.total) : 0) + "%";
    document.getElementById("pnote").textContent =
      `${s.done} of ${s.total}` + (s.cancelled ? " - stopping" : "");
    document.getElementById("pnow").textContent = s.now || "";
    markRows(s);
  }
  if (s.finished){
    stopPolling();
    if (here) markRows(s);
    const box = SEEN[WATCH.task] || (SEEN[WATCH.task] = {});
    box.done = s;
    if (here) finish(s);
    // if you are elsewhere, box.done is what show() finishes the card with
    WATCH = null;
  }
}

/* A tick against each line as it goes, the way the Windows app did it. A single
   bar says how far along it is; this says WHICH ones - and when four files out
   of nine hundred fail, which four is the only thing you actually want. */
function markRows(s){
  const bad = new Set(s.stumbled || []);
  const upto = Math.min(s.done, 5000);
  for (let i = 0; i < upto; i++){
    const tr = document.getElementById("r" + i);
    if (!tr || tr.classList.contains("did") || tr.classList.contains("didnt")) continue;
    tr.classList.remove("doing");
    tr.classList.add(bad.has(i) ? "didnt" : "did");
  }
  for (const tr of document.querySelectorAll("tr.doing")) tr.classList.remove("doing");
  const now = document.getElementById("r" + upto);
  if (now && !s.finished) now.classList.add("doing");
}

/* A run can move the ground the form is standing on.
   Re-mirror a library you have reorganised and the folder in the box may not be
   there any more - it was renamed, or emptied and tidied away - and the boxes go
   on showing where things used to be. So after anything is applied they are
   checked and re-derived, and a box pointing at a folder that has gone SAYS so
   rather than being quietly rewritten: it is what you typed, and you should be
   the one to change it. */
async function repoint(){
  if (!CURRENT) return;
  const boxes = CURRENT.options
    .filter(o => o.kind === "folder")
    .map(o => [o, document.getElementById("o_" + o.name)])
    .filter(([, el]) => el && el.value.trim());
  if (!boxes.length) return;

  let there = {};
  try{
    const q = boxes.map(([, el]) => "path=" + encodeURIComponent(el.value.trim()));
    there = (await (await fetch("api/exists?" + q.join("&"))).json()).there || {};
  }catch(e){ return; }

  const gone = boxes.filter(([o, el]) => there[el.value.trim()] === false
                                         && !(o.tree && mirroring()));
  greyDestinations();                       // re-derive whatever mirroring owns
  const note = document.getElementById("followed");
  if (note && gone.length)
    note.textContent = gone.map(([o, el]) =>
      `${o.label}: ${el.value.trim()} is not there any more`).join(" \u00b7 ");
}

/* ------------------------------------------------------------ what happened

   "Done" with a list of numbers under it was true and almost unreadable: the
   four things you want to know after a run - what it did, what it deliberately
   left, what it could not reach, and what failed - were a sentence, a stats
   grid and a <pre> block, in that order, with the failures last.

   They are four counters now, side by side, each saying which of the four it
   is, and the detail stays underneath for when one of them is not zero. The
   numbers come from two places on purpose: the RESULT knows what it managed,
   and the PLAN knows what it had already decided to leave alone - a run that
   reports "184 done" out of 400 rows has not told you about the other 216. */
function outcomeTiles(s){
  const r = s.result || {};
  const planned = (PLAN && PLAN.impact && PLAN.impact.count != null)
    ? PLAN.impact.count : (PLAN && PLAN.rows ? PLAN.rows.length : 0);
  const left = (PLAN && PLAN.skipped) ? PLAN.skipped.length : 0;
  const missed = Math.max(0, planned - (r.done || 0) - (r.failed || 0));
  const tiles = [["Done", r.done || 0, "good", "check"]];
  if (left) tiles.push(["Left alone", left, "", "info"]);
  if (missed) tiles.push([r.cancelled ? "Not reached" : "Unchanged", missed,
                          r.cancelled ? "warn" : "", "info"]);
  tiles.push(["Failed", r.failed || 0, (r.failed ? "bad" : ""), "warn"]);
  return `<div class="outcome">` + tiles.map(([word, n, cls, ico]) =>
    `<div class="${cls}"><span>${icon(ico)}${esc(word)}</span><b>${num(n)}</b></div>`
  ).join("") + `</div>`;
}

/* And the one line a report should always end with: what to do about it. */
function nextStep(s){
  const r = s.result || {};
  if (r.failed) return S.nextFailed;
  if (r.cancelled) return S.nextCancelled;
  if (PLAN && PLAN.skipped && PLAN.skipped.length) return S.nextSkipped;
  return "";
}

function finish(s){
  const card = document.getElementById("apply");
  setStep(4);
  if (s.error){ card.innerHTML = `<b class="bad">${icon("warn")} It stopped with an error</b>
    <pre>${esc(s.error)}</pre>`; return; }
  const r = s.result || {done:0, failed:0, stats:[], details:[]};
  const bad = r.failed > 0;
  let h = `<b class="${bad ? "warn" : "good"}">`
    + (r.cancelled ? "Stopped part way" : bad ? "Finished, with some failures" : "Done")
    + `</b>` + outcomeTiles(s)
    + `<div class="stats" style="margin-top:12px">`
    + r.stats.map(x => `<div>${esc(x[0])}</div><div>${esc(x[1])}</div>`).join("")
    + `</div>`;
  if (r.details.length) h += `<div class="scroll" style="margin-top:12px"><pre>`
    + r.details.map(esc).join("\n") + `</pre></div>`;
  const said = nextStep(s);
  if (said) h += `<div class="note" style="margin-top:10px">${esc(said)}</div>`;
  h += `<div class="act" style="margin-top:12px">
        <button class="ghost" id="again">${WORDS.again}</button></div>`;
  card.innerHTML = h;
  document.getElementById("again").onclick = run;
  repoint();
}

/* ------------------------------------------------------------------ the map
   Where each photograph would be pinned, BEFORE anything is written - which is
   when a wrong clock is cheap to notice. A table of coordinates cannot show you
   that half a trip landed in the airport car park; a map shows it at a glance.

   No map library: a map is square tiles at a zoom level and dots in the right
   places, and that is sixty lines rather than a dependency. The tiles come
   from OpenStreetMap, over the internet, to your BROWSER - the NAS fetches
   nothing. With no internet the dots are still drawn, in the right places
   relative to each other, on a plain background. */
function mapCard(points){
  return `<div class="card"><b>Where they would go</b>
    <span class="note">(${points.length} photo${points.length === 1 ? "" : "s"})</span>
    <div class="pmmap" id="pmmap"></div>
    <div class="note" style="margin-top:6px;font-size:11.5px">Map &copy;
      OpenStreetMap contributors. ${esc(S.nothingUntilApply)}</div>
  </div>`;
}

/* One map in the app, two ways of using it.

   A plan draws a still picture of where its rows would land - that is a
   check, and panning it would be a toy. The Places screen is the opposite: the
   whole point is to go and look, so it pans, zooms and answers a click with
   the photographs that are there.

   Same projection, same tiles, same dots either way. A second map would be the
   two-tooltip-engines mistake with a web of tile maths in it. */
const MAPAT = {z: 0, cx: 0, cy: 0, on: false, dragged: false};

function mapPx(lat, lon, z){
  const s = 256 * Math.pow(2, z);
  const r = Math.max(-85, Math.min(85, lat)) * Math.PI / 180;
  return [(lon + 180) / 360 * s,
          (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * s];
}

function drawMap(points, opts){
  opts = opts || {};
  const box = document.getElementById("pmmap");
  if (!box || !points || !points.length) return;
  const W = box.clientWidth || 600, H = box.clientHeight || 320;
  if (!opts.keep || !MAPAT.on){
    const lats = points.map(p => p[0]), lons = points.map(p => p[1]);
    const top = Math.max(...lats), bottom = Math.min(...lats);
    const left = Math.min(...lons), right = Math.max(...lons);
    /* The closest zoom at which every point fits with a margin - and never
       closer than a street, because one photograph shown at zoom 19 is a
       picture of a roof. */
    let z = 15;
    for (; z > 1; z--){
      const a = mapPx(top, left, z), b = mapPx(bottom, right, z);
      if (b[0] - a[0] < W * 0.8 && b[1] - a[1] < H * 0.8) break;
    }
    const c = mapPx((top + bottom) / 2, (left + right) / 2, z);
    MAPAT.z = z; MAPAT.cx = c[0]; MAPAT.cy = c[1]; MAPAT.on = true;
  }
  paintMap(points, opts);
  if (opts.interactive && !box.dataset.live){
    box.dataset.live = "1";
    mapGrips(box, points, opts);
  }
}

function paintMap(points, opts){
  const box = document.getElementById("pmmap");
  if (!box) return;
  const W = box.clientWidth || 600, H = box.clientHeight || 320;
  const z = MAPAT.z;
  const ox = MAPAT.cx - W / 2, oy = MAPAT.cy - H / 2;
  const n = Math.pow(2, z);
  let tiles = "";
  for (let tx = Math.floor(ox / 256); tx <= Math.floor((ox + W) / 256); tx++)
    for (let ty = Math.floor(oy / 256); ty <= Math.floor((oy + H) / 256); ty++){
      if (ty < 0 || ty >= n) continue;
      const wx = ((tx % n) + n) % n;
      tiles += `<img alt="" loading="lazy" draggable="false"
        src="https://tile.openstreetmap.org/${z}/${wx}/${ty}.png"
        style="left:${Math.round(tx * 256 - ox)}px;top:${Math.round(ty * 256 - oy)}px"
        onerror="this.remove()">`;
    }
  const dots = points.map((p, i) => {
    const [x, y] = mapPx(p[0], p[1], z);
    const count = p[3];
    const where = `left:${Math.round(x - ox)}px;top:${Math.round(y - oy)}px`;
    const title = `${esc(p[2])}  ${p[0].toFixed(5)}, ${p[1].toFixed(5)}`;
    if (count == null)
      return `<span class="pmdot" style="${where}" title="${title}"></span>`;
    /* A pin that says how many is a pin you can read at a glance - and one you
       can press, which is the whole reason the screen exists. */
    return `<button type="button" class="pmpin" data-i="${i}" style="${where}"
      title="${title}">${num(count)}</button>`;
  }).join("");
  box.innerHTML = tiles + dots
    + (opts.interactive ? `<div class="pmzoom">
        <button type="button" onclick="mapZoom(1)" aria-label="Zoom in">+</button>
        <button type="button" onclick="mapZoom(-1)" aria-label="Zoom out">\u2212</button>
      </div>` : "");
  /* The pins are pressed through the BOX, not through themselves. Every pan and
     every zoom rewrites this element's contents, so a handler hung on a pin is
     a handler on an element that is about to be thrown away - which is why
     pressing one did nothing with a mouse and worked on a tablet, where a tap
     does not move the map first. One listener, on the thing that survives. */
  if (opts.pick) box.onclick = ev => {
    if (MAPAT.dragged) return;               // that was a drag, not a press
    const hit = ev.target.closest(".pmpin");
    if (!hit || !box.contains(hit)) return;
    const one = (MAPPOINTS || points)[+hit.dataset.i];
    if (one) opts.pick(one);
  };
}

function mapZoom(by, at){
  const box = document.getElementById("pmmap");
  if (!box) return;
  const z = Math.max(1, Math.min(18, MAPAT.z + by));
  if (z === MAPAT.z) return;
  const k = Math.pow(2, z - MAPAT.z);
  /* Zoom about a point rather than about the middle, so the thing you are
     looking at stays where you are looking. */
  const W = box.clientWidth, H = box.clientHeight;
  const fx = at ? at[0] : W / 2, fy = at ? at[1] : H / 2;
  const wx = MAPAT.cx - W / 2 + fx, wy = MAPAT.cy - H / 2 + fy;
  MAPAT.cx = wx * k - (fx - W / 2);
  MAPAT.cy = wy * k - (fy - H / 2);
  MAPAT.z = z;
  if (MAPPOINTS) paintMap(MAPPOINTS, MAPOPTS);
}

let MAPPOINTS = null, MAPOPTS = {};

function mapGrips(box, points, opts){
  MAPPOINTS = points; MAPOPTS = opts;
  let down = null;
  box.addEventListener("pointerdown", e => {
    if (e.target.closest(".pmzoom")) return;
    /* A press on a pin starts no drag and captures no pointer: capturing it
       would make the browser deliver the click to the map instead of to the
       pin, which is the other half of why pressing one did nothing. */
    if (e.target.closest(".pmpin")) return;
    down = {x: e.clientX, y: e.clientY, cx: MAPAT.cx, cy: MAPAT.cy, moved: false};
    MAPAT.dragged = false;
    box.setPointerCapture(e.pointerId);
  });
  box.addEventListener("pointermove", e => {
    if (!down) return;
    const dx = e.clientX - down.x, dy = e.clientY - down.y;
    /* Nothing happens for the first few pixels. A mouse moves a little between
       pressing and letting go, and repainting the map on that is what used to
       replace the pin under the cursor mid-click. */
    if (!down.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    if (!down.moved){ down.moved = true; box.classList.add("dragging"); }
    MAPAT.cx = down.cx - dx;
    MAPAT.cy = down.cy - dy;
    paintMap(MAPPOINTS, MAPOPTS);
  });
  const up = () => {
    MAPAT.dragged = !!(down && down.moved);
    down = null;
    box.classList.remove("dragging");
    // let the click that follows this pointerup see that it was a drag, then
    // forget, or the next real press would be swallowed too
    setTimeout(() => { MAPAT.dragged = false; }, 0);
  };
  box.addEventListener("pointerup", up);
  box.addEventListener("pointercancel", up);
  /* ONE NOTCH IS NOT ONE ZOOM LEVEL. A wheel notch is 100 or 120, a trackpad
     sends a stream of 4s, and a map that jumped a whole level per event went
     from a street to a continent in a flick. The turning is added up and a
     level is crossed when it is really meant. */
  let rolled = 0, lastRoll = 0;
  box.addEventListener("wheel", e => {
    e.preventDefault();
    const now = Date.now();
    if (now - lastRoll > 400) rolled = 0;       // a new gesture, not the same one
    lastRoll = now;
    rolled += e.deltaY * (e.deltaMode === 1 ? 20 : e.deltaMode === 2 ? 200 : 1);
    const STEP = 220;
    if (Math.abs(rolled) < STEP) return;
    const by = rolled < 0 ? 1 : -1;
    rolled = 0;
    const r = box.getBoundingClientRect();
    mapZoom(by, [e.clientX - r.left, e.clientY - r.top]);
  }, {passive: false});
}


/* ---------------------------------------------------------------- the guide
   A tour, not a manual: one idea a page, and a button to the feature it is
   about. It remembers the page you were on, because a guide that starts again
   from Welcome every time is one you stop opening. */
let GPAGE = 0;
function guideOpen(){
  try{ GPAGE = Math.min(GUIDE.length - 1,
                        Math.max(0, +localStorage.getItem("pm-guide") || 0)); }
  catch(e){ GPAGE = 0; }
  document.getElementById("guidebox").hidden = false;
  drawGuide();
  document.getElementById("gnext").focus();
}
let GDRAWER = false;
function guideClose(){
  document.getElementById("guidebox").hidden = true;
  guideSpot(null);
  if (GDRAWER){ closeDrawer(); GDRAWER = false; }
  document.body.classList.remove("guiding");
}
function guideGo(n){
  GPAGE = Math.max(0, Math.min(GUIDE.length - 1, n));
  try{ localStorage.setItem("pm-guide", GPAGE); }catch(e){}
  drawGuide();
}
function guideTarget(g){
  /* What the page is about, on the screen: the feature in the menu, or the
     one control a page is about. Nothing when it is an idea, not a place. */
  if (g.spot){
    const el = document.querySelector(g.spot);
    if (el && el.getClientRects().length) return el;
  }
  if (!g.open) return null;
  /* In the library the features are in the rail, under their group - and
     shut away there, so lighting one means opening its group first. */
  return typeof shellOn === "function" && shellOn() ? railTarget(g.open) : null;
}
function guideSpot(el){
  const ring = document.getElementById("gspot");
  const box = document.getElementById("guidebox");
  const card = box.querySelector(".gcard");
  if (!el){
    ring.hidden = true; box.classList.remove("spotting");
    card.style.left = card.style.top = ""; return;
  }
  const r = el.getBoundingClientRect();
  const pad = 5;
  ring.hidden = false;
  box.classList.add("spotting");
  Object.assign(ring.style, {left: (r.left - pad) + "px", top: (r.top - pad) + "px",
    width: (r.width + pad * 2) + "px", height: (r.height + pad * 2) + "px"});
  /* The card sits beside what it is talking about at a desk, never on top of
     it. On a phone it stays at the bottom, and the menu is scrolled so the
     lit line is above it. */
  if (!isPhone()){
    const w = card.offsetWidth, h = card.offsetHeight;
    let left = r.right + 18, top = r.top - 24;
    if (left + w > innerWidth - 12) left = Math.max(12, r.left - w - 18);
    top = Math.max(12, Math.min(innerHeight - h - 12, top));
    card.style.left = left + "px"; card.style.top = top + "px";
  } else { card.style.left = card.style.top = ""; }
}
function drawGuide(){
  const g = GUIDE[GPAGE];
  document.getElementById("guidecount").textContent = `${GPAGE + 1} of ${GUIDE.length}`;
  document.getElementById("gtitle").textContent = g.title;
  document.getElementById("gbody").innerHTML =
    (g.svg ? `<div class="gart"><svg viewBox="0 0 320 130" aria-hidden="true">${g.svg}</svg></div>` : "")
    + g.body.map(b => `<p>${esc(b)}</p>`).join("");
  document.getElementById("gdots").innerHTML = GUIDE.map((_, i) =>
    `<button type="button" class="gdot${i === GPAGE ? " on" : ""}"
       aria-label="Page ${i + 1}" onclick="guideGo(${i})"></button>`).join("");
  const open = document.getElementById("gopen");
  const t = g.open ? byName(g.open) : null;
  open.hidden = !t;
  if (t) open.textContent = `Open ${t.title} ›`;
  open.onclick = () => { guideClose(); show(g.open); };
  document.getElementById("gprev").disabled = GPAGE === 0;
  const next = document.getElementById("gnext");
  next.textContent = GPAGE === GUIDE.length - 1 ? "Done" : "Next";
  const card = document.querySelector("#guidebox .gcard");
  card.classList.remove("turn"); void card.offsetWidth; card.classList.add("turn");
  // light up the feature it is about
  const inNav = (g.open && !g.spot) || g.spot === "#rail";
  /* The rail goes into the drawer at a wider width than "a phone", so in the
     library it is asked whether it is on the screen rather than guessed. */
  const shut = typeof shellOn === "function" && shellOn() ? railShut() : isPhone();
  if (inNav && shut && !document.body.classList.contains("drawer")){
    openDrawer(); GDRAWER = true;
  } else if (!inNav && GDRAWER){ closeDrawer(); GDRAWER = false; }
  /* Room under the list while the card covers the bottom of the drawer, so
     the last group (Settings) can be scrolled up above it. */
  document.body.classList.toggle("guiding", GDRAWER);
  const el = guideTarget(g);
  if (el && (isPhone() || GDRAWER)){
    const nav = document.getElementById("rail");
    if (nav && nav.contains(el) && nav !== el)
      nav.scrollTop = Math.max(0, el.offsetTop - nav.clientHeight * .18);
  }
  guideSpot(null);
  setTimeout(() => guideSpot(guideTarget(g)), GDRAWER ? 220 : 0);
}
function bindGuide(){
  /* The guide lives at the foot of the menu, not floating in a corner: a
     round button over the page sat on top of Setup on a phone, and on
     whatever was lowest on the screen held sideways. */
  document.getElementById("gclose").onclick = guideClose;
  document.getElementById("gprev").onclick = () => guideGo(GPAGE - 1);
  document.getElementById("gnext").onclick = () =>
    GPAGE === GUIDE.length - 1 ? guideClose() : guideGo(GPAGE + 1);
  document.getElementById("guidebox").onclick = e => {
    if (e.target.id === "guidebox") guideClose();
  };
  addEventListener("resize", () => {
    if (!document.getElementById("guidebox").hidden) guideSpot(guideTarget(GUIDE[GPAGE]));
  });
  addEventListener("keydown", e => {
    if (document.getElementById("guidebox").hidden) return;
    if (e.key === "Escape") guideClose();
    else if (e.key === "ArrowRight") guideGo(GPAGE + 1);
    else if (e.key === "ArrowLeft") guideGo(GPAGE - 1);
  });
}
bindGuide();

/* The features are up. The library goes in front of them. */
boot().then(() => { if (typeof shellStart === "function") shellStart(); });
