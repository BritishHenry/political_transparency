from django.shortcuts import render, get_object_or_404

from .models import Document


def document_library(request):
    context={}
    return render(request, "document_library.html", context)

def documents(request):
    context={}
    return render(request, "documents.html", context)

def document_chat(request, slug):
    document = get_object_or_404(Document, slug=slug)
    context={"document":document}
    return render(request, "document_chat.html", context)
