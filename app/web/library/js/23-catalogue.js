/* ------------------------------------------------- 4.0 - the catalogue

   Three things the new look needs from the script, each wrapped round a
   function that already exists rather than written into it.

   THE SECTION INK. A page knows which group it is in: a tool by the group
   it is listed under (`sideGroup`, the same arrangement the rail draws), the
   Tools screen by the group it is showing. That group's tone goes on the
   body as `data-tone`, and library/css/14-catalogue.css turns it into one
   ink, `--sec`, for the band, the lit step and the marks.

   THE TURN. A new screen or a different tool slides in from the side you are
   going towards; Back slides it in from the other. Only on arriving: a page
   redrawn in place (Home while the index reads, a tool after a save) does
   not move.

   WHAT IS SAID. A sighted person sees a list arrive, a toast with Undo, a run
   finish. None of that reached a screen reader. Each now also goes into the
   one live region on the page (#said, index.html), in the words already on
   the screen. */

function toneOf(name){
  const f = typeof sideGroup === "function" ? sideGroup(name) : null;
  if (f) return f.tone || "grey";
  const t = typeof byName === "function" ? byName(name) : null;
  return t && t.parent ? toneOf(t.parent) : "";
}

function paintTone(tone){
  if (tone) document.body.dataset.tone = tone;
  else delete document.body.dataset.tone;
}

let TURNED = "";
let TURNTIMER = 0;
function turnPage(where, place){
  if (place === TURNED) return;
  TURNED = place;
  const box = where === "feature" ? document.querySelector("body.shell main")
                                  : document.getElementById("stage");
  if (!box) return;
  const back = typeof GOINGBACK !== "undefined" && GOINGBACK;
  /* Taken off and put back, so the same class plays again; and taken off
     for good once it has played, so whatever is drawn into the screen later
     (a list arriving, a count refreshing) does not slide in a second time. */
  box.classList.remove("turn", "back");
  void box.offsetWidth;
  box.classList.add("turn");
  box.classList.toggle("back", back);
  clearTimeout(TURNTIMER);
  TURNTIMER = setTimeout(() => {
    /* Only the two screens: the Guide's card has a `turn` of its own. */
    document.querySelectorAll("#stage.turn, main.turn")
      .forEach(el => el.classList.remove("turn", "back"));
  }, 700);
}

const catalogueShow = show;
show = function(name){
  const out = catalogueShow(name);
  paintTone(toneOf(name) || "grey");
  if (shellOn()) turnPage("feature", "feature:" + name);
  return out;
};

const catalogueGo = goScreen;
goScreen = function(name, how){
  const out = catalogueGo(name, how);
  if (name !== "feature"){
    const fam = name === "tools" && TOOLFAM && typeof famByKey === "function"
      ? famByKey(TOOLFAM) : null;
    paintTone(fam ? fam.tone || "grey" : "");
    turnPage("screen", name + ":" + (TOOLFAM || "") + ":" + (ALBUM || ""));
  }
  return out;
};

/* ------------------------------------------------------------- what is said */

function announce(text){
  const box = document.getElementById("said");
  text = String(text || "").replace(/\s+/g, " ").trim();
  if (!box || !text) return;
  /* Emptied first and filled a moment later: a live region that is given the
     same words twice says nothing the second time. */
  box.textContent = "";
  setTimeout(() => { box.textContent = text; }, 80);
}

/* A toast carrying a button (Undo, above all) stays long enough to be
   reached: two and a half seconds was gone before a keyboard got to it. */
const catalogueToast = toast;
toast = function(text, ms, action, fn){
  const out = catalogueToast(text, action ? Math.max(ms || 0, 6000) : ms, action, fn);
  announce(action ? `${text}. ${action}` : text);
  return out;
};

/* The list, or the sentence saying there is nothing to do. The apply card is
   read as its headline and its operation: "Nothing has been written yet.
   Operation: Move 412 files". Anything else as its first line. */
const catalogueRender = render;
render = function(p){
  const out = catalogueRender(p);
  const box = document.getElementById("out");
  const apply = box && box.querySelector("#apply");
  if (apply){
    const head = apply.querySelector(".ckhead");
    const op = apply.querySelector(".ckcount")
      || apply.querySelector(".changing > div:nth-child(2)");
    announce((head ? head.textContent + " " : "") + (op ? op.textContent : ""));
  } else if (box){
    const first = box.querySelector(".card b") || box.querySelector(".card");
    if (first) announce(first.textContent);
  }
  return out;
};

/* What happened: the headline and the four counters, "Done. Done 412,
   Failed 0". */
const catalogueFinish = finish;
finish = function(state){
  const out = catalogueFinish(state);
  const card = document.getElementById("apply");
  if (card){
    const head = card.querySelector("b");
    const counts = [...card.querySelectorAll(".outcome > div")]
      .map(d => d.textContent.replace(/\s+/g, " ").trim()).join(", ");
    announce([head ? head.textContent : "", counts].filter(Boolean).join(". "));
  }
  return out;
};

/* Skip to the page: the tool's form when one is open, the screen otherwise. */
(function(){
  const link = document.getElementById("skiplink");
  if (!link) return;
  link.addEventListener("click", e => {
    e.preventDefault();
    const onTool = document.body.classList.contains("onfeature")
      || !document.body.classList.contains("shell");
    const to = document.getElementById(onTool ? "form" : "stage");
    if (!to) return;
    to.setAttribute("tabindex", "-1");
    to.focus();
  });
})();
