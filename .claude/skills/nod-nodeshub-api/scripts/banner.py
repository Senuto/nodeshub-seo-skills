"""
CLI banner for Nodeshub SEO Skills.

Displays compact pixel-art logo alongside project info.
Uses half-block characters to compress 2 pixel rows into 1 terminal line.

Usage:
    from banner import print_banner
    print_banner("SERP Analysis")
"""

import os
import sys

VERSION = "v0.1.0"

# 7x6 pixel grid (compact version, even rows for half-block compression).
# 0 = transparent, 1 = blue, 2 = light blue, 3 = muted blue
GRID = [
    [1, 0, 0, 0, 0, 0, 1],  # antennae
    [0, 1, 2, 2, 2, 1, 0],  # head
    [0, 1, 0, 1, 0, 1, 0],  # eyes
    [2, 2, 2, 2, 2, 2, 2],  # muzzle
    [0, 3, 0, 3, 0, 3, 0],  # legs
    [0, 0, 0, 0, 0, 0, 0],  # padding
]

# RGB palette.
COLOR_MAP = {
    1: (59, 130, 246),   # #3b82f6 — blue
    2: (96, 165, 250),   # #60a5fa — light blue
    3: (45, 90, 160),    # #2d5aa0 — muted blue
}

RESET = "\033[0m"
HALF_TOP = "\u2580"     # ▀ upper half block
HALF_BOT = "\u2584"     # ▄ lower half block
FULL = "\u2588"         # █ full block


def _fg(rgb):
    return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def _bg(rgb):
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def _render_art() -> list[str]:
    """Render the pixel grid using half-block chars: 2 pixel rows = 1 terminal line, 1 char wide per pixel."""
    lines = []
    for y in range(0, len(GRID), 2):
        top_row = GRID[y]
        bot_row = GRID[y + 1] if y + 1 < len(GRID) else [0] * len(top_row)
        parts = []
        for t, b in zip(top_row, bot_row):
            if t == 0 and b == 0:
                parts.append(" ")
            elif t != 0 and b == 0:
                parts.append(f"{_fg(COLOR_MAP[t])}{HALF_TOP}{RESET}")
            elif t == 0 and b != 0:
                parts.append(f"{_fg(COLOR_MAP[b])}{HALF_BOT}{RESET}")
            elif t == b:
                parts.append(f"{_fg(COLOR_MAP[t])}{FULL}{RESET}")
            else:
                parts.append(f"{_fg(COLOR_MAP[t])}{_bg(COLOR_MAP[b])}{HALF_TOP}{RESET}")
        lines.append("".join(parts))
    return lines


def _project_path() -> str:
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    return cwd


def print_banner(skill_name: str) -> None:
    """Print the startup banner with pixel art and project info."""
    art = _render_art()
    info = [
        f"\033[1mNodeshub SEO Skills\033[0m {VERSION}",
        f"\033[2m{skill_name}\033[0m",
        f"\033[2m{_project_path()}\033[0m",
    ]

    # Center info vertically against art
    pad_top = max(0, (len(art) - len(info)) // 2)
    info_padded = [""] * pad_top + info
    info_padded += [""] * (len(art) - len(info_padded))

    separator = "   "
    try:
        width = os.get_terminal_size().columns
    except OSError:
        width = 60
    rule = f"\033[2m{'─' * width}\033[0m"
    lines = [rule]
    for art_line, info_line in zip(art, info_padded):
        lines.append(f"  {art_line}{separator}{info_line}")
    print("\n".join(lines))
