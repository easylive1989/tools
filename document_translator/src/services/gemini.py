import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure repo root is in sys.path so `common` package is importable
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from common.gemini import GeminiClient as _BaseGeminiClient, is_gemini_cli_available

__all__ = ["GeminiClient", "is_gemini_cli_available"]


class GeminiClient:
    def __init__(self, model_name: str = "flash", use_cli: bool = False):
        self._client = _BaseGeminiClient(model_name=model_name, use_cli=use_cli)
        self.use_cli = use_cli
        self.model_name = model_name

    def _build_prompt(self, text: str, target_lang: str) -> str:
        return (
            f"Translate the following text into {target_lang}. "
            "Maintain the original tone and style. "
            "Do not add any explanations or extra text. "
            "Just provide the translation.\n\n"
            f"Text: {text}"
        )

    def translate_text(self, text: str, target_lang: str = "Traditional Chinese") -> str:
        """
        Translates text to the target language.

        Args:
            text (str): Text to translate.
            target_lang (str): Target language.

        Returns:
            str: Translated text.
        """
        if not text or not text.strip():
            return text
        prompt = self._build_prompt(text, target_lang)
        return self._client.generate(prompt)

    def translate_texts(self, texts: list[str], target_lang: str,
                        max_workers: int = 5, on_complete=None) -> list[str]:
        """
        Translates multiple texts in parallel using ThreadPoolExecutor.

        Args:
            texts: List of texts to translate.
            target_lang: Target language.
            max_workers: Maximum number of concurrent workers.
            on_complete: Optional callback invoked after each translation completes.

        Returns:
            List of translated texts in the same order as input.
        """
        results = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.translate_text, text, target_lang): i
                for i, text in enumerate(texts)
            }
            for future in as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()
                if on_complete:
                    on_complete()
        return results
