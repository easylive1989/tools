import os
import unittest
from unittest.mock import MagicMock
import sys

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.handlers.markdown import MarkdownHandler
from src.handlers.docx import DocxHandler
from src.services.gemini import GeminiClient

class TestHandlers(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GeminiClient)
        self.mock_client.translate_text.side_effect = lambda text, lang: f"[TR:{lang}] {text}"
        self.target_lang = "Spanish"
        self.test_files = []

    def tearDown(self):
        # Cleanup test files
        for f in self.test_files:
            if os.path.exists(f):
                os.remove(f)

    def test_markdown_handler(self):
        handler = MarkdownHandler(self.mock_client, self.target_lang)
        input_md = "test_handlers_sample.md"
        self.test_files.append(input_md)
        output_md = "test_handlers_sample_translated.md"
        self.test_files.append(output_md)

        with open(input_md, 'w') as f:
            f.write("# Hello\n\n```\ncode\n```")

        output_path = handler.process(input_md)
        self.assertTrue(os.path.exists(output_path))

        with open(output_path, 'r') as f:
            content = f.read()
            # Code block should be preserved
            self.assertIn("```", content)
            # Text should be translated (mocked)
            self.assertIn("[TR:Spanish]", content)

    def test_docx_handler(self):
        handler = DocxHandler(self.mock_client, self.target_lang)
        input_docx = "test_handlers_sample.docx"
        self.test_files.append(input_docx)
        output_docx = "test_handlers_sample_translated.docx"
        self.test_files.append(output_docx)

        from docx import Document
        doc = Document()
        doc.add_paragraph("Hello World")
        doc.save(input_docx)

        output_path = handler.process(input_docx)
        self.assertTrue(os.path.exists(output_path))

        doc = Document(output_path)
        # Check if text is translated (mocked)
        full_text = " ".join([p.text for p in doc.paragraphs])
        self.assertIn("[TR:Spanish]", full_text)

if __name__ == '__main__':
    unittest.main()
