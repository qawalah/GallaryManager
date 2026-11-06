
/* ----------------------------------------------------------- the pinned few

   Five screens and forty-eight features is the right shape for a library and
   the wrong shape for the two things one particular person does every single
   day. Which two is different for everybody, so it is not a decision this app
   can make - it is a pin, on the feature itself, and what it pins sits at the
   top level of the rail beside Home and Photos. */

function pinnedRow(name){
  const t = typeof byName === "function" ? byName(name) : null;
  if (!t) return "";
  const on = SCREEN === "feature" && CURRENT && CURRENT.name === name;
  /* The cross is a button of its own beside the row, not a span inside it: a
     button in a button cannot be reached by Tab, and it showed only on hover,
     so without a mouse there was no way to unpin at all. */
  const label = t.tab || t.title;
  return `<div class="pinwrap"><button type="button" class="railrow pinned${on ? " on" : ""}"
    data-p="${esc(name)}" onclick="openFeature('${quoted(name)}')"
    title="${esc(t.line || t.summary || "")}">${icon(t.icon)}
    <span>${esc(label)}</span></button>
    <button type="button" class="unpin" aria-label="Take ${esc(label)} off the main list"
      title="Take it off the main list"
      onclick="pinToggle('${quoted(name)}')">${icon("cross")}</button></div>`;
}

async function pinToggle(name){
  if (!name) return;
  const want = PINNED.indexOf(name) >= 0
    ? PINNED.filter(p => p !== name) : PINNED.concat([name]);
  try{
    const got = await (await fetch("api/pinned", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pinned: want})})).json();
    PINNED = got.pinned || [];
  }catch(e){ return toast("That did not reach the app", 4000); }
  drawRail();
  if (SCREEN === "feature" && CURRENT) show(CURRENT.name);
  const t = byName(name);
  toast(PINNED.indexOf(name) >= 0
    ? `${(t && (t.tab || t.title)) || "It"} is on the main list`
    : `Taken off the main list`, 2600);
}
