/* ------------------------------------------------ Setup changes, everywhere

   Change the library in Setup and every other place has to follow it - and
   for a while most of them did not. The page reads the settings once, when it
   opens, and keeps copies of them: each form remembers what was in its boxes
   when you left it (SEEN), Photos keeps its folder board and its menus, and
   the shortened paths are worked out from the trees. Setup's own Save re-read
   the task list, but a form you had already opened came back with the boxes
   it was left with - so Search went on searching the old library. And a
   change made anywhere else (the sample library borrowing the trees, the
   command line, another browser) reached nothing at all until a reload.

   So the server says which version of the settings file it is on, in the
   health answer the page asks for every few seconds anyway, and when that
   moves the page re-reads everything drawn from it and lets each copy follow.
   A box only follows if it still holds what Setup used to say: a folder you
   typed into a form yourself is yours, and stays. */

let SETTINGS_STAMP = "";

/* Each health answer. The first one only notes where things stand. */
function settingsStamped(h){
  const now = String((h && h.settings) || "");
  if (!now) return;
  if (!SETTINGS_STAMP){ SETTINGS_STAMP = now; return; }
  if (now === SETTINGS_STAMP) return;
  SETTINGS_STAMP = now;
  if (TASKS.length) refreshTasks();
}

/* What each setting-backed box started as, per task. */
function settingValues(tasks){
  const out = {};
  for (const t of tasks || [])
    for (const o of t.options || [])
      if (o.setting) out[t.name + "/" + o.name] = o.default;
  return out;
}

const sameText = (a, b) =>
  String(a == null ? "" : a).trim() === String(b == null ? "" : b).trim();

/* After the task list has been re-read. `was` is the list it replaced and
   `wasRoots` the trees as they were. */
function followSettings(was, wasRoots){
  const before = settingValues(was), after = settingValues(TASKS);
  const running = WATCH && WATCH.task;
  for (const key of Object.keys(after)){
    if (!(key in before) || sameText(before[key], after[key])) continue;
    const [task, name] = key.split("/");
    const box = SEEN[task];
    if (box && box.values && name in box.values
        && sameText(box.values[name], before[key])){
      box.values[name] = after[key];
      /* Whatever that tab was showing was worked out from the old value -
         the same reason opening a folder in a tab clears it. A run still
         going is left alone: it is real, and its card is how it ends. */
      if (task !== running && box.out){ box.out = ""; box.plan = null; box.done = null; }
    }
    if (CURRENT && CURRENT.name === task){
      const el = document.getElementById("o_" + name);
      if (el && el.type !== "checkbox" && sameText(el.value, before[key])){
        el.value = after[key];
        el.dispatchEvent(new Event("input", {bubbles: true}));
        el.dispatchEvent(new Event("change", {bubbles: true}));
      }
    }
  }
  /* The open form's description of itself, so the next plan reads the new
     task list rather than the one this page opened with. */
  if (CURRENT) CURRENT = byName(CURRENT.name) || CURRENT;

  const hadPrefix = !!PREFIX;
  PREFIX = commonHome();
  if (!hadPrefix && PREFIX) watchPaths();   // nothing was being shortened yet

  if (JSON.stringify(wasRoots || []) !== JSON.stringify(ROOTS || [])
      && typeof shellOn === "function" && shellOn()){
    /* A different library is a different answer to everything Photos holds.
       Standing in one of the old library's folders is standing nowhere. */
    WHERE = "";
    forgetIndexAnswers();
    redrawLibraryScreen();
  }
}

/* What the library screens keep between draws, worked out from the index.
   Dropped whenever the index has changed under them: the folder board and the
   menus of cameras and places were kept for good, so they still listed what
   was there when the page opened. */
function forgetIndexAnswers(){
  SUMS = null;
  BOARD = null;
  CHOICES = null;
  WALL = null;
}

function redrawLibraryScreen(){
  if (SCREEN === "home") drawHomeScreen();
  else if (SCREEN === "photos") loadShots(true);
  else if (SCREEN === "albums") drawAlbums();
  else if (SCREEN === "places") drawPlaces();
  drawRail();
}
