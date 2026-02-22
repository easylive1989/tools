import os
import re
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from src.services.gemini import GeminiClient

console = Console()

class MarkdownHandler:
    def __init__(self, gemini_client: GeminiClient, target_lang: str):
        self.client = gemini_client
        self.target_lang = target_lang

    def process(self, input_path: str):
        """
        Reads a markdown file, splits it into blocks, translates text blocks,
        and saves the result.
        """
        output_path = f"{os.path.splitext(input_path)[0]}_translated.md"

        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = re.compile(r'(```[\s\S]*?```|---[\s\S]*?---|`[^`\n]+`)')
        parts = pattern.split(content)

        # Build the structure and collect texts to translate
        # Each entry in structure is either:
        #   ("keep", text) - kept as-is (special blocks, empty parts)
        #   ("translate", part_idx, para_idx) - placeholder referencing texts_to_translate
        structure = []
        texts_to_translate = []

        for part in parts:
            if not part:
                continue

            is_special = (
                part.startswith('```') or
                part.startswith('---') or
                (part.startswith('`') and part.endswith('`'))
            )

            if is_special:
                structure.append(("keep", part))
            else:
                paragraphs = part.split('\n\n')
                part_entries = []
                for p in paragraphs:
                    if p.strip():
                        idx = len(texts_to_translate)
                        texts_to_translate.append(p)
                        part_entries.append(("translate", idx))
                    else:
                        part_entries.append(("keep", p))
                structure.append(("paragraphs", part_entries))

        # Batch translate all collected texts
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

        # Reassemble the document
        translated_parts = []
        for entry in structure:
            if entry[0] == "keep":
                translated_parts.append(entry[1])
            elif entry[0] == "paragraphs":
                para_results = []
                for sub in entry[1]:
                    if sub[0] == "translate":
                        para_results.append(translated_texts[sub[1]])
                    else:
                        para_results.append(sub[1])
                translated_parts.append('\n\n'.join(para_results))

        final_content = "".join(translated_parts)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_content)

        return output_path
