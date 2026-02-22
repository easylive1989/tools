# Plan: EPUB Translator Implementation & Refactoring

## Goal
Implement a dedicated EPUB translator (`src/epub_translator.py`) and extract common logic (CLI setup, API key management) into a shared module to avoid code duplication with `src/docx_translator.py`.

## Tasks

### Phase 1: Preparation & Dependencies
- [ ] Update `requirements.txt` to include `EbookLib` and `beautifulsoup4`.
- [ ] Install new dependencies.

### Phase 2: Refactoring Common Logic
- [ ] Create `src/utils/cli_helper.py` (or `src/common.py`).
    - [ ] Move `get_api_key` logic (Environment variable check -> Prompt) here.
    - [ ] Move `validate_file` logic here.
    - [ ] Move `setup_gemini_client` logic here (handling initialization and error printing).
- [ ] Refactor `src/docx_translator.py` to use the new shared functions.
    - [ ] Verify `docx_translator.py` still works correctly.

### Phase 3: EPUB Handler Implementation
- [ ] Create `src/handlers/epub.py`.
    - [ ] Class `EpubHandler`.
    - [ ] Use `EbookLib` to read `.epub` files.
    - [ ] Iterate through items, identifying `ITEM_DOCUMENT` (XHTML).
    - [ ] Use `BeautifulSoup` to parse HTML content.
    - [ ] Traverse text nodes (handling exclusion of code/script if necessary, though less common in standard ebooks than web pages).
    - [ ] Call `GeminiClient` to translate text.
    - [ ] Replace text in the soup object.
    - [ ] Write updated content back to the EPUB item.
    - [ ] Save the new `.epub` file using `ebooklib`.

### Phase 4: EPUB Translator CLI
- [ ] Create `src/epub_translator.py`.
    - [ ] Use `typer` for CLI arguments (similar to `docx_translator.py`).
    - [ ] Use shared logic from `src/utils/cli_helper.py` for API key and setup.
    - [ ] Instantiate and run `EpubHandler`.

### Phase 5: Testing & Documentation
- [ ] Create a simple test EPUB file (or find a sample).
- [ ] Run `python src/epub_translator.py test.epub`.
- [ ] Verify output content and formatting.
- [ ] Update `README.md` and `GEMINI.md` to mention the new tool and usage.

## Technical Details

### Shared Module Interface (`src/utils/cli_helper.py`)
```python
def get_or_prompt_api_key(api_key_arg: Optional[str], console: Console) -> str: ...
def validate_file_exists(filepath: str, console: Console) -> None: ...
def initialize_gemini(model_name: str, console: Console) -> GeminiClient: ...
```

### EPUB Handling Strategy
- **Granularity:** Translate paragraph by paragraph (`<p>`).
- **Context:** Preserve HTML tags.
- **Concurrency:** Single-threaded initially.

