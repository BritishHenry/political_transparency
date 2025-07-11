from django.contrib import admin

from document_manager.models.general import Tag, Document
from document_manager.models.logs import ProcessingLog
from document_manager.models.chunks import DocumentChunk
from document_manager.models.summaries import DocumentSummary

from django_q.tasks import async_task


import logging
logger = logging.getLogger(__name__)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('name', 'processing_status', 'file', 'created_at')
    list_filter = ('processing_status', 'created_at', 'tags')
    search_fields = ('name', 'description')
    filter_horizontal = ('tags',)
    readonly_fields = ('file_hash', 'file_size', 'mime_type', 'created_at', 'updated_at')

    actions = ['process_documents_async']

    def process_documents_async(self, request, queryset):
        """Queue selected documents for async processing."""
        count = 0
        for document in queryset:
            if document.processing_status not in ['processing', 'completed', 'failed']:
                
                # Queue the task
                async_task('apps.document_manager.tasks.process_documents_task', document.id)
                count += 1
    process_documents_async.short_description = "Process selected documents (async)"

    

@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_type', 'chunk_index', 'vector_id', 'created_at', 'pk')
    list_filter = ('created_at',)
    search_fields = ('document__name', 'content')
    readonly_fields = ('created_at',)


@admin.register(DocumentSummary)
class DocumentSummaryAdmin(admin.ModelAdmin):
    list_display = ('document', 'summary_type', 'section_name', 'vector_id', 'created_at', 'pk')
    list_filter = ('created_at',)
    search_fields = ('document__name', 'content')
    readonly_fields = ('created_at',)


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ('document', 'event_type', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('document__name', 'message')
    readonly_fields = ('created_at',)