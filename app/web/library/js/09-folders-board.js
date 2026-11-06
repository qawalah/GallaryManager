
/* ------------------------------------------------- the folders, on the home

   The one thing the old Library tab could tell you that nothing else can:
   WHICH SHOOTS ARE NOT FINISHED. Not how many photographs there are - which
   folder you walked away from halfway through rating.

   It used to cost a minute behind a button, because answering it properly
   means reading the front of every JPEG over SMB. The index has already read
   them, so here it is simply on the screen, rolled up, with the three marks
   that matter and a filter for the only question anybody opens it with. The
   Library tab still has the whole survey - previews and negatives in their own
   trees, which the index does not see - and says the same thing about the part
   they share. */

let BOARD = null;             // the folder tree, kept so Home redraws for free
let FONLY = "all";            // which folders it is showing

async function drawFolderBoard(again){
  const box = document.getElementById("homefolders");
  if (!box) return;
  if (!BOARD || again){
    box.innerHTML = `<div class="card"><b>Your folders</b>
      <div class="note" style="margin-top:6px">Reading the index...</div></div>`;
    try{
      BOARD = await (await fetch("api/folders?only=" + encodeURIComponent(FONLY))).json();
    }catch(e){
      box.innerHTML = couldNotReach("The folder board could not be read.");
      return;
    }
  }
  if (SCREEN !== "home") return;
  /* THE LIBRARY TAB'S OWN TABLE. Not a second one that looks like it: the same
     `treeCard` and `drawTree` from page.py, the same columns, the same column
     picker, the same three pips, the same click-a-mark-to-open-that-feature.
     What differs is where the numbers came from - the index rather than a
     survey of five trees - and the line under the heading says so. */
  const chips = (BOARD.onlys || []).map(([key, label]) =>
    `<button type="button" class="fchip${key === FONLY ? " on" : ""}"
      onclick="foldOnly('${key}')">${esc(label)}</button>`).join("");
  box.innerHTML = `<div class="fchips" style="margin-bottom:8px">${chips}</div>`
    + (BOARD.rows && BOARD.rows.length
       ? treeCard({tree: BOARD.rows})
       : nothingHere({icon: "folder", title: "No folder answers to that",
                      said: "Every folder in the library is finished, as far as "
                          + "the index can see.",
                      acts: [{label: "Show them all",
                              go: "foldOnly('all')"}]}))
    + `<div class="card"><span class="note">${esc(say("boardNote", {at: BOARD.measured || ""}))}</span>
       <div class="act" style="margin-top:10px">
         <button class="ghost" onclick="openFeature('library')">The whole survey</button>
       </div></div>`;
  if (BOARD.rows && BOARD.rows.length) drawTree(BOARD.rows);
}

/* The column picker lives in page.py and redraws the plan it was built for.
   On Home there is no plan - this is the same table over the index - so it
   needs a way to say "and that one". */
function boardTreeRedraw(){
  if (SCREEN === "home" && BOARD && BOARD.rows && document.getElementById("treebody"))
    drawFolderBoard();
}

function foldOnly(key){
  FONLY = key;
  BOARD = null;
  drawFolderBoard(true);
}

/* A folder on this board is a folder in the grid - the same files, by the same
   index - so pressing it goes there rather than opening a second way of
   looking at the same thing. Folder view, and straight to that heading. */
async function showFolder(path){
  if (typeof closeMenu === "function") closeMenu();
  FILTER = {};
  ALBUM = "";
  VIEWBY = "folder";
  try{ localStorage.setItem("pm-viewby", "folder"); }catch(e){}
  goScreen("photos");
  for (let wait = 0; wait < 40 && !GROUPS.length; wait++)
    await new Promise(r => setTimeout(r, 50));
  if (GROUPS.some(g => g.key === path)) jumpGroup(path);
}
