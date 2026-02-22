import os
import typer
from rich.console import Console
from rich.prompt import Prompt
from typing import Optional
from src.services.gemini import GeminiClient, is_gemini_cli_available

def get_or_prompt_api_key(api_key_arg: Optional[str], console: Console) -> str:
    """
    Retrieves the API key from argument, environment variable, or interactive prompt.
    """
    key = api_key_arg or os.getenv("GOOGLE_API_KEY")
    if not key:
        console.print("[bold yellow]API Key not found in environment variables.[/bold yellow]")
        key = Prompt.ask("Please enter your Google Gemini API Key", password=True)

    if not key:
        console.print("[bold red]Error: API Key is required to proceed.[/bold red]")
        raise typer.Exit(code=1)

    # Update env var for subsequent usage if needed
    os.environ["GOOGLE_API_KEY"] = key
    return key

def validate_file_exists(filename: str, console: Console) -> None:
    """
    Validates that the file exists. Exits if not found.
    """
    if not os.path.exists(filename):
        console.print(f"[bold red]Error: File '{filename}' not found.[/bold red]")
        raise typer.Exit(code=1)

def initialize_gemini(model_name: str, console: Console, api_key: Optional[str] = None) -> GeminiClient:
    """
    Initializes the Gemini Client.
    Prioritizes local gemini CLI; falls back to API if CLI is not available.
    """
    if is_gemini_cli_available():
        console.print("[bold cyan]Detected local Gemini CLI, using CLI mode (no API key needed).[/bold cyan]")
        return GeminiClient(model_name=model_name, use_cli=True)

    # CLI not available, need API key
    console.print("[bold yellow]Gemini CLI not found, falling back to API mode.[/bold yellow]")
    get_or_prompt_api_key(api_key, console)

    try:
        return GeminiClient(model_name=model_name, use_cli=False)
    except Exception as e:
        console.print(f"[bold red]Error initializing Gemini Client: {e}[/bold red]")
        raise typer.Exit(code=1)
