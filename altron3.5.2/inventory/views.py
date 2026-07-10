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
from datetime import timedelta


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
            
            # Log successful login
            SystemLog.log_event(
                event_type='user_login',
                title=f'User {user.username} Logged In',
                level='info',
                user=user,
                request=request
            )
            
            # Trigger 30-day log cleanup
            try:
                SystemLog.cleanup()
            except Exception as e:
                logger.error(f"Log cleanup failed: {e}")

            return redirect('dashboard')
        else:
            return render(request, 'inventory/login.html', {'error': 'Invalid credentials'})
    return render(request, 'inventory/login.html')

def user_logout(request):
    if request.user.is_authenticated:
        SystemLog.log_event(
            event_type='user_logout',
            title=f'User {request.user.username} Logged Out',
            level='info',
            user=request.user,
            request=request
        )
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
        test_id = request.POST.get('test_id')  # Check for existing draft test_id

        # Parse date filters
        from_date = request.GET.get('from_date') or request.POST.get('from_date')
        to_date = request.GET.get('to_date') or request.POST.get('to_date')
        
        # Set default values if not provided (last 30 days)
        if not to_date:
            to_date = timezone.now().date().isoformat()
        if not from_date:
            from_date = (timezone.now().date() - timedelta(days=30)).isoformat()

        form = TestForm(request.POST,
                        selected_sku_id=selected_sku_id,
                        selected_batch_id=selected_batch_id,
                        selected_template_id=selected_template_id,
                        from_date=from_date,
                        to_date=to_date)

        if form.is_valid():
            if is_ajax:
                return render(request, 'inventory/new_test.html', {
                    'form': form,
                    'from_date': from_date,
                    'to_date': to_date,
                })
            else:
                logger.debug("Form cleaned data: %s", form.cleaned_data)

                sku_instance = form.cleaned_data['sku']
                batch_instance = form.cleaned_data['batch']
                barcode_instance = form.cleaned_data['barcode']
                template_instance = form.cleaned_data['template']

                # Check if we're updating an existing test or creating new
                is_new_test = False  # Flag to track if this is a new test or update
                if test_id:
                    try:
                        # Query by id and user only - don't filter by status since we want to update regardless of current status
                        test = Test.objects.get(id=test_id, user=request.user)
                        # Store old status for logging
                        old_status = test.overall_status
                        # Update existing test
                        test.sku = sku_instance
                        test.batch = batch_instance
                        test.barcode = barcode_instance
                        test.template_used = template_instance
                        test.overall_status = form.cleaned_data['overall_status']
                        test.save()

                        # Delete old answers and recreate them
                        TestAnswer.objects.filter(test=test).delete()
                        logger.debug(f"Updated existing test {test.id}")

                        # Log status change if status changed
                        barcode_display = barcode_instance.sequence_number if barcode_instance else 'No Barcode'
                        if old_status != test.overall_status:
                            SystemLog.log_event(
                                event_type='test_status_changed',
                                title=f'Test Status Changed: {old_status.upper()} → {test.overall_status.upper()}',
                                description=f'Test for {barcode_display} (SKU: {sku_instance.code}, Batch: {batch_instance.prefix}) status changed from {old_status} to {test.overall_status}',
                                level='info',
                                user=request.user,
                                barcode=barcode_instance,
                                test=test,
                                request=request,
                                details={
                                    'old_status': old_status,
                                    'new_status': test.overall_status,
                                    'sku_code': sku_instance.code,
                                    'batch_prefix': batch_instance.prefix,
                                    'template': template_instance.name if template_instance else None,
                                }
                            )
                    except Test.DoesNotExist:
                        # Test not found, create new test instead
                        logger.warning(f"Test {test_id} not found, creating new test")
                        is_new_test = True
                        test = Test.objects.create(
                            sku=sku_instance,
                            batch=batch_instance,
                            barcode=barcode_instance,
                            user=request.user,
                            template_used=template_instance,
                            overall_status=form.cleaned_data['overall_status']
                        )
                else:
                    # Create new test
                    is_new_test = True
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

                # Log test creation (only for new tests, not updates)
                barcode_display = barcode_instance.sequence_number if barcode_instance else 'No Barcode'
                if is_new_test:
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
        # Check if resuming a draft
        resume_draft_id = request.GET.get('resume_draft')
        initial_data = {}
        resume_test = None

        if resume_draft_id:
            try:
                # Load the draft test
                resume_test = Test.objects.get(
                    id=resume_draft_id,
                    user=request.user,
                    overall_status='draft'
                )

                # Pre-fill form with draft data
                initial_data = {
                    'sku': resume_test.sku_id,
                    'batch': resume_test.batch_id,
                    'barcode': resume_test.barcode_id if resume_test.barcode else None,
                    'template': resume_test.template_used_id,
                    'overall_status': resume_test.overall_status
                }

                # Pre-fill answers
                for answer in resume_test.answers.select_related('question').all():
                    status_field_name = f'question_{answer.question_id}_status'
                    output_field_name = f'question_{answer.question_id}_output'
                    remarks_field_name = f'question_{answer.question_id}_remarks'

                    initial_data[status_field_name] = 'pass' if answer.is_passed else 'fail'
                    if answer.technical_output:
                        initial_data[output_field_name] = answer.technical_output
                    if answer.remarks:
                        initial_data[remarks_field_name] = answer.remarks

                logger.info(f"Resuming draft test {resume_draft_id}")

                # Create form with initial data AND selected template
                # The selected_template_id kwarg tells the form to load question fields
                form = TestForm(
                    initial=initial_data,
                    selected_sku_id=resume_test.sku_id,
                    selected_batch_id=resume_test.batch_id,
                    selected_template_id=resume_test.template_used_id
                )

            except Test.DoesNotExist:
                logger.warning(f"Draft test {resume_draft_id} not found")
                form = TestForm()
        else:
            form = TestForm()

        # Check for user's recent draft tests (exclude the one being resumed)
        draft_tests = Test.objects.filter(
            user=request.user,
            overall_status='draft'
        ).select_related('sku', 'batch', 'template_used').order_by('-updated_at')

        # If resuming a specific draft, exclude it from the list
        if resume_test:
            draft_tests = draft_tests.exclude(id=resume_test.id)

        draft_tests = draft_tests[:5]

        # Parse date filters for initial load
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        
        # Set default values if not provided (last 30 days)
        if not to_date:
            to_date = timezone.now().date().isoformat()
        if not from_date:
            from_date = (timezone.now().date() - timedelta(days=30)).isoformat()

        return render(request, 'inventory/new_test.html', {
            'form': form,
            'draft_tests': draft_tests,
            'resume_test_id': resume_test.id if resume_test else None,
            'from_date': from_date,
            'to_date': to_date,
        })

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

            # Log draft creation
            barcode_display = barcode_instance.sequence_number if barcode_instance else 'No Barcode'
            SystemLog.log_event(
                event_type='test_draft_created',
                title=f'Draft Test Created for {barcode_display}',
                description=f'Draft test created for {barcode_display} (SKU: {sku_instance.code}, Batch: {batch_instance.prefix})',
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
def get_test_draft(request, test_id):
    """API endpoint to fetch draft test data for resuming"""
    if request.user.role not in ['admin', 'tester']:
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

    try:
        test = Test.objects.get(id=test_id, user=request.user, overall_status='draft')

        # Serialize answers data
        answers_data = []
        for answer in test.answers.select_related('question').all():
            answers_data.append({
                'question_id': answer.question_id,
                'is_passed': answer.is_passed,
                'technical_output': answer.technical_output or '',
                'remarks': answer.remarks or ''
            })

        return JsonResponse({
            'status': 'success',
            'test_id': test.id,
            'sku_id': test.sku_id,
            'batch_id': test.batch_id,
            'template_id': test.template_used_id,
            'barcode_id': test.barcode_id or '',
            'overall_status': test.overall_status,
            'answers': answers_data
        })
    except Test.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Draft not found or cannot be accessed'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching draft: {str(e)}")
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
    overall_status = request.GET.get('overall_status')

    # Performance fix: Add select_related to prevent N+1 queries
    # Include all tests (drafts are now shown in results)
    tests = Test.objects.select_related('sku', 'batch', 'barcode', 'template_used', 'user')

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
    if overall_status:
        tests = tests.filter(overall_status=overall_status)

    tests = tests.order_by('-test_date')

    counts = tests.aggregate(
        total=Count('id'),
        passed=Count('id', filter=Q(overall_status='passed')),
        failed=Count('id', filter=Q(overall_status='failed')),
        pending=Count('id', filter=Q(overall_status='pending')),
        draft=Count('id', filter=Q(overall_status='draft'))
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
        'overall_status': overall_status,
    }
    return render(request, 'inventory/test_results.html', context)


@login_required
@never_cache # Added never_cache decorator
def test_detail(request, test_id):
    if request.user.role not in ['admin', 'tester', 'service']:
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
        manual_serial_number = request.POST.get('manual_serial_number', '').strip()
        is_legacy = False

        if manual_serial_number:
            # Try to find an existing barcode matching the entered serial
            barcode = Barcode.objects.filter(sequence_number__iexact=manual_serial_number).first()
            if barcode:
                # Found in system — link via FK, auto-fetch latest test
                test = Test.objects.filter(barcode=barcode).order_by('-test_date').first()
                is_legacy = False
            else:
                # NOT found — this is a legacy/old product
                barcode = None
                test = None
                is_legacy = True
        else:
            if barcode_id_form:
                barcode = get_object_or_404(Barcode, id=barcode_id_form)
            if test_id_form:
                test = get_object_or_404(Test, id=test_id_form)

        # Create service case
        service_case = ServiceCase(
            test=test,
            barcode=barcode,
            manual_serial_number=manual_serial_number if manual_serial_number else None,
            is_legacy=is_legacy,
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
        serial_display = barcode.sequence_number if barcode else (manual_serial_number or 'N/A')
        SystemLog.log_event(
            event_type='service_created',
            title=f'Service Case {service_case.case_id} Created',
            description=f'Service case created for {"legacy " if is_legacy else ""}barcode {serial_display}',
            level='info',
            user=request.user,
            barcode=barcode,
            test=test,
            service_case=service_case,
            request=request,
            details={
                'status': service_case.status,
                'service_date': str(service_case.service_date),
                'issue_description': service_case.issue_description[:100],
                'is_legacy': is_legacy,
                'manual_serial_number': manual_serial_number or None,
            }
        )

        messages.success(request, f'Service case {service_case.case_id} created successfully!')
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
    legacy_info = None

    if serial_number:
        # Try to find the barcode in the system
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

            # Filter: system barcode match OR legacy manual_serial_number match
            service_cases = service_cases.filter(
                Q(barcode=searched_barcode) | Q(manual_serial_number__icontains=serial_number)
            )
        else:
            # Barcode not found in system — search legacy cases by manual_serial_number
            legacy_cases = service_cases.filter(manual_serial_number__icontains=serial_number)
            if legacy_cases.exists():
                service_cases = legacy_cases
                legacy_info = {
                    'serial_number': serial_number,
                    'service_case_count': legacy_cases.count(),
                    'first_case_date': legacy_cases.order_by('created_at').first().created_at,
                }
            else:
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
        'legacy_info': legacy_info,
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

            # Log service case update
            SystemLog.log_event(
                event_type='service_updated',
                title=f'Service Case {service_case.case_id} Updated',
                description=f'Status updated to: {service_case.get_status_display()}',
                level='info',
                user=request.user,
                service_case=service_case,
                request=request,
                details={'status': service_case.status}
            )

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

@login_required
def reorder_questions(request, template_id):
    """View to handle drag-and-drop reordering of questions within a template"""
    if request.user.role != 'admin':
        return redirect('dashboard')
        
    template = get_object_or_404(TestTemplate, id=template_id)
    
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
            ordered_ids = data.get('ordered_ids', [])
            
            # Bulk update orders
            for i, question_id in enumerate(ordered_ids):
                TestQuestion.objects.filter(id=question_id, template=template).update(order=i)
            
            # Log the action
            SystemLog.log_event(
                event_type='template_managed',
                title=f'Question Order Updated',
                description=f'Questions reordered for template "{template.name}".',
                level='info',
                user=request.user,
                request=request
            )
            
            return HttpResponse(json.dumps({'status': 'success'}), content_type='application/json')
        except Exception as e:
            return HttpResponse(json.dumps({'status': 'error', 'message': str(e)}), status=400, content_type='application/json')
            
    questions = template.questions.all().order_by('order', 'id')
    return render(request, 'inventory/reorder_questions.html', {
        'template': template,
        'questions': questions
    })


@login_required
@never_cache
def soluqis_bi(request):
    """Business Intelligence Dashboard for Quality and Service operations"""
    if request.user.role not in ['admin', 'service', 'tester']:
        return redirect('dashboard')

    from django.db.models import Count, Q, Min, OuterRef, Subquery, F, Sum
    from django.db.models.functions import TruncDate
    from django.utils import timezone
    from datetime import datetime, timedelta
    import json

    # --- Global Parameter: Date Filtering ---
    today_dt = timezone.now()
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')
    label = request.GET.get('label', '30days')

    # Defaults
    to_date = today_dt.date()
    from_date = (today_dt - timedelta(days=30)).date()

    if label == 'today':
        from_date = today_dt.date()
        to_date = today_dt.date()
    elif label == '7days':
        from_date = (today_dt - timedelta(days=7)).date()
        to_date = today_dt.date()
    elif label == '30days':
        from_date = (today_dt - timedelta(days=30)).date()
        to_date = today_dt.date()
    elif label == 'thismonth':
        from_date = today_dt.date().replace(day=1)
        to_date = today_dt.date()
    elif from_date_str and to_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            label = 'custom'
        except ValueError:
            pass  # Fallback to default 30 days

    # Make aware datetimes for database filtering
    from_datetime = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
    to_datetime = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))

    # --- 1. Production & Throughput Metrics ---
    production_kpi = Batch.objects.filter(
        created_at__range=(from_datetime, to_datetime)
    ).aggregate(
        total_barcodes=Sum('quantity'),
        total_batches=Count('id')
    )
    total_barcodes = production_kpi['total_barcodes'] or 0
    total_batches = production_kpi['total_batches'] or 0

    # --- 2. Quality Control & Testing Metrics ---
    counts = Test.objects.filter(
        test_date__range=(from_datetime, to_datetime)
    ).aggregate(
        total_tests=Count('id'),
        passed_tests=Count('id', filter=Q(overall_status='passed')),
        failed_tests=Count('id', filter=Q(overall_status='failed')),
        pending_tests=Count('id', filter=Q(overall_status='pending'))
    )
    total_tests = counts['total_tests'] or 0
    passed_tests = counts['passed_tests'] or 0
    failed_tests = counts['failed_tests'] or 0
    pending_tests = counts['pending_tests'] or 0
    
    qa_pass_rate = round((passed_tests / (passed_tests + failed_tests) * 100), 1) if (passed_tests + failed_tests) > 0 else 0.0

    # First Pass Yield (FPY)
    first_test_id_sub = Test.objects.filter(barcode=OuterRef('id')).order_by('id').values('id')[:1]
    
    barcodes_with_first_test = Barcode.objects.annotate(
        first_test_status=Subquery(
            Test.objects.filter(id=Subquery(first_test_id_sub), test_date__range=(from_datetime, to_datetime)).values('overall_status')[:1]
        )
    ).filter(first_test_status__isnull=False)

    fpy_total_tested = barcodes_with_first_test.count()
    fpy_first_pass_passed = barcodes_with_first_test.filter(first_test_status='passed').count()
    overall_fpy = round((fpy_first_pass_passed / fpy_total_tested * 100), 1) if fpy_total_tested > 0 else 0.0

    # FPY by SKU
    sku_fpy_data = []
    for sku_obj in SKU.objects.all():
        tested_in_sku = barcodes_with_first_test.filter(sku=sku_obj)
        tested_count = tested_in_sku.count()
        if tested_count > 0:
            passed_first_count = tested_in_sku.filter(first_test_status='passed').count()
            sku_fpy = round((passed_first_count / tested_count * 100), 1)
            sku_fpy_data.append({
                'code': sku_obj.code,
                'description': sku_obj.description or sku_obj.code,
                'tested': tested_count,
                'passed_first': passed_first_count,
                'fpy': sku_fpy
            })
    sku_fpy_data = sorted(sku_fpy_data, key=lambda x: x['fpy'], reverse=True)

    # Top Failure Modes (Pareto Data)
    top_failures = TestAnswer.objects.filter(
        is_passed=False,
        test__test_date__range=(from_datetime, to_datetime)
    ).values(
        'question__question_text', 'question__template__name'
    ).annotate(
        fail_count=Count('id')
    ).order_by('-fail_count')[:7]

    pareto_labels = []
    pareto_data = []
    for item in top_failures:
        lbl = f"{item['question__question_text']} ({item['question__template__name']})"
        pareto_labels.append(lbl)
        pareto_data.append(item['fail_count'])

    # Daily Test Velocity
    daily_tests = Test.objects.filter(
        test_date__range=(from_datetime, to_datetime)
    ).annotate(
        day=TruncDate('test_date')
    ).values('day').annotate(
        passed=Count('id', filter=Q(overall_status='passed')),
        failed=Count('id', filter=Q(overall_status='failed'))
    ).order_by('day')

    velocity_dates = []
    velocity_passed = []
    velocity_failed = []
    for row in daily_tests:
        if row['day']:
            velocity_dates.append(row['day'].strftime('%Y-%m-%d'))
            velocity_passed.append(row['passed'])
            velocity_failed.append(row['failed'])

    # --- 3. Service & Field Quality Metrics ---
    service_counts = ServiceCase.objects.filter(
        created_at__range=(from_datetime, to_datetime)
    ).aggregate(
        total_cases=Count('id'),
        open_cases=Count('id', filter=Q(status='open')),
        in_progress_cases=Count('id', filter=Q(status='in_progress')),
        completed_cases=Count('id', filter=Q(status='completed'))
    )
    total_service = service_counts['total_cases'] or 0
    open_service = service_counts['open_cases'] or 0
    in_progress_service = service_counts['in_progress_cases'] or 0
    completed_service = service_counts['completed_cases'] or 0

    # Field Failure Rate (Quality Leakage) %
    total_barcodes_tested = Test.objects.filter(
        test_date__range=(from_datetime, to_datetime)
    ).values('barcode').distinct().count()

    total_barcodes_serviced = ServiceCase.objects.filter(
        created_at__range=(from_datetime, to_datetime),
        barcode__isnull=False
    ).values('barcode').distinct().count()

    field_failure_rate = round((total_barcodes_serviced / total_barcodes_tested * 100), 1) if total_barcodes_tested > 0 else 0.0

    # Service Escalations by Batch (Quality Leakage)
    service_leakage = ServiceCase.objects.filter(
        created_at__range=(from_datetime, to_datetime)
    ).values(
        'barcode__batch__prefix', 'barcode__batch__sku__code'
    ).annotate(
        service_count=Count('id')
    ).order_by('-service_count')[:5]

    leakage_batches = []
    leakage_counts = []
    for item in service_leakage:
        if item['barcode__batch__prefix']:
            leakage_batches.append(f"{item['barcode__batch__prefix']} ({item['barcode__batch__sku__code']})")
            leakage_counts.append(item['service_count'])

    # === STAFF PERFORMANCE ANALYSIS ===
    # 1. Tester Performance
    tester_stats = Test.objects.filter(
        test_date__range=(from_datetime, to_datetime)
    ).values('user__username', 'user__role').annotate(
        total_tests=Count('id'),
        passed_tests=Count('id', filter=Q(overall_status='passed')),
        failed_tests=Count('id', filter=Q(overall_status='failed'))
    ).order_by('-total_tests')

    tester_data = []
    for t in tester_stats:
        total = t['total_tests']
        passed = t['passed_tests']
        rate = round((passed / total * 100), 1) if total > 0 else 0.0
        tester_data.append({
            'username': t['user__username'],
            'role': t['user__role'],
            'total': total,
            'passed': passed,
            'failed': t['failed_tests'],
            'pass_rate': rate
        })

    # 2. Technician Performance
    tech_stats = ServiceCase.objects.filter(
        created_at__range=(from_datetime, to_datetime)
    ).values('technician').annotate(
        total_cases=Count('id'),
        completed_cases=Count('id', filter=Q(status='completed'))
    ).order_by('-total_cases')

    tech_data = []
    for tc in tech_stats:
        total = tc['total_cases']
        completed = tc['completed_cases']
        rate = round((completed / total * 100), 1) if total > 0 else 0.0
        tech_data.append({
            'name': tc['technician'] or 'Unassigned',
            'total': total,
            'completed': completed,
            'rate': rate
        })

    # === PRODUCT PERFORMANCE ANALYSIS ===
    # 3. SKU Performance (Yield & returns)
    sku_data = []
    for sku in SKU.objects.all():
        sku_tests = Test.objects.filter(sku=sku, test_date__range=(from_datetime, to_datetime))
        total_t = sku_tests.count()
        sku_services = ServiceCase.objects.filter(barcode__sku=sku, created_at__range=(from_datetime, to_datetime))
        total_s = sku_services.count()

        if total_t > 0 or total_s > 0:
            sku_barcodes_fpy = barcodes_with_first_test.filter(sku=sku)
            sku_fpy_tested = sku_barcodes_fpy.count()
            sku_fpy_passed = sku_barcodes_fpy.filter(first_test_status='passed').count()
            sku_fpy = round((sku_fpy_passed / sku_fpy_tested * 100), 1) if sku_fpy_tested > 0 else 0.0

            passed_t = sku_tests.filter(overall_status='passed').count()
            pass_rate = round((passed_t / total_t * 100), 1) if total_t > 0 else 0.0

            sku_data.append({
                'code': sku.code,
                'description': sku.description or sku.code,
                'total_tests': total_t,
                'pass_rate': pass_rate,
                'fpy': sku_fpy,
                'returns': total_s
            })
    sku_data = sorted(sku_data, key=lambda x: x['fpy'])

    # 4. Batch Performance (Yield, coverage, and returns)
    batch_data = []
    batches_in_period = Batch.objects.filter(
        created_at__range=(from_datetime, to_datetime)
    ).select_related('sku').annotate(
        tested_count=Count('barcode__test', distinct=True),
        return_count=Count('barcode__service_cases', distinct=True)
    )
    for batch in batches_in_period:
        if batch.quantity > 0:
            coverage = round((batch.tested_count / batch.quantity * 100), 1)
            
            batch_barcodes_fpy = barcodes_with_first_test.filter(batch=batch)
            batch_fpy_tested = batch_barcodes_fpy.count()
            batch_fpy_passed = batch_barcodes_fpy.filter(first_test_status='passed').count()
            batch_fpy = round((batch_fpy_passed / batch_fpy_tested * 100), 1) if batch_fpy_tested > 0 else 0.0

            batch_data.append({
                'prefix': batch.prefix,
                'sku_code': batch.sku.code,
                'total': batch.quantity,
                'tested': batch.tested_count,
                'coverage': coverage,
                'fpy': batch_fpy,
                'returns': batch.return_count
            })
    batch_data = sorted(batch_data, key=lambda x: x['coverage'])[:10]

    # --- 4. Exception & Alert Dashboard Data ---
    # Stale Drafts (tests in draft > 24 hours)
    stale_drafts = Test.objects.filter(
        overall_status='draft',
        updated_at__lt=timezone.now() - timedelta(hours=24)
    ).select_related('sku', 'batch', 'barcode', 'user').order_by('-updated_at')[:5]

    # SLA Breaches (service cases open > 7 days)
    sla_breaches = ServiceCase.objects.filter(
        status__in=['open', 'in_progress'],
        created_at__lt=timezone.now() - timedelta(days=7)
    ).select_related('barcode', 'barcode__sku').order_by('created_at')[:5]

    # Low Coverage Batches in period (tested < 50% of quantity)
    low_coverage_batches = []
    batches_with_test_counts = Batch.objects.filter(
        created_at__range=(from_datetime, to_datetime)
    ).select_related('sku').annotate(
        tested_count=Count('barcode__test', distinct=True)
    )
    for batch in batches_with_test_counts:
        if batch.quantity > 0:
            coverage = (batch.tested_count / batch.quantity)
            if coverage < 0.50:
                low_coverage_batches.append({
                    'id': batch.id,
                    'prefix': batch.prefix,
                    'sku_code': batch.sku.code,
                    'tested': batch.tested_count,
                    'total': batch.quantity,
                    'coverage_pct': round(coverage * 100, 1)
                })
    low_coverage_batches = sorted(low_coverage_batches, key=lambda x: x['coverage_pct'])[:5]

    # High Failure Rate SKUs in period (>10% fail rate on at least 5 tests)
    high_failure_skus = []
    for sku in SKU.objects.all():
        tests_in_period = Test.objects.filter(sku=sku, test_date__range=(from_datetime, to_datetime))
        total = tests_in_period.count()
        if total >= 5:
            failed = tests_in_period.filter(overall_status='failed').count()
            fail_rate = (failed / total * 100)
            if fail_rate > 10.0:
                high_failure_skus.append({
                    'code': sku.code,
                    'description': sku.description or sku.code,
                    'total_tests': total,
                    'failed_tests': failed,
                    'failure_rate': round(fail_rate, 1)
                })
    high_failure_skus = sorted(high_failure_skus, key=lambda x: x['failure_rate'], reverse=True)[:5]

    context = {
        # Date Filters
        'from_date': from_date.strftime('%Y-%m-%d'),
        'to_date': to_date.strftime('%Y-%m-%d'),
        'label': label,
        # Production & QA KPIs
        'total_barcodes': total_barcodes,
        'total_batches': total_batches,
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'pending_tests': pending_tests,
        'qa_pass_rate': qa_pass_rate,
        'overall_fpy': overall_fpy,
        'sku_fpy_data': sku_fpy_data,
        'pareto_labels_json': json.dumps(pareto_labels),
        'pareto_data_json': json.dumps(pareto_data),
        'velocity_dates_json': json.dumps(velocity_dates),
        'velocity_passed_json': json.dumps(velocity_passed),
        'velocity_failed_json': json.dumps(velocity_failed),
        # Service & Field KPIs
        'total_service': total_service,
        'open_service': open_service,
        'in_progress_service': in_progress_service,
        'completed_service': completed_service,
        'field_failure_rate': field_failure_rate,
        'leakage_batches_json': json.dumps(leakage_batches),
        'leakage_counts_json': json.dumps(leakage_counts),
        # Exceptions & Alerts KPIs
        'stale_drafts': stale_drafts,
        'sla_breaches': sla_breaches,
        'low_coverage_batches': low_coverage_batches,
        'high_failure_skus': high_failure_skus,
        # Staff & Product details
        'tester_data': tester_data,
        'tech_data': tech_data,
        'sku_data': sku_data,
        'batch_data': batch_data,
    }
    return render(request, 'inventory/soluqis_bi.html', context)

