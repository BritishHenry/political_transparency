
from django.db import models
from .general import Document

class EventEnum(models.TextChoices):
    # Document Upload Phase
    UPLOAD_STARTED = 'upload_started', 'Upload Started'
    VALIDATION_COMPLETED = 'validation_completed', 'Validation Completed'
    UPLOAD_COMPLETED = 'upload_completed', 'Upload Completed'
    
    # Text Extraction Phase
    TEXT_EXTRACTION_STARTED = 'text_extraction_started', 'Text Extraction Started'
    TEXT_EXTRACTION_COMPLETED = 'text_extraction_completed', 'Text Extraction Completed'
    
    # Processing Pipeline Stages
    PROCESSING_STARTED = 'processing_started', 'Processing Started'
    METADATA_EXTRACTION_COMPLETED = 'metadata_extraction_completed', 'Metadata Extraction Completed'
    
    # Semantic Chunking Phase
    CHUNKING_STARTED = 'chunking_started', 'Chunking Started'
    CHUNKING_COMPLETED = 'chunking_completed', 'Chunking Completed'
    
    # Embedding Generation Phase
    EMBEDDING_STARTED = 'embedding_started', 'Embedding Started'
    EMBEDDING_COMPLETED = 'embedding_completed', 'Embedding Completed'
    
    # Vector Database Operations
    VECTORDB_UPLOAD_STARTED = 'vectordb_upload_started', 'Vector DB Upload Started'
    VECTORDB_UPLOAD_COMPLETED = 'vectordb_upload_completed', 'Vector DB Upload Completed'
    
    # Document Analysis Phase
    SUMMARISATION_STARTED = 'summarisation_started', 'Summarisation Started'
    SUMMARISATION_COMPLETED = 'summarisation_completed', 'Summarisation Completed'
    
    # Document Status Changes
    DOCUMENT_ACTIVATED = 'document_activated', 'Document Activated'
    DOCUMENT_DEACTIVATED = 'document_deactivated', 'Document Deactivated'
    DOCUMENT_UPDATED = 'document_updated', 'Document Updated'
    
    # System Maintenance
    REPROCESSING_STARTED = 'reprocessing_started', 'Reprocessing Started'
    REINDEXING_COMPLETED = 'reindexing_completed', 'Reindexing Completed'
    
    # Error States
    PROCESSING_FAILED = 'processing_failed', 'Processing Failed'
    VALIDATION_FAILED = 'validation_failed', 'Validation Failed'
    CHUNKING_FAILED = 'chunking_failed', 'Chunking Failed'
    SUMMARISATION_FAILED = 'summarisation_failed', 'Summarisation Failed'
    EMBEDDING_FAILED = 'embedding_failed', 'Embedding Failed'
    VECTORDB_UPLOAD_FAILED = 'vectordb_upload_failed', 'Vector DB Upload Failed'


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
        choices=EventEnum.choices
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
    
    @classmethod
    def create_log(
        cls,
        document:Document, 
        event_type:EventEnum,
        message:str="",
        error_traceback:str="",
        ) -> bool:
        '''Update ProcessingLog utility function'''

        if not Document.objects.filter(pk=document.id).exists():
            return ValueError("Document does not exist.")
        
        if event_type is None:
            return ValueError("Event type is None")
        
        return cls.objects.create(
            document=document,
            event_type=event_type,
            message=message,
            error_traceback=error_traceback
        )