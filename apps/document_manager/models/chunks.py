from django.db import models


class DocumentChunk(models.Model):
    """Represents a chunk of document text for vector processing"""
    document = models.ForeignKey(
        'Document', 
        on_delete=models.CASCADE, 
        related_name='chunks'
    )

    chunk_index = models.IntegerField(help_text="Order of this chunk in the document")
    chunk_type = models.CharField(max_length=20) # eg 'sentence', 'paragraph', etc.
    page_start = models.IntegerField()
    page_end = models.IntegerField() 

    content = models.TextField(help_text="The actual text content of this chunk")
    vector_id = models.CharField(
        max_length=100, 
        blank=True,
        null=True, # When chunk is initially saved, it won't have an embedding.
        help_text="ID of this chunk in the vector database"
    )
    embedding_model = models.CharField(
        max_length=50,
        default='Not specified',
        help_text="Model used for embedding generation"
    )
    embedded_at = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict)  # Stores the flexible dict

    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
            models.Index(fields=['vector_id']),
        ]
        ordering = ['document', 'chunk_index']
        unique_together = [['document', 'chunk_index']]
    
    def __str__(self):
        return f"{self.document.name} - Chunk {self.chunk_index}"