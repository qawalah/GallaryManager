
/* ------------------------------------------------------------------ going back

   Six screens, forty-eight features and no way back. You press a folder on the
   board, which opens the grid; from a photograph you open Tag photos; and the
   way back to where you were is to work out where you were.

   So: a trail. Every move writes down the place being LEFT - which screen, with
   which filters and which album, or which feature - and Back returns to it and
   forgets it. Each step of the trail is also one entry in the browser's
   history, and the two move together: the arrow on the page asks the browser
   to go back, and the browser's going back is what takes the step. One source
   of truth, so ten presses of the page's arrow do not leave ten entries
   behind for the browser's own Back to do nothing with. */

const TRAIL = [];
const TRAILMAX = 40;
let GOINGBACK = false;      // true while Back is moving, so it records nothing
let TRAILON = false;        // the app starting up is not somewhere you have been
let OPENING = false;        // one move, even though it is two calls

function hereNow(){
  if (SCREEN === "feature")
    return {kind: "feature", name: (typeof CURRENT === "object" && CURRENT
                                    ? CURRENT.name : ""), fam: TOOLFAM};
  return {kind: "screen", name: SCREEN, album: ALBUM, fam: TOOLFAM,
          filter: Object.assign({}, FILTER), by: VIEWBY};
}

function sameSpot(a, b){
  try{ return JSON.stringify(a) === JSON.stringify(b); }
  catch(e){ return false; }
}

function trailPush(spot){
  if (!TRAILON || GOINGBACK || !spot || !spot.name) return;
  if (sameSpot(TRAIL[TRAIL.length - 1], spot)) return;
  TRAIL.push(spot);
  if (TRAIL.length > TRAILMAX) TRAIL.shift();
  /* The browser's own Back lands here too. One entry per move, with no change
     to the address, so a feature's #name link still means what it meant. */
  try{ history.pushState({pmback: TRAIL.length}, ""); }catch(e){}
  drawBack();
}

function drawBack(){
  const b = document.getElementById("back");
  if (!b) return;
  b.innerHTML = icon("back");
  b.onclick = goBack;
  b.hidden = !TRAIL.length;
  const last = TRAIL[TRAIL.length - 1];
  b.title = last
    ? `Back to ${last.kind === "feature" ? (featureTitle(last.name) || "what you had open")
                                         : screenTitle(last.name)} (Alt and left arrow)`
    : "Back";
}

function screenTitle(name){
  const said = {home: "Home", photos: "Photos", places: "Places",
                albums: "Albums", people: "People", tools: "Tools"};
  return said[name] || name;
}

function featureTitle(name){
  const t = typeof byName === "function" ? byName(name) : null;
  return t ? t.title : "";
}

function goBack(){
  /* The viewer is a place too: Back closes it rather than leaving the screen
     out from under it. */
  if (document.getElementById("viewer")){ viewerClose(); return; }
  if (!TRAIL.length) return;
  /* The browser takes the step, and its popstate does the moving - so the
     trail and the history cannot drift apart. Only when the entry on top is
     not one of ours (the browser refused pushState) is the step taken here. */
  if (history.state && history.state.pmback){
    try{ history.back(); return; }catch(e){}
  }
  stepBack();
}

function stepBack(){
  const spot = TRAIL.pop();
  drawBack();
  if (!spot) return;
  GOINGBACK = true;
  try{
    if (spot.kind === "feature" && spot.name) show(spot.name);
    else goScreen(spot.name, {filter: spot.filter || {}, album: spot.album || "",
                              fam: spot.fam || ""});
    if (spot.by && spot.by !== VIEWBY && spot.kind !== "feature"){
      VIEWBY = spot.by;
      if (SCREEN === "photos") drawPhotos();
    }
  } finally {
    GOINGBACK = false;
  }
}

/* Every way into a new place goes through one of these two, so this is the
   whole of it: record where we were, then move. */
const featureOpen = openFeature;
openFeature = function(name, opts){
  OPENING = true;
  try{ return featureOpen(name, opts); }
  finally{ OPENING = false; }
};

const screenGo = goScreen;
goScreen = function(name, how){
  trailPush(hereNow());
  const out = screenGo(name, how);
  drawBack();
  return out;
};

const shellShow = show;
show = function(name){
  /* `openFeature` is two calls - move to the feature screen, then draw the
     feature - and it has already recorded where you were. A push from here as
     well would record the half-finished state in between: on the feature
     screen, with the PREVIOUS feature still current. That is a place nobody
     was ever in, and it was the place Back went to. */
  /* Opening a feature straight from a library screen - the header's History,
     a job row, the guide's "Open it" - is a move too, and Back has to return
     to the screen it was opened from. */
  if (!OPENING && (SCREEN !== "feature" || !CURRENT || CURRENT.name !== name))
    trailPush(hereNow());
  const out = shellShow(name);
  drawBack();
  return out;
};

/* The browser's own Back, and the page's arrow through it. Nothing else adds
   history entries - a feature writes its name into the address without
   adding one - so one entry here is one step of the trail. */
addEventListener("popstate", () => {
  if (!shellOn()) return;
  /* With a photograph open the browser's Back closes it, as the arrow does -
     and the entry it used is put back, because the trail did not move. */
  if (document.getElementById("viewer")){
    viewerClose();
    if (TRAIL.length) try{ history.pushState({pmback: TRAIL.length}, ""); }catch(e){}
    return;
  }
  if (!TRAIL.length) return;
  stepBack();
});

addEventListener("keydown", e => {
  if (!shellOn()) return;
  if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  if (e.altKey && e.key === "ArrowLeft"){ e.preventDefault(); goBack(); }
});

