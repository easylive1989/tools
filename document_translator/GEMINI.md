# Gemini Local Translator CLI

## Project Overview
This project is a command-line interface (CLI) tool designed to translate local documents (Markdown, DOCX, PDF, EPUB) using Google's Gemini models (Flash and Pro). It prioritizes privacy by processing files locally and sending only the text content to the Gemini API for translation.

**Key Features:**
*   **BYOK (Bring Your Own Key):** Users provide their own Google Gemini API Key.
*   **Format Preservation:**
    *   **Markdown:** Preserves code blocks, frontmatter, and inline code.
    *   **DOCX:** Preserves document structure and tables.
    *   **PDF:** Converts to DOCX first, then translates.
    *   **EPUB:** Preserves HTML structure, iterating through paragraphs.
*   **Models:** Supports `gemini-2.0-flash` (default, fast) and `gemini-2.5-pro` (high quality).

## Technology Stack
*   **Language:** Python 3.x
*   **CLI Framework:** `typer`
*   **UI/Output:** `rich`
*   **AI Integration:** `google-generativeai` (Gemini API)
*   **File Handling:**
    *   `python-docx` (Word documents)
    *   `pdf2docx` (PDF conversion)
    *   `EbookLib` (EPUB read/write)
    *   `beautifulsoup4` (HTML parsing for EPUB)
*   **Utilities:** `tenacity` (retries), `python-dotenv` (config)

## Architecture

### Directory Structure
*   `src/docx_translator.py`: The entry point for DOCX/PDF/Markdown translation.
*   `src/epub_translator.py`: The entry point for EPUB translation.
*   `src/services/gemini.py`: Encapsulates the interaction with the Gemini API. It handles model initialization and includes retry logic for robust network requests.
*   `src/utils/cli_helper.py`: Shared logic for API key retrieval, file validation, and client initialization.
*   `src/handlers/`: Contains specific logic for parsing and reconstructing different file formats.
    *   `markdown.py`: Splits content by code blocks/frontmatter to ensure only text is translated.
    *   `docx.py`: Likely iterates through paragraphs and tables in a Word document.
    *   `pdf.py`: orchestrates PDF-to-DOCX conversion before translation.
    *   `epub.py`: Iterates through EPUB items and uses BeautifulSoup to translate text content.

### Data Flow
1.  User executes `src/docx_translator.py` or `src/epub_translator.py` with a target file.
2.  Application loads API key from environment or prompt (via `src/utils/cli_helper.py`).
3.  `GeminiClient` is initialized with the selected model.
4.  Based on file extension, a specific Handler (e.g., `EpubHandler`) is instantiated.
5.  The Handler parses the file, identifying translatable text vs. structural elements (code blocks, formatting).
6.  Translatable text chunks are sent to `GeminiClient`.
7.  Translated text is reassembled into the original format and saved as a new file (e.g., `filename_translated.epub`).

## Setup and Usage

### Prerequisites
*   Python 3.x
*   Google Gemini API Key

### Installation
```bash
# Clone the repo
git clone <repository-url>
cd <repository-folder>

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Tool

#### Document Translator (DOCX, PDF, MD)
```bash
# Basic usage
python src/docx_translator.py <filename> [OPTIONS]

# Example: Translate a markdown file to Spanish
python src/docx_translator.py README.md --target-lang "Spanish"

# Example: Use the Pro model
python src/docx_translator.py document.pdf --model pro
```

#### EPUB Translator
```bash
# Basic usage
python src/epub_translator.py <filename.epub> [OPTIONS]

# Example: Translate an EPUB file
python src/epub_translator.py ebook.epub --target-lang "Traditional Chinese"
```

**Options:**
*   `--target-lang`, `-l`: Target language (default: "Traditional Chinese").
*   `--model`, `-m`: `flash` or `pro`.
*   `--api-key`, `-k`: Pass API key directly (optional if `GOOGLE_API_KEY` env var is set).

## Development Conventions

*   **Testing:** Unit tests are located in `tests/`. Run them using `python3 -m unittest tests/test_handlers.py`.
*   **Formatting:** Follow standard Python PEP 8 guidelines.
*   **Environment:** Use `.env` files for local configuration (handled by `python-dotenv`).
*   **Error Handling:** Use `tenacity` for transient API errors (Rate limits, Service Unavailable).