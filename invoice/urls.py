from django.urls import path

from . import views

app_name = 'invoice'

urlpatterns = [
    path('invoices/', views.all_invoices, name='all_invoices'),
    path('invoices/create/<str:bookingId>/', views.create_invoice, name='create_invoice'),
    path('invoices/edit/<str:invoiceId>/', views.edit_invoice, name='edit_invoice'),
    path('invoices/delete/<str:invoiceId>/', views.delete_invoice, name='delete_invoice'),
    path('invoices/detail/<str:invoiceId>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/mark-paid/<str:invoiceId>/', views.mark_invoice_paid, name='mark_invoice_paid'),
    path('invoices/<str:invoiceId>/preview/', views.invoice_preview, name='invoice_preview'),
    path('invoices/<str:invoiceId>/generate-pdf/', views.generate_pdf, name='generate_pdf'),
]