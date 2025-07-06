
'''
Use this file to store prompts.
Primary use is to keep other files clean and easier to read and maintain.
'''

def get_chunk_page_prompt(content):
  # Prompt designed specifically for political/legal documents

  prompt = f"""
Analyze this page of a political document and identify all sentences and paragraphs.

Page content:
{content}

Return a JSON object with:
{{
  "sentences": ["sentence 1", "sentence 2", ...],
  "paragraphs": ["paragraph 1", "paragraph 2", ...]
}}

Guidelines:
- Preserve exact text content (no summarizing or paraphrasing)
- Maintain proper sentence boundaries (handle legal citations correctly)
- Group sentences into logical paragraphs based on topic/theme
- Handle numbered/lettered sections appropriately (e.g., "(a) text here")
- Preserve regulatory formatting and cross-references
- Each paragraph should be a cohesive unit for search purposes
"""
  return prompt