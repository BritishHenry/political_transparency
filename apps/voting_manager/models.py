from django.db import models

class RequestedDocument(models.Model):
    """
    Model for user-requested documents that may be added to the platform.
    """
    # Define the max length constant at the model level
    MAX_NAME_LENGTH = 255
    
    document_name = models.CharField(
        max_length=MAX_NAME_LENGTH,
        verbose_name="Document Name",
        help_text="Name or description of the document you'd like to see added"
    )

    document_url = models.URLField(
        verbose_name="Document URL",
        help_text="Link to the document (optional)",
        blank=True,
        null=True
    )

    votes = models.PositiveIntegerField(default=0)

    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-votes', '-requested_at']
        verbose_name = "Requested Document"
        verbose_name_plural = "Requested Documents"
    
    def __str__(self):
        return self.document_name