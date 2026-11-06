/* ------------------------------------------------- Search and Photos, both ways

   Two screens that ask the same question with the same criteria (core/find.py
   reads both) of two different things. Photos asks the library index: quick,
   and only as complete as the index is. Search reads the folders themselves:
   slower, any folder, and exactly as the files are now. Each one hands its
   criteria to the other, so changing your mind is one press and not every box
   typed again. */

const READS_INDEX = "Photos reads the library index. Search reads the folders "
  + "themselves, any folder, as they are now.";

/* From the Photos filter panel to Search, with what is in the panel - applied
   or not - under the same names Search's options use. Filled in, not run: the
   point of going to Search is usually to pick a folder first. */
function searchInstead(){
  const box = document.getElementById("filters");
  const ask = {};
  if (box) box.querySelectorAll("[data-f]").forEach(el => {
    const v = String(el.value || "").trim();
    if (v) ask[el.dataset.f] = v;
  });
  const keys = typeof SEARCHKEYS !== "undefined" ? SEARCHKEYS : [];
  for (const k of Object.keys(ask)) if (keys.indexOf(k) < 0) delete ask[k];
  openFeature("search");
  setTimeout(() => searchFill(ask), 90);
}

/* Is every folder a search looked in part of the library? Only then can the
   index show the same photographs; a search of another drive cannot be. Paths
   that look like Windows ones are compared without case, as Windows does. */
function underLibrary(folders){
  const lib = String((typeof TREES !== "undefined" && TREES.library) || "").trim();
  if (!lib) return false;
  const windowsy = /^[A-Za-z]:|^\\\\/.test(lib);
  const norm = p => {
    let s = String(p || "").trim().replace(/\\/g, "/").replace(/\/+$/, "");
    return windowsy ? s.toLowerCase() : s;
  };
  const root = norm(lib);
  const list = (folders || []).map(norm).filter(Boolean);
  if (!list.length) return true;          // an empty box means the library
  return list.every(p => p === root || p.indexOf(root + "/") === 0);
}

function searchedFolders(){
  const box = document.getElementById("o_folders");
  return box ? String(box.value || "").split("\n").map(s => s.trim()).filter(Boolean)
             : [];
}

/* From a search to Photos, with the same criteria as the grid's filter. The
   folders stay behind: the grid is the whole library, which is why the button
   is only offered when the search was inside it. */
function showInPhotos(){
  const ask = typeof searchNow === "function" ? searchNow() : {};
  delete ask.folders;
  FILTER = {};
  for (const [k, v] of Object.entries(ask))
    if (v !== "" && v != null && v !== false) FILTER[k] = v === true ? "1" : String(v);
  ALBUM = "";
  if (typeof VIEWBY !== "undefined" && VIEWBY === "folder") VIEWBY = "date";
  goScreen("photos");
}

function showInPhotosButton(){
  if (!underLibrary(searchedFolders())) return "";
  return `<button class="ghost" id="showinphotos" onclick="showInPhotos()"
    >${icon("photos")} Show in Photos</button>`;
}
