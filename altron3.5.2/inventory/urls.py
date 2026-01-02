from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('barcode/', views.barcode_module, name='barcode_module'),
    path('create_batch/', views.create_batch, name='create_batch'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batch/<int:batch_id>/barcodes/', views.barcode_list, name='barcode_list'),
    path('batch/<int:batch_id>/print/', views.print_barcodes, name='print_barcodes'),
    path('batch/<int:batch_id>/print/<int:barcode_id>/', views.print_barcodes, name='print_single_barcode'),
    path('testing/', views.testing_module, name='testing_module'),
    path('new_test/', views.new_test, name='new_test'),
    path('test_results/', views.test_results, name='test_results'),
    path('barcodes/<int:batch_id>/pdf/', views.print_barcodes_pdf, name='print_barcodes_pdf'),
    path('barcode-img/<str:sequence_number>/', views.barcode_image_view, name='barcode_image'),
    path('test/<int:test_id>/', views.test_detail, name='test_detail'),
    path('test/<int:test_id>/print/', views.print_test_report, name='print_test_report'), # <--- THIS IS THE CRUCIAL LINE
    path('keep-alive/', views.session_keep_alive, name='session_keep_alive'),

    # Service Module URLs
    path('service/', views.service_module, name='service_module'),
    path('service/create/', views.create_service_case, name='create_service_case'),
    path('service/create/<int:barcode_id>/', views.create_service_case, name='create_service_case_barcode'),
    path('service/create/<int:barcode_id>/<int:test_id>/', views.create_service_case, name='create_service_case_with_test'),
    path('service/history/<int:barcode_id>/', views.service_history, name='service_history'),
    path('service/list/', views.service_list, name='service_list'),
    path('service/list/print/', views.print_service_report, name='print_service_report'),
    path('service/case/<str:case_id>/', views.service_detail, name='service_detail'),
    path('service/case/<str:case_id>/print/', views.print_service_case_detail, name='print_service_case_detail'),
]