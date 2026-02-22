import os
import re
from rich.console import Console
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

        # Split content by code blocks and frontmatter
        # Regex to capture:
        # 1. Frontmatter (YAML style between ---)
        # 2. Code blocks (between ```)
        # 3. Inline code (between `) - actually inline code is harder to split,
        #    usually we treat paragraphs as units.
        #    For MVP, let's split by major code blocks.

        # Strategy: Use a regex to find code blocks, then everything between them is text to translate.

        pattern = re.compile(r'(```[\s\S]*?```|---[\s\S]*?---|`[^`\n]+`)')

        parts = pattern.split(content)
        translated_parts = []

        total_parts = len(parts)

        for i, part in enumerate(parts):
            if not part:
                continue

            # Check if this part is a special block (code or frontmatter)
            is_special = (
                part.startswith('```') or
                part.startswith('---') or
                (part.startswith('`') and part.endswith('`'))
            )

            if is_special:
                translated_parts.append(part)
            else:
                # This is a text block. It might contain multiple paragraphs.
                # We should translate it.
                # Optimization: Split by newlines to avoid sending huge blobs?
                # Or just send the whole chunk if it's not too big.
                # For safety and formatting, let's split by double newlines (paragraphs)

                paragraphs = part.split('\n\n')
                translated_paragraphs = []
                for p in paragraphs:
                    if p.strip():
                        # Determine if it's a header or list item, etc.
                        # Gemini usually handles "Translate this Markdown text" well.
                        translated_text = self.client.translate_text(p, self.target_lang)
                        translated_paragraphs.append(translated_text)
                    else:
                        translated_paragraphs.append(p)

                translated_parts.append('\n\n'.join(translated_paragraphs))

            # Simple progress log (real progress bar handled in main)
            # console.log(f"Processed part {i+1}/{total_parts}")

        final_content = "".join(translated_parts)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_content)

        return output_path
