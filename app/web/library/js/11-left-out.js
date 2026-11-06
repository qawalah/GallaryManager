
/* ------------------------------------------------- folders left out of the grid

   Not the exclusion list in Setup, and the difference is the whole point. That
   one means NOTHING GOES IN HERE: no walk, no feature, no index - right for the
   phone dump and Synology's own folders. This means "not while I am looking":
   the scanned negatives beside the shoots are real photographs that should
   still be geotagged, counted and backed up, and you simply do not want to
   scroll past four hundred of them to find the holiday.

   One list would have made the cheap wish cost the expensive thing. */

let HIDDEN = [];

function drawHideChip(){
  const chip = document.getElementById("hidebtn");
  if (!chip) return;
  chip.hidden = !HIDDEN.length;
  chip.innerHTML = `${icon("cross")} ${esc(say("foldersHidden", {n: HIDDEN.length}))}`;
}

async function sendHidden(folders){
  try{
    const got = await (await fetch("api/hidden", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({folders: folders})})).json();
    HIDDEN = got.hidden || [];
    drawHideChip();
    loadShots(true);
    return true;
  }catch(e){ toast("That did not reach the app", 4000); return false; }
}

async function hideFolder(path){
  if (!path) return;
  if (HIDDEN.indexOf(path) >= 0) return;
  await sendHidden(HIDDEN.concat([path]));
  toast(`${path.split(/[\\/]/).pop()} is out of the Photos screen - `
        + `everything else still sees it`, 4000);
}

async function showFolderAgain(path){
  await sendHidden(HIDDEN.filter(p => p !== path));
}

function hiddenPanel(){
  const box = document.getElementById("hiddenbox");
  if (!box) return;
  if (!box.hidden){ box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = `<div class="card"><b>Left out of this screen</b>
    <span class="note"> - still indexed, still counted, still backed up. This is
      a view, not the exclusion list in Setup.</span>
    <div class="fchips" style="margin-top:10px">${HIDDEN.map(p =>
      `<button type="button" class="fchip" onclick="showFolderAgain('${quoted(p)}')"
        title="Show it again">${esc(p.split(/[\\/]/).pop() || p)} ${icon("cross")}</button>`
      ).join("") || `<span class="note">Nothing is hidden.</span>`}</div>
    <div class="act" style="margin-top:12px">
      <button class="ghost" onclick="sendHidden([])">Show everything again</button>
      <button class="ghost" onclick="hiddenPanel()">Close</button>
    </div></div>`;
}
