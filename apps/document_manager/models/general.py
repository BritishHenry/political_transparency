from django.db import models
from django.core.exceptions import ValidationError
import hashlib

from document_manager.uploading.validators import validate_document_file, generate_safe_filename


class Tag(models.Model):
    """Tags for categorizing documents"""

    name = models.CharField(max_length=250)
    slug = models.SlugField(
            max_length=100, 
            unique=True, 
            blank=True,  # Make it optional in forms. So if leaft blank in admin creation, slug will generate automatically.
            help_text="URL-friendly version of the name. Leave blank to auto-generate."
        )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        """
        Override the save method to automatically generate the slug field
        from the company name if it's not set or if the name has changed.
        """
        from django.utils.text import slugify
        
        # Generate slug if it's missing or if name has changed
        if not self.slug or not self.pk or slugify(self.name) != self.slug:
            original_slug = slugify(self.name)
            self.slug = original_slug
            
            # Handle potential slug collisions
            # If a company with the same slug already exists, add a number suffix
            counter = 1
            while Tag.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
    class Meta:
        app_label = 'document_manager'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['name']), 
        ]
        ordering = ['name']
        verbose_name = "Tag"
        verbose_name_plural = "Tags"


class Document(models.Model):
    """Document model for RAG system"""

    name = models.CharField(max_length=250)
    slug = models.SlugField(
            max_length=100, 
            unique=True, 
            blank=True,  # Make it optional in forms. So if leaft blank in admin creation, slug will generate automatically.
            help_text="URL-friendly version of the name. Leave blank to auto-generate."
        )
    
    is_active = models.BooleanField(default=False, null=False)
    date = models.DateField(null=True, blank=True)
    description = models.TextField(
        help_text="Brief description of the document content"
    )  # Renamed from 'descriptor' for clarity
    
    tags = models.ManyToManyField(
        'document_manager.Tag', 
        related_name='documents',  # More intuitive reverse relation name
        blank=True
    )
    
    file = models.FileField(
        upload_to=generate_safe_filename,
        validators=[validate_document_file],
        help_text="Upload the document file (PDF, TXT, DOC, etc.). Max size: 100MB"
    )

    contents_page = models.TextField(
        blank=True,
        help_text="Formatted table of contents with headlines and page ranges"
    )
    
    # Additional metadata fields for RAG system
    file_hash = models.CharField(
        max_length=64, 
        editable=False, 
        blank=True,
        help_text="SHA256 hash of the file for integrity checking"
    )
    
    file_size = models.BigIntegerField(
        editable=False,
        null=True,
        help_text="File size in bytes"
    )
    
    mime_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="MIME type of the uploaded file"
    )
    
    processing_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending',
        help_text="Status of vector database processing"
    )
    
    vector_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID reference in the vector database"
    )
    
    collection_name = models.CharField(max_length=250, blank=True, null=True)

    
    metadata = models.JSONField(default=dict, blank=True)  # Stores the flexible dict
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Validate the document before saving"""
        # File validation is now handled by the field validators
        if self.file and not self.date:
            raise ValidationError("Date field is required when uploading a file")
    
    def save(self, *args, **kwargs):
        """Extended save method with file processing"""
        # Calculate file hash if file is being uploaded
        if self.file and not self.file_hash:
            self.file.seek(0)
            file_hash = hashlib.sha256()
            for chunk in iter(lambda: self.file.read(4096), b''):
                file_hash.update(chunk)
            self.file_hash = file_hash.hexdigest()
            self.file.seek(0)
            
            # Store file size
            self.file_size = self.file.size
            
            # Detect MIME type using Django's built-in method
            import mimetypes
            self.mime_type = mimetypes.guess_type(self.file.name)[0] or 'application/octet-stream'
        
        """
        Override the save method to automatically generate the slug field
        from the company name if it's not set or if the name has changed.
        """
        from django.utils.text import slugify
        
        # Generate slug if it's missing or if name has changed
        if not self.slug or not self.pk or slugify(self.name) != self.slug:
            original_slug = slugify(self.name)
            self.slug = original_slug
            
            # Handle potential slug collisions
            # If a company with the same slug already exists, add a number suffix
            counter = 1
            while Document.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1

        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.processing_status})"
    
    class Meta:
        app_label = 'document_manager'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['processing_status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['file_hash']),  # For duplicate detection
        ]
        ordering = ['-created_at']

        verbose_name = "Document"
        verbose_name_plural = "Documents"
