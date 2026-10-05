#!/usr/bin/env python3
"""
BearBox — NEXUS build entrypoint.

This build does one thing: show the NEXUS booth's live ticket sales. There are
no USB profiles, no idle cycle, nothing to detect. The systemd service runs
this file, so it just hands straight off to the NEXUS screen.
"""

import os
import sys

BASE = "/home/bearbox/bearbox"
sys.path.insert(0, os.path.join(BASE, "core"))

os.execv(sys.executable, [sys.executable, os.path.join(BASE, "core", "nexus.py")])
