from django.shortcuts import render, get_object_or_404
from django.views import View
from document_manager.models import Document
from django.http import JsonResponse
from django.utils import timezone



class ChatView(View):
    
    def get(self, request, slug):
        print('get request: ', request)

        document = get_object_or_404(Document, slug=slug)
        messages = request.session.get("chat_messages", [])

        context={"document":document, "slug":slug, "messages":messages}
        return render(request, "document_chat.html", context)
    
    def post(self, request, slug):
        message = request.POST.get("message", "").strip()
        if message:
            messages = request.session.get("chat_messages", [])
            new_message = {
                "sender":"user",
                "text": message,
                "timestamp": timezone.now().strftime("%H:%M:%S"),
            }
            messages.append(new_message)
            test_msg = {
                "sender":"ai",
                "text": "wagwan, I am AI",
                "timestamp": timezone.now().strftime("%H:%M:%S"),
            }
            messages.append(test_msg)
            request.session["chat_messages"] = messages
            return JsonResponse({"success": True, "slug":slug, "message": new_message})
        return JsonResponse({"success": False, "slug":slug})
