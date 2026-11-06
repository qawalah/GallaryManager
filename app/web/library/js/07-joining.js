
/* ------------------------------------------------------- joining the two halves

   `show()` is the app's own function for opening a feature and it is called
   from everywhere - the guide, the checklist, a chart you clicked. Wrapped
   rather than edited: whatever opens a feature should also put the screen on
   the feature, and there should be exactly one place that knows it. */
const featureShow = show;
show = function(name){
  const out = featureShow(name);
  if (shellOn()){
    if (SCREEN !== "feature"){
      SCREEN = "feature";
      document.body.classList.add("onfeature");
    }
    /* Every time, not only on arriving: `openFeature` has already moved to the
       feature screen and drawn the rail before this runs, so the rail was
       always marking the feature you had open BEFORE - Library lit up while
       Cull by rating was on the page. */
    drawRail();
  }
  return out;
};

/* The bar along the bottom of a phone. Same five places as the rail's top, so
   the phone and the desk are the same app rather than two. */
const SHELLBOTTOM = [["home", "home", "Home"], ["photos", "photos", "Photos"],
                     ["places", "map", "Places"], ["tools", "tools", "Tools"],
                     ["menu", "menu", "More"]];

function drawShellBottom(){
  const bar = document.getElementById("bottom");
  if (!bar || !shellOn()) return;
  bar.innerHTML = SHELLBOTTOM.map(([key, glyph, label]) =>
    `<button type="button" data-b="${key}" class="${SCREEN === key ? "on" : ""}"
      onclick="${key === "menu" ? "toggleDrawer()" : `goScreen('${key}')`}"
      >${icon(glyph)}<span>${esc(label)}</span></button>`).join("");
}

const railDraw = drawRail;
drawRail = function(){ railDraw(); drawShellBottom(); };

addEventListener("keydown", e => {
  if (!shellOn()) return;
  if (document.getElementById("viewer")) return;
  if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  if (e.key === "Escape" && PICK.size) pickClear();
});
