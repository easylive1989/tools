import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString
from src.services.gemini import GeminiClient
from rich.console import Console

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
                
                # Parse HTML content
                try:
                    content = item.get_content()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Translate text nodes
                    self._translate_soup(soup)
                    
                    # Update item content
                    item.set_content(str(soup).encode('utf-8'))
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to process item {item.get_name()}: {e}[/yellow]")

        # Write output file
        epub.write_epub(output_path, book, {})
        return output_path

    def _translate_soup(self, soup: BeautifulSoup):
        """
        Recursively finds and translates text in the soup.
        """
        # We look for text nodes that are not inside script or style tags
        # and are substantial enough to be translated.
        
        # Using find_all with text=True (in older BS4) or just finding tags and iterating contents
        # A safer approach for valid HTML structure:
        # Iterate over all tags that usually contain text: p, div, span, h1-h6, li, etc.
        # But text can be naked too.
        
        # Let's iterate over all text strings in the document
        for text_node in soup.find_all(string=True):
            if isinstance(text_node, NavigableString):
                parent_name = text_node.parent.name
                if parent_name in ['script', 'style', 'head', 'title', 'meta', '[document]']:
                    continue
                
                original_text = str(text_node).strip()
                if not original_text:
                    continue
                
                # Skip numeric-only or symbol-only strings to save API calls
                if original_text.isdigit() or len(original_text) < 2:
                    continue

                try:
                    # Show current text being translated
                    preview = original_text[:80] + ("..." if len(original_text) > 80 else "")
                    console.print(f"  [dim]原文:[/dim] {preview}")

                    translated_text = self.client.translate_text(original_text, self.target_lang)

                    translated_preview = translated_text[:80] + ("..." if len(translated_text) > 80 else "")
                    console.print(f"  [green]譯文:[/green] {translated_preview}")

                    text_node.replace_with(translated_text)
                except Exception as e:
                    console.print(f"  [red]翻譯失敗: {e}[/red]")
                    pass
