#!/usr/bin/env python3
"""Setup verification for content-brief — delegates to nodeshub-api."""

import subprocess
import sys
from pathlib import Path

check = Path(__file__).resolve().parents[2] / 'nodeshub-api' / 'scripts' / 'check_setup.py'
sys.exit(subprocess.call([sys.executable, str(check)]))
