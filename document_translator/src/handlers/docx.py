import os
from docx import Document
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from src.services.gemini import GeminiClient

console = Console()

class DocxHandler:
    def __init__(self, gemini_client: GeminiClient, target_lang: str):
        self.client = gemini_client
        self.target_lang = target_lang

    def process(self, input_path: str):
        """
        Reads a DOCX file, translates paragraphs and table cells,
        and saves the result.
        """
        output_path = f"{os.path.splitext(input_path)[0]}_translated.docx"

        doc = Document(input_path)

        # Collect all paragraphs that need translation
        para_refs = []
        texts = []

        for para in doc.paragraphs:
            if para.text.strip():
                para_refs.append(para)
                texts.append(para.text)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        if para.text.strip():
                            para_refs.append(para)
                            texts.append(para.text)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("[green]Translating...", total=len(texts))

            translated_texts = self.client.translate_texts(
                texts, self.target_lang,
                on_complete=lambda: progress.advance(task)
            )

        # Write back translated texts
        for para, translated_text in zip(para_refs, translated_texts):
            para.clear()
            para.add_run(translated_text)

        doc.save(output_path)
        return output_path
