
/* ------------------------------------------------------ the guide, in the rail

   The guide was written for the old sidebar, where every feature was a line
   you could always see. In the library they are in the rail, inside a group
   that is shut until you open it - so the tour opens the group the page is
   about, and lights the feature in it. Without this every page about a
   feature lit nothing, and the card jumped to the corner of the screen. */

function railTarget(name){
  const t = byName(name);
  if (!t) return null;
  const fams = [...((typeof FAMILIES !== "undefined" && FAMILIES) || []), SETFAM];
  // a tab is listed under its group too; failing that, its parent is
  const fam = fams.find(f => f.tasks.indexOf(name) >= 0)
    || (t.parent && fams.find(f => f.tasks.indexOf(t.parent) >= 0));
  if (!fam) return null;           // in the Bin: nowhere to point at
  if (RAILFAM !== fam.key){ RAILFAM = fam.key; drawRail(); }
  const rail = document.getElementById("rail");
  return rail.querySelector(`.railkids [data-t="${CSS.escape(name)}"]`)
    || (t.parent && rail.querySelector(`.railkids [data-t="${CSS.escape(t.parent)}"]`))
    || rail.querySelector(`[data-fam="${CSS.escape(fam.key)}"]`);
}

/* Off the side of the screen, waiting in the drawer. */
function railShut(){
  const rail = document.getElementById("rail");
  if (!rail) return false;
  return rail.getBoundingClientRect().right <= 1;
}
