"""Shared code for the video skills: media probing, ffmpeg runners, transcripts.

Skill scripts live next to this toolkit (skills/<skill>/scripts/x.py and
skills/video-toolkit/), both in the repo and once installed in
~/.claude/skills, so they import it with:

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-toolkit"))
"""

from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = TOOLKIT_DIR / "assets"
