from django.contrib import admin
from .models import Tag, Document, DocumentChunk, ProcessingLog


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
    

@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'vector_id', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('document__name', 'content')
    readonly_fields = ('created_at',)


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ('document', 'event_type', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('document__name', 'message')
    readonly_fields = ('created_at',)