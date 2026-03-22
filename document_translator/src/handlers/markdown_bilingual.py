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
        #   ("translate", index)     — text paragraph referencing texts_to_translate
        structure = []
        texts_to_translate = []

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
                        idx = len(texts_to_translate)
                        texts_to_translate.append(p)
                        para_entries.append(("translate", idx))
                structure.append(("paragraphs", para_entries))

        # Batch translate
        if texts_to_translate:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[green]Translating...", total=len(texts_to_translate))

                translated_texts = self.client.translate_texts(
                    texts_to_translate, self.target_lang,
                    on_complete=lambda: progress.advance(task)
                )
        else:
            translated_texts = []

        # Reassemble: for translated paragraphs, place translation below original
        output_parts = []
        for entry in structure:
            if entry[0] == "keep":
                output_parts.append(entry[1])
            elif entry[0] == "paragraphs":
                para_results = []
                for sub in entry[1]:
                    if sub[0] == "translate":
                        original = texts_to_translate[sub[1]]
                        translated = translated_texts[sub[1]]
                        # Original paragraph followed by translation
                        para_results.append(f"{original}\n\n{translated}")
                    else:
                        para_results.append(sub[1])
                output_parts.append('\n\n'.join(para_results))

        final_content = "".join(output_parts)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_content)

        return output_path
