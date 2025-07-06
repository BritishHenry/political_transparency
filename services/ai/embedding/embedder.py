'''
This file will handle the embedding of all the document's chunks
'''
from .validators import validate_embedding_input, validate_embedding_response
from general.decorators import retry_with_backoff

import logging
logger = logging.getLogger(__name__)

class Embedder:
    def __init__(self, llm_service, embedding_model):
        self.llm_service = llm_service
        self.embedding_model = embedding_model
        self.vector_size = self._get_vector_size_for_model(embedding_model)
        logger.info(f"Embedder initialized with model: {embedding_model}, vector size: {self.vector_size}")

    def _get_vector_size_for_model(self, model_name):
        """Get expected vector dimensions for the embedding model"""
        model_dimensions = {
            'text-embedding-ada-002': 1536,
            'text-embedding-3-small': 1536,
            'text-embedding-3-large': 3072,
        }
        
        return model_dimensions.get(model_name, 1536)  # Default fallback
    
    def _initialise_vector_database_client(self):
        '''Initialise the Qdrant vector database with API key.'''
        logger.info("Initializing Qdrant vector database client")
        
        from django.conf import settings
        from qdrant_client import QdrantClient
        
        try:
            qdrant_client = QdrantClient(
                url=settings.QDRANT_POLITICAL_TRANSPARENCY_ENDPOINT, # I have seen url listed as 'url' and 'host' in the docs -> may need to change if not working.
                api_key=settings.QDRANT_API_KEY,
            )
            logger.info(f"Successfully connected to Qdrant at {settings.QDRANT_POLITICAL_TRANSPARENCY_ENDPOINT}")
            return qdrant_client
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            raise

    @retry_with_backoff(base_delay=5)
    def get_embedding(self, input):
        '''Create the embedding using OpenAI Responses API: used for document upload and user messages'''
        
        # Handle both objects with .content and plain strings
        text = input.content if hasattr(input, 'content') else input
        
        if not validate_embedding_input(text):
            raise Exception("Embedding input failed validation.")

        # Log text length for monitoring
        text_length = len(text)
        logger.debug(f"Creating embedding for text of length: {text_length}")
        
        try:
            response = self.llm_service.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            
            embedding = validate_embedding_response(response, self.vector_size)
            return embedding
        except Exception as e:
            logger.error(f"Error creating embedding for text length {text_length}: {e}")
            raise Exception(f"Error creating embedding: {e}")
    

    def _create_collection(self, qdrant_client, collection_name):
        '''If a Collection does not exist, create one in Qdrant. Each Document will have its own Collection.'''
        logger.info(f"Creating new Qdrant collection: {collection_name}")
        
        from qdrant_client.models import Distance, VectorParams
        
        try:
            collection = qdrant_client.create_collection(
                collection_name=collection_name, 
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            
            if not collection:
                logger.error(f"Failed to create collection {collection_name}")
                raise ValueError("Error creating collection")

            if not qdrant_client.collection_exists(collection_name=collection_name):
                logger.error(f"Collection {collection_name} was not created successfully")
                raise ValueError(f"Collection '{collection_name}' does not exist in Qdrant")
            
            logger.info(f"Successfully created collection: {collection_name}")
            return
        except Exception as e:
            logger.error(f"Error creating collection {collection_name}: {e}")
            raise
        
    def _save(self, data_to_save, qdrant_client, collection_name):
        '''Save the embeddings to Qdrant and update the relvant fields in the Postgresql models.'''
        logger.info(f"Starting save operation for {len(data_to_save)} items to collection: {collection_name}")
        
        from qdrant_client import models
        from document_manager.models.chunks import DocumentChunk
        from document_manager.models.summaries import DocumentSummary
        from django.db import transaction
        import uuid
        from django.utils import timezone

        points_to_upsert = []
        chunks_to_update = []
        summaries_to_update = []
        
        logger.debug("Preparing data for upsert...")
        for i, data in enumerate(data_to_save): #this implementation relies on the similarities in the DocumentChunk and DocumentSummary models
            vector_uuid = str(uuid.uuid4())

            point = models.PointStruct(
                id=vector_uuid, 
                vector=data["vector"], 
                payload={
                    "type":data["type"], 
                    "object_id":data["object_id"], 
                    "document_id":data["document_id"]
                    }
                )
            points_to_upsert.append(point)

            data["object"].vector_id = vector_uuid
            data["object"].embedding_model = self.embedding_model
            data["object"].embedded_at = timezone.now()
            #data["object"].save(update_fields=['vector_id', 'embedding_model', 'embedded_at'])
            if data["model"] == "DocumentChunk":
                chunks_to_update.append(data["object"])
            elif data["model"] == "DocumentSummary":
                summaries_to_update.append(data["object"])
            
            if (i + 1) % 100 == 0:  # Log progress every 100 items
                logger.debug(f"Prepared {i + 1}/{len(data_to_save)} items for upsert")

        logger.info(f"Prepared {len(chunks_to_update)} chunks and {len(summaries_to_update)} summaries for database update")
        logger.info(f"Prepared {len(points_to_upsert)} points for Qdrant upsert")

        try:
            logger.debug(f"Upserting {len(points_to_upsert)} points to Qdrant collection: {collection_name}")
            qdrant_client.upsert(
                collection_name = collection_name,
                wait = True, # Ensures operation completes
                points = points_to_upsert
            )
            logger.info(f"Successfully upserted {len(points_to_upsert)} points to Qdrant")
            
            # Verify the upsert succeeded
            saved_count = qdrant_client.count(
                collection_name=collection_name,
                exact = True,
            )

            if saved_count < len(points_to_upsert):
                raise Exception(f"Qdrant verification failed: expected {len(points_to_upsert)}, found {saved_count}")

            with transaction.atomic():
                logger.debug("Starting atomic transaction for database and Qdrant updates")
                
                if chunks_to_update:
                    logger.debug(f"Bulk updating {len(chunks_to_update)} DocumentChunk objects")
                    DocumentChunk.objects.bulk_update(
                        chunks_to_update,
                        fields=['vector_id', 'embedding_model', 'embedded_at'],
                        batch_size=100 # recommended when updating a lot of instances
                    )
                    logger.info(f"Successfully updated {len(chunks_to_update)} DocumentChunk objects")

                if summaries_to_update:
                    logger.debug(f"Bulk updating {len(summaries_to_update)} DocumentSummary objects")
                    DocumentSummary.objects.bulk_update(
                        summaries_to_update,
                        fields=['vector_id', 'embedding_model', 'embedded_at'],
                        batch_size=100 # recommended when updating a lot of instances
                    )
                    logger.info(f"Successfully updated {len(summaries_to_update)} DocumentSummary objects")
                                
        except Exception as e:
            logger.error(f"Error while saving data to DocumentChunk, DocumentSummary or Qdrant: {e}")
            raise Exception(f"Error while saving data to Documentchunk, DocumentSummary or Qdrant | Error: {e}")
        
        return

    def process_document(self, document):
        '''
        The flow:
            1) Get the chunks and summaries
            2) loop through the chunks and summaries and create an embedding for them
            3) create dic of thechunks and summaries (data), prepared for saving
            4) initialise the vecotr database
            5) check the collection exists. if not, create one.
            6) save the data:
                - create PointStruct objects from the data 
                - update the relevant object fields
                use atomic transaction to save all data to qdrant and my database
        
        Costs:
            - Using text-embedding-3-small, assuming a 300 page pdf doc, which given our chunking methodology, will cost approx $0.0163
            - If cost is an issue, look to batch embed the sentances and maybe paragraphs.
        '''
        logger.info(f"Starting embedding process for document: {document.id} ({document.title if hasattr(document, 'title') else 'Unknown title'})")
        
        from document_manager.models.chunks import DocumentChunk
        from document_manager.models.summaries import DocumentSummary
                
        logger.debug("Fetching chunks and summaries from database")
        chunks =    DocumentChunk.objects.filter(document=document, vector_id__isnull=True) 
        summaries = DocumentSummary.objects.filter(document=document, vector_id__isnull=True)
        
        chunk_count = chunks.count()
        summary_count = summaries.count()
        total_items = chunk_count + summary_count
        
        logger.info(f"Found {chunk_count} chunks and {summary_count} summaries to embed (total: {total_items})")
        
        if total_items == 0:
            logger.warning(f"No items to embed for document {document.id}")
            return


        data_to_save = []            
        
        if chunks:
            logger.info(f"Creating embeddings for {chunk_count} chunks...")
            for i, chunk in enumerate(chunks):
                try:
                    embedding = self.get_embedding(chunk)
                    data = {"object":chunk, "model":"DocumentChunk", "object_id":chunk.pk, "type": chunk.chunk_type, "document_id":chunk.document.id, "vector":embedding}
                    data_to_save.append(data)
                    
                    if (i + 1) % 50 == 0:  # Log progress every 50 chunks
                        logger.info(f"Embedded {i + 1}/{chunk_count} chunks")
                        
                except Exception as e:
                    logger.error(f"Failed to create embedding for chunk {chunk.pk}: {e}")
                    raise
            
            logger.info(f"Successfully created embeddings for all {chunk_count} chunks")
        
        if summaries:
            logger.info(f"Creating embeddings for {summary_count} summaries...")
            for i, summary in enumerate(summaries):
                try:
                    embedding = self.get_embedding(summary)
                    data = {"object":summary, "model":"DocumentSummary", "object_id":summary.pk, "type": summary.summary_type, "document_id":summary.document.id, "vector":embedding}
                    data_to_save.append(data)
                    
                    if (i + 1) % 10 == 0:  # Log progress every 10 summaries
                        logger.info(f"Embedded {i + 1}/{summary_count} summaries")
                        
                except Exception as e:
                    logger.error(f"Failed to create embedding for summary {summary.pk}: {e}")
                    raise
            
            logger.info(f"Successfully created embeddings for all {summary_count} summaries")
        
        logger.debug("Initializing vector database client")
        qdrant_client = self._initialise_vector_database_client()

        # Santise the collection name to ensure no Qdrant naming issues -> Replaces all NON uppercase letters, lowercase letters, digits, underscores and hyphens with an underscore.
        import re
        collection_name = f"{re.sub(r'[^a-zA-Z0-9]', '_', document.slug)}__{document.id}"
        logger.info(f"Using collection name: {collection_name}")

        logger.debug(f"Checking if collection {collection_name} exists")
        ###! Need to change: if not exist, qdrant returns an exception, not None. So need to handle this with a try/except block to set value, then if/else to check it.
        if not qdrant_client.collection_exists(collection_name=collection_name):
            logger.warning(f"Collection {collection_name} does not exist, creating it")
            self._create_collection(qdrant_client, collection_name)
        else:
            logger.info(f"Collection {collection_name} already exists")
        
        if (data_to_save is not None) and (qdrant_client.collection_exists(collection_name=collection_name)):
            logger.info(f"Saving {len(data_to_save)} embeddings to database and Qdrant")
            #self._save(data_to_save, qdrant_client, collection_name) -> moving this to the pipeline for more control
            
            logger.info(f"Document embedding process completed successfully for document {document.id}")
            return data_to_save, qdrant_client, collection_name
        else:
            logger.error(f"Cannot save data: data_to_save is None or collection {collection_name} does not exist")
            
        return