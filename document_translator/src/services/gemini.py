import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable


def is_gemini_cli_available() -> bool:
    """Check if gemini CLI is installed locally."""
    return shutil.which("gemini") is not None


class GeminiClient:
    def __init__(self, model_name: str = "flash", use_cli: bool = False):
        """
        Initialize the Gemini Client.

        Args:
            model_name (str): "flash" or "pro". Defaults to "flash".
            use_cli (bool): If True, use gemini CLI instead of API.
        """
        self.use_cli = use_cli
        self.model_name = model_name

        if self.use_cli:
            # CLI mode: no API key needed
            self.model_map = {
                "flash": "gemini-2.0-flash",
                "pro": "gemini-2.5-pro"
            }
            return

        # API mode: requires API key
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set.")

        genai.configure(api_key=api_key)

        self.model_map = {
            "flash": "gemini-2.0-flash",
            "pro": "gemini-2.5-pro"
        }

        target_model = self.model_map.get(model_name.lower(), model_name)
        self.model = genai.GenerativeModel(target_model)

    def _build_prompt(self, text: str, target_lang: str) -> str:
        return (
            f"Translate the following text into {target_lang}. "
            "Maintain the original tone and style. "
            "Do not add any explanations or extra text. "
            "Just provide the translation.\n\n"
            f"Text: {text}"
        )

    def _translate_via_cli(self, text: str, target_lang: str) -> str:
        """Translate text using the gemini CLI."""
        prompt = self._build_prompt(text, target_lang)
        target_model = self.model_map.get(self.model_name.lower(), self.model_name)

        result = subprocess.run(
            ["gemini", "-m", target_model, "-o", "text", prompt],
            input=text,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Gemini CLI error: {result.stderr.strip()}")

        return result.stdout.strip()

    @retry(
        retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable)),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(20)
    )
    def _translate_via_api(self, text: str, target_lang: str) -> str:
        """Translate text using the Gemini API."""
        prompt = self._build_prompt(text, target_lang)
        response = self.model.generate_content(prompt)
        return response.text.strip()

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

        if self.use_cli:
            return self._translate_via_cli(text, target_lang)
        else:
            return self._translate_via_api(text, target_lang)

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
