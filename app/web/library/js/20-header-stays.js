
/* ------------------------------------------------------- the header stays put

   The header is stuck to the top of the window at every width now, and the
   only thing it needs from a script is to know when something has scrolled
   under it, so a soft shadow can say so. Nothing is measured on every scroll:
   one boolean, changed only when it changes. */
let SCROLLED = null;
function headerShadow(){
  const on = (window.scrollY || document.documentElement.scrollTop || 0) > 2;
  if (on === SCROLLED) return;
  SCROLLED = on;
  document.body.classList.toggle("scrolled", on);
}
addEventListener("scroll", headerShadow, {passive: true});
headerShadow();
