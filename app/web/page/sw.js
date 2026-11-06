
const SHELL = "pm-shell-__RELEASE__-__CODE__";
const PICS = "pm-thumbs-__RELEASE__";
const KEEP = [SHELL, PICS];
const NEEDED = ["./", "./icon-192.png", "./icon-512.png",
                "./font/archivo-latin.woff2", "./font/archivo-latin-ext.woff2"];
// The app page says it is the app; the sign-in page, served at the same
// address with a 200 when there is no ticket, does not.
const APP_MARK = '<meta name="pm-shell" content="app">';
// Enough thumbnails for a long scroll through the grid, and no more: every
// version of every thumbnail used to be kept for ever.
const PICS_MAX = 3000;
let PICS_PUT = 0;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(async c => {
    for (const one of NEEDED){
      const got = await fetch(one, {cache: "no-store"}).catch(() => null);
      if (got && got.ok && (one !== "./" || await isApp(got))) await c.put(one, got);
    }
  }).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(names => Promise.all(names.filter(n => !KEEP.includes(n)).map(n => caches.delete(n))))
    .then(() => self.clients.claim()));
});

// "forget" clears everything; "forget-pics" only the thumbnails, which the
// page sends when it says the pictures may have changed (freshPics).
self.addEventListener("message", e => {
  if (e.data === "forget") caches.keys().then(ns => ns.forEach(n => caches.delete(n)));
  if (e.data === "forget-pics") caches.delete(PICS);
});

async function isApp(got){
  try{ return (await got.clone().text()).includes(APP_MARK); }
  catch(e){ return false; }
}

async function trimPics(c){
  const keys = await c.keys();
  for (const k of keys.slice(0, Math.max(0, keys.length - PICS_MAX))) await c.delete(k);
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  // Thumbnails: from the store first. They are named by the file's own date and
  // size, so one that changed is a different address and can never be stale.
  if (url.pathname.endsWith("/api/thumb")){
    e.respondWith(caches.open(PICS).then(async c => {
      const had = await c.match(req);
      if (had) return had;
      const got = await fetch(req);
      if (got.ok){
        await c.put(req, got.clone());
        if (++PICS_PUT % 100 === 0) trimPics(c);
      }
      return got;
    }));
    return;
  }
  // Everything else the app asks for is live, or it is not worth having.
  if (url.pathname.includes("/api/")) return;

  // Every navigation is the same page - Reload adds ?t=<now> to get past the
  // browser's cache - so it is kept under one key, not one per address.
  const nav = req.mode === "navigate";
  e.respondWith(fetch(req).then(got => {
    if (got.ok && nav){
      // Kept beside the answer, not before it: the page is not held back
      // while its copy is read for the mark.
      const copy = got.clone();
      e.waitUntil(isApp(copy).then(ok => ok
        && caches.open(SHELL).then(c => c.put("./", copy))));
    } else if (got.ok && url.pathname.endsWith(".png")){
      caches.open(SHELL).then(c => c.put(req, got.clone()));
    }
    return got;
  }).catch(async () => {
    const had = (nav ? null : await caches.match(req)) || await caches.match("./");
    if (had) return had;
    return new Response("The app could not be reached, and this page is not "
      + "kept for offline yet.", {status: 503, headers: {"Content-Type": "text/plain"}});
  }));
});
