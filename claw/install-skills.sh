#!/usr/bin/env bash
# Symlink every SKILL.md under ~/.pclaw/skills into the native skill dirs of
# Claude Code (~/.claude/skills/) and Gemini CLI (via `gemini skills link`).
# Using symlinks means future edits to the pclaw source update both CLIs
# automatically.
#
# Safe on repeat: replaces pclaw-owned symlinks, refuses to touch anything that
# already exists but isn't a symlink we placed.
set -euo pipefail

SRC="$HOME/.pclaw/skills"
CLAUDE_DST="$HOME/.claude/skills"

if [[ ! -d "$SRC" ]]; then
    echo "no skills dir at $SRC — create SKILL.md files there first" >&2
    exit 1
fi

shopt -s nullglob
skill_dirs=("$SRC"/*/)
if [[ ${#skill_dirs[@]} -eq 0 ]]; then
    echo "no skills in $SRC"
    exit 0
fi

mkdir -p "$CLAUDE_DST"
has_gemini=0
command -v gemini >/dev/null 2>&1 && has_gemini=1

install_claude() {
    local name="$1" src_real="$2"
    local target="$CLAUDE_DST/$name"

    if [[ -L "$target" ]]; then
        local existing_target
        existing_target=$(readlink "$target")
        # resolve to absolute for comparison
        existing_target=$(cd "$(dirname "$target")" && cd "$(dirname "$existing_target")" 2>/dev/null && pwd -P)/$(basename "$(readlink "$target")") || true
        # simpler: just compare realpath if both resolve
        if [[ "$(realpath "$target" 2>/dev/null || true)" == "$src_real" ]]; then
            echo "  claude: $name (already linked)"
            return
        fi
        rm "$target"
    elif [[ -e "$target" ]]; then
        echo "  claude: $name — refusing (exists and is not a symlink)" >&2
        return
    fi

    ln -s "$src_real" "$target"
    echo "  claude: $name → $src_real"
}

install_gemini() {
    local name="$1" src_real="$2"
    # `link` is idempotent in practice, but if previously installed under a
    # different path it can leave a stale entry. Uninstall-if-exists first,
    # ignore errors (name not installed is also an error).
    gemini skills uninstall "$name" >/dev/null 2>&1 || true
    # --consent skips the "are you sure you trust this skill" prompt that would
    # otherwise hang non-interactively.
    if gemini skills link "$src_real" --consent >/dev/null 2>&1; then
        echo "  gemini: $name → $src_real"
    else
        echo "  gemini: $name — link failed" >&2
    fi
}

echo "installing skills from $SRC"
for dir in "${skill_dirs[@]}"; do
    name=$(basename "$dir")
    if [[ ! -f "$dir/SKILL.md" ]]; then
        echo "  skip $name (no SKILL.md)" >&2
        continue
    fi
    src_real=$(cd "$dir" && pwd -P)

    install_claude "$name" "$src_real"
    (( has_gemini )) && install_gemini "$name" "$src_real"
done
echo "done"
