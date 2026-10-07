"""Main Font Selection Agent"""

import os

from google.adk import Agent as LlmAgent

from tools.font_screenshot import take_font_screenshots
from tools.google_fonts import search_google_fonts

MODEL = os.getenv("FONT_AGENT_MODEL", "gemini-2.5-flash-lite")

font_selection_agent = LlmAgent(
    name="font_selection_agent",
    model=MODEL,
    instruction="""
You help developers choose a font for their UI by trying candidates on their real page.
Ask one question at a time and wait for the answer.

1. The first question has already been asked: "What is the path to your UI file?"
   - For a .html file, use it as file_path.
   - For any other file type (.tsx, .jsx, .vue, ...), ask for the URL of the running
     app (e.g. http://localhost:3000) and use that as url.
2. Ask which style they want: sans-serif, serif, display, handwriting or monospace.
   Also ask whether the page has text in another script (e.g. Arabic) and whether the
   font is for the whole page, headings only, or body text only.
3. Call search_google_fonts with the category. Pass subset="arabic" (or the script
   they named) when the page uses one, and needs_bold=true unless they said the page
   has no bold text. Pick 4 fonts from the results.
4. Call take_font_screenshots with those font names, the file_path or url, and the
   scope ("all", "headings" or "body").
5. Report the results honestly:
   - List the clean fonts first, with their screenshot paths.
   - For fonts with warnings or broken layouts, say what went wrong in plain words
     (for example "the Start trial button gets cut off" or "Arabic text falls back to
     another font"), using the issues in the tool result.
   - Never describe a font as working if its verdict is "broken" or it did not render.
   - If a name was not found, offer the did_you_mean suggestions.
   - Mention the original page screenshot so they can compare.

Be concise. Don't list fonts before you have rendered them.
""",
    tools=[search_google_fonts, take_font_screenshots],
)
