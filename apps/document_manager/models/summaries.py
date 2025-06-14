from django.db import models
from django.core.exceptions import ValidationError

from .general import Document

class DocumentSummary(models.Model):
    """
    Summary model for hierarchical RAG system.
    
    Handles both document-level and section-level summaries in a unified model.
    Each summary is embedded in the vector database for semantic search and 
    included in chat context assembly.
    """
    
    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE, 
        related_name='summaries',
        help_text="The document this summary belongs to"
    )
    
    summary_type = models.CharField(
        max_length=20,
        choices=[
            ('document', 'Document Summary'),
            ('section', 'Section Summary'),
            # Future extensibility for other summary types
        ],
        help_text="Type of summary: document-level or section-level"
    )
    
    # Section-specific fields (null for document summaries)
    section_name = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="Name of the section (e.g., 'Eligibility Requirements'). Null for document summaries."
    )
    
    # Core summary content
    content = models.TextField(
        help_text="The actual summary text content"
    )
    
    summarisation_model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Model used to generate summaries"
    )

    # Vector database integration
    vector_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="ID reference in the vector database (Qdrant)"
    )
    
    embedding_model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Model used to generate embeddings for this summary"
    )
    embedded_at = models.DateTimeField(auto_now_add=False, auto_now=False)
    
    # Processing metadata
    processing_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Version of the processing pipeline used to generate this summary"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Validate the summary before saving"""
        super().clean()
        
        if self.summary_type == 'document':
            # Document summaries shouldn't have section-specific data
            if self.section_name:
                raise ValidationError(
                    "Document summaries cannot have section_name"
                )
            
            # Ensure unique document summary per document
            existing = DocumentSummary.objects.filter(
                document=self.document,
                summary_type='document'
            ).exclude(pk=self.pk)
            
            if existing.exists():
                raise ValidationError("A document can only have one document-level summary")
        
        elif self.summary_type == 'section':
            # Section summaries must have section name
            if not self.section_name:
                raise ValidationError("Section summaries must have a section_name")
            
            # Ensure unique section summary per document+section combination
            existing = DocumentSummary.objects.filter(
                document=self.document,
                summary_type='section',
                section_name=self.section_name
            ).exclude(pk=self.pk)
            
            if existing.exists():
                raise ValidationError(
                    f"A summary for section '{self.section_name}' already exists for this document"
                )
    
    def save(self, *args, **kwargs):
        """Extended save method with content processing"""
        
        # Clean section-specific fields for document summaries
        if self.summary_type == 'document':
            self.section_name = None
        
        super().save(*args, **kwargs)
    
    def get_word_count(self):
        """
        Return word count for the summary content.
        
        Uses improved regex to handle political/legal document text patterns:
        - Contractions: "don't", "can't", "won't"
        - Possessives: "government's", "citizen's"  
        - Hyphenated terms: "twenty-first", "state-of-the-art"
        - Acronyms: "U.S.", "etc."
        """
        if not self.content:
            return 0
        import re
        # Improved regex that handles contractions, possessives, and hyphenated words
        words = re.findall(r"\b[\w''-]+\b", self.content)
        return len(words)
    
    def get_context_label(self):
        """Return label for use in chat context assembly"""
        if self.summary_type == 'document':
            return f"Document Summary: {self.document.name}"
        else:
            return f"Section: {self.section_name}"
    
    @classmethod
    def get_context_summaries(cls, document):
        """
        Get all summaries for a document optimized for chat context assembly.
        Returns document summary and all section summaries in the order they need
        to be included in LLM context.
        """
        summaries = cls.objects.filter(
            document=document
        ).order_by(
            'summary_type',  # document first, then sections
            'section_name'   # sections in alphabetical order
        )
        
        doc_summary = None
        section_summaries = []
        
        for summary in summaries:
            if summary.summary_type == 'document':
                doc_summary = summary
            else:
                section_summaries.append(summary)
        
        return {
            'document_summary': doc_summary,
            'section_summaries': section_summaries,
            'all_summaries': list(summaries)  # For cases where you need them all in order
        }
    
    def estimate_tokens(self, words_per_token=0.75):
        """
        Estimate token count for this summary content.
        Uses rough approximation of 0.75 words per token for English text.
        """
        word_count = self.get_word_count()
        return int(word_count / words_per_token)
    
    def __str__(self):
        if self.summary_type == 'document':
            return f"Document Summary: {self.document.name}"
        else:
            return f"Section Summary: {self.section_name} ({self.document.name})"
    
    class Meta:
        indexes = [
            models.Index(fields=['document', 'summary_type']),
            models.Index(fields=['vector_id']),
            models.Index(fields=['created_at']),
        ]
        
        # Note: unique_together not used because NULL handling in SQL doesn't work as expected
        # for document summaries (where section_name is NULL). Uniqueness is enforced in clean() method.
        
        ordering = ['summary_type', 'section_name']  # Document summaries first, then sections alphabetically
        
        verbose_name = "Document Summary"
        verbose_name_plural = "Document Summaries"