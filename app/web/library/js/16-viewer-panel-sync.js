
/* The side panel keeps up with the viewer. One line, at the one place the
   viewer changes what it is showing - rather than every caller remembering to
   say so, which is how it came to be told once and then never again. */
const shellViewerShow = viewerShow;
viewerShow = function(dir){
  const out = shellViewerShow(dir);
  infoReady();
  followShot();
  return out;
};
