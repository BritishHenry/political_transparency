from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from document_manager.models import Document
from django.http import JsonResponse
from django.utils import timezone
import re 
from django.http import FileResponse, Http404


from django_q.tasks import async_task
from django_q.models import Task

class ChatView(View):
    
    
    def get(self, request, slug):

        document = get_object_or_404(Document, slug=slug)
        messages = request.session.get("chat_messages")

        context={"document":document, "slug":slug, "messages":messages}
        return  render(request, "document_chat.html", context)
    
    def post(self, request, slug):
        message = request.POST.get("message", "").strip()
        # Add in a token estimation and reject message with error msg if too long.

        if not message:
            print('returning json')
            return JsonResponse({"success": False, "slug":slug})
        
        messages = request.session.get("chat_messages")
        if not messages:
            messages = []

        new_message = {
            "sender":"user",
            "text": message,
            "timestamp": timezone.now().strftime("%H:%M:%S"),
        }
        messages.append(new_message)
        request.session["chat_messages"] = messages

        # Get document and organise data for response generation
        document = get_object_or_404(Document, slug=slug)
        response_params = {
            "message": message,
            "collection_name": f"{re.sub(r'[^a-zA-Z0-9]', '_', document.slug)}__{document.id}",
            "document_slug": document.slug
        }
        
        # Schedule the response generation and recieve an ID to query via AJAX polling
        task_id = async_task('apps.chat_manager.tasks.generate_response', response_params) #removed 'save=True', as I don't know what its for

        return JsonResponse({"success": True, "slug":slug, "message": new_message, "task_id":task_id})


    
def get_response(request, slug, task_id):
    try:
        task = Task.objects.get(id=task_id)
        response = task.result
        
        if response:
            new_message = {
                "sender":"ai",
                "text": response,
                "timestamp": timezone.now().strftime("%H:%M:%S"),
            }

            messages = request.session.get("chat_messages")
            messages.append(new_message)
            request.session["chat_messages"] = messages

            return JsonResponse({"response_ready": True, "message": new_message})
        
    except Exception as e:
        return JsonResponse({"response_ready": False})

def view_document_source(request, slug):
    document = get_object_or_404(Document, slug=slug)
    try:
        # For local files
        return FileResponse(
            document.file.open('rb'),
            content_type='application/pdf',
            as_attachment=False,  # False = view in browser, True = download
            filename=document.name
        )
    
    except FileNotFoundError:
        raise Http404("PDF file not found")
