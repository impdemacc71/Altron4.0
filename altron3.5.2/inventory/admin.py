from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import CustomUser, SKU, Batch, Barcode, TestQuestion, Test, TestAnswer, TestTemplate, TechnicalOutputChoice, BatchSpecTemplate, ServiceCase, Technician, SystemLog # Import ALL Models

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'role', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role',)}),
    )

# 💡 NEW ADMIN: Batch Spec Template
@admin.register(BatchSpecTemplate)
class BatchSpecTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'display_fields')
    search_fields = ('name',)
    
    # Method to display the fields_json contents clearly
    def display_fields(self, obj):
        return ", ".join(obj.fields_json)
    display_fields.short_description = 'Required Specs'


class TestQuestionAdmin(admin.ModelAdmin):
    # Display the template and question text
    list_display = ['template', 'question_text', 'created_at']
    # Filter by template
    list_filter = ['template', 'technical_outputs']
    # Search by question text and template name
    search_fields = ['question_text', 'template__name']
    # Use filter_horizontal for many-to-many field
    filter_horizontal = ['technical_outputs']


class TestAnswerInline(admin.TabularInline):
    model = TestAnswer
    extra = 0
    # Only show first 20 to prevent page crashes
    # Users can view/edit all answers via the "View All Answers" button
    max_num = 20
    show_full_result_count = False

class TestAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'sku', 'batch', 'template_used', 'overall_status', 'test_date', 'user', 'view_answers_button']
    list_filter = ['overall_status', 'test_date', 'sku', 'batch', 'template_used']
    search_fields = ['barcode__sequence_number']
    inlines = [TestAnswerInline]

    def view_answers_button(self, obj):
        """Add a button to view all answers in a separate paginated page"""
        from django.urls import reverse
        url = reverse('admin:inventory_testanswer_changelist') + f'?test__id__exact={obj.id}'
        return format_html('<a href="{}" class="button" style="background-color: #417690; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px;">View All Answers ({})</a>', url, obj.answers.count())
    view_answers_button.short_description = 'Test Answers'

class BatchAdmin(admin.ModelAdmin):
    list_display = ['sku', 'prefix', 'batch_date', 'quantity', 'spec_template', 'created_at'] # Added spec_template
    list_filter = ['sku', 'batch_date', 'spec_template'] # Added spec_template
    search_fields = ['prefix']
    ordering = ['-created_at']

class BarcodeAdmin(admin.ModelAdmin):
    list_display = ['sequence_number', 'batch']
    list_filter = ['batch__sku']
    search_fields = ['sequence_number']

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(SKU)
admin.site.register(Batch, BatchAdmin)
admin.site.register(Barcode, BarcodeAdmin)
admin.site.register(TestTemplate)
admin.site.register(TestQuestion, TestQuestionAdmin)
admin.site.register(Test, TestAdmin)
# TestAnswer Admin with search and filter capabilities
@admin.register(TestAnswer)
class TestAnswerAdmin(admin.ModelAdmin):
    list_display = ['test', 'question', 'is_passed', 'technical_output', 'remarks_preview']
    list_filter = ['is_passed', 'test__template_used', 'test__overall_status', 'question']
    search_fields = ['question__question_text', 'technical_output', 'remarks', 'test__barcode__sequence_number']
    readonly_fields = ['test']
    list_select_related = ['test', 'question']  # Optimize queries

    def remarks_preview(self, obj):
        """Show preview of remarks (first 100 chars)"""
        if obj.remarks:
            return obj.remarks[:100] + '...' if len(obj.remarks) > 100 else obj.remarks
        return '-'
    remarks_preview.short_description = 'Remarks'


# 💡 Existing Admin for Technical Output Choices
@admin.register(TechnicalOutputChoice)
class TechnicalOutputChoiceAdmin(admin.ModelAdmin):
    list_display = ('value', 'is_active', 'order')
    list_editable = ('is_active', 'order')
    search_fields = ('value',)


# 💡 Technician Admin
@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ['name', 'employee_id', 'is_active', 'contact_number', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'employee_id']
    list_editable = ['is_active']
    ordering = ['name']


# 💡 Service Case Admin
@admin.register(ServiceCase)
class ServiceCaseAdmin(admin.ModelAdmin):
    list_display = ['case_id', 'barcode', 'status', 'service_date', 'technician', 'created_at']
    list_filter = ['status', 'service_date', 'technician', 'created_at']
    search_fields = ['case_id', 'barcode__sequence_number', 'technician__name', 'issue_description']
    readonly_fields = ['case_id', 'created_at', 'updated_at']
    date_hierarchy = 'service_date'
    ordering = ['-created_at']

    fieldsets = (
        ('Service Identification', {
            'fields': ('case_id', 'test', 'barcode', 'service_date', 'technician')
        }),
        ('Issue & Actions', {
            'fields': ('status', 'issue_description', 'actions_taken', 'remarks')
        }),
        ('Attachments & Parts', {
            'fields': ('attachments', 'spare_parts_used')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )


# 💡 System Log Admin
@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'event_type_badge', 'level_badge', 'title', 'user', 'barcode_link', 'test_link', 'service_case_link']
    list_filter = ['event_type', 'level', 'timestamp', 'user']
    search_fields = ['title', 'description', 'barcode__sequence_number', 'test__barcode__sequence_number', 'service_case__case_id', 'user__username']
    readonly_fields = ['timestamp', 'event_type', 'level', 'title', 'description', 'details', 'user', 'barcode', 'test', 'service_case', 'batch', 'ip_address', 'user_agent']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']

    fieldsets = (
        ('Event Information', {
            'fields': ('timestamp', 'event_type', 'level', 'title', 'description')
        }),
        ('Related Objects', {
            'fields': ('user', 'barcode', 'test', 'service_case', 'batch')
        }),
        ('Technical Details', {
            'fields': ('details', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        # Logs should only be created programmatically
        return False

    def has_change_permission(self, request, obj=None):
        # Logs should be read-only
        return False

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete logs
        return request.user.is_superuser

    def event_type_badge(self, obj):
        colors = {
            'test_failed': 'red',
            'test_passed': 'green',
            'service_created': 'blue',
            'service_updated': 'yellow',
            'service_completed': 'green',
            'batch_created': 'purple',
            'user_login': 'gray',
            'user_logout': 'gray',
            'system_error': 'red',
            'validation_error': 'orange',
            'performance_issue': 'orange',
            'other': 'gray',
        }
        color = colors.get(obj.event_type, 'gray')
        return format_html('<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 10px; font-size: 11px;">{}</span>', color, obj.get_event_type_display())
    event_type_badge.short_description = 'Event Type'

    def level_badge(self, obj):
        colors = {
            'info': 'blue',
            'warning': 'orange',
            'error': 'red',
            'critical': 'darkred',
        }
        color = colors.get(obj.level, 'gray')
        return format_html('<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 10px; font-size: 11px;">{}</span>', color, obj.get_level_display().upper())
    level_badge.short_description = 'Level'

    def barcode_link(self, obj):
        if obj.barcode:
            return format_html('<a href="/admin/inventory/barcode/{}/change/" target="_blank">{}</a>', obj.barcode.pk, obj.barcode.sequence_number)
        return '-'
    barcode_link.short_description = 'Barcode'

    def test_link(self, obj):
        if obj.test:
            return format_html('<a href="/admin/inventory/test/{}/change/" target="_blank">Test #{}</a>', obj.test.pk, obj.test.pk)
        return '-'
    test_link.short_description = 'Test'

    def service_case_link(self, obj):
        if obj.service_case:
            return format_html('<a href="/admin/inventory/servicecase/{}/change/" target="_blank">{}</a>', obj.service_case.pk, obj.service_case.case_id)
        return '-'
    service_case_link.short_description = 'Service Case'

