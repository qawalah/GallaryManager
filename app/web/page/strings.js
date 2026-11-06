/* ------------------------------------------------------- the page's own words

   Every sentence the page says that is not a tool's (a toast, a dialog, the
   count under a folder) is in page/strings.json, so Setup > Wording can edit
   it and tests/test_wording.py can hold it to the style guide. STRINGS is
   that table as it shipped; WORDING carries the edits, put in by the server
   when the page is sent (app/pagetext.py), and is empty otherwise.

   S.name is a plain string. say("name", {n: 3}) fills it in: {n} is the
   value, {n:file|files} is the word for one or for any other number, so no
   sentence on the page has to say "file(s)". */

const S = Object.assign({}, STRINGS, WORDING.page || {});

for (const [at, edit] of Object.entries(WORDING.guide || {})){
  const page = GUIDE[+at];
  if (!page) continue;
  if (edit.title) page.title = edit.title;
  for (const [i, text] of Object.entries(edit.body || {})) page.body[+i] = text;
}

function say(name, vars){
  const v = vars || {};
  return String(S[name] == null ? name : S[name]).replace(
    /\{(\w+)(?::([^|}]*)\|([^}]*))?\}/g, (whole, key, one, many) => {
      if (!(key in v)) return whole;
      if (one === undefined) return typeof v[key] === "number"
        ? v[key].toLocaleString() : String(v[key]);
      return Number(v[key]) === 1 ? one : many;
    });
}

