'''
This file will handle the embedding of all the document's chunks
'''

class Embedder:
    def __init__(self, llm_service, embedding_model):
        self.llm_service = llm_service
        self.embedding_model = embedding_model
        self.vector_size = 1536

    def _initialise_vector_database_client(self):
        '''Initialise the Qdrant vector database with API key.'''
        from django.conf import settings
        from qdrant_client import QdrantClient
        
        qdrant_client = QdrantClient(
            url=settings.QDRANT_POLITICAL_TRANSPARENCY_ENDPOINT, # I have seen url listed as 'url' and 'host' in the docs -> may need to change if not working.
            api_key=settings.QDRANT_API_KEY,
        )
        
        return qdrant_client

    def get_embedding(self, input):
        '''Create the embedding using OpenAI Responses API'''

        # Handle both objects with .content and plain strings
        text = input.content if hasattr(input, 'content') else input

        try:
            response = self.llm_service.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"Error creating embedding: {e}")
    
    def _create_collection(self, qdrant_client, collection_name):
        '''If a Collection does not exist, create one in Qdrant. Each Document will have its own Collection.'''
        from qdrant_client.models import Distance, VectorParams
        collection = qdrant_client.create_collection(
            collection_name=collection_name, 
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
        
        if not collection:
            raise ValueError("Error creating collection")

        if not qdrant_client.collection_exists(collection_name=collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist in Qdrant")
        
        return
        
    def _save(self, data_to_save, qdrant_client, collection_name):
        '''Save the embeddings to Qdrant and update the relvant fields in the Postgresql models.'''
        from qdrant_client.models import PointStruct
        from apps.document_manager.models import DocumentChunk, DocumentSummary
        from django.db import transaction
        import uuid
        from django.utils import timezone

        points_to_upsert = []
        chunks_to_update = []
        summaries_to_update = []
        for data in data_to_save: #this implementation relies on the similarities in the DocumentChunk and DocumentSummary models
            vector_uuid = str(uuid.uuid4())

            point = PointStruct(
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
            #data["object"].save(update_fields=['vector_id', 'embedding_model', 'embeded_at'])
            if data["model"] == "DocumentChunk":
                chunks_to_update.append(data["object"])
            elif data["model"] == "DocumentSummary":
                summaries_to_update.append(data["object"])

        try:
            with transaction.atomic():
                DocumentChunk.objects.bulk_update(
                    chunks_to_update,
                    fields=['vector_id', 'embedding_model', 'embedded_at'],
                    batch_size=500 # recommended when updating a lot of instances
                )

                DocumentSummary.objects.bulk_update(
                    summaries_to_update,
                    fields=['vector_id', 'embedding_model', 'embedded_at'],
                    batch_size=500 # recommended when updating a lot of instances
                )

                qdrant_client.upsert(
                    collection_name = collection_name,
                    wait = True,
                    points = points_to_upsert
                )
        except Exception as e:
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
        '''
        from apps.document_manager.models import DocumentChunk, DocumentSummary
        chunks =    DocumentChunk.objects.filter(document=document, vector_id__isnull=True)
        summaries = DocumentSummary.objects.filter(document=document, vector_id__isnull=True)

        # Santise the collection name to ensure no Qdrant naming issues -> Replaces all NON uppercase letters, lowercase letters, digits, underscores and hyphens with an underscore.
        import re
        collection_name = re.sub(r'[^a-zA-Z0-9_-]', '_', document.slug)

        data_to_save = []
        if chunks:
            for chunk in chunks:
                embedding = self.get_embedding(chunk)
                data = {"object":chunk, "model":"DocumentChunk", "object_id":chunk.pk, "type": chunk.chunk_type, "document_id":chunk.document.id, "vector":embedding}
                data_to_save.append(data)
        
        if summaries:
            for summary in summaries:
                embedding = self.get_embedding(summary)
                data = {"object":summary, "model":"DocumentSummary", "object_id":summary.pk, "type": summary.summary_type, "document_id":summary.document.id, "vector":embedding}
                data_to_save.append(data)
        
        qdrant_client = self._initialise_vector_database_client()

        if not qdrant_client.collection_exists(collection_name=collection_name):
            self._create_collection(qdrant_client, collection_name)
        
        if (data_to_save is not None) and (qdrant_client.collection_exists(collection_name=collection_name)):
            self._save(data_to_save, qdrant_client, collection_name)
        
        return