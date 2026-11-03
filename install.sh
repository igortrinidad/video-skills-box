#!/usr/bin/env sh
# Symlinks every skill in ./skills into ~/.claude/skills (macOS/Linux).
# An existing real directory is moved to ~/.claude/skills/.trash/<name>-<timestamp> first.
set -eu
src="$(cd "$(dirname "$0")" && pwd)/skills"
target="${1:-$HOME/.claude/skills}"
stamp="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$target"
for dir in "$src"/*/; do
  name="$(basename "$dir")"
  [ -f "$dir/SKILL.md" ] || continue
  dest="$target/$name"
  if [ -L "$dest" ]; then
    rm "$dest"
  elif [ -e "$dest" ]; then
    mkdir -p "$target/.trash"
    mv "$dest" "$target/.trash/$name-$stamp"
    echo "  backup: $dest -> $target/.trash/$name-$stamp"
  fi
  ln -s "${dir%/}" "$dest"
  echo "  linked: $dest -> ${dir%/}"
done
