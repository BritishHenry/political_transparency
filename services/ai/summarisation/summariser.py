import json
from json import JSONDecodeError
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from django.db import transaction, IntegrityError
from django.utils import timezone

from .prompts import (
    generate_headline_prompts, 
    generate_six_page_summary_prompts, 
    identify_sections_from_headlines_prompts, 
    generate_section_summary_prompts,
    generate_document_summary_prompts
    )

@dataclass
class HeadlineChunk(): # this is added to after creation, so must be mutable.
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
    1. Document Chunking → 2. Summary Generation (this class) → 3. Embedding → 4. Vector Storage
    
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

    def _call_openai(self, purpose:str, *args) -> str:

        prompt_map = {
            "generate_headline": generate_headline_prompts,
            "generate_six_page_summary": generate_six_page_summary_prompts,
            "identify_sections_from_headlines": identify_sections_from_headlines_prompts,
            "generate_section_summary": generate_section_summary_prompts,
            "generate_document_summary":generate_document_summary_prompts,
        }

        func = prompt_map.get(purpose)

        if not func:
            raise ValueError(f"Unknown purpose: {purpose}")

        instructions, input = func(*args)

        try:
            response = self.client.responses.create(
                model = self.model,
                instructions = instructions, 
                input = input
            )
            
            return response.output_text.strip()

        except Exception as e:
            print(f"LLM call failed for {purpose}: {e}")
            raise RuntimeError(f"Failed to generate {purpose}") from e
        

    def _generate_contents_page(self, headlines: List[HeadlineChunk]) -> str:
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
    
    def _parse_sections_json(self, response) -> List[DocumentSection]:
        """
        Turn the section string into JSON then into a list using the DocumentSection dataclass.
        """
        try:

            try:
                data = json.loads(response)

                # Validate expected structure

                # check data is a dic and sections are in it
                if not isinstance(data, dict) or 'sections' not in data:
                    raise ValueError("Response missing 'sections' key")
                
                # check sections are a list
                if not isinstance(data['sections'], list):
                    raise ValueError("'sections' must be a list")
                
            except JSONDecodeError as exc:
                raise ValueError("LLM returned invalid JSON for sections") from exc
            
            # Convert JSON to DocumentSection objects
            sections = []
            for section in data['sections']:
                doc_section = DocumentSection(
                    section_id=section['section_id'],
                    title=section['title'],
                    headline_indices=section['headline_indices']
                )
                sections.append(doc_section)
            
            return sections
        except Exception as e:
            print(f"Error parsing JSON response | Response: {response} | Error: {e}")
            raise
    
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

        # Store the query in a dic to prevent multiple DB queries
        chunks_by_id = {chunk.id: chunk for chunk in six_page_chunks}
        
        if not six_page_chunks:
            raise ValueError(f"No 6-page chunks found for document {self.document.id}")
        
        print(f"Processing {len(six_page_chunks)} 6-page chunks...")
        
        # Step 1: Generate headlines for each 6-page chunk
        print("\n=== Generating Headlines ===")
        for chunk in six_page_chunks:
            headline = self._call_openai(
                'generate_headline',
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
            chunk = chunks_by_id[headline_chunk.chunk_id]
            summary = self._call_openai('generate_six_page_summary',chunk.content, headline_chunk.headline)
            headline_chunk.summary = summary
            print(f"Generated summary for: {headline_chunk.headline}")
        
        # Step 3: Identify logical sections from headlines
        print("\n=== Identifying Document Sections ===")
        response = self._call_openai('identify_sections_from_headlines',self.headlines)
        self.sections = self._parse_sections_json(response)
        for section in self.sections:
            print(f"Section {section.section_id}: {section.title} (includes {len(section.headline_indices)} chunks)")
        
        # Step 4: Generate section summaries
        print("\n=== Generating Section Summaries ===")
        for section in self.sections:
            section.summary = self._call_openai('generate_section_summary', section, self.headlines)
            print(f"Generated summary for section: {section.title}")
        
        # Step 5: Generate document summary
        print("\n=== Generating Document Summary ===")
        self.document_summary = self._call_openai('generate_document_summary', self.sections)
        print("Document summary generated")
        
        # Step 6: Generate contents page
        print("\n=== Generating Contents Page ===")
        self.contents_page = self._generate_contents_page(self.headlines)
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
        
        try:

            with transaction.atomic():

                # Update document with contents page and metadata
                self.document.contents_page = self.contents_page
                self.document.metadata = {
                    "processing_info": {
                        "summarized_at": timezone.now().isoformat(),
                        "model_used": self.model,
                        "num_headlines": len(self.headlines),
                        "num_sections": len(self.sections)
                    }
                }
                self.document.save(update_fields=['contents_page', 'metadata'])
            

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
        except IntegrityError: # this is raised if there are *any* integrity errors in the satements in the transaction.
            print("Integrity Error while saving items to database.")
            raise
        except Exception as e: # this is raised if there are *any* NON-integrity errors in the satements in the transaction.
            print(f"Failed to save summaries for document {self.document.id}: {e}")
            raise # Only non-IntegrityError exceptions are re-raised

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