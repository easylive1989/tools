import os
import re
import shutil
import subprocess
from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDJKsuhl]|\r")


def is_claude_cli_available() -> bool:
    """Check if claude CLI is installed locally."""
    return shutil.which("claude") is not None


class GeminiClient:
    def __init__(self, model_name: str = "flash", use_cli: bool = False):
        self.use_cli = use_cli
        self.model_name = model_name

        self.model_map = {
            "flash": "gemini-2.5-flash",
            "pro": "gemini-2.5-pro"
        }

        if self.use_cli:
            return

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set.")

        self.client = genai.Client(api_key=api_key)

    def _generate_via_cli(self, prompt: str, timeout: int = 120) -> str:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")

        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "sonnet"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        if result.returncode != 0:
            err = _ANSI_RE.sub("", result.stderr).strip()
            raise RuntimeError(f"Claude CLI error: {err}")

        return _ANSI_RE.sub("", result.stdout).strip()

    @retry(
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(20)
    )
    def _generate_via_api(self, prompt: str) -> str:
        target_model = self.model_map.get(self.model_name.lower(), self.model_name)
        response = self.client.models.generate_content(model=target_model, contents=prompt)
        return response.text.strip()

    def generate(self, prompt: str, timeout: int = 120) -> str:
        if self.use_cli:
            return self._generate_via_cli(prompt, timeout=timeout)
        else:
            return self._generate_via_api(prompt)
