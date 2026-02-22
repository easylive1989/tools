import os
import sys

# Ensure project root is in sys.path so imports starting with 'src.' work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import typer
from typing import Optional
from rich.console import Console
from dotenv import load_dotenv
from src.utils.cli_helper import validate_file_exists, initialize_gemini

# Initialize Typer app and Rich console
app = typer.Typer(help="Gemini EPUB Translator CLI")
console = Console()

# Load environment variables
load_dotenv()

@app.command()
def translate(
    filename: str = typer.Argument(..., help="Path to the EPUB file to be translated"),
    target_lang: str = typer.Option("Traditional Chinese", "--target-lang", "-l", help="Target language for translation"),
    model: str = typer.Option("flash", "--model", "-m", help="Gemini model to use: 'flash' or 'pro'"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="Google Gemini API Key (only needed if Gemini CLI is not installed)")
):
    """
    Translates an EPUB document using Google Gemini.
    Prioritizes local Gemini CLI if available; falls back to API.
    """

    # 1. File Validation
    validate_file_exists(filename, console)

    ext = os.path.splitext(filename)[1].lower()
    if ext != ".epub":
        console.print(f"[bold red]Error: File '{filename}' is not an EPUB file.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Starting translation for:[/bold green] {filename}")
    console.print(f"Target Language: {target_lang}")
    console.print(f"Model: {model}")

    # 2. Initialize Gemini Client (auto-detects CLI vs API)
    client = initialize_gemini(model, console, api_key)

    try:
        from src.handlers.epub import EpubHandler
        handler = EpubHandler(client, target_lang)
        output_file = handler.process(filename)

        if output_file:
             console.print(f"[bold green]Translation completed successfully![/bold green]")
             console.print(f"Output saved to: {output_file}")

    except Exception as e:
        console.print(f"[bold red]An error occurred during translation: {e}[/bold red]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
