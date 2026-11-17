---
name: Backalor
description: Native research workbench for historical cipher keys
colors:
  accent: "#206b49"
  accent-hover: "#185639"
  rail: "#182820"
  rail-active: "#2d523d"
  rail-hover: "#263e31"
  rail-text: "#d7e4db"
  rail-muted: "#b9cfc0"
  paper: "#f7f8f5"
  surface: "#ffffff"
  ink: "#202e26"
  secondary: "#56665c"
  heading: "#20392b"
  line: "#d8e0d8"
  control-line: "#bdcebf"
  selection: "#deeee2"
  selection-ink: "#163f2b"
  focus: "#347e55"
  canvas: "#e7ebe4"
  table-header: "#f0f4ed"
  disabled-bg: "#edf1eb"
  disabled-ink: "#65776a"
  l1: "#a9684a"
  l2: "#9b7a2c"
  l3: "#2e7d32"
  non-symbol: "#757575"
typography:
  display:
    fontFamily: "system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
  headline:
    fontFamily: "system-ui, sans-serif"
    fontSize: "27px"
    fontWeight: 600
  title:
    fontFamily: "system-ui, sans-serif"
    fontSize: "23px"
    fontWeight: 600
  body:
    fontFamily: "system-ui, sans-serif"
    fontSize: "13px"
  label:
    fontFamily: "system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
rounded:
  field: "5px"
  control: "6px"
  container: "7px"
spacing:
  compact: "6px"
  control: "8px"
  section: "16px"
  portal: "34px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "#334c3c"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-google:
    backgroundColor: "{colors.surface}"
    textColor: "#23372b"
    rounded: "{rounded.control}"
    padding: "14px 20px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "8px"
  navigation-active:
    backgroundColor: "{colors.rail-active}"
    textColor: "{colors.surface}"
    rounded: "{rounded.container}"
    padding: "11px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.container}"
---

# Design System: Backalor

## Overview

**Creative North Star: "The Research Workbench"**

Backalor is a native PyQt6 research workbench, primarily on macOS. Its confirmed visual direction pairs dark forest navigation with a pale workspace and restrained green actions. The source scan is the working material: navigation establishes position while light tables, forms and canvas areas keep annotation and review legible. The direction contract in `app/portal.py` records seed `a66aa05c`, candidate 6.

The atmosphere is quiet, practical and dense enough for sustained desktop work. Shared Qt styling, the system font and small outline icons tie the login, projects hub and editor together. Large type belongs to entry screens; operational screens devote their area to pages, hierarchy, source imagery and properties. “The Research Workbench” is descriptive documentation language for this implemented direction.

**Key Characteristics:**

- Dark persistent navigation beside a light workspace.
- Forest green actions and pale green selection states.
- System typography, compact forms and native vector icons.
- Source image, hierarchy and properties remain visible together.

## Colors

The palette combines deep forest navigation, green-tinted paper neutrals and a single green action family. Frontmatter values are normative; `app/theme.py` is the implementation source.

### Primary

- **Forest Green** (`accent`): contextual next actions, project creation, review confirmation, checked controls and progress.
- **Deep Forest Green** (`accent-hover`): primary hover and selected control text.
- **Leaf Focus** (`focus`): keyboard focus border on buttons and tool buttons.

### Neutral

- **Forest Charcoal** (`rail`): login identity panel and persistent navigation.
- **Moss Navigation** (`rail-active`, `rail-hover`): selected and hovered navigation rows.
- **Pale Leaf Text** (`rail-text`, `rail-muted`): rail controls, identity and supporting copy against the dark ground.
- **Research Paper** (`paper`): application background; **White Surface** (`surface`): tables, toolbar and inspector.
- **Forest Ink** (`ink`, `heading`): working text and screen headings; **Muted Ink** (`secondary`): instructions and status.
- **Soft Structure** (`line`, `control-line`): dividers, panels and input outlines.
- **Pale Selection** (`selection`, `selection-ink`): current tree/list row and checked tool state.
- **Canvas Ground** (`canvas`): neutral space surrounding the scan, distinct from white forms.
- **Table Ground** (`table-header`): table headers and alternate base role.
- **Inactive Surface** (`disabled-bg`, `disabled-ink`): disabled controls with readable labels.

### Annotation semantics

The `l1`, `l2` and `l3` tokens identify section, pair and element outlines on the scan. `non-symbol` distinguishes an explicitly marked non-symbol. These are data semantics, not additional brand accents; keep them stable when adding navigation or actions.

**The Context Rule.** Use green selection fills for application context and preserve the annotation outline colors for document geometry.

## Typography

Use the native Qt application font. The portable `system-ui, sans-serif` token represents that choice; no bundled web font or fixed SF Pro dependency exists. The theme selects Qt Fusion styling, sets an application fallback of 10 points, then applies a shared 13-pixel widget rule. Pixel values describe Qt stylesheet units rather than physical display pixels.

- **Display**: semibold login statement; wraps naturally within the dark identity panel.
- **Headline**: semibold login and projects headings.
- **Title**: semibold editor stage heading; project name appears alongside in smaller muted text.
- **Body**: normal controls, table content, instructions and working forms.
- **Label**: semibold panel titles and primary actions.

The wordmark is uppercase, semibold (18px), with letter spacing (2px). The Google button uses semibold text (15px); empty-state titles use semibold text (22px). Line heights remain Qt/font metrics; do not invent a web line-height scale.

## Layout

This is a resizable desktop window system. There are no mobile breakpoints or responsive web containers. Dimensions below are Qt logical units.

- **Login:** initial portal size (1120×760), minimum (860×620). A dark identity panel takes the left share (4:6 stretch), constrained to a width of 300–460. Its margins are 42; the light form uses horizontal margins of 48 and vertical margins of 40. The Google action spans the form and has a minimum height of 48. Supporting copy wraps at smaller widths.
- **Projects hub:** fixed dark rail (220), with margins (22,30,22,24). The light body uses margins (34,30,34,28) and spacing (16). Title, short explanation and create/open actions precede local/server tabs. A two-column table stretches through the remaining height. Service readiness and selected-project action anchor the footer. Long paths may elide inside table cells; the shell remains desktop-shaped.
- **Editor:** minimum (1100×720). Fixed rail (184), with margins (16,26,16,22) and row spacing (8). The content area uses margins (18,16,18,12), spacing (10), and a fixed-height contextual header above the optional annotation toolbar. Projects, scans, annotation, symbols, review and models are the rail destinations; the underlying center tab bar is hidden.
- **Working area:** page navigation and hierarchy share a left panel constrained to 225–250 wide. During annotation the page list height is capped at 125, leaving room for the tree. Splitters allocate remaining width to the canvas and inspector. The inspector remains visible beside the scan; advanced geometry and notes use a collapsed disclosure. Review gives its main width to the filter/action row and table, retaining the page list.

Ukrainian (`uk`) and Slovak (`sk`) are supported. The editor shell follows the active source-language selection; portal copy uses the language selected at startup. The portal has no separate live language switch. Wrap supporting prose and verify operational labels in both languages rather than reducing type to force a fit.

Observed screenshots: `.impeccable/review/redesign-login-{wide,small}.png`, `redesign-projects-{wide,small}.png`, `redesign-editor-{wide,small}.png` and `redesign-review-small.png`. Small portal captures are 900×650; small editor/review captures are 1100×720. These captures establish visual evidence, not live authentication or cloud-service completion.

## Elevation & Depth

The implemented theme is flat: no custom drop shadows or decorative elevation stack. Dark/light surface contrast, pale selection fills, thin structural borders and splitter handles establish hierarchy. Tooltips invert to a dark surface with pale text. Standard Qt/macOS window and menu presentation may add platform-managed depth outside this theme.

No custom transition-duration or easing system is defined. Hover, checked, focus, pressed, disabled and busy states update through Qt; asynchronous requests use a thin indeterminate progress indicator rather than decorative motion.

## Shapes

Controls have gently rounded corners: fields use `field`, buttons/list surfaces use `control`, navigation rows/toolbars/group boxes use `container`. List rows and scroll handles use smaller corners (4px). Checkboxes use compact square indicators (16×16, radius 3); radio indicators are circular. Do not turn ordinary data rows into floating cards.

Rail icons are drawn by native `QPainter` vectors on a 24×24 transparent pixmap, with rounded strokes (1.7) and displayed at 20×20 in the editor. Continue this consistent outline vocabulary; no icon font or emoji navigation is used.

## Components

### Actions and focus

Primary buttons use white semibold text on Forest Green. Secondary buttons use white surfaces, muted green ink and a fine outline. Both use compact horizontal padding and have hover, pressed and disabled styling. Buttons/tool buttons receive an explicit focus border (2px); fields receive an accent focus border (1px). Keep focus visible independently of selection.

The Google button is a distinct white outlined entry action, with larger type and padding. It stays disabled until backend readiness and Google configuration are known. Waiting, retry, cancellation and configuration errors are expressed beside this action; the app opens the system browser and never presents an in-app Google password form.

### Navigation

The rail is persistent and labeled, with an icon and text on editor destinations. Active rows use a moss fill and semibold white labels; hover uses a quieter tonal fill. Account identity anchors the bottom. Tabs within the projects surface distinguish local history from server copies using a green underline and semibold selected text.

### Tables, lists and containers

White bordered tables use pale headers and stable columns. The projects table selects a whole row and allows opening the selection or double-clicking. Selection-dependent actions remain disabled without a row. Lists and hierarchy trees use the shared pale selection; tree rows have a minimum height (29). White group boxes and toolbars carry thin structural borders rather than shadows. There is no independent marketing-card or chip component system.

### Fields and disclosures

Fields use white backgrounds, muted green outlines and modest padding. Role and element type precede recognition fields. Readable L3 elements expose transcription; cipher symbols expose code and text reference. Notes, caption, parent and coordinates remain inside the additional-properties disclosure, with long form rows allowed to wrap. Advanced model and recognition controls use disclosure rather than occupying the main review table area.

### Workflow and state

The production sequence is backend readiness → verified Google sign-in → explicit project choice → editor. New identities are registered by the existing Google callback. After login, the hub offers creation, opening a local folder and downloading an owned server project. The production account dialog hides address/connect/login setup controls; server transfers are explicit snapshot operations.

Authentication is verified by the API. A remember-login checkbox persists the token in an OS credential vault; local JSON contains only profile hints. On restart the editor remains closed until `/auth/me` succeeds. Session failure locks and hides the editor after a recovery checkpoint, with recovery information kept for reauthentication. Local folders remain ordinary operating-system files, and server ownership checks remain authoritative for private copies. Normal startup connects to the configured cloud API and never starts a local database. Explicit development mode may reuse a compatible loopback service or own a local child process. An unavailable remote service reports failure rather than being launched locally.

No real Google identity was used in the redesign checks. Isolated tests used mock identities, while production retains the verified Google callback flow. These visual and implementation observations do not establish a successful live Google sign-in or full cloud synchronization.

## Do's and Don'ts

### Do:

- Do use the dark rail, pale workspace and green action family on new application surfaces.
- Do preserve space for the scan and retain page/hierarchy context beside the inspector.
- Do show distinct selection, focus, disabled and busy states.
- Do check Ukrainian and Slovak copy at each window’s actual minimum size.
- Do label server transfers as explicit snapshots or copies and keep service readiness separate from authentication.

### Don't:

- Don’t restore the previous blue action palette or top-tab workflow navigation.
- Don’t substitute a web landing-page or mobile layout for the native desktop shell.
- Don’t use decorative gradients, imagery or shadow stacks over the working material.
- Don’t imply that local folders are access-controlled by Google sign-in or that server copies synchronize continuously.
- Don’t treat screenshots with mock identities as evidence of successful live Google authentication.
