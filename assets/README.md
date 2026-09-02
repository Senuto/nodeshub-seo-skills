# Assets

- `seo-skills-robot.svg` – the blue pixel robot shown when a skill is invoked.
  Generated from the pixel grid in
  `.claude/skills/nod-nodeshub-api/scripts/banner.py`, so if you change `GRID`
  or `COLOR_MAP` there, regenerate this file to keep them in sync.
- `nodeshub-logo-pixel.svg` / `nodeshub-logo-pixel-dark.svg` – pixel-art NodesHub
  logo used in the main `README.md`, matching the robot's style. The first is for
  dark backgrounds, the second for light ones; `README.md` swaps between them via
  `<picture>` + `prefers-color-scheme`. The gradient behind the mark is sampled
  cell-by-cell from the official logo, so it keeps the real pink/teal tones.
- `nodeshub-logo-light-bg.svg` / `nodeshub-logo-dark-bg.svg` – the official
  (non-pixel) NodesHub logo from nodeshub.io, kept for other uses.
- `branding/` – logos, colors and fonts used by HTML reports. See `branding/README.md`.
- `demo.gif` – a skill running in Claude Code, embedded in the "See it in action"
  section of the main `README.md`.
- `install.gif` – cloning the repo and opening it in the editor, embedded in the
  Installation section.

## Regenerating the GIFs

Both were converted from `.mov` screen recordings with ffmpeg, using a two-pass
palette for readable terminal text:

```bash
ffmpeg -i input.mov -vf "fps=8,scale=800:-2:flags=lanczos,palettegen=max_colors=64:stats_mode=diff" palette.png
ffmpeg -i input.mov -i palette.png -lavfi "fps=8,scale=800:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" output.gif
```

8 fps at 800 px keeps each file comfortably under 5 MB, above which GitHub starts
lazy-loading them. Raising the width or frame rate makes the files grow quickly.
