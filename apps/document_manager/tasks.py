from document_manager.models import Document 
from django.shortcuts import get_object_or_404

import logging
logger = logging.getLogger(__name__)

def process_documents_task(document_id):
    """
    Admin action to process selected documents through the pipeline
    """
    logger.info("process_documents_task triggered")
    document = get_object_or_404(Document, id=document_id)
    
    try:
        from .pipeline import Control
        
        # Initialize with required parameters
        pipeline = Control(document)
        logger.info("Initialised document processing control pipeline")
        
        # Call the process_document method
        result = pipeline.process_document()

        logger.info("Successfully executed process_documents_task")

    except Exception as e:
        logger.error(f"Failed to process document {document.id}: {str(e)}")
    