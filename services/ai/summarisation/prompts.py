'''

Using this file to create utility prompt functions, which just keeps the sumariser.py file clean.

'''

def generate_headline_prompts(page_start, page_end, chunk_content):
    instructions =f"""
Generate a descriptive headline for the inputted section of a political document.

Requirements:
- 10-15 words that capture the main theme or focus
- Clear and specific (not generic like "Introduction")
- Include key topics, policies, or requirements covered
- Written for a table of contents

Example headlines:
- "Eligibility Requirements for Small Business Tax Credits"
- "Environmental Impact Assessment Procedures and Timeline"
- "Enforcement Mechanisms and Penalty Structures"

Return only the headline text, no quotes or formatting.
"""
    
    input = f"""
Pages {page_start}-{page_end} content:
{chunk_content}
    """

    return instructions, input


def generate_six_page_summary_prompts(headline, chunk_content):
    instructions = f"""
Create a detailed summary of the inputted section of a political document.

Requirements:
- 400-600 words capturing all key information
- Include specific policies, requirements, or provisions
- Note important definitions, exceptions, or conditions
- Preserve technical terms and regulatory language where important
- Maintain neutral, factual tone without interpretation
- Structure with clear topic sentences and logical flow

Focus on completeness - this summary will be used to create higher-level summaries later.
"""
    input = f"""
Section headline: "{headline}"

Content:
{chunk_content}
"""
    return instructions, input


def identify_sections_from_headlines_prompts(headline_list):
    instructions = f"""
Analyze the inputted headlines from a political document and group them into logical sections.

Guidelines:
- Group headlines that cover related topics, policies, or document parts
- Section titles should be clear and descriptive (2-5 words)
- Sections should follow the document's natural flow
- Include reasoning to make grouping logic transparent
- Typical sections might include: Overview, Eligibility, Requirements, Procedures, Enforcement, Appendices

Create and output logical document sections by grouping related headlines. Return a JSON object in this format:
{{
    "sections": [
        {{
            "section_id": "A",
            "title": "Clear section title",
            "headline_indices": [0, 1, 2],  // 0-based indices of headlines in this section
            "reasoning": "Why these headlines belong together"
        }},
        ...
    ]
}}

## WARNING:
- In the response output, do NOT include any content, spaces or strings outside of the JSON object. There should be NO prefix or suffix. ONLY return the JSON, no additional content.
"""
    
    input = f"""
Headlines:
{headline_list}
"""
    
    return instructions, input


def generate_section_summary_prompts(section_title, combined_summaries):
    instructions = f"""
Create a cohesive section summary from the inputted, related 6-page summaries.

Requirements:
- 150-250 words capturing the essence of this section
- Synthesize information, don't just concatenate
- Highlight key policies, requirements, or provisions
- Maintain factual accuracy and neutral tone
- Focus on what users need to know about this section
- Write as a coherent summary, not a list

This summary will be included in every chat response for context.
"""
    
    input = f"""
Section: "{section_title}"

6-page summaries to synthesize:
{combined_summaries}
"""
    return instructions, input


def generate_document_summary_prompts(document_title, combined_sections):
    instructions = f"""
Create a high-level document summary from the inputted section summaries.

Requirements:
- 100-150 words capturing the document's overall purpose and scope
- Mention the type of document (legislation, policy, regulation, etc.)
- Highlight the most important aspects users should know
- Maintain neutral, factual tone
- Write for someone who needs to quickly understand what this document is about

This summary will be included in every chat response for context.
"""
    input = f"""
Document: "{document_title}"

Section summaries:
{combined_sections}
"""
    return instructions, input