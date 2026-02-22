# Gemini Local Translator CLI

A command-line tool to translate local documents (Markdown, DOCX, PDF) using Google Gemini models (Flash/Pro), designed for privacy and ease of use.

## Features

- **BYOK (Bring Your Own Key):** Uses your personal Google Gemini API Key.
- **Local Processing:** Files are processed locally; content is sent to Gemini API only for translation. No intermediate servers.
- **Format Support:**
  - **Markdown (.md):** Preserves code blocks (```...```) and translates text content.
  - **Word (.docx):** Translates paragraphs and table content while preserving basic structure.
  - **PDF (.pdf):** Converts PDF to DOCX and then translates it (output is a translated DOCX file).
- **Models:** Supports `Gemini 1.5 Flash` (fast, cheap) and `Gemini 1.5 Pro` (higher quality).

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-folder>
   ```

2. **Install dependencies:**
   It is recommended to use a virtual environment.
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Configuration

You need a Google Gemini API Key. You can get one from [Google AI Studio](https://aistudio.google.com/).

**Option 1: Environment Variable (Recommended)**
Set the `GOOGLE_API_KEY` environment variable.
```bash
export GOOGLE_API_KEY="your_api_key_here"
```

**Option 2: Interactive Input**
If the environment variable is not set, the tool will prompt you to enter the key securely when you run it.

**Option 3: Command Line Argument**
You can pass the key directly (less secure for history logs).
```bash
python src/docx_translator.py document.md --api-key "your_key"
```

## Usage

Run the tool from the project root directory.

### Basic Syntax
```bash
python src/docx_translator.py <filename> [OPTIONS]
```

### Examples

**Translate a Markdown file to Traditional Chinese (default):**
```bash
python src/docx_translator.py README.md
```
*Output:* `README_translated.md`

**Translate a PDF to Spanish using the Pro model:**
```bash
python src/docx_translator.py report.pdf --target-lang "Spanish" --model pro
```
*Output:* `report_translated.docx` (Note: PDF is converted to editable DOCX)

**Translate a Word document to Japanese:**
```bash
python src/docx_translator.py specs.docx --target-lang "Japanese"
```
*Output:* `specs_translated.docx`

### Options

- `filename`: Path to the input file (required).
- `--target-lang`, `-l`: Target language (default: "Traditional Chinese").
- `--model`, `-m`: Gemini model to use: `flash` or `pro` (default: "flash").
- `--api-key`, `-k`: Google Gemini API Key.
- `--help`: Show help message.

## Development

**Run Tests:**
```bash
python3 -m unittest tests/test_handlers.py
```
