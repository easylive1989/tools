import os
import re
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from src.services.gemini import GeminiClient

console = Console()


class MarkdownBilingualHandler:
    """
    Translates a markdown file paragraph by paragraph,
    placing the translation below each original paragraph.
    Images, links, code blocks, and frontmatter are kept as-is.
    """

    # Regex patterns for lines that should NOT be translated
    IMAGE_PATTERN = re.compile(r'^\s*!\[.*\]\(.*\)\s*$')
    LINK_ONLY_PATTERN = re.compile(r'^\s*\[.*\]\(.*\)\s*$')

    def __init__(self, gemini_client: GeminiClient, target_lang: str):
        self.client = gemini_client
        self.target_lang = target_lang

    def _should_skip(self, paragraph: str) -> bool:
        """Return True if this paragraph should NOT be translated."""
        stripped = paragraph.strip()
        if not stripped:
            return True
        # Image-only paragraph
        if self.IMAGE_PATTERN.match(stripped):
            return True
        # Link-only paragraph
        if self.LINK_ONLY_PATTERN.match(stripped):
            return True
        return False

    def process(self, input_path: str) -> str:
        output_path = f"{os.path.splitext(input_path)[0]}_translated.md"

        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split into blocks: code fences and frontmatter vs. normal text
        # This regex captures fenced code blocks (```...```) and frontmatter (---...---)
        pattern = re.compile(r'(```[\s\S]*?```|^---[\s\S]*?^---)', re.MULTILINE)
        parts = pattern.split(content)

        # Build structure:
        #   ("keep", text)           — code blocks, frontmatter, images, links, empty
        #   ("translate", text)      — text paragraph to translate
        structure = []
        total_to_translate = 0

        for part in parts:
            if not part:
                continue

            is_special = (
                part.startswith('```') or
                (part.startswith('---') and part.endswith('---') and '\n' in part)
            )

            if is_special:
                structure.append(("keep", part))
            else:
                # Split into paragraphs by double newline
                paragraphs = part.split('\n\n')
                para_entries = []
                for p in paragraphs:
                    if self._should_skip(p):
                        para_entries.append(("keep", p))
                    else:
                        total_to_translate += 1
                        para_entries.append(("translate", p))
                structure.append(("paragraphs", para_entries))

        # Incrementally translate and write to file
        with open(output_path, 'w', encoding='utf-8') as out_f:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task(
                    "[green]Translating...", total=max(total_to_translate, 1)
                )

                first_block = True
                for entry in structure:
                    if not first_block:
                        # structure blocks were produced by regex split,
                        # joining them back without separator preserves original content
                        pass
                    first_block = False

                    if entry[0] == "keep":
                        out_f.write(entry[1])
                        out_f.flush()
                    elif entry[0] == "paragraphs":
                        first_para = True
                        for sub in entry[1]:
                            if not first_para:
                                out_f.write('\n\n')
                            first_para = False

                            if sub[0] == "translate":
                                original = sub[1]
                                preview = original.replace('\n', ' ')[:60]
                                console.print(f"[dim]Translating: {preview}...[/dim]")
                                translated = self.client.translate_text(
                                    original, self.target_lang
                                )
                                out_f.write(f"{original}\n\n{translated}")
                                out_f.flush()
                                progress.advance(task)
                            else:
                                out_f.write(sub[1])
                                out_f.flush()

        return output_path
