#!/usr/bin/env python3
"""Render README.md with GitHub's own renderer and open it in a browser.

Uses `gh api /markdown` (mode=gfm), so the output matches what GitHub shows on
the repo page. Relative asset paths are rewritten to absolute local paths so the
GIFs and logos actually load.
"""

import html
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path("/tmp/readme_preview.html")

CSS = """
  :root { color-scheme: light dark; }
  body {
    max-width: 1012px; margin: 0 auto; padding: 32px 48px;
    font: 16px/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    color: #1f2328; background: #fff;
  }
  h1, h2 { padding-bottom: .3em; border-bottom: 1px solid #d1d9e0; }
  h1, h2, h3 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; }
  img { max-width: 100%; }
  code { padding: .2em .4em; background: #eff1f3; border-radius: 6px; font-size: 85%; }
  pre { padding: 16px; overflow: auto; background: #f6f8fa; border-radius: 6px; }
  pre code { padding: 0; background: none; }
  table { border-collapse: collapse; display: block; overflow: auto; margin-bottom: 16px; }
  table td, table th { padding: 6px 13px; border: 1px solid #d1d9e0; }
  table tr, table th, table td { background: #fff; }
  blockquote { padding: 0 1em; color: #59636e; border-left: .25em solid #d1d9e0; margin-left: 0; }

  @media (prefers-color-scheme: dark) {
    body { color: #e6edf3; background: #0d1117; }
    a { color: #4493f8; }
    h1, h2 { border-bottom-color: #30363d; }
    code, pre { background: #161b22; }
    table tr, table th, table td { background: #0d1117; border-color: #30363d; }
    blockquote { color: #9198a1; border-left-color: #30363d; }
  }
"""


def _slug(text: str) -> str:
    """Match GitHub's anchor slugs: lowercase, drop punctuation, spaces to dashes.

    Punctuation is removed without collapsing the spaces around it, so headings
    like "Skills - overview" and "Infrastructure & setup" end up with a double
    dash, exactly as GitHub renders them.
    """
    s = re.sub(r"<[^>]+>", "", text)          # strip inline tags (e.g. <code>)
    s = html.unescape(s)                      # &amp; -> & so it gets dropped, not spelled "amp"
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def _add_anchor(m: "re.Match[str]") -> str:
    level, inner = m.group(1), m.group(2)
    return f'<h{level} id="{_slug(inner)}">{inner}</h{level}>'


def main() -> int:
    md = (REPO / "README.md").read_text()
    res = subprocess.run(
        ["gh", "api", "--method", "POST", "/markdown", "--input", "-"],
        input=json.dumps({"mode": "gfm", "text": md}),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"gh api failed: {res.stderr[:300]}", file=sys.stderr)
        return 1

    body = res.stdout
    for attr in ("src", "srcset"):
        body = body.replace(f'{attr}="assets/', f'{attr}="{REPO}/assets/')

    # The /markdown API returns bare <h2>Foo</h2>; GitHub's own frontend is what
    # adds the id= anchors. Add them here with the same slug rules so the table
    # of contents links are clickable in the preview too.
    body = re.sub(r"<h([1-6])>(.*?)</h\1>", _add_anchor, body, flags=re.DOTALL)

    OUT.write_text(
        f'<!doctype html>\n<meta charset="utf-8">\n'
        f"<title>README preview</title>\n<style>{CSS}</style>\n{body}\n"
    )
    print(OUT)
    subprocess.run(["open", str(OUT)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
