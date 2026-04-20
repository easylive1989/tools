#!/usr/bin/env bash
# Wire every SKILL.md under ~/.pclaw/skills into the native registries of
# Claude Code and Gemini CLI — **scoped to pclaw**, not installed globally.
#
# Claude: builds a local plugin at ~/.pclaw/.claude/ that the bot loads via
#         --plugin-dir on every invocation. ~/.claude/skills/ stays untouched.
# Gemini: uses workspace scope with cwd=~/.pclaw/workdir/, so the symlink lives
#         under that workspace's .gemini/ rather than the global ~/.gemini/.
#
# Uses symlinks — editing a SKILL.md under ~/.pclaw/skills takes effect in both
# CLIs immediately without re-running this script.

set -euo pipefail

PCLAW="$HOME/.pclaw"
SRC="$PCLAW/skills"
CLAUDE_ROOT="$PCLAW/.claude"
CLAUDE_SKILLS_DST="$CLAUDE_ROOT/skills"
GEMINI_WORKSPACE="$PCLAW"

if [[ ! -d "$SRC" ]]; then
    echo "no skills dir at $SRC — create SKILL.md files there first" >&2
    exit 1
fi

# --- Claude plugin scaffold -------------------------------------------------
mkdir -p "$CLAUDE_ROOT/.claude-plugin" "$CLAUDE_SKILLS_DST"
if [[ ! -f "$CLAUDE_ROOT/.claude-plugin/plugin.json" ]]; then
    cat > "$CLAUDE_ROOT/.claude-plugin/plugin.json" <<'EOF'
{
  "name": "pclaw",
  "description": "Skills invoked from the pclaw Discord bot",
  "version": "0.1.0",
  "author": { "name": "pclaw" }
}
EOF
    echo "created $CLAUDE_ROOT/.claude-plugin/plugin.json"
fi

# --- One-time migration: evict pclaw symlinks that live in the global dir ---
if [[ -d "$HOME/.claude/skills" ]]; then
    for old in "$HOME/.claude/skills"/*; do
        [[ -L "$old" ]] || continue
        target=$(readlink "$old" 2>/dev/null || echo "")
        case "$target" in
            "$SRC"/*|*"/.pclaw/skills/"*)
                echo "  migrate: rm $old (moving under $CLAUDE_SKILLS_DST)"
                rm "$old"
                ;;
        esac
    done
fi

# --- Install each skill into both CLIs --------------------------------------
shopt -s nullglob
skill_dirs=("$SRC"/*/)
if [[ ${#skill_dirs[@]} -eq 0 ]]; then
    echo "no skills in $SRC"
    exit 0
fi

has_gemini=0
command -v gemini >/dev/null 2>&1 && has_gemini=1
mkdir -p "$GEMINI_WORKSPACE"

install_claude() {
    local name="$1" src_real="$2"
    local target="$CLAUDE_SKILLS_DST/$name"

    if [[ -L "$target" ]]; then
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
    echo "  claude: $name"
}

install_gemini_workspace() {
    local name="$1" src_real="$2"
    # Run from the workspace so gemini scopes the link there, not in ~/.gemini/.
    (
        cd "$GEMINI_WORKSPACE"
        gemini skills uninstall "$name" --scope workspace >/dev/null 2>&1 || true
        # Also evict a global-scope stale link from a previous install_skills.sh.
        gemini skills uninstall "$name" --scope user >/dev/null 2>&1 || true
        if gemini skills link "$src_real" --scope workspace --consent >/dev/null 2>&1; then
            echo "  gemini: $name"
        else
            echo "  gemini: $name — link failed" >&2
        fi
    )
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
    (( has_gemini )) && install_gemini_workspace "$name" "$src_real"
done
echo "done"
