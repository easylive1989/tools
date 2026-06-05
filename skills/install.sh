#!/usr/bin/env bash
# Install SKILL.md packages from this repo's skills/ into the global skills
# directory of Claude Code and/or Antigravity CLI — by copying (a snapshot,
# not a symlink).
#
# Usage:
#   ./skills/install.sh <target> [skill ...]
#
#   target : claude | antigravity | all
#   skill  : optional skill name(s) to install; defaults to every skill
#            directory under skills/ that contains a SKILL.md
#
# Targets:
#   claude       -> ~/.claude/skills/<name>/
#   antigravity  -> ~/.gemini/antigravity/skills/<name>/

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

CLAUDE_DST="$HOME/.claude/skills"
ANTIGRAVITY_DST="$HOME/.gemini/antigravity/skills"

usage() {
    cat >&2 <<EOF
usage: $(basename "$0") <target> [skill ...]

  target : claude | antigravity | all
  skill  : skill name(s) to install (default: all skills under skills/)

examples:
  $(basename "$0") claude
  $(basename "$0") all pr-walkthrough
  $(basename "$0") antigravity pr-walkthrough project-onboarding
EOF
    exit 1
}

[[ $# -ge 1 ]] || usage
target="$1"
shift

case "$target" in
    claude | antigravity | all) ;;
    *)
        echo "error: invalid target '$target'" >&2
        usage
        ;;
esac

# Resolve which skills to install.
declare -a skills=()
if [[ $# -gt 0 ]]; then
    for name in "$@"; do
        if [[ ! -f "$SRC/$name/SKILL.md" ]]; then
            echo "error: skill '$name' not found (no $SRC/$name/SKILL.md)" >&2
            exit 1
        fi
        skills+=("$name")
    done
else
    shopt -s nullglob
    for dir in "$SRC"/*/; do
        name="$(basename "$dir")"
        if [[ -f "$dir/SKILL.md" ]]; then
            skills+=("$name")
        else
            echo "  skip $name (no SKILL.md)" >&2
        fi
    done
    if [[ ${#skills[@]} -eq 0 ]]; then
        echo "error: no skills with a SKILL.md found under $SRC" >&2
        exit 1
    fi
fi

# Copy one skill directory into a destination skills dir, replacing any
# existing copy and dropping .DS_Store noise.
install_one() {
    local label="$1" dst_root="$2" name="$3"
    local dst="$dst_root/$name"

    mkdir -p "$dst_root"
    rm -rf "$dst"
    cp -R "$SRC/$name" "$dst"
    rm -f "$dst/.DS_Store"
    echo "  $label: $name"
}

install_target() {
    local label="$1" dst_root="$2"
    echo "installing into $dst_root"
    for name in "${skills[@]}"; do
        install_one "$label" "$dst_root" "$name"
    done
}

if [[ "$target" == "claude" || "$target" == "all" ]]; then
    install_target claude "$CLAUDE_DST"
fi
if [[ "$target" == "antigravity" || "$target" == "all" ]]; then
    install_target antigravity "$ANTIGRAVITY_DST"
fi

echo "done"
