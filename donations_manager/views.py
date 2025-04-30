from django.shortcuts import render

# Create your views here.


def donations(request):
    context={}
    return render(request, "donations.html", context)