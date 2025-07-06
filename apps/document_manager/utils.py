from document_manager.models import Document 

import logging
logger = logging.getLogger(__name__)

def validate_document(document:Document) -> bool:
    '''Validate document before processing it.'''
    if not Document.objects.filter(pk=document.id).exists():
        return False

    if document.processing_status not in ['pending', 'failed']:
        logger.error("Document processing_status is not pending or failed.")
        return False
    
    if not document.file:
        raise ValueError("Document has no file attached")
    
    if not document.file.name.endswith('.pdf'):
        raise ValueError("Only PDF documents are supported")
    
    return True
    
def update_processing_status(document:Document, status:str) -> None:
    if not document:
        raise ValueError("No document given.")
    if not status:
        raise ValueError("No status update given.")
    
    old_status = document.processing_status
    document.processing_status = status
    document.save(update_fields=['processing_status'])
    
    # Log status changes
    logger.info(f"Document {document.id} status: {old_status} → {status}")