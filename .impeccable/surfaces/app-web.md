---
version: 1
slug: "app-web"
primary_target: "app/web"
related_targets: ["app/web/page/style.css","app/web/library"]
---

# The whole page (app/web): Exhibition catalogue redesign

Scope: every screen of the served page (frame, Home, Photos, viewer, Places, Albums, People, All tools, every tool page with its four steps, Settings, Guide, login). Mode: Operate.
Audience and job: enthusiast photographers and family-library owners putting a folder library in order; desk for big runs, phone on the LAN for looks and ratings (PRODUCT.md).
Asked for (ALI, 2026-10-21): bolder, easier to look at and use; photos the star, gallery-like and dark, with room for tools and settings to breathe; sleek transitions that fit.
Constraints: no tool or option disappears; the four steps stay; theme, accent and frame choices in Settings stay (new look becomes the default, the old one stays choosable); standard library, no build step, no fonts or scripts from the internet; WCAG 2.2 AA; wording rules in core/wording.py.
Memorable moment: Check the list read as a catalogue checklist, the count set at plate size.
Unresolved: none blocking. Pricing is undecided and appears nowhere.

## Direction contract

THESIS: The app is typeset like a museum photography catalogue: photographs are the plates, everything else is set around them with strict type, hairline rules and numbered sections. It refuses the category default of grey SaaS cards nested in cards, pastel KPI tiles, rounded everything and one blue accent.

OWN-WORLD: Black catalogue stock by default (near-black ground, a half-step lighter surface, bone ink, warm grey secondary ink, hairline rules), white stock in light mode. Square corners (2px), no shadows on flat surfaces, rules instead of boxes. Primary actions printed in solid ink (bone on black, black on white). Five section inks, one per tool group, kept on the tones core/families.py already gives each group (Organize cobalt, Metadata viridian, Review ochre, Develop violet, Maintain and Settings warm grey), each at 4.5:1 or better as text on both stocks, used as section bands, markers and the lit step. Tabular numerals; one type scale 12/13/14/16/20/28/40/64. No kickers or eyebrows above headings (craft floor).

STORY: The visitor sees their photos first, knows which section of the catalogue they are in from its colour and number, reads every run as a checklist before it happens, and moves between screens without losing their place.

FIRST VIEWPORT (Home, desktop): rail left on the stock, section colour markers beside group names. Main column: screen title at 40px with the index line under it; then the latest photos as a band of large plates (first plate twice the width), wall-label captions under each; then one ruled row of four catalogue facts with 40px tabular numerals; dashboard below. Phone: the plates band scrolls sideways under the title, bottom tabs stay. Tool pages: a 4px band in the group's ink across the top of the form, the group's name heading the list beside the form, title at 28px, step strip as numbered catalogue tabs; Check the list ends in the checklist: count at 64px, verb line, facts in two ruled columns, a solid ink button.

FORM: Exhibition catalogue (International Typographic Style photography catalogue), candidate 6 of 7 on the resonance list; seed key 85502d26 (degraded roll, no challengers). Signature move: the catalogue checklist and section inks. Motion grammar: screens enter like a turned spread (fade with a short horizontal travel, 280ms), photos fade up in sequence, the lit step slides; all off under reduced motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
