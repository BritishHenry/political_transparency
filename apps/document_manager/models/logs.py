
from django.db import models
from .general import Document

class ProcessingLog(models.Model):
    """
    Log processing events for documents

    Each event in the document's pipeline should be logged using this:
        From upload to chat-ready.
    
    """
    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE, 
        related_name='processing_logs'
    )
    event_type = models.CharField(
    max_length=50,
    choices=[
        # Document Upload Phase
        ('upload_started', 'Upload Started'),
        ('validation_completed', 'Validation Completed'),
        ('upload_completed', 'Upload Completed'),
        
        # Text Extraction Phase
        ('text_extraction_started', 'Text Extraction Started'),
        ('text_extraction_completed', 'Text Extraction Completed'),
        
        # Processing Pipeline Stages
        ('processing_started', 'Processing Started'),
        ('metadata_extraction_completed', 'Metadata Extraction Completed'),
        
        # Semantic Chunking Phase
        ('chunking_started', 'Chunking Started'),
        ('chunking_completed', 'Chunking Completed'),
        
        # Embedding Generation Phase
        ('embedding_started', 'Embedding Started'),
        ('embedding_completed', 'Embedding Completed'),
        
        # Vector Database Operations
        ('vectordb_upload_started', 'Vector DB Upload Started'),
        ('vectordb_upload_completed', 'Vector DB Upload Completed'),
        
        # Document Analysis Phase
        ('analysis_started', 'Analysis Started'),
        ('entity_extraction_completed', 'Entity Extraction Completed'),
        ('summary_generation_completed', 'Summary Generation Completed'),
        ('analysis_completed', 'Analysis Completed'),
        
        # Document Status Changes
        ('document_activated', 'Document Activated'),
        ('document_deactivated', 'Document Deactivated'),
        ('document_updated', 'Document Updated'),
        
        # System Maintenance
        ('reprocessing_started', 'Reprocessing Started'),
        ('reindexing_completed', 'Reindexing Completed'),
        
        # Error States
        ('processing_failed', 'Processing Failed'),
        ('validation_failed', 'Validation Failed'),
        ('chunking_failed', 'Chunking Failed'),
        ('embedding_failed', 'Embedding Failed'),
        ('vectordb_upload_failed', 'Vector DB Upload Failed'),
        ('analysis_failed', 'Analysis Failed'),
    ]
)
    message = models.TextField(blank=True)
    error_traceback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['document', 'created_at']),
            models.Index(fields=['event_type']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.document.name} - {self.event_type} at {self.created_at}"