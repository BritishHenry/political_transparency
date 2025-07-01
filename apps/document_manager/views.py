from django.shortcuts import render, get_object_or_404

from .models import Document


def document_library(request):
    context={}
    return render(request, "document_library.html", context)

def documents(request):
    context={}
    return render(request, "documents.html", context)

