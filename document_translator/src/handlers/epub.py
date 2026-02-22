import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString
from src.services.gemini import GeminiClient
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

class EpubHandler:
    def __init__(self, gemini_client: GeminiClient, target_lang: str):
        self.client = gemini_client
        self.target_lang = target_lang

    def process(self, input_path: str) -> str:
        """
        Reads an EPUB file, translates text content in HTML documents, and saves the result.
        """
        output_path = f"{os.path.splitext(input_path)[0]}_translated.epub"

        try:
            book = epub.read_epub(input_path)
        except Exception as e:
            raise ValueError(f"Failed to read EPUB file: {e}")

        items = list(book.get_items())
        total_items = len([i for i in items if i.get_type() == ebooklib.ITEM_DOCUMENT])
        processed_count = 0

        for item in items:
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                processed_count += 1
                console.print(f"Processing chapter {processed_count}/{total_items}...", style="dim")

                try:
                    content = item.get_content()
                    soup = BeautifulSoup(content, 'html.parser')

                    self._translate_soup(soup)

                    item.set_content(str(soup).encode('utf-8'))
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to process item {item.get_name()}: {e}[/yellow]")

        epub.write_epub(output_path, book, {})
        return output_path

    def _translate_soup(self, soup: BeautifulSoup):
        """
        Collects all translatable text nodes, batch-translates them, and writes back.
        """
        # Collect all translatable text nodes
        node_refs = []
        texts = []

        for text_node in soup.find_all(string=True):
            if isinstance(text_node, NavigableString):
                parent_name = text_node.parent.name
                if parent_name in ['script', 'style', 'head', 'title', 'meta', '[document]']:
                    continue

                original_text = str(text_node).strip()
                if not original_text:
                    continue

                if original_text.isdigit() or len(original_text) < 2:
                    continue

                node_refs.append(text_node)
                texts.append(original_text)

        if not texts:
            return

        # Batch translate
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("[green]Translating chapter...", total=len(texts))

            translated_texts = self.client.translate_texts(
                texts, self.target_lang,
                on_complete=lambda: progress.advance(task)
            )

        # Write back translated texts
        for text_node, translated_text in zip(node_refs, translated_texts):
            text_node.replace_with(translated_text)
