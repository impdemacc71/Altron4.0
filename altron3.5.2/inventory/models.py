import string
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
# from .utils import generate_barcode # Assuming this is not strictly needed for model definition

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('batch', 'Batch Generation'),
        ('tester', 'Tester'),
        ('service', 'Service'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tester')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class SKU(models.Model):
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code

def increment_suffix(suffix: str) -> str:
    """
    Increment suffix like:
    A001 ... A999 -> B001 ... Z999 -> AA001 ... ZZ999 -> AAA001 ...
    """
    letters = suffix[:-3]
    number = int(suffix[-3:])

    if number < 999:
        return f"{letters}{str(number + 1).zfill(3)}"

    # Number reached 999, increment letters part
    letters_list = list(letters)
    i = len(letters_list) - 1
    while i >= 0:
        if letters_list[i] == 'Z':
            letters_list[i] = 'A'
            i -= 1
        else:
            letters_list[i] = chr(ord(letters_list[i]) + 1)
            break
    else:
        # All letters were 'Z', add another 'A' at the front
        letters_list.insert(0, 'A')

    new_letters = "".join(letters_list)
    return f"{new_letters}001"

class BatchSpecTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True) # e.g., SOLAR PCU, MPPT, LI-UPS
    # Stores a list of required field names: ["battery", "capacity", "mppt_cap"]
    # Corresponds to field names on the Batch model
    fields_json = models.JSONField(default=list) 
    
    def __str__(self):
        return self.name

class Batch(models.Model):
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE)
    prefix = models.CharField(max_length=20)  # keep this field, auto-set to sku.code
    batch_date = models.DateField(default=timezone.now)
    quantity = models.PositiveIntegerField()
    device_name = models.CharField(max_length=100, blank=True, null=True) # <-- ADDED null=True    battery = models.CharField(max_length=100, blank=True)
    capacity = models.CharField(max_length=50, blank=True)
    mppt_cap = models.CharField(max_length=50, blank=True, null=True)
    voc_max = models.CharField(max_length=50, blank=True, null=True)
    feature_spec = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ef = models.CharField(max_length=50, null=True, blank=True)
    battery = models.CharField(max_length=100, blank=True, null=True)
    # NEW FIELDS BASED ON PDF TEMPLATES:
    input_range = models.CharField(max_length=50, blank=True, null=True)        # Used in LI-UPS [cite: 12]
    output_range = models.CharField(max_length=50, blank=True, null=True)       # Used in LI-UPS [cite: 12]
    current_max = models.CharField(max_length=50, blank=True, null=True)        # Used in BATTERY CHARGER [cite: 8]
    
    system_cap = models.CharField(max_length=50, blank=True, null=True)         # SYSTEM Cap [cite: 4, 9, 12]
    spv_max = models.CharField(max_length=50, blank=True, null=True)            # SPV Max [cite: 4]
    dc_load = models.CharField(max_length=50, blank=True, null=True)            # DC LOAD [cite: 2]
    kel_po = models.CharField(max_length=50, blank=True, null=True)             # KEL-PO [cite: 13]

    # Dynamic Template Link
    spec_template = models.ForeignKey(BatchSpecTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prefix} - {self.batch_date}"

    def save(self, *args, **kwargs):
        # Auto-set prefix from SKU code before saving
        self.prefix = self.sku.code

        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            last_barcode = (
                Barcode.objects
                .filter(sequence_number__startswith=self.prefix)
                .order_by('-sequence_number')
                .first()
            )
            if last_barcode:
                last_suffix = last_barcode.sequence_number.replace(self.prefix, '')
                if len(last_suffix) < 4:
                    last_suffix = None
            else:
                last_suffix = None

            next_suffix = "A001" if not last_suffix else increment_suffix(last_suffix)

            barcodes = []
            for _ in range(self.quantity):
                full_code = f"{self.prefix}{next_suffix}"
                barcodes.append(
                    Barcode(
                        batch=self,
                        sku=self.sku,
                        sequence_number=full_code,
                        #barcode_image=generate_barcode(full_code)
                    )
                )
                next_suffix = increment_suffix(next_suffix)

            Barcode.objects.bulk_create(barcodes)


class Barcode(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE)
    sequence_number = models.CharField(max_length=30, unique=True)
    #barcode_image = models.ImageField(upload_to='barcodes/', blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['sequence_number']),
            models.Index(fields=['batch']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return self.sequence_number

class TestTemplate(models.Model): # NEW MODEL
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class TestQuestion(models.Model):
    # Changed from batch to template
    template = models.ForeignKey(TestTemplate, on_delete=models.CASCADE, related_name='questions',null=True, blank=True)
    question_text = models.CharField(max_length=255)
    # Map specific technical outputs to this question
    technical_outputs = models.ManyToManyField('TechnicalOutputChoice', blank=True, related_name='questions')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Updated string representation to reflect the change
        return f"Template: {self.template.name} - {self.question_text}"

class Test(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
    )
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE)
    barcode = models.ForeignKey(Barcode, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    template_used = models.ForeignKey(TestTemplate, on_delete=models.SET_NULL, null=True, blank=True) # NEW FIELD to record which template was used
    overall_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    test_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['overall_status']),
            models.Index(fields=['test_date']),
            models.Index(fields=['sku', 'batch']),
            models.Index(fields=['-test_date']),  # For ordering
        ]

    def __str__(self):
        return f"Test {self.id} - {self.barcode.sequence_number} ({self.overall_status})"

class TestAnswer(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE)
    is_passed = models.BooleanField(default=False)
    technical_output = models.CharField(max_length=50, blank=True, null=True)
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"{self.test} - {self.question} ({'Passed' if self.is_passed else 'Failed'})"

class TechnicalOutputChoice(models.Model):
    value = models.CharField(max_length=50, unique=True, help_text="e.g., 200W, 1700W, 300A")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0) # For custom sorting

    class Meta:
        ordering = ['order', 'value']

    def __str__(self):
        return self.value


class Technician(models.Model):
    """Master model for service technicians"""
    name = models.CharField(max_length=100, unique=True, help_text="Full name of the technician")
    employee_id = models.CharField(max_length=50, blank=True, null=True, help_text="Employee ID (optional)")
    is_active = models.BooleanField(default=True, help_text="Whether this technician is active")
    contact_number = models.CharField(max_length=20, blank=True, null=True, help_text="Contact number (optional)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Technician"
        verbose_name_plural = "Technicians"

    def __str__(self):
        return self.name


class ServiceCase(models.Model):
    """Service case for tracking product service operations"""
    CASE_STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
    ]

    # Link to test/barcode
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_cases', help_text="Reference to the original test record")
    barcode = models.ForeignKey(Barcode, on_delete=models.SET_NULL, null=True, blank=True, related_name='service_cases', help_text="Barcode being serviced")

    # Service identification
    case_id = models.CharField(max_length=20, unique=True, editable=False, help_text="Unique service case identifier (e.g., SVC-2025-0001)")

    # Service details
    service_date = models.DateField(help_text="Date when service was performed")
    technician = models.ForeignKey(Technician, on_delete=models.PROTECT, null=True, blank=True, help_text="Service technician assigned to this case")

    # Issue and action tracking
    issue_description = models.TextField(help_text="Description of the issue reported")
    actions_taken = models.TextField(help_text="Actions taken during service")
    remarks = models.TextField(blank=True, help_text="Additional notes or remarks")

    # Status tracking
    status = models.CharField(max_length=20, choices=CASE_STATUS_CHOICES, default='open', help_text="Current status of the service case")

    # Attachments
    attachments = models.FileField(upload_to='service_attachments/%Y/%m/', blank=True, null=True, help_text="Service photos, test reports, or other attachments")

    # Spare parts tracking (optional JSON field for flexibility)
    spare_parts_used = models.JSONField(blank=True, null=True, help_text="JSON field to store spare parts details")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_service_cases')

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Service Case"
        indexes = [
            models.Index(fields=['case_id']),
            models.Index(fields=['barcode']),
            models.Index(fields=['status']),
            models.Index(fields=['service_date']),
            models.Index(fields=['technician']),
            models.Index(fields=['-created_at']),  # Already ordering by this
        ]
        verbose_name_plural = "Service Cases"

    def __str__(self):
        return f"{self.case_id} - {self.barcode.sequence_number if self.barcode else 'No Barcode'}"

    def save(self, *args, **kwargs):
        # Auto-generate case ID if not provided
        if not self.case_id:
            # Get current year and count of cases this year
            from django.utils import timezone
            import datetime
            current_year = datetime.datetime.now().year
            year_count = ServiceCase.objects.filter(case_id__startswith=f'SVC-{current_year}-').count()
            self.case_id = f'SVC-{current_year}-{year_count + 1:04d}'
        super().save(*args, **kwargs)


class SystemLog(models.Model):
    """System event logging for issue analysis and tracking"""
    LOG_LEVEL_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    EVENT_TYPE_CHOICES = [
        ('test_failed', 'Test Failed'),
        ('test_passed', 'Test Passed'),
        ('service_created', 'Service Case Created'),
        ('service_updated', 'Service Case Updated'),
        ('service_completed', 'Service Case Completed'),
        ('batch_created', 'Batch Created'),
        ('user_login', 'User Login'),
        ('user_logout', 'User Logout'),
        ('system_error', 'System Error'),
        ('validation_error', 'Validation Error'),
        ('performance_issue', 'Performance Issue'),
        ('other', 'Other'),
    ]

    # Event details
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES, db_index=True, help_text="Type of event")
    level = models.CharField(max_length=20, choices=LOG_LEVEL_CHOICES, default='info', db_index=True, help_text="Log level")

    # Related objects (optional)
    barcode = models.ForeignKey(Barcode, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs', help_text="Related barcode if applicable")
    test = models.ForeignKey(Test, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs', help_text="Related test if applicable")
    service_case = models.ForeignKey(ServiceCase, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs', help_text="Related service case if applicable")
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs', help_text="Related batch if applicable")

    # User who triggered the event
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs', help_text="User who triggered the event")

    # Event information
    title = models.CharField(max_length=255, db_index=True, help_text="Brief title of the event")
    description = models.TextField(blank=True, help_text="Detailed description of the event")

    # Technical details (JSON for flexibility)
    details = models.JSONField(blank=True, null=True, help_text="Additional technical details as JSON")

    # Metadata
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, help_text="When the event occurred")
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="IP address of the user")
    user_agent = models.TextField(blank=True, help_text="Browser/user agent information")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "System Log"
        verbose_name_plural = "System Logs"
        indexes = [
            models.Index(fields=['event_type', 'level']),
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['barcode', '-timestamp']),
            models.Index(fields=['test', '-timestamp']),
            models.Index(fields=['service_case', '-timestamp']),
        ]

    def __str__(self):
        return f"[{self.level.upper()}] {self.event_type} - {self.title}"

    @classmethod
    def log_event(cls, event_type, title, description="", level='info', user=None, barcode=None, test=None, service_case=None, batch=None, details=None, request=None):
        """
        Utility method to create log entries

        Usage:
            SystemLog.log_event(
                event_type='test_failed',
                title='Test failed for barcode ABC123',
                description='Multiple test questions failed',
                level='warning',
                user=request.user,
                test=test_obj,
                request=request
            )
        """
        log_entry = cls(
            event_type=event_type,
            title=title,
            description=description,
            level=level,
            user=user,
            barcode=barcode,
            test=test,
            service_case=service_case,
            batch=batch,
            details=details or {},
        )

        # Capture request metadata if available
        if request:
            # Get IP address from request
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                log_entry.ip_address = x_forwarded_for.split(',')[0]
            else:
                log_entry.ip_address = request.META.get('REMOTE_ADDR')

            # Get user agent
            log_entry.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]  # Limit to 500 chars

        log_entry.save()
        return log_entry

