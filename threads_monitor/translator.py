import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.gemini import GeminiClient

_HAN_RE = re.compile(r"[㐀-䶿一-鿿]")
_KANA_RE = re.compile(r"[぀-ヿ]")
_FOREIGN_WORD_RE = re.compile(r"[^\W\d_]+")

# 一個漢字約等於一個詞，故以「漢字數 vs 外文單字數」比較；
# 漢字佔比達此門檻即視為中文（容忍中英夾雜的貼文）
_HAN_RATIO_THRESHOLD = 0.5


def is_chinese(text: str) -> bool:
    """判斷內文是否已是中文。含日文假名視為非中文（日文也用漢字）。"""
    if _KANA_RE.search(text):
        return False
    han = len(_HAN_RE.findall(text))
    foreign_words = len(_FOREIGN_WORD_RE.findall(_HAN_RE.sub(" ", text)))
    if han + foreign_words == 0:
        return True  # 純數字/符號，不需翻譯
    return han / (han + foreign_words) >= _HAN_RATIO_THRESHOLD


class Translator:
    def __init__(self, gemini: GeminiClient) -> None:
        self.gemini = gemini

    def translate_to_chinese(self, text: str) -> str:
        prompt = (
            "請將以下社群貼文內容翻譯成繁體中文（台灣用語）。"
            "只輸出翻譯結果，不要加任何說明或前綴。"
            "保留原文中的 hashtag、@提及與網址不翻譯。\n\n"
            f"{text}"
        )
        return self.gemini.generate(prompt)
