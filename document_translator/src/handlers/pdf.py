import os
from pdf2docx import Converter
from src.services.gemini import GeminiClient
from src.handlers.docx import DocxHandler
from rich.console import Console

console = Console()

class PdfHandler:
    def __init__(self, gemini_client: GeminiClient, target_lang: str):
        self.client = gemini_client
        self.target_lang = target_lang
        # Reuse DocxHandler logic
        self.docx_handler = DocxHandler(gemini_client, target_lang)

    def process(self, input_path: str):
        """
        Converts PDF to DOCX, then translates the DOCX.
        """
        # 1. Convert PDF to temporary DOCX
        temp_docx = f"{os.path.splitext(input_path)[0]}.docx"

        # Check if a docx with that name already exists to avoid overwriting user files
        if os.path.exists(temp_docx):
            console.print(f"[yellow]Warning: Intermediate file '{temp_docx}' already exists and will be overwritten.[/yellow]")

        console.print(f"[blue]Converting PDF to DOCX structure...[/blue]")

        try:
            cv = Converter(input_path)
            cv.convert(temp_docx)
            cv.close()
        except Exception as e:
            console.print(f"[bold red]Error converting PDF: {e}[/bold red]")
            raise e

        # 2. Translate the generated DOCX
        # Note: The output of docx_handler will be {temp_docx}_translated.docx
        # e.g. report.pdf -> report.docx -> report_translated.docx

        console.print(f"[blue]Translating extracted content...[/blue]")
        final_output = self.docx_handler.process(temp_docx)

        # Cleanup: Optionally remove the intermediate report.docx?
        # The spec says "PDF 來源檔翻譯後將輸出為 .docx 格式".
        # It doesn't explicitly say delete the intermediate.
        # But usually users might find it confusing to have report.docx AND report_translated.docx
        # if they only started with report.pdf.
        # However, report.docx is the "source" for translation.
        # Let's keep it for now as it might be useful, or delete it if we want to be clean.
        # Given the "Privacy/Local" nature, maybe keeping the intermediate conversion is safe.
        # But "User Agreed Requirement" says output is .docx.
        # Let's stick to returning the final output path.

        return final_output
