import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


log = logging.getLogger(__name__)

_SLASH_RE = re.compile(r"^/(\S+)(?:\s+([\s\S]*))?$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.+?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    template: str

    def render(self, user_input: str) -> str:
        rendered = self.template.replace("{{input}}", user_input)
        if "{{input}}" not in self.template and user_input:
            # Skill didn't declare an input placeholder but user passed args —
            # append them so nothing gets lost.
            rendered = f"{rendered}\n\n{user_input}"
        return rendered.strip()


class SkillRegistry:
    """Discovers SKILL.md files under `skills_dir`.

    Layout (openclaw / Claude-compatible):

        <skills_dir>/<skill-name>/SKILL.md

    Each SKILL.md has YAML frontmatter (`name`, `description`) and a markdown
    body that is used as the prompt template. Use `{{input}}` inside the body
    to mark where the user's slash-command argument should be spliced in.
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        if not self.skills_dir.exists():
            return
        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                skill = _parse_skill_file(skill_md)
            except Exception as e:
                log.warning("skill load failed for %s: %s", skill_md, e)
                continue
            self._skills[skill.name] = skill
        log.info("loaded %d skills: %s", len(self._skills), sorted(self._skills))

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return sorted(self._skills.keys())


def parse_slash(content: str) -> tuple[str, str] | None:
    """Return (skill_name, args) for a leading-slash message, or None."""
    m = _SLASH_RE.match(content.strip())
    if not m:
        return None
    return m.group(1), (m.group(2) or "").strip()


def _parse_skill_file(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path} is missing YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    name = meta.get("name") or path.parent.name
    description = meta.get("description", "")
    body = m.group(2).strip()
    if not body:
        raise ValueError(f"{path} has empty body")
    return Skill(name=str(name), description=str(description), template=body)
