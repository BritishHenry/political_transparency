import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from django.db import transaction
from django.utils import timezone


@dataclass
class HeadlineChunk:
    """Represents a 6-page chunk with its generated headline."""
    chunk_id: int
    headline: str
    page_start: int
    page_end: int
    summary: Optional[str] = None  # Temporary, will be deleted after section summaries


@dataclass
class DocumentSection:
    """Represents a logical section identified from headlines."""
    section_id: str
    title: str
    headline_indices: List[int]
    summary: Optional[str] = None


class DocumentSummarizer:
    """
    Handles the complete summarization pipeline for the Hierarchical RAG system.
    
    This is Step 2 of the processing pipeline:
    1. Document Chunking → 2. Summary Generation (this class) → 3. Embedding → 4. Storage
    
    Process flow:
    1. Generate headlines for 6-page chunks
    2. Create 6-page summaries (temporary)
    3. Use headlines to identify logical sections
    4. Create section summaries from 6-page summaries
    5. Create document summary from section summaries
    6. Generate contents page from headlines
    
    The 6-page summaries are deleted after section summaries are created
    to optimize storage while maintaining all necessary context.
    """
    
    def __init__(self, document_instance,llm_service, model="gpt-4"):
        """
        Initialize the summarizer with a Django Document model instance.
        
        Args:
            document_instance: Django Document model instance to summarize
            openai_client: OpenAI client instance for API calls
            model: OpenAI model to use for summarization
        """
        self.document = document_instance
        self.client = llm_service
        self.model = model
        
        # Storage for intermediate results
        self.headlines = []  # List of HeadlineChunk objects
        self.sections = []   # List of DocumentSection objects
        self.document_summary = None
        self.contents_page = None
    
    def generate_headline(self, chunk_content: str, page_start: int, page_end: int) -> str:
        """
        Generate a descriptive headline for a 6-page chunk.
        
        Headlines serve dual purposes:
        1. Enable logical section grouping by the LLM
        2. Create a navigable contents page for users
        
        Args:
            chunk_content: Text content of the 6-page chunk
            page_start: Starting page number (1-indexed)
            page_end: Ending page number (1-indexed)
            
        Returns:
            A 10-15 word headline capturing the main theme
        """
        prompt = f"""
Generate a descriptive headline for this section of a political document.

Pages {page_start}-{page_end} content:
{chunk_content[:2000]}...  # Truncate for context window

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
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temperature for consistency
            max_tokens=50
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_six_page_summary(self, chunk_content: str, headline: str) -> str:
        """
        Generate a detailed summary of a 6-page chunk.
        
        These summaries are temporary and will be used to create
        section summaries, then deleted to save storage.
        
        Args:
            chunk_content: Full text of the 6-page chunk
            headline: Previously generated headline for context
            
        Returns:
            A 400-600 word summary of the chunk
        """
        prompt = f"""
Create a detailed summary of this section of a political document.

Section headline: "{headline}"

Content:
{chunk_content}

Requirements:
- 400-600 words capturing all key information
- Include specific policies, requirements, or provisions
- Note important definitions, exceptions, or conditions
- Preserve technical terms and regulatory language where important
- Maintain neutral, factual tone without interpretation
- Structure with clear topic sentences and logical flow

Focus on completeness - this summary will be used to create higher-level summaries later.
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=800
        )
        
        return response.choices[0].message.content.strip()
    
    def identify_sections_from_headlines(self, headlines: List[HeadlineChunk]) -> List[DocumentSection]:
        """
        Use LLM to group headlines into logical document sections.
        
        This is the key innovation that makes section formation transparent
        and debuggable - the LLM explicitly explains its grouping logic.
        
        Args:
            headlines: List of HeadlineChunk objects with headlines
            
        Returns:
            List of DocumentSection objects representing logical sections
        """
        # Format headlines for the prompt
        headline_list = "\n".join([
            f"{i+1}. \"{h.headline}\" (pages {h.page_start}-{h.page_end})"
            for i, h in enumerate(headlines)
        ])
        
        prompt = f"""
Analyze these headlines from a political document and group them into logical sections.

Headlines:
{headline_list}

Create logical document sections by grouping related headlines. Return a JSON object with:
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

Guidelines:
- Group headlines that cover related topics, policies, or document parts
- Section titles should be clear and descriptive (2-5 words)
- Sections should follow the document's natural flow
- Include reasoning to make grouping logic transparent
- Typical sections might include: Overview, Eligibility, Requirements, Procedures, Enforcement, Appendices
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"}  # Ensure JSON response
        )
        
        section_data = json.loads(response.choices[0].message.content)
        
        # Convert JSON to DocumentSection objects
        sections = []
        for section in section_data['sections']:
            doc_section = DocumentSection(
                section_id=section['section_id'],
                title=section['title'],
                headline_indices=section['headline_indices']
            )
            sections.append(doc_section)
        
        return sections
    
    def generate_section_summary(self, section: DocumentSection, 
                               headlines: List[HeadlineChunk]) -> str:
        """
        Generate a section summary from the 6-page summaries within that section.
        
        Args:
            section: DocumentSection object defining the section
            headlines: List of all HeadlineChunk objects (with summaries)
            
        Returns:
            A 150-250 word section summary
        """
        # Gather relevant 6-page summaries for this section
        relevant_summaries = []
        for idx in section.headline_indices:
            headline_chunk = headlines[idx]
            if headline_chunk.summary:
                relevant_summaries.append(f"Pages {headline_chunk.page_start}-{headline_chunk.page_end}:\n{headline_chunk.summary}")
        
        combined_summaries = "\n\n---\n\n".join(relevant_summaries)
        
        prompt = f"""
Create a cohesive section summary from these related 6-page summaries.

Section: "{section.title}"

6-page summaries to synthesize:
{combined_summaries}

Requirements:
- 150-250 words capturing the essence of this section
- Synthesize information, don't just concatenate
- Highlight key policies, requirements, or provisions
- Maintain factual accuracy and neutral tone
- Focus on what users need to know about this section
- Write as a coherent summary, not a list

This summary will be included in every chat response for context.
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=400
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_document_summary(self, sections: List[DocumentSection]) -> str:
        """
        Generate the overall document summary from all section summaries.
        
        Args:
            sections: List of DocumentSection objects with summaries
            
        Returns:
            A 100-150 word document summary
        """
        # Compile all section summaries
        section_summaries = []
        for section in sections:
            if section.summary:
                section_summaries.append(f"{section.title}:\n{section.summary}")
        
        combined_sections = "\n\n".join(section_summaries)
        
        prompt = f"""
Create a high-level document summary from these section summaries.

Document: "{self.document.title}"

Section summaries:
{combined_sections}

Requirements:
- 100-150 words capturing the document's overall purpose and scope
- Mention the type of document (legislation, policy, regulation, etc.)
- Highlight the most important aspects users should know
- Maintain neutral, factual tone
- Write for someone who needs to quickly understand what this document is about

This summary will be included in every chat response for context.
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=250
        )
        
        return response.choices[0].message.content.strip()
    
    def generate_contents_page(self, headlines: List[HeadlineChunk]) -> str:
        """
        Generate a formatted contents page from all headlines.
        
        This serves as a navigation aid and is included in every chat response.
        
        Args:
            headlines: List of HeadlineChunk objects with headlines
            
        Returns:
            Formatted contents page as a string
        """
        contents = "DOCUMENT CONTENTS\n" + "="*50 + "\n\n"
        
        for i, headline in enumerate(headlines):
            # Format: "1. Headline text........................pages 12-18"
            page_range = f"pages {headline.page_start}-{headline.page_end}"
            
            # Calculate dots for alignment (assuming ~80 char width)
            headline_text = f"{i+1}. {headline.headline}"
            dots_count = max(1, 70 - len(headline_text) - len(page_range))
            dots = "." * dots_count
            
            contents += f"{headline_text}{dots}{page_range}\n"
        
        contents += "\n" + "="*50
        
        return contents
    
    def process_document(self) -> Dict:
        """
        Main method to run the complete summarization pipeline.
        
        This processes all 6-page chunks through the full pipeline:
        1. Headlines → 2. 6-page summaries → 3. Section identification → 
        4. Section summaries → 5. Document summary → 6. Contents page
        
        Returns:
            Dictionary containing all generated summaries and metadata
        """
        from apps.document_manager.models import DocumentChunk
        
        # Get all 6-page chunks from the database
        six_page_chunks = DocumentChunk.objects.filter(
            document=self.document,
            chunk_type='6_page'
        ).order_by('chunk_index')
        
        if not six_page_chunks:
            raise ValueError(f"No 6-page chunks found for document {self.document.id}")
        
        print(f"Processing {len(six_page_chunks)} 6-page chunks...")
        
        # Step 1: Generate headlines for each 6-page chunk
        print("\n=== Generating Headlines ===")
        for chunk in six_page_chunks:
            headline = self.generate_headline(
                chunk.content, 
                chunk.page_start, 
                chunk.page_end
            )
            
            headline_chunk = HeadlineChunk(
                chunk_id=chunk.id,
                headline=headline,
                page_start=chunk.page_start,
                page_end=chunk.page_end
            )
            self.headlines.append(headline_chunk)
            print(f"Pages {chunk.page_start}-{chunk.page_end}: {headline}")
        
        # Step 2: Generate 6-page summaries (temporary)
        print("\n=== Generating 6-Page Summaries ===")
        for headline_chunk in self.headlines:
            chunk = six_page_chunks.get(id=headline_chunk.chunk_id)
            summary = self.generate_six_page_summary(chunk.content, headline_chunk.headline)
            headline_chunk.summary = summary
            print(f"Generated summary for: {headline_chunk.headline}")
        
        # Step 3: Identify logical sections from headlines
        print("\n=== Identifying Document Sections ===")
        self.sections = self.identify_sections_from_headlines(self.headlines)
        for section in self.sections:
            print(f"Section {section.section_id}: {section.title} (includes {len(section.headline_indices)} chunks)")
        
        # Step 4: Generate section summaries
        print("\n=== Generating Section Summaries ===")
        for section in self.sections:
            section.summary = self.generate_section_summary(section, self.headlines)
            print(f"Generated summary for section: {section.title}")
        
        # Step 5: Generate document summary
        print("\n=== Generating Document Summary ===")
        self.document_summary = self.generate_document_summary(self.sections)
        print("Document summary generated")
        
        # Step 6: Generate contents page
        print("\n=== Generating Contents Page ===")
        self.contents_page = self.generate_contents_page(self.headlines)
        print("Contents page generated")
        
        # Step 7: Save to database
        print("\n=== Saving to Database ===")
        self._save_results_to_database()
        
        # Return all results
        return {
            'headlines': [(h.headline, h.page_start, h.page_end) for h in self.headlines],
            'sections': [(s.title, s.summary) for s in self.sections],
            'document_summary': self.document_summary,
            'contents_page': self.contents_page
        }
    
    def _save_results_to_database(self):
        """
        Save all summaries and metadata to the database.
        
        Note: 6-page summaries are NOT saved as they're temporary.
        This follows the storage architecture where only permanent
        summaries are kept to optimize storage.
        """
        from apps.document_manager.models import DocumentSummary
        from django.utils import timezone
        
        with transaction.atomic():
            # Update document with contents page and metadata
            # Assumes you've added a contents_page TextField to Document model
            self.document.contents_page = self.contents_page
            self.document.metadata = {
                "headlines": [
                    {
                        "headline": h.headline,
                        "page_start": h.page_start,
                        "page_end": h.page_end
                    } for h in self.headlines
                ],
                "sections": [
                    {
                        "section_id": s.section_id,
                        "title": s.title,
                        "headline_indices": s.headline_indices
                    } for s in self.sections
                ],
                "processing_info": {
                    "summarized_at": timezone.now().isoformat(),
                    "model_used": self.model,
                    "num_headlines": len(self.headlines),
                    "num_sections": len(self.sections)
                }
            }
            self.document.save(update_fields=['contents_page', 'metadata', 'updated_at'])
            
            # Save document summary
            doc_summary, created = DocumentSummary.objects.update_or_create(
                document=self.document,
                summary_type='document',
                defaults={
                    'content': self.document_summary,
                    'summarisation_model': self.model,
                    # 'word_count' is calculated via get_word_count() method
                }
            )
            
            # Save section summaries
            for section in self.sections:
                # Note: The model uses section_name, not section_id
                # Since sections don't have page ranges anymore, we'll leave those null
                section_summary, created = DocumentSummary.objects.update_or_create(
                    document=self.document,
                    summary_type='section',
                    section_name=section.title,  # Using the section title as the name
                    defaults={
                        'content': section.summary,
                        'summarisation_model': self.model,
                        # page_start and page_end are left null since sections can be non-contiguous
                    }
                )
            
            print(f"Updated document metadata and contents page for: {self.document.id}")
            print(f"Saved document summary: {doc_summary.id}")
            print(f"Saved {len(self.sections)} section summaries")


# Example usage:
# from your_app.models import Document
# import openai
# 
# # Initialize OpenAI client
# client = openai.OpenAI(api_key="your-api-key")
# 
# # Get document that has been chunked
# document = Document.objects.get(id=1)
# 
# # Initialize and run summarizer
# summarizer = DocumentSummarizer(document, client, model="gpt-4")
# results = summarizer.process_document()
# 
# # Access results
# print(results['document_summary'])
# print(results['contents_page'])