---
name: app-icon-restyle
description: Generate a new desktop app icon set (icon.png, icon.ico, icons/NxN.png) that keeps the visual style of an existing or borrowed icon but depicts the current app. Use whenever the user wants to restyle, redraw, replace or "make a new" app icon, says the icons were copied from another project, or wants icons matching an existing icon's look, even if they don't say "skill" or name the files.
---

# App icon restyle

The user has icons copied from another project. They like the look (shape, palette, rendering style) but the artwork shows the wrong app. Produce a replacement that is unmistakably *this* app while feeling like the same family as the old one.

## 1. Learn the style from the existing icon

View the largest existing PNG (e.g. `app/assets/icons/512x512.png`) with the Read tool. Write down, concretely:
- Container shape (rounded square / squircle, corner radius as a fraction of width, margins to the canvas edge) and background (flat or gradient, exact colours).
- Illustration language: flat vs. glossy, outline vs. fill, shadows, highlights, border strokes.
- Palette: sample real pixel values with Pillow (`Image.getpixel`) rather than guessing hex codes.
- Typography on the icon, if any: weight, colour, position.
- Accent elements (badge, status dots) and where they sit.

Reusing exact colours and proportions is what makes the new icon read as "same style"; eyeballed approximations drift.

## 2. Learn what the app is

Read the project's README/CLAUDE.md and the main entry points. Pick one clear central metaphor plus at most one or two supporting cues (e.g. source -> output, or the app's main action). Icons are viewed at 16-32px, so more than three elements turns to mush. Replace any text from the old icon that names another app; if text stays, keep it to a few characters.

## 3. Draw a 1024px master

Draw with Pillow at 2x supersampling (2048 canvas, downsample to 1024) so edges are smooth, or write SVG and rasterize if a rasterizer is installed. Put the script in the scratchpad/temp directory, not the repo, and save the master there too. Transparent corners outside the container shape.

Then view the master with Read, and also view a downscaled 32px and 16px version. Iterate until the shapes still read at 32px and nothing is clipped. Compare side by side with the old icon: same container, palette and rendering language, different subject.

## 4. Export

```bash
python <skill-dir>/scripts/export_icons.py <master.png> <app>/assets
```

This overwrites `icon.png`, `icon.ico` and `icons/{16..512}.png`. Check the project's build config (for Electron: `package.json` `build.win/mac/linux.icon` and the `BrowserWindow` `icon` option) to confirm these file names are what it uses, and adjust only if they differ. Files are tracked by git, so the old set is recoverable; no backup copy needed.

## 5. Report

Show the final 512px result, say which colours/shape were carried over, what changed in the subject, and list files written. Offer to tweak (different metaphor, label text, accent colour). Do not commit unless asked.
