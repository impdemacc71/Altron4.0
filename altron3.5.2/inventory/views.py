# your_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.conf import settings # Import settings for MEDIA_URL
from django.views.decorators.cache import never_cache # Import never_cache decorator
from .forms import  BatchCreateForm, TestForm, TestOverallStatusForm, ServiceCaseForm
from .models import Batch, Barcode, SKU, Test, TestQuestion, TestAnswer, CustomUser, TestTemplate, ServiceCase, Technician, SystemLog
import logging
from django.core.paginator import Paginator
from django.template.loader import get_template
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone


SPEC_FIELD_MAP = {
    'device_name': 'Device Name',
    'battery': 'Battery',
    'capacity': 'BATTERY Cap',         
    'mppt_cap': 'MPPT Cap',
    'voc_max': 'Voc Max',             
    'feature_spec': 'Feature / Spec',
    'ef': 'EF',
    'system_cap': 'SYSTEM Cap',       
    'spv_max': 'SPV Max',             
    'dc_load': 'DC LOAD',             
    'kel_po': 'KEL-PO',               
    'current_max': 'CURRENT Max',     
    'input_range': 'INPUT Range',     
    'output_range': 'OUTPUT Range',   
}

# Import HTML from weasyprint
try:
    from weasyprint import HTML
    # Configure WeasyPrint logging to be more verbose
    logging.getLogger('weasyprint').setLevel(logging.DEBUG) # Set WeasyPrint logger to DEBUG
except (ImportError, OSError) as e:
    import logging
    logging.error("WeasyPrint failed to import: %s", e)
    logging.warning("PDF generation features will be disabled. GTK3 libraries may be missing.")
    HTML = None


# Setup logging for debugging
logger = logging.getLogger(__name__)

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'inventory/login.html', {'error': 'Invalid credentials'})
    return render(request, 'inventory/login.html')

def user_logout(request):
    logout(request)
    return redirect('login')

@login_required
@never_cache # Added never_cache decorator
def dashboard(request):
    # Calculate test statistics in a SINGLE query (performance fix)
    from django.db.models import Count, Q

    counts = Test.objects.aggregate(
        total_tests=Count('id'),
        passed_tests=Count('id', filter=Q(overall_status='passed')),
        failed_tests=Count('id', filter=Q(overall_status='failed')),
        pending_tests=Count('id', filter=Q(overall_status='pending'))
    )

    context = {
        'total_tests': counts['total_tests'] or 0,
        'passed_tests': counts['passed_tests'] or 0,
        'failed_tests': counts['failed_tests'] or 0,
        'pending_tests': counts['pending_tests'] or 0,
    }
    return render(request, 'inventory/dashboard.html', context)

@login_required
@never_cache # Added never_cache decorator
def barcode_module(request):
    # Admin, Batch Generation, and Tester can access
    if request.user.role not in ['admin', 'batch', 'tester']:
        return redirect('dashboard')
    return render(request, 'inventory/barcode_module.html')

@login_required
@never_cache
def create_batch(request):
    # Only Admin and Batch Generation can create batches
    if request.user.role not in ['admin', 'batch']:
        return redirect('dashboard')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = BatchCreateForm(request.POST)

        if form.is_valid():
            if is_ajax:
                # AJAX successful validation—this branch is usually just hit for form rendering,
                # but we'll include it for completeness if the view must return HTML.
                pass # Proceed to save and redirect below
            else:
                batch = form.save()

                # Log batch creation
                SystemLog.log_event(
                    event_type='batch_created',
                    title=f'Batch {batch.prefix} Created',
                    description=f'Batch created with {batch.quantity} barcodes for SKU {batch.sku.code}',
                    level='info',
                    user=request.user,
                    batch=batch,
                    request=request,
                    details={
                        'sku_code': batch.sku.code,
                        'quantity': batch.quantity,
                        'batch_date': str(batch.batch_date),
                        'spec_template': batch.spec_template.name if batch.spec_template else None,
                    }
                )

                return redirect('batch_list')
        
        # If form is invalid or we are handling an AJAX update request:
        if is_ajax:
            # Render ONLY the dynamic fields section for the AJAX response
            return render(request, 'inventory/create_batch_dynamic_fields.html', {'form': form})
        else:
            # Regular POST failure: render the full page with errors
            return render(request, 'inventory/create_batch.html', {'form': form})
    else:
        # Initial GET request
        form = BatchCreateForm()
    
    return render(request, 'inventory/create_batch.html', {'form': form})


@login_required
@never_cache # Added never_cache decorator
def batch_list(request):
    # Admin, Batch Generation, and Tester can view batch list
    if request.user.role not in ['admin', 'batch', 'tester']:
        return redirect('dashboard')

    # Performance fix: Add select_related to prevent N+1 queries
    batches = Batch.objects.select_related('sku', 'spec_template')

    sku_code = request.GET.get('sku_code')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    if sku_code:
        batches = batches.filter(sku__code__icontains=sku_code)

    if from_date:
        batches = batches.filter(batch_date__gte=from_date)

    if to_date:
        batches = batches.filter(batch_date__lte=to_date)

    #batches = batches.order_by('-batch_date')
    # Order by 'created_at' in descending order to get latest first
    batches = batches.order_by('-created_at') # CHANGED THIS LINE

    context = {
        'batches': batches,
        'sku_code': sku_code,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'inventory/batch_list.html', context)

@login_required
@never_cache # Added never_cache decorator
def barcode_list(request, batch_id):
    batch = get_object_or_404(Batch, id=batch_id)
    barcode_queryset = Barcode.objects.filter(batch=batch).order_by('sequence_number')

    barcode_number = request.GET.get('barcode_number')

    if barcode_number:
        barcode_queryset = barcode_queryset.filter(sequence_number__icontains=barcode_number)

    paginator = Paginator(barcode_queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    SPEC_FIELD_MAP = {
    'device_name': 'Device Name',
    'battery': 'Battery',
    'capacity': 'BATTERY Cap',         
    'mppt_cap': 'MPPT Cap',
    'voc_max': 'Voc Max',             
    'feature_spec': 'Feature / Spec',
    'ef': 'EF',
    'system_cap': 'SYSTEM Cap',       
    'spv_max': 'SPV Max',             
    'dc_load': 'DC LOAD',             
    'kel_po': 'KEL-PO',               
    'current_max': 'CURRENT Max',     
    'input_range': 'INPUT Range',     
    'output_range': 'OUTPUT Range',   
}

    context = {
        'batch': batch,
        'page_obj': page_obj,
        'barcode_number': barcode_number,
        # 💡 NEW: Pass the SPEC_FIELD_MAP
        'spec_field_map': SPEC_FIELD_MAP,
    }
    return render(request, 'inventory/barcode_list.html', context)

@login_required
@never_cache # Added never_cache decorator
def print_barcodes(request, batch_id, barcode_id=None):
    # Admin, Batch Generation, and Tester can print barcodes
    if request.user.role not in ['admin', 'batch', 'tester']:
        return redirect('dashboard')
    batch = get_object_or_404(Batch, id=batch_id)
    if barcode_id:
        barcodes = [get_object_or_404(Barcode, id=barcode_id, batch=batch)]
    else:
        barcodes = Barcode.objects.filter(batch=batch)
        
    context = {
        'batch': batch, 
        'barcodes': barcodes,
        # 💡 NEW: Pass the SPEC_FIELD_MAP
        'spec_field_map': SPEC_FIELD_MAP,
    }
    return render(request, 'inventory/print_barcodes.html', context)    
    #return render(request, 'inventory/print_barcodes.html', {'batch': batch, 'barcodes': barcodes})

@login_required
@never_cache # Added never_cache decorator
def testing_module(request):
    if request.user.role not in ['admin', 'tester']:
        return redirect('dashboard')
    return render(request, 'inventory/testing_module.html')


@login_required
@never_cache # Added never_cache decorator
def new_test(request):
    if request.user.role not in ['admin', 'tester']:
        return redirect('dashboard')

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        selected_sku_id = request.POST.get('sku')
        selected_batch_id = request.POST.get('batch')
        selected_template_id = request.POST.get('template')

        form = TestForm(request.POST,
                        selected_sku_id=selected_sku_id,
                        selected_batch_id=selected_batch_id,
                        selected_template_id=selected_template_id)

        if form.is_valid():
            if is_ajax:
                return render(request, 'inventory/new_test.html', {'form': form})
            else:
                logger.debug("Form cleaned data: %s", form.cleaned_data)
                
                sku_instance = form.cleaned_data['sku']
                batch_instance = form.cleaned_data['batch']
                barcode_instance = form.cleaned_data['barcode']
                template_instance = form.cleaned_data['template']

                test = Test.objects.create(
                    sku=sku_instance,
                    batch=batch_instance,
                    barcode=barcode_instance,
                    user=request.user,
                    template_used=template_instance,
                    overall_status=form.cleaned_data['overall_status']
                )
                
                questions = TestQuestion.objects.filter(template=template_instance)
                for question in questions:
                    status_field_name = f'question_{question.id}_status'
                    output_field_name = f'question_{question.id}_output' # NEW FIELD NAME
                    remarks_field_name = f'question_{question.id}_remarks'

                    status = form.cleaned_data.get(status_field_name, 'fail')
                    is_passed = (status == 'pass')
                    technical_output = form.cleaned_data.get(output_field_name, None) # NEW DATA EXTRACTION
                    remarks = form.cleaned_data.get(remarks_field_name, '')

                    logger.debug("Saving answer for question %s: status=%s, remarks=%s",
                                 question.id, status, remarks)
                    TestAnswer.objects.create(
                        test=test,
                        question=question,
                        is_passed=is_passed,
                        # NEW FIELD SAVING
                        technical_output=technical_output,
                        remarks=remarks
                    )

                # Log test creation
                barcode_display = barcode_instance.sequence_number if barcode_instance else 'No Barcode'
                if test.overall_status == 'failed':
                    SystemLog.log_event(
                        event_type='test_failed',
                        title=f'Test Failed for {barcode_display}',
                        description=f'Test failed for {barcode_display} (SKU: {sku_instance.code}, Batch: {batch_instance.prefix})',
                        level='warning',
                        user=request.user,
                        barcode=barcode_instance,
                        test=test,
                        request=request,
                        details={
                            'sku_code': sku_instance.code,
                            'batch_prefix': batch_instance.prefix,
                            'template': template_instance.name if template_instance else None,
                        }
                    )
                elif test.overall_status == 'passed':
                    SystemLog.log_event(
                        event_type='test_passed',
                        title=f'Test Passed for {barcode_display}',
                        description=f'Test passed for {barcode_display} (SKU: {sku_instance.code}, Batch: {batch_instance.prefix})',
                        level='info',
                        user=request.user,
                        barcode=barcode_instance,
                        test=test,
                        request=request,
                        details={
                            'sku_code': sku_instance.code,
                            'batch_prefix': batch_instance.prefix,
                            'template': template_instance.name if template_instance else None,
                        }
                    )

                return redirect('test_detail', test_id=test.id)
        else:
            logger.error("Form validation failed: %s", form.errors)
            return render(request, 'inventory/new_test.html', {'form': form})

    else:
        form = TestForm()

    return render(request, 'inventory/new_test.html', {'form': form})

@login_required
def auto_save_test(request):
    """Auto-save test data as draft"""
    if request.user.role not in ['admin', 'tester']:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    try:
        # Get or create test ID from session
        test_id = request.POST.get('test_id')
        sku_id = request.POST.get('sku')
        batch_id = request.POST.get('batch')
        barcode_id = request.POST.get('barcode')
        template_id = request.POST.get('template')
        overall_status = request.POST.get('overall_status', 'draft')

        if not all([sku_id, batch_id, template_id]):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields (SKU, Batch, and Template are required)'}, status=400)

        # Get instances
        sku_instance = SKU.objects.get(id=sku_id)
        batch_instance = Batch.objects.get(id=batch_id)
        template_instance = TestTemplate.objects.get(id=template_id)
        barcode_instance = Barcode.objects.filter(id=barcode_id).first() if barcode_id else None

        # Get or create test
        if test_id:
            test = Test.objects.get(id=test_id, user=request.user)
            # Update basic fields
            test.sku = sku_instance
            test.batch = batch_instance
            test.template_used = template_instance
            test.barcode = barcode_instance
            test.overall_status = overall_status
            test.save()

            # Delete existing answers for this test (we'll recreate them)
            TestAnswer.objects.filter(test=test).delete()
        else:
            # Create new test as draft
            test = Test.objects.create(
                sku=sku_instance,
                batch=batch_instance,
                barcode=barcode_instance,
                user=request.user,
                template_used=template_instance,
                overall_status='draft'
            )

        # Save question answers
        questions = TestQuestion.objects.filter(template=template_instance)
        answers_count = 0

        for question in questions:
            status_field_name = f'question_{question.id}_status'
            output_field_name = f'question_{question.id}_output'
            remarks_field_name = f'question_{question.id}_remarks'

            status = request.POST.get(status_field_name)

            # Only save if status is provided
            if status:
                is_passed = (status == 'pass')
                technical_output = request.POST.get(output_field_name, '')
                remarks = request.POST.get(remarks_field_name, '')

                TestAnswer.objects.create(
                    test=test,
                    question=question,
                    is_passed=is_passed,
                    technical_output=technical_output,
                    remarks=remarks
                )
                answers_count += 1

        return JsonResponse({
            'status': 'success',
            'test_id': test.id,
            'message': f'Saved {answers_count} answers'
        })

    except SKU.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid SKU'}, status=400)
    except Batch.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid Batch'}, status=400)
    except TestTemplate.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Invalid Template'}, status=400)
    except Test.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Test not found'}, status=404)
    except Exception as e:
        logger.error(f"Auto-save error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@never_cache # Added never_cache decorator
def test_results(request):
    if request.user.role not in ['admin', 'tester']:
        return redirect('dashboard')

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    sku = request.GET.get('sku')
    batch = request.GET.get('batch')
    barcode = request.GET.get('barcode')
    template_used = request.GET.get('template_used')

    # Performance fix: Add select_related to prevent N+1 queries
    # Exclude draft tests from results
    tests = Test.objects.select_related('sku', 'batch', 'barcode', 'template_used', 'user').exclude(overall_status='draft')

    if from_date:
        tests = tests.filter(test_date__gte=from_date)
    if to_date:
        tests = tests.filter(test_date__lte=to_date)
    if sku:
        tests = tests.filter(sku__code=sku)
    if batch:
        tests = tests.filter(batch__id=batch)
    if barcode:
        tests = tests.filter(barcode__sequence_number__icontains=barcode)
    if template_used:
        tests = tests.filter(template_used__id=template_used)

    tests = tests.order_by('-test_date')

    counts = tests.aggregate(
        total=Count('id'),
        passed=Count('id', filter=Q(overall_status='passed')),
        failed=Count('id', filter=Q(overall_status='failed')),
        pending=Count('id', filter=Q(overall_status='pending'))
    )

    context = {
        'tests': tests,
        'counts': counts,
        'skus': SKU.objects.all(),
        'batches': Batch.objects.select_related('sku'),  # Performance fix
        'templates': TestTemplate.objects.all(),
        'from_date': from_date,
        'to_date': to_date,
        'sku': sku,
        'batch': batch,
        'barcode': barcode,
        'template_used': template_used,
    }
    return render(request, 'inventory/test_results.html', context)


@login_required
@never_cache # Added never_cache decorator
def test_detail(request, test_id):
    if request.user.role not in ['admin', 'tester']:
        return redirect('dashboard')
    
    test = get_object_or_404(Test.objects.select_related('sku', 'batch', 'barcode', 'user', 'template_used'), id=test_id)
    
    if request.method == 'POST':
        form = TestOverallStatusForm(request.POST, instance=test)
        if form.is_valid():
            form.save()
            return redirect('test_detail', test_id=test.id)
        else:
            logger.error("Overall status form validation failed: %s", form.errors)
    else:
        form = TestOverallStatusForm(instance=test)
    
    test_answers = test.answers.select_related('question').all() 

    context = {
        'test': test,
        'form': form,
        'test_answers': test_answers,
    }
    return render(request, 'inventory/test_detail.html', context)

@login_required
@never_cache # Added never_cache decorator
def print_test_report(request, test_id):
    # Ensure user has permission
    if request.user.role not in ['admin', 'tester', 'service']:
        return redirect('dashboard')
    
    # Fetch test and related answers
    test = get_object_or_404(Test.objects.select_related('sku', 'batch', 'barcode', 'user', 'template_used'), id=test_id)
    test_answers = test.answers.select_related('question').all()

    # Build absolute URLs for images using settings.MEDIA_URL
    # This is the most reliable way to get absolute URLs for media files
    header_url = request.build_absolute_uri(settings.MEDIA_URL + 'reports/header.png')
    footer_url = request.build_absolute_uri(settings.MEDIA_URL + 'reports/footer.png')

    context = {
        'test': test,
        'test_answers': test_answers,
        'header_url': header_url, # Pass absolute header URL to template
        'footer_url': footer_url, # Pass absolute footer URL to template
    }
    
    # Render the HTML template for the report
    template = get_template('inventory/print_test_report.html')
    html_content = template.render(context)

    # Convert HTML to PDF using WeasyPrint
    if HTML: # Check if WeasyPrint was successfully imported
        # Log the base_url to help debug if images are not found
        base_url = request.build_absolute_uri() # This is the base URL for relative paths in HTML
        logger.info(f"WeasyPrint base_url for PDF: {base_url}")
        
        try: # Added try-except block for more specific error logging
            pdf_file = HTML(string=html_content, base_url=base_url).write_pdf()
            response = HttpResponse(pdf_file, content_type='application/pdf')
            response['Content-Disposition'] = f'filename="test_report_{test.barcode.sequence_number}.pdf"'
            return response
        except Exception as e:
            logger.error(f"WeasyPrint PDF generation failed: {e}", exc_info=True) # Log full traceback
            return HttpResponse(f"Error generating PDF: {e}", status=500)
    else:
        return HttpResponse("Weasyprint is not installed. Please install it to generate PDF reports.", status=500)


@never_cache # Added never_cache decorator
def print_barcodes_pdf(request, batch_id):
    if HTML:
        batch = Batch.objects.get(id=batch_id)
        barcodes = Barcode.objects.filter(batch=batch)
        template = get_template('inventory/print_barcodes_pdf.html')
        html_content = template.render({'barcodes': barcodes, 'batch': batch})

        pdf_file = HTML(string=html_content, base_url=request.build_absolute_uri()).write_pdf()

        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'filename="barcodes_batch_{batch.prefix}.pdf"'
        return response
    else:
        return HttpResponse("Weasyprint is not installed. Please install it to generate PDF reports.", status=500)


import io
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
import barcode
from barcode.writer import ImageWriter

@never_cache
def barcode_image_view(request, sequence_number):
    buffer = io.BytesIO()
    code128 = barcode.get_barcode_class('code128')

    # Improved writer options for better scanning
    writer = ImageWriter()
    writer.format = 'PNG'  # Ensure high-quality PNG output

    options = {
        'module_width': 0.5,    # slightly thicker bars
        'module_height': 22.0,  # taller bars
        'quiet_zone': 6.5,      # extra whitespace for scanners
        'font_size': 10,        # text size (not used here)
        'text_distance': 2.0,   
        'dpi': 300,             # high print quality
        'write_text': False,    # we'll display text in template
        'background': 'white',
        'foreground': 'black'
    }

    code128(sequence_number, writer=writer).write(buffer, options)
    return HttpResponse(buffer.getvalue(), content_type='image/png')

@login_required
def session_keep_alive(request):
    """
    A view that the client-side can ping to keep the session alive.
    """
    return JsonResponse({'status': 'ok'})


# ==================== SERVICE MODULE VIEWS ====================

@login_required
@never_cache
def service_module(request):
    """Service management module landing page"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')
    return render(request, 'inventory/service_module.html')


@login_required
@never_cache
def search_serial_number(request):
    """Search for test sheet by barcode/serial number"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    test_sheet = None
    barcode = None

    if request.method == 'POST':
        serial_number = request.POST.get('serial_number', '').strip()
        if serial_number:
            # Try to find barcode by sequence number
            barcode = Barcode.objects.filter(sequence_number__icontains=serial_number).first()

            if barcode:
                # Get the most recent test for this barcode
                test_sheet = Test.objects.filter(
                    barcode=barcode
                ).order_by('-test_date').first()

    context = {
        'test_sheet': test_sheet,
        'barcode': barcode,
        'serial_number': request.POST.get('serial_number', '') if request.method == 'POST' else '',
    }
    return render(request, 'inventory/search_serial.html', context)


@login_required
@never_cache
def create_service_case(request, barcode_id=None, test_id=None):
    """Create a new service case"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    barcode = None
    test = None

    # Get barcode and test if provided
    if barcode_id:
        barcode = get_object_or_404(Barcode, id=barcode_id)
    if test_id:
        test = get_object_or_404(Test, id=test_id)

    if request.method == 'POST':
        # Get barcode and test from form data
        barcode_id_form = request.POST.get('barcode_id')
        test_id_form = request.POST.get('test_id')

        if barcode_id_form:
            barcode = get_object_or_404(Barcode, id=barcode_id_form)
        if test_id_form:
            test = get_object_or_404(Test, id=test_id_form)

        # Create service case
        service_case = ServiceCase(
            test=test,
            barcode=barcode,
            service_date=request.POST.get('service_date'),
            technician=request.user.username,
            issue_description=request.POST.get('issue_description'),
            actions_taken=request.POST.get('actions_taken'),
            remarks=request.POST.get('remarks', ''),
            status=request.POST.get('status', 'open'),
            created_by=request.user,
        )

        # Handle attachment
        if request.FILES.get('attachment'):
            service_case.attachments = request.FILES.get('attachment')

        service_case.save()

        # Log service case creation
        SystemLog.log_event(
            event_type='service_created',
            title=f'Service Case {service_case.case_id} Created',
            description=f'Service case created for barcode {barcode.sequence_number if barcode else "N/A"}',
            level='info',
            user=request.user,
            barcode=barcode,
            test=test,
            service_case=service_case,
            request=request,
            details={
                'status': service_case.status,
                'service_date': str(service_case.service_date),
                'issue_description': service_case.issue_description[:100],  # First 100 chars
            }
        )

        return redirect('service_detail', case_id=service_case.case_id)

    context = {
        'barcode': barcode,
        'test': test,
        'technicians': Technician.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'inventory/create_service_case.html', context)


@login_required
@never_cache
def service_history(request, barcode_id):
    """View service history for a specific barcode"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    barcode = get_object_or_404(Barcode, id=barcode_id)
    service_cases = ServiceCase.objects.filter(
        barcode=barcode
    ).order_by('-created_at')

    # Get most recent test for reference
    recent_test = Test.objects.filter(
        barcode=barcode
    ).order_by('-test_date').first()

    context = {
        'barcode': barcode,
        'service_cases': service_cases,
        'recent_test': recent_test,
    }
    return render(request, 'inventory/service_history.html', context)


@login_required
@never_cache
def service_list(request):
    """List all service cases with filtering options"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    service_cases = ServiceCase.objects.select_related(
        'barcode', 'test', 'created_by'
    ).all()

    # Calculate statistics (for all service cases, not filtered)
    all_service_cases = ServiceCase.objects.all()
    counts = all_service_cases.aggregate(
        total=Count('id'),
        open=Count('id', filter=Q(status='open')),
        in_progress=Count('id', filter=Q(status='in_progress')),
        completed=Count('id', filter=Q(status='completed')),
        on_hold=Count('id', filter=Q(status='on_hold')),
        cancelled=Count('id', filter=Q(status='cancelled')),
    )

    # Filter parameters
    case_id = request.GET.get('case_id')
    serial_number = request.GET.get('serial_number')
    technician = request.GET.get('technician')
    status = request.GET.get('status')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    # Barcode search - check if barcode exists and if it has service cases
    searched_barcode = None
    barcode_info = None

    if serial_number:
        # Try to find the barcode
        searched_barcode = Barcode.objects.filter(
            sequence_number__icontains=serial_number
        ).first()

        if searched_barcode:
            # Get the most recent test for this barcode
            recent_test = Test.objects.filter(
                barcode=searched_barcode
            ).order_by('-test_date').first()

            barcode_info = {
                'barcode': searched_barcode,
                'recent_test': recent_test,
                'service_case_count': service_cases.filter(barcode=searched_barcode).count()
            }

            # Filter service cases for this barcode only
            service_cases = service_cases.filter(barcode=searched_barcode)
        else:
            # Barcode not found
            service_cases = ServiceCase.objects.none()

    # Apply other filters (only if not searching by specific barcode)
    else:
        if case_id:
            service_cases = service_cases.filter(case_id__icontains=case_id)
        if technician:
            service_cases = service_cases.filter(technician__name__icontains=technician)
        if status:
            service_cases = service_cases.filter(status=status)
        if from_date:
            service_cases = service_cases.filter(service_date__gte=from_date)
        if to_date:
            service_cases = service_cases.filter(service_date__lte=to_date)

    # Order by most recent first
    service_cases = service_cases.order_by('-created_at')

    # Pagination
    paginator = Paginator(service_cases, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'case_id': case_id,
        'serial_number': serial_number,
        'technician': technician,
        'status': status,
        'from_date': from_date,
        'to_date': to_date,
        'status_choices': ServiceCase.CASE_STATUS_CHOICES,
        'searched_barcode': searched_barcode,
        'barcode_info': barcode_info,
        'counts': counts,
    }
    return render(request, 'inventory/service_list.html', context)


@login_required
@never_cache
def print_service_report(request):
    """Print service cases report as PDF"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    # Get filter parameters
    case_id = request.GET.get('case_id')
    serial_number = request.GET.get('serial_number')
    technician = request.GET.get('technician')
    status = request.GET.get('status')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    # Build queryset with filters
    service_cases = ServiceCase.objects.select_related(
        'barcode', 'test', 'created_by'
    ).all()

    if serial_number:
        searched_barcode = Barcode.objects.filter(
            sequence_number__icontains=serial_number
        ).first()
        if searched_barcode:
            service_cases = service_cases.filter(barcode=searched_barcode)
        else:
            service_cases = ServiceCase.objects.none()
    else:
        if case_id:
            service_cases = service_cases.filter(case_id__icontains=case_id)
        if technician:
            service_cases = service_cases.filter(technician__name__icontains=technician)
        if status:
            service_cases = service_cases.filter(status=status)
        if from_date:
            service_cases = service_cases.filter(service_date__gte=from_date)
        if to_date:
            service_cases = service_cases.filter(service_date__lte=to_date)

    # Order and get all results (no pagination for print)
    service_cases = service_cases.order_by('-created_at')

    # Calculate counts
    counts = service_cases.aggregate(
        total=Count('id'),
        completed=Count('id', filter=Q(status='completed')),
        in_progress=Count('id', filter=Q(status='in_progress')),
        open=Count('id', filter=Q(status='open')),
    )

    # Calculate trends (top 5 issues)
    from django.db.models.functions import Lower
    trends = list(service_cases.values(
        'issue_description'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5])

    total_for_trends = counts['total'] or 1
    for trend in trends:
        trend['percentage'] = round((trend['count'] / total_for_trends) * 100, 1)

    # Build absolute URLs for images
    header_url = request.build_absolute_uri(settings.MEDIA_URL + 'reports/header.png')
    footer_url = request.build_absolute_uri(settings.MEDIA_URL + 'reports/footer.png')

    context = {
        'service_cases': service_cases,
        'total_count': counts['total'],
        'completed_count': counts['completed'],
        'in_progress_count': counts['in_progress'],
        'open_count': counts['open'],
        'generated_at': timezone.now(),
        'filter_serial_number': serial_number,
        'filter_technician': technician,
        'filter_status': status,
        'filter_from_date': from_date,
        'filter_to_date': to_date,
        'header_url': header_url,
        'footer_url': footer_url,
        'trends': trends if trends else None,
    }

    # Render the HTML template for the report
    template = get_template('inventory/print_service_report.html')
    html_content = template.render(context)

    # Convert HTML to PDF using WeasyPrint
    if HTML:
        base_url = request.build_absolute_uri()

        try:
            pdf_file = HTML(string=html_content, base_url=base_url).write_pdf()
            response = HttpResponse(pdf_file, content_type='application/pdf')
            response['Content-Disposition'] = f'filename="service_report_{timezone.now:Y-m-d_H-i}.pdf"'
            return response
        except Exception as e:
            logger.error(f"WeasyPrint PDF generation failed: {e}", exc_info=True)
            return HttpResponse(f"Error generating PDF: {e}", status=500)
    else:
        return HttpResponse("WeasyPrint is not installed. Please install it to generate PDF reports.", status=500)


@login_required
@never_cache
def service_detail(request, case_id):
    """View and edit details of a specific service case"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    service_case = get_object_or_404(
        ServiceCase.objects.select_related('barcode', 'test', 'created_by'),
        case_id=case_id
    )

    # Check if case can be edited (not cancelled or completed)
    can_edit = service_case.status not in ['cancelled', 'completed']

    # Handle form submission for editing
    if request.method == 'POST' and can_edit:
        form = ServiceCaseForm(request.POST, request.FILES, instance=service_case)
        if form.is_valid():
            updated_case = form.save(commit=False)
            # Automatically set technician to logged-in user
            updated_case.technician = request.user.username
            updated_case.save()
            messages.success(request, f'Service case {service_case.case_id} updated successfully!')
            return redirect('service_detail', case_id=service_case.case_id)
    else:
        form = None

    # Get related service history for the same barcode
    related_cases = ServiceCase.objects.filter(
        barcode=service_case.barcode
    ).exclude(id=service_case.id).order_by('-created_at')

    context = {
        'service_case': service_case,
        'related_cases': related_cases,
        'can_edit': can_edit,
        'form': form,
    }
    return render(request, 'inventory/service_detail.html', context)


@login_required
@never_cache
def print_service_case_detail(request, case_id):
    """Print individual service case as PDF"""
    if request.user.role not in ['admin', 'service']:
        return redirect('dashboard')

    service_case = get_object_or_404(
        ServiceCase.objects.select_related('barcode', 'test', 'created_by', 'barcode__sku', 'barcode__batch'),
        case_id=case_id
    )

    # Build absolute URLs for header/footer images
    header_url = request.build_absolute_uri(settings.MEDIA_URL + 'reports/header.png')
    footer_url = request.build_absolute_uri(settings.MEDIA_URL + 'reports/footer.png')

    context = {
        'service_case': service_case,
        'header_url': header_url,
        'footer_url': footer_url,
    }

    # Generate PDF using WeasyPrint
    template = get_template('inventory/print_service_case_detail.html')
    html_content = template.render(context)

    try:
        from weasyprint import HTML
        base_url = request.build_absolute_uri()
        pdf_file = HTML(string=html_content, base_url=base_url).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'filename="service_case_{service_case.case_id}.pdf"'
        return response
    except ImportError:
        return HttpResponse("WeasyPrint is not installed. Please install it to generate PDF reports.", status=500)
    except Exception as e:
        logger.error(f"WeasyPrint PDF generation failed: {e}", exc_info=True)
        return HttpResponse(f"Error generating PDF: {e}", status=500)

