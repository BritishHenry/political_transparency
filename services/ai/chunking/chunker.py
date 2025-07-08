import pdfplumber
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
from django.db import transaction

from general.decorators import retry_with_backoff


import logging 
logger = logging.getLogger(__name__)

@dataclass
class DocumentChunk:
    """
    Represents a chunk of document content with metadata.
    
    This is the fundamental data structure for our Hierarchical RAG system.
    Each chunk will be stored in PostgreSQL with a corresponding embedding
    in the vector database (Qdrant) for semantic search.
    """
    content: str  # The actual text content
    chunk_type: str  # 'sentence', 'paragraph', 'page', '6_page'
    page_start: int  # First page this chunk appears on (1-indexed for human readability)
    page_end: int  # Last page this chunk appears on (1-indexed for human readability)
    # chunk_index: int  # Sequential index within this chunk type - removed as it doesnt assit logic and adds complexity. just adding in when ready to save.
    metadata: Dict = None  # Additional metadata for context
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PDFDocumentChunker:
    """
    Handles initial chunking of PDF documents into multiple granularity levels.
    
    This is Step 1 of our Hierarchical RAG processing pipeline:
    1. Document Chunking (this class) → 2. Summary Generation → 3. Embedding → 4. Storage
    
    Creates four levels of granularity:
    - Sentences: For precise fact retrieval and exact quotes
    - Paragraphs: For contextual information around specific topics
    - Pages: For understanding document structure and page-specific content
    - 6-page chunks: For processing intermediate summaries and broader context
    
    Why these levels?
    - Political documents have complex hierarchical structure
    - Different query types need different levels of detail
    - LLM context windows require manageable chunk sizes
    - Vector search works better with semantic units of appropriate size
    
    Note: All page numbers in this system are 1-indexed for human readability.
    The first page of a document is page 1, not page 0.
    """
    
    def __init__(self, document, llm_service=None, chunking_model=None):
        """
        Initialize the chunker with a Django Document model instance.
        
        Args:
            document: Django Document model instance this chunker will process
            llm_service: Service for LLM calls (inject your OpenAI/etc. client)
                        If None, falls back to simple regex-based chunking
        """
        self.document = document  # Store the Django model instance
        self.llm_service = llm_service
        self.chunking_model = chunking_model
        self.pages = []  # Store raw page text for reference
        self.chunks = {
            'sentences': [],
            'paragraphs': [],
            'pages': [],
            '6_pages': []
        }
    
    def _extract_pdf_pages(self, pdf_path: str) -> List[str]:
        """
        Extract text from each page of the PDF using pdfplumber.
        
        pdfplumber is chosen over PyPDF2 because:
        - Better handling of complex layouts (tables, columns)
        - More accurate text extraction for government documents
        - Preserves spatial relationships in text
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of page text content, one string per page
        """
        pages = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    # layout=True preserves spacing and formatting
                    # This is crucial for regulatory documents with specific formatting
                    page_text = page.extract_text(layout=True)
                    
                    if page_text:
                        # Clean up common PDF artifacts but preserve structure
                        page_text = self._clean_page_text(page_text)
                        pages.append(page_text)
                    else:
                        # Handle empty pages (common in government PDFs)
                        pages.append("")
                        
        except Exception as e:
            raise Exception(f"Error extracting PDF pages: {str(e)}")
            
        return pages
    
    def _clean_page_text(self, text: str) -> str:
        """
        Remove excessive whitespace while preserving document structure.
        
        Political documents often have specific formatting that conveys meaning
        (indentation, line breaks, etc.) so we clean conservatively.
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    
    @retry_with_backoff(base_delay=5)
    def _chunk_page_with_llm(self, page_text: str, page_num: int) -> Dict[str, List[str]]:
        """
        Use LLM to intelligently identify sentences and paragraphs.
        
        Why use LLM for chunking?
        - Political documents have complex sentence structures
        - Regulatory text has numbered/lettered subsections
        - Simple regex fails on legal citations and cross-references
        - LLM understands semantic boundaries better than rules
        
        Args:
            page_text: Text content of the page
            page_num: Page number (1-indexed) for error reporting
            
        Returns:
            Dict with 'sentences' and 'paragraphs' lists
        """
        if not self.llm_service:
            # If no LLM available, use simple fallback
            logger.warning("LLM not available, falling back to simple chunking.")
            return self._simple_chunk_page(page_text)
        
        from .prompts import get_chunk_page_prompt
        prompt = get_chunk_page_prompt(page_text)
        
        try:
            response = self.llm_service.responses.create(model=self.chunking_model, input=prompt)

            # Response validation
            if not response or not hasattr(response, 'output_text'):
                print(f"Invalid response from LLM for page {page_num}, using simple chunking")
                return self._simple_chunk_page(page_text)
            
            response_text = response.output_text.strip()
        
            # Check if response looks like JSON
            if not response_text.startswith('{'): # This is sometimes causes errors as it outputs "json {...}" -> need to remove anything before the {}
                print(f"Non-JSON response for page {page_num}: {response_text[:100]}...")
                return self._simple_chunk_page(page_text)
                
            return json.loads(response_text)
        
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"LLM chunking failed for page {page_num}, falling back to simple chunking: {e}")
            return self._simple_chunk_page(page_text)
    
    def _simple_chunk_page(self, page_text: str) -> Dict[str, List[str]]:
        """
        Fallback chunking method using regex when LLM is unavailable.
        
        This is a basic implementation that works reasonably well but
        misses the nuanced understanding that LLM provides for legal text.
        """
        import re
        
        # Basic sentence splitting - looks for period/question/exclamation + capital letter
        # This will miss some legal citations but works for most cases
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(sentence_pattern, page_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Paragraph splitting on double newlines or significant whitespace
        # Political documents often use formatting to separate logical sections
        paragraphs = page_text.split('\n\n')
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        return {
            'sentences': sentences,
            'paragraphs': paragraphs
        }
    
    def _create_chunks_from_pages(self, pages: List[str]) -> None:
        """
        Process all pages and create chunks at each granularity level.
        
        This method orchestrates the creation of our hierarchical chunk structure:
        1. Process each page individually with LLM
        2. Create sentence and paragraph chunks with proper indexing
        3. Create page-level chunks
        4. Create 6-page chunks for summary processing
        
        The chunk indexing is important for maintaining order and
        creating relationships between different granularity levels.
        """
        
        # Process each page individually
        for page_idx, page_text in enumerate(pages):
            if page_idx % 10 == 0:  # Log every 10 pages
                logger.info(f"Processing page {page_idx + 1}/{len(pages)}")

            # Skip empty pages (common in government documents)
            if not page_text.strip():
                continue
            
            # Convert to 1-indexed page number for storage and display
            page_num = page_idx + 1
            
            # Get LLM-identified sentences and paragraphs for this page
            page_chunks = self._chunk_page_with_llm(page_text, page_num)
            
            # Create sentence chunks - these will be used for precise fact retrieval
            for sentence in page_chunks['sentences']:
                chunk = DocumentChunk(
                    content=sentence,
                    chunk_type='sentence',
                    page_start=page_num,  # 1-indexed
                    page_end=page_num,    # 1-indexed
                    metadata={'original_page': page_num}  # 1-indexed
                )
                self.chunks['sentences'].append(chunk)
            
            # Create paragraph chunks - these provide context around sentences
            for paragraph in page_chunks['paragraphs']:
                chunk = DocumentChunk(
                    content=paragraph,
                    chunk_type='paragraph',
                    page_start=page_num,  # 1-indexed
                    page_end=page_num,    # 1-indexed
                    metadata={'original_page': page_num}  # 1-indexed
                )
                self.chunks['paragraphs'].append(chunk)
            
            # Create page chunk - useful for understanding document flow and structure
            page_chunk = DocumentChunk(
                content=page_text,
                chunk_type='page',
                page_start=page_num,  # 1-indexed
                page_end=page_num,    # 1-indexed
                metadata={
                    'sentence_count': len(page_chunks['sentences']),
                    'paragraph_count': len(page_chunks['paragraphs']),
                    'page_number': page_num  # 1-indexed page number
                }
            )
            self.chunks['pages'].append(page_chunk)
        
        # Create 6-page chunks for intermediate processing
        self._create_six_page_chunks(pages)
    
    def _create_six_page_chunks(self, pages: List[str]) -> None:
        """
        Create 6-page sequential chunks for summary generation.
        
        Why 6 pages?
        - Manageable size for LLM summary generation
        - Large enough to capture thematic sections
        - Small enough to process efficiently
        - Based on testing with political document structure
        
        These chunks will be used to create section summaries in Step 2
        of our pipeline, then deleted to save storage space.
        """
        
        for i in range(0, len(pages), 6):
            # Get up to 6 pages (or remaining pages if less than 6)
            page_group = pages[i:i+6]
            page_start = i + 1  # Convert to 1-indexed
            page_end = min(i + 6, len(pages))  # 1-indexed end page
            
            # Combine pages with clear separators for LLM processing
            # PAGE BREAK markers help LLM understand document structure
            combined_content = '\n\n--- PAGE BREAK ---\n\n'.join(page_group)
            
            chunk = DocumentChunk(
                content=combined_content,
                chunk_type='6_page',
                page_start=page_start,  # 1-indexed
                page_end=page_end,      # 1-indexed
                metadata={
                    'page_count': len(page_group),
                    'pages_included': list(range(page_start, page_end + 1))  # 1-indexed list
                }
            )
            self.chunks['6_pages'].append(chunk)
    
    def save_chunks_to_database(self) -> Dict[str, List]:
        """
        Save all processed chunks to the Django database.
        
        This method:
        1. Deletes any existing chunks for this document (clean slate)
        2. Creates DocumentChunk instances for all chunk types
        3. Uses bulk_create for efficient database insertion
        4. Returns the created Django model instances
        
        Why bulk_create?
        - Single database query instead of one per chunk
        - Much faster for large documents (1000 chunks: ~1s vs ~30s)
        - Reduces database load and connection overhead
        
        Returns:
            Dictionary mapping chunk types to lists of created DocumentChunk instances
        """
        # Import the Django model here to avoid circular imports
        # IMPORTANT: Update this import path to match your Django app structure
        from document_manager.models.chunks import DocumentChunk as DjangoDocumentChunk
        
        # Use a transaction to ensure all-or-nothing behavior
        with transaction.atomic():
            # Delete all existing chunks for this document
            # This ensures we don't have orphaned chunks from previous processing
            DjangoDocumentChunk.objects.filter(document=self.document).delete()
            
            created_chunks = {
                'sentences': [],
                'paragraphs': [],
                'pages': [],
                '6_pages': []
            }

            global_chunk_index = 0
            # Process each chunk type
            for chunk_type, chunks in self.chunks.items():
                # Prepare Django model instances for bulk creation
                django_chunks = []
                
                for chunk in chunks:
                    django_chunk = DjangoDocumentChunk(
                        document=self.document,
                        chunk_index=global_chunk_index,
                        chunk_type=chunk.chunk_type,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        content=chunk.content,
                        metadata=chunk.metadata,
                        vector_id=None, # vector_id will be populated later after embedding generation
                        embedding_model='Not specified'  # Will be updated when embeddings are created
                    )
                    django_chunks.append(django_chunk)
                    global_chunk_index += 1
                
                # Bulk create all chunks of this type in a single query
                if django_chunks:
                    created = DjangoDocumentChunk.objects.bulk_create(django_chunks)
                    created_chunks[chunk_type] = created
                    logger.info(f"Saved {len(created)} {chunk_type} chunks to database")
        
        
        self.document.chunking_model = self.chunking_model
        self.document.save(update_fields=['chunking_model'])
        logger.info(f"Updated Document chunking_model to: {self.chunking_model}")
        
        return created_chunks
    
    def process_document(self) -> Dict[str, List[DocumentChunk]]:
        """
        Main method to process a PDF document into all chunk types.
        
        This is the entry point for Step 1 of our Hierarchical RAG pipeline.
        The output chunks will be passed to the summary generation stage.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing all chunk types with their chunks
            
        Next steps after this method:
        1. Store all chunks in PostgreSQL (handled by save_chunks_to_database)
        2. Generate embeddings for each chunk type
        3. Store embeddings in Qdrant vector database
        4. Generate summaries using 6-page chunks
        5. Generate section and document summaries
        """
        # Reset chunks for new document processing
        self.chunks = {
            'sentences': [],
            'paragraphs': [],
            'pages': [],
            '6_pages': []
        }

        # Extract all pages from PDF
        logger.info(f"Extracting pages from {self.document.file.path}...")
        pages = self._extract_pdf_pages(self.document.file.path) # Unsure if this should be .file or .file.path
        self.pages = pages
        
        if not pages:
            raise Exception("No pages extracted from PDF")
        
        logger.info(f"Extracted {len(pages)} pages")
        
        # Create all chunk types
        logger.info("Creating hierarchical chunks...")
        self._create_chunks_from_pages(pages)
        
        # Print summary for monitoring
        logger.info("\n=== Chunking Complete ===")
        for chunk_type, chunk_list in self.chunks.items():
            logger.info(f"{chunk_type}: {len(chunk_list)} chunks")
        logger.info("=========================\n")
        
        
        # Note: The save_chunks_to_database call could be moved outside this method
        # for more control over when database operations occur. This would allow
        # for validation, testing, or other processing steps before committing to DB.
        
        return self.chunks
    
    def get_chunks_by_type(self, chunk_type: str) -> List[DocumentChunk]:
        """
        Get all chunks of a specific type.
        
        Useful for processing pipeline steps that need specific granularity levels.
        """
        return self.chunks.get(chunk_type, [])


# Example usage:
# from your_app.models import Document
# 
# # Get or create your Document instance
# document = Document.objects.get(id=1)
# 
# # Initialize chunker with the document instance
# chunker = PDFDocumentChunker(document=document, llm_service=your_llm_service)
# 
# # Process the PDF and save to database
# chunks = chunker.process_document('/path/to/document.pdf')
# 
# # Note: All page numbers stored in the database will be 1-indexed
# # e.g., the first page is page 1, second page is page 2, etc.