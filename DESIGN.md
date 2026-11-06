---
name: Photo Manager
description: A photo-library manager typeset like an exhibition catalogue, on black stock by default, with the photographs as its plates.
colors:
  accent-dark: "#f1efe9"
  accent-light: "#151514"
  on-accent-dark: "#121211"
  on-accent-light: "#ffffff"
  tone-blue-dark: "#7a9bff"
  tone-blue-light: "#2450d6"
  tone-teal-dark: "#45c79f"
  tone-teal-light: "#0d7656"
  tone-orange-dark: "#f2b33d"
  tone-orange-light: "#9a5b00"
  tone-purple-dark: "#b89cff"
  tone-purple-light: "#6a42c9"
  tone-grey-dark: "#aaa69e"
  tone-grey-light: "#67635c"
  good-dark: "#63c98a"
  good-light: "#1c7c3c"
  warn-dark: "#d9a441"
  warn-light: "#9a6b00"
  bad-dark: "#ef6d63"
  bad-light: "#b3261e"
  label-red: "#e5484d"
  label-yellow: "#f5c518"
  label-green: "#30a46c"
  label-blue: "#3e63dd"
  label-purple: "#8e4ec6"
  bg-dark: "#0f0f0e"
  card-dark: "#181817"
  ink-dark: "#f1efe9"
  dim-dark: "#a8a49c"
  line-dark: "#2e2d2a"
  wash-dark: "#232321"
  accent-soft-dark: "#2b2a27"
  bg-light: "#ffffff"
  card-light: "#ffffff"
  ink-light: "#151514"
  dim-light: "#5d5a54"
  line-light: "#dddad3"
  wash-light: "#f3f3f3"
  accent-soft-light: "#ebeae6"
typography:
  display:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "64px"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.04em"
    fontFeature: "\"tnum\" 1"
    fontVariation: "\"wdth\" 104"
  headline:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "40px"
    fontWeight: 800
    lineHeight: 1.02
    letterSpacing: "-0.03em"
    fontVariation: "\"wdth\" 110"
  figure:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "40px"
    fontWeight: 750
    lineHeight: 1.05
    letterSpacing: "-0.03em"
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "28px"
    fontWeight: 750
    lineHeight: 1.15
    letterSpacing: "-0.02em"
    fontVariation: "\"wdth\" 106"
  section:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "20px"
    fontWeight: 750
    letterSpacing: "-0.015em"
  masthead:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 800
    letterSpacing: "-0.01em"
    fontVariation: "\"wdth\" 118"
  subtitle:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    letterSpacing: "-0.005em"
  body:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  small:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    letterSpacing: "0.04em"
  caption:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "\"tnum\" 1"
  mono:
    fontFamily: "ui-monospace, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  card: "2px"
  ctl: "2px"
  pill: "2px"
  dot: "50%"
spacing:
  tile-gap: "4px"
  gutter-phone: "16px"
  card-pad: "20px 22px"
  stage: "32px 40px 72px"
  plate-gap: "20px 14px"
components:
  button-primary:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.on-accent-dark}"
    rounded: "{rounded.ctl}"
    padding: "10px 18px"
  button-primary-light:
    backgroundColor: "{colors.accent-light}"
    textColor: "{colors.on-accent-light}"
    rounded: "{rounded.ctl}"
    padding: "10px 18px"
  button-apply:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.on-accent-dark}"
    rounded: "{rounded.ctl}"
    padding: "12px 28px"
    height: "48px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.accent-dark}"
    rounded: "{rounded.ctl}"
    padding: "10px 18px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.dim-dark}"
    padding: "7px 9px"
  button-danger:
    backgroundColor: "{colors.bad-dark}"
    textColor: "{colors.on-accent-dark}"
    rounded: "{rounded.ctl}"
    padding: "10px 18px"
  button-contextual:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.ink-dark}"
    rounded: "{rounded.ctl}"
    padding: "7px 13px"
  chip-filter:
    backgroundColor: "{colors.card-dark}"
    textColor: "{colors.ink-dark}"
    typography: "{typography.small}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "36px"
  chip-filter-on:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.on-accent-dark}"
    rounded: "{rounded.pill}"
    height: "36px"
  chip-status:
    backgroundColor: "{colors.wash-dark}"
    textColor: "{colors.ink-dark}"
    typography: "{typography.small}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "36px"
  input-field:
    backgroundColor: "{colors.wash-dark}"
    textColor: "{colors.ink-dark}"
    typography: "{typography.body}"
    rounded: "{rounded.ctl}"
    padding: "9px 12px"
    height: "40px"
  rail-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink-dark}"
    typography: "{typography.body}"
    rounded: "{rounded.ctl}"
    padding: "10px 14px"
    height: "40px"
  rail-row-active:
    backgroundColor: "{colors.accent-soft-dark}"
    textColor: "{colors.ink-dark}"
    rounded: "{rounded.ctl}"
  step-tab:
    textColor: "{colors.dim-dark}"
    typography: "{typography.small}"
    padding: "12px 2px 2px"
  step-tab-now:
    textColor: "{colors.ink-dark}"
    typography: "{typography.small}"
  fact:
    textColor: "{colors.ink-dark}"
    typography: "{typography.figure}"
    padding: "16px 0 18px"
  checklist-count:
    textColor: "{colors.ink-dark}"
    typography: "{typography.display}"
  help-bubble:
    backgroundColor: "{colors.ink-dark}"
    textColor: "{colors.bg-dark}"
    typography: "{typography.body}"
    rounded: "{rounded.ctl}"
    padding: "12px 14px"
    width: "360px"
---

# Design System: Photo Manager

This file records the visual system of the served page (release 4.0, the catalogue). `docs/DESIGN.md` is a different file: it explains why the app behaves as it does.

The tokens live in the build, not here: the palette, shapes, type scale and motion at the top of `app/web/page/style.css`, the section inks at the top of `app/web/library/css/01-shell.css`, and the catalogue's own pieces in `app/web/library/css/14-catalogue.css`. Keys ending in `-dark` and `-light` above are the two values of one CSS custom property (`accent-dark` and `accent-light` are `--accent`). Dark is the default a new browser gets.

## Overview

**Creative North Star: "The Exhibition Catalogue"**

Photo Manager is set like a museum photography catalogue. The photographs are the plates, and everything else is set around them in one typeface, on one type scale, divided by hairline rules, with each section of tools opened by a band of its own ink. The default stock is black: a near-black ground, a sheet a half step lighter, bone ink, and a warm grey for the quieter line. In light mode the same page is printed on white stock in black ink.

Density follows the job. Home and Photos give the plates the room, tool pages and Settings are a column of ruled rows with space between them, and the list a run is about to apply reads as a catalogue checklist with its count at plate size. Colour is rationed. Apart from the photographs, the only colour in the chrome is the ink of the section you are in, one of five, one per group of tools. The primary action is printed in the page's own ink.

The system refuses the category default of grey cards nested in cards, pastel figure tiles, rounded everything and one blue accent. Motion is a page being turned and laid flat: quick to arrive, slow to settle, never a bounce, and nothing at all for anybody who has asked the machine for less.

**Key Characteristics:**
- Black catalogue stock by default and white stock in light mode, in one warm neutral family.
- One variable typeface, Archivo, served by the app itself, on eight sizes and nothing between.
- Every surface, control and chip cut square at 2px.
- Hairlines and ink rules instead of boxes and shadows.
- Five section inks, used only to say which group of tools something belongs to.
- Every count in tabular numerals, and the count you approve set at 64px.
- Screens turn like spreads in 280ms, and stand still under reduced motion.

## Colors

Warm black and bone, with five section inks and three state inks held in reserve.

### Primary
- **Printed Ink** (#f1efe9 on black stock, #151514 on white stock): the accent is the page's own ink. It fills the one primary button on a screen, a filter that is on, the focus ring, the text caret and progress bars. What is written on it is `on-accent` (#121211 on bone, #ffffff on black), which `app/page.py` works out from the colour so that a label never drops under contrast whatever accent is chosen.

### Secondary
The five section inks, one per group of tools in `core/families.py`, each with a value for each stock. A page gets its group's ink as `--sec` from `body[data-tone]` (`library/js/23-catalogue.js`).
- **Organize Cobalt** (`tone-blue`, #7a9bff dark, #2450d6 light): Organize, and Automation, which stands apart from the five headings.
- **Metadata Viridian** (`tone-teal`, #45c79f dark, #0d7656 light): Metadata.
- **Review Ochre** (`tone-orange`, #f2b33d dark, #9a5b00 light): Review.
- **Develop Violet** (`tone-purple`, #b89cff dark, #6a42c9 light): Develop.
- **Maintain Warm Grey** (`tone-grey`, #aaa69e dark, #67635c light): Maintain, Settings, and anything not in a group.

They appear as the 4px band over a tool's form, the 3px rule under the step you are on, the group's mark in the rail and in the list beside a tool, a Tools group's 4px band and title mark, a tool's name under the pointer on the Tools page, the mark on a selection-bar action that opens a tool of that group, the 2px band over the current phone tab, and the tint of selected text.

### Tertiary
- **Done Green** (`good`, #63c98a dark, #1c7c3c light): finished counts, a flow that is on, the tick beside a finished step.
- **Caution Amber** (`warn`, #d9a441 dark, #9a6b00 light): the trouble strip, a flow that is waiting, set stars.
- **Irreversible Red** (`bad`, #ef6d63 dark, #b3261e light): the destructive button, the 4px band over a run that cannot be undone, and its count.
- **The colour labels** (`label-red` #e5484d, `label-yellow` #f5c518, `label-green` #30a46c, `label-blue` #3e63dd, `label-purple` #8e4ec6): the five colour labels a photo can carry, the same in both modes and defined once, so a yellow is the same yellow in the grid, the menus and the viewer. They are the photo's data, not the page's chrome.

Charts on Home keep their own eight-slot categorical palette and seven-step ramp (`--s1` to `--s8`, `--q1` to `--q7` in `page/style.css`). They are data colours that predate the catalogue and are not part of this palette; every chart also carries its values as text.

### Neutral
- **Black Stock** (`bg-dark`, #0f0f0e): the ground in the default dark mode.
- **Black Sheet** (`card-dark`, #181817): the header, the rail, cards and the viewer's panel, a half step above the ground.
- **Bone Ink** (`ink-dark`, #f1efe9): all text and the 1px rules that open a printed section.
- **Warm Grey Ink** (`dim-dark`, #a8a49c): lines under titles, labels, notes, a quiet button, a step not yet reached. 7.2:1 on the sheet.
- **Dark Hairline** (`line-dark`, #2e2d2a): every divider and every card's edge.
- **Dark Wash** (`wash-dark`, #232321): a breath of ink on the sheet for a field, a value chip, a code word, a row under the pointer.
- **Dark Ink Panel** (`accent-soft-dark`, #2b2a27): where you are in the rail and in a group's list, and a header control that is on.
- **White Stock** (`bg-light` and `card-light`, #ffffff): ground and card are the same white, so a card is told by its hairline.
- **Black Ink** (`ink-light`, #151514): text and ink rules on white.
- **Warm Grey** (`dim-light`, #5d5a54): the quieter line on white, 6.9:1.
- **Light Hairline** (`line-light`, #dddad3).
- **Light Wash** (`wash-light`, #f3f3f3): `color-mix(in srgb, var(--ink) 5%, var(--card))`.
- **Light Ink Panel** (`accent-soft-light`, #ebeae6).

### Named Rules
**The Printed Ink Rule.** The primary action is printed in the page's own ink, bone on black and black on white. There is no brand colour; the blue-grey look before 4.0 is the Original theme with the Blue accent under Appearance, and the other palettes, accents and frames there are the viewer's choices, not this system.

**The Section Ink Rule.** A section ink says which group of tools something belongs to, and nothing else. Home, Photos, Places, Albums and People are in no section, so their own chrome is ink only.

**The 4.5 Rule.** Every section ink reads at 4.5:1 or better as text on the ground and on the card, in both modes. `tests/test_design.py` holds it, so a new ink is checked before it ships.

**The Never By Colour Alone Rule.** A state is said in shape and word as well as hue: the step you are on is bold and lit, a finished step has a drawn tick, a status dot is a hollow ring when off and filled when on with its word beside it, and a run that cannot be undone is banded, headed with a warning mark and counted in red.

## Typography

**Display Font:** Archivo (with system-ui, -apple-system, Segoe UI, Roboto, sans-serif)
**Body Font:** Archivo (the same file)
**Label/Mono Font:** ui-monospace (with Consolas, monospace), for paths and file names only

**Character:** One variable grotesque does every job, served by the app from two woff2 files split by script, so the page asks the internet for nothing. Weight (400 to 800) and width (100% to 118%) make the hierarchy: headings run heavy and a little wide like a catalogue's section titles, and reading text stays at normal width.

### Hierarchy
- **Display** (800, 64px, 0.95, width 104%, tabular): the count on Check the list, and nothing else. 40px on a phone.
- **Headline** (800, 40px, 1.02, width 110%): a screen's title, such as Home, Photos or Tools. 28px on a phone.
- **Figure** (750, 40px, 1.05, tabular): Home's four facts. 28px on a phone.
- **Title** (750, 28px, 1.15, width 106%): a tool's name over its form and a group's name on the Tools page. The counters under What happened share the size at 700, in tabular numerals.
- **Section** (750, 20px): Home's section heads, Latest, a month on Photos. The verb and unit either side of the count use the size, the verb at 700 and the unit at 650 in warm grey.
- **Masthead** (800, 16px, width 118%): the app's name in the header, wide, heavy and small.
- **Subtitle** (700, 16px): a card's heading and the group's name over the list beside a tool; a tool's name in a list is the same size at 650.
- **Body** (400, 14px, 1.55): everything that is read. The line under a screen's title stops at 62ch.
- **Small** (13px): secondary lines, chips, steps, tables and header controls.
- **Label** (700, 12px, 0.04em, sentence case): the running heads in the rail and the list beside a tool.
- **Caption** (400, 12px): a plate's file name and date. Table headers use it at 600 with 0.02em.
- **Mono** (13px, 1.5): a path or a file name in a checklist, a result or a menu.

### Named Rules
**The Eight Sizes Rule.** Every size is one of 12, 13, 14, 16, 20, 28, 40 and 64px (`--t-xs` to `--t-4xl`). A size off the scale is a size somebody guessed, and `tests/test_design.py` fails it.

**The Columned Numbers Rule.** Every count is set in tabular numerals, so a column of 1,204 and 87 reads as numbers and not as a ragged edge.

**The Sentence Case Rule.** Headings, legends, fold rows and running heads are in sentence case. A running head is small and spaced, never capitals, and nothing sits above a heading: the line about a screen goes under its title.

## Layout

The frame is a running head over a rail and a stage. The header is sticky, solid sheet, 57px tall (`--head`) with a hairline under it. The rail is 256px of sheet with a hairline on its right, sticky under the header and full height, so its foot (index status, Re-read library, help) sits at the bottom of the window. The stage has no maximum width and pads 32px 40px 72px: a wider window means more columns, not longer lines.

A screen opens with its title, the line about it under the title, and its tools pushed to the right end of the same row, 24px above the content. Home then hangs the latest photos as plates: five columns, the newest spanning two by two, six round it cut 4:3, seven in all so the wall fills two rows, 20px by 14px apart, each with a wall label under it. Under 1060px it is three columns and six plates. The four facts follow in one ruled row (columns at least 176px, 28px apart), and the dashboard below opens each part with a 1px ink rule 44px under what came before.

Photos is a grid of square tiles that grow with the window (`clamp(140px, 9vw, 240px)`) 4px apart, with month rows that stick under the header on a hairline and a 72px year rail down the right. A tool's page puts its form in a column up to 1180px and its group's list in a 250px column to the right, 32px apart, divided by a hairline; results take the full width under both. Under 1060px the list moves under the form with a hairline above it. The Tools page sets its groups in columns at least 300px wide, 40px by 36px apart.

In a form, a group of settings is a heading and a rule 30px below the last, never a box. A control is as wide as the answer it takes: text 640px, a list 560px, a password 320px, a number 220px, and a path beside Browse takes the row.

On a phone (860px and under) the rail becomes a drawer (82vw, at most 320px), tabs sit fixed at the foot, and the stage pads 16px with 92px clear at the bottom. The plates become one row you swipe (the newest at 68%, the rest at 42%, all square, snapping), the facts go two by two, the filters become one row you swipe, the count drops to 40px and the apply button takes the full width. Everything a thumb presses is at least 44px: `--chip-h` becomes 44px.

### Named Rules
**The Plates First Rule.** On Home the newest photos come before any figure: the newest at twice the size, a wall label under every plate, and the four facts after them.

**The Answer Width Rule.** A field is as wide as what goes in it. A box for "60" stretched across a wide column reads as a mistake.

## Elevation & Depth

The catalogue is flat. `--shadow-card` is `none`: a surface sits on the page by its 1px hairline, a printed section opens under a 1px rule of ink, and a section of the catalogue opens under a 4px band of its ink. Depth is kept for what floats over the page. The viewer's stage and panel are black whatever the mode, so a photo is always seen on black.

### Shadow Vocabulary
- **Pop** (`box-shadow: 0 18px 40px -12px rgba(20,18,14,.28), 0 0 0 1px rgba(20,18,14,.06)` light, `0 18px 44px -10px rgba(0,0,0,.75), 0 0 0 1px rgba(255,255,255,.07)` dark): menus, the selection bar, anything that floats over the page.
- **Running head** (`box-shadow: 0 8px 24px -14px rgba(16,24,40,.35)` light, `0 8px 24px -12px rgba(0,0,0,.7)` dark): the header, only once the page has scrolled under it.
- **Bubble** (`box-shadow: 0 8px 26px rgba(0,0,0,.3)`): the help bubble.

### Named Rules
**The Hairline Rule.** A card sits on the page by its hairline alone. Nothing flat casts a shadow; only a menu, a bar or a bubble that floats over the page does.

**The Band, Not Stripe Rule.** A section or a state is banded across the top: a 4px band, a 3px lit step, a 2px band on a phone tab. Nothing carries a coloured stripe down one side; a 1px hairline between two columns is a divider, not a stripe, and `tests/test_design.py` fails any left border of 2px or more.

## Shapes

Everything is cut square, like a print on a wall. `--r-card`, `--r-ctl` and `--r-pill` are all 2px, so a card, a button, a field and a chip share one corner, and a filter is told apart by filling with ink when it is on, not by its shape. Round is kept for dots: a status dot, a colour-label dot or swatch, the Guide's page dots, and the tick that marks a selected photo.

Lines have four weights and each says one thing: a 1px hairline in `line` divides, a 1px rule in `ink` opens a printed section (a part of the checklist, a fact, a Home section), a 3px rule lights the current step, and a 4px band in a section ink or in `bad` opens a section or marks the irreversible. Photos are cropped to fill their cell: square in the grid, 4:3 round the newest plate on Home, and the newest fills its two by two cell. A plate carries a 1px hairline ring so a dark photo still has an edge on black stock.

Icons come from one sprite on a 24px grid, drawn at a 1.7 stroke with round caps and joins in `currentColor`: 19px in a row, 16px in a list, 14px for the small marks (close, arrow, fold, chevron), which are drawn and never typed.

### Named Rules
**The Square Cut Rule.** 2px on every card, control and chip. What sets a control apart is its fill, its weight or its rule, never its roundness.

## Components

### Buttons
Printed, square and named by their verb.
- **Shape:** square cut (2px).
- **Primary:** a plain button: ink fill, `on-accent` label, 10px 18px, 14px at 650. One per screen, and it carries the real verb with its count ("Move 412 files"). The apply button on Check the list is the same button at 48px tall, 12px 28px and 16px, full width on a phone.
- **Hover / Focus:** a pressed button moves down 1px; colour and border ease over `--t-fast` (160ms). Focus is a 2px ring in the accent, 2px out, on every control.
- **Secondary (`.ghost`):** no fill, a 1px ink border and an ink label. Cancel, Check again, Browse.
- **Quiet (`.quiet`):** text only, warm grey, underlined 3px below, turning to ink under the pointer. Something you may never press.
- **Destructive (`.danger`):** filled with `bad`, and only where something cannot be undone.
- **Contextual (`.pillbtn`):** acts on what is selected and lives in the selection bar: sheet fill, 1px hairline, 7px 13px, 14px at 600, its mark in the ink of the group its tool belongs to.
- **Header controls:** 36px tall, 13px at 600, warm grey with no box until the pointer is on them (a hairline and a 9% tint); a control that is on has an ink border on the ink panel.

**The Six Roles Rule.** Every button is one of primary, secondary, quiet, destructive, filter or contextual. A seventh kind is a feature that has not said which of these it means, and `tests/test_design.py` fails a new one.

### Chips
- **Filter (`.fchip`):** 36px tall (44px on a phone), 0 14px, 13px at 500, sheet fill, 1px hairline, ink label. Under the pointer the border turns ink; when on it fills with ink and its label turns `on-accent` at 600. A filter that opens a list carries a drawn chevron.
- **Value (`.chip`):** a chosen value on a form. The same height, wash fill and hairline, with a drawn cross to remove it (36px to press on a phone).
- **Status (the header's Live and Flows):** one neutral chip, wash fill and hairline, with the colour carried by the dot and the word only. Off is a hollow ring, on is a filled green dot, running is a filled ink dot that pulses. A chevron says when pressing it opens something.

### Cards / Containers
- **Corner Style:** square cut (2px).
- **Background:** the sheet (`card`) on the ground (`bg`); in light mode both are white.
- **Shadow Strategy:** none (The Hairline Rule).
- **Border:** a 1px hairline.
- **Internal Padding:** 20px 22px (`--pad-card`).
- **A tool's form** is the one card on its page and opens under its group's 4px band, with 24px under the band.
- **What a run found and what it would do** are printed, not boxed: each part opens under a 1px ink rule, pads 20px 0 8px, and sits 28px from the next. A table keeps a hairline above and below so its header row still sticks.
- **A Tools group** is printed, not boxed: a 4px band in its ink, 20px under it, the group's name as a title with its mark in its ink, a line about it, then its tools as ruled entries (name 16px at 650, line 13px in warm grey, a 16px mark in warm grey). Under the pointer an entry takes the wash and its name and mark take the group's ink.

### Inputs / Fields
- **Style:** wash fill, 1px hairline, 2px corners, 9px 12px, at least 40px tall (44px for the password on the sign-in page). Under the pointer the hairline darkens toward the ink.
- **Focus:** a 2px ink outline drawn 1px inside the edge.
- **Locked:** the field at 62% and the option at 45%, with a not-allowed pointer and the reason beside it.
- **Help:** a 20px ring beside the label, pressable across 44px, opens the help bubble: ink ground, stock-coloured text, 14px at 1.5, at most 360px wide, 2px corners, fading in over 120ms. The explanation lives there and the label stays a name.

### Navigation
- **Header:** a running head on solid sheet, never frosted. The app's name as masthead, the status chips, then the controls hard right.
- **Rail:** rows 40px tall (44px on a phone), 14px at 500, 19px marks in warm grey; the wash under the pointer. Where you are is the ink panel and weight 700, never a colour on a colour. Each tool group's mark is in its section ink, so the rail is the key to the colours the pages use. Running heads are labels in warm grey; Settings is set apart by a 12px gap rather than a heading.
- **The list beside a tool:** an index in the margin, divided from the form by a hairline. The group's name heads it at 16px 700 with its mark in its ink; rows are 38px tall (44px on a phone), 14px in warm grey; the current tool is the ink panel at 700 with its mark in `--sec`.
- **Phone tabs:** fixed at the foot on the sheet with a hairline above, 12px at 600 in warm grey; the current tab is ink at 750 under a 2px band of the section's ink, or plain ink on a screen in no section. The rail opens as a drawer from the left.

### Step strip
Four numbered columns under one hairline, like the running heads of a catalogue. The step you are on is bold ink and its 3px rule fills in from the left in the section ink over `--t-slow`. A finished step keeps its rule at 30% ink and gets a tick drawn in green beside its number. Numbers are 13px at 700 in tabular numerals.

### The catalogue checklist
Check the list ends in a checklist, the signature of the system. A headline sentence ("Nothing has been written yet.", 16px at 700), then one count line on a shared baseline: the verb at 20px, the count at 64px, the unit at 20px in warm grey, 18px clear above and below. Then the facts in two ruled columns under a 1px ink rule: labels in warm grey in a column at least 112px wide, 28px from their values, each row padded 11px above and below and ruled with a hairline, paths in mono. Then the apply button, solid ink, naming the operation. The count settles into place from 14px below over `--t-slow`. A run that cannot be undone keeps its red: a 4px band in `bad` over it, and the verb and count in `bad`. On a phone the count is 40px, the verb and unit 16px, the label column 96px, and the button full width.

### Plates
The latest photos on Home, hung like prints. Square cut with a 1px hairline ring, the newest at twice the size, the rest cut 4:3, and a wall label under each: the place at 14px 650 (16px for the newest), the file name and the date as captions. They arrive one after another 30ms apart, rising 10px over `--t-slow`.

### Home facts
Four figures in one ruled row, each under a 1px ink rule: the figure first (40px, tabular), then its name at 13px 650 in ink, then a note at 13px in warm grey. Ink only, with no marks and no tints, since Home is in no section.

### The turn
Moving to another screen or tool, what arrives fades in and travels 18px from the side you are going towards, over `--t-mid` (280ms) on `--ease` (`cubic-bezier(.16,1,.3,1)`). Going back travels from the other side. The parts after the first follow 40ms apart, up to 120ms. It plays only on arriving; a page redrawn in place does not move, and the screen clips its sideways overflow while it turns.

### Keyboard and screen readers
A skip link is the first thing a keyboard reaches, hidden above the window until focused: ink ground, stock-coloured text, 12px 18px at 700, with a focus ring in the section ink. One polite live region says what the eye sees arrive: a toast and its Undo, the checklist's headline and count, a run's result. A toast that carries a button stays for at least six seconds.

## Do's and Don'ts

### Do:
- **Do** print the one primary action on a screen in ink (`accent` with `on-accent`), and name it with its verb and count ("Move 412 files").
- **Do** take every size from the scale (`--t-xs` 12px to `--t-4xl` 64px) and set every count in tabular numerals.
- **Do** divide with 1px hairlines (`line`), open a printed section with a 1px ink rule, and open a section of the catalogue with a 4px band of its ink.
- **Do** reach a section ink only through `--sec` (from `body[data-tone]`) or a group's own `--tone`, and only on something that belongs to a group of tools.
- **Do** keep every corner at 2px (`--r-card`, `--r-ctl`, `--r-pill`) and keep round for dots.
- **Do** keep everything a thumb presses at 44px or more on a phone (`--chip-h` is 44px under 860px).
- **Do** say a state in shape and word as well as colour: bold and lit for the current step, a drawn tick for a finished one, a ring or a filled dot with its word for a status.
- **Do** draw every mark (close, arrow, fold, chevron) from the icon sprite or in CSS, at 14px beside text.
- **Do** time motion with `--ease` and `--t-fast` (160ms), `--t-mid` (280ms) or `--t-slow` (480ms), and stop all of it under `prefers-reduced-motion`.
- **Do** set headings in sentence case, with any line about them underneath.

### Don't:
- **Don't** build the category default: grey cards nested in cards, pastel figure tiles, rounded everything, one blue accent.
- **Don't** box a group of settings inside a card; a group is a heading and a rule.
- **Don't** run a coloured stripe down the side of anything; a left border of 2px or more fails `tests/test_design.py`.
- **Don't** colour the chrome of a screen that is in no section (Home, Photos, Places, Albums, People) with a section ink, or use a section ink as decoration.
- **Don't** cast a shadow from a flat surface, or let the header turn see-through.
- **Don't** add a seventh button role, or a second primary button on a screen.
- **Don't** add a type size off the scale, a second typeface, or a font or script fetched from the internet.
- **Don't** put a kicker or an eyebrow above a heading, or set a heading in capitals.
- **Don't** type a mark as a character (× ‹ › ▾ ▸ ↑ ↓).
- **Don't** bounce, and don't loop anything but the pulse of a running status dot or a progress bar that cannot measure.
