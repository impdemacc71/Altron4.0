# Role-Based Access Control (RBAC) Implementation

## User Roles and Permissions

### 1. **Admin**
- **Access**: All modules and features
- **Can Do**:
  - ✅ Create batches
  - ✅ Generate barcodes
  - ✅ View batch list
  - ✅ Product testing (all operations)
  - ✅ Service cases (all operations)
  - ✅ User management (via Django admin)

### 2. **Batch Generation**
- **Access**: Barcode and Batch management
- **Can Do**:
  - ✅ Create new batches
  - ✅ Generate barcodes
  - ✅ View batch list
  - ✅ Print barcodes
- **Cannot Do**:
  - ❌ Product testing
  - ❌ Service cases

### 3. **Tester**
- **Access**: Product testing and Batch viewing
- **Can Do**:
  - ✅ Create new tests
  - ✅ View test results
  - ✅ View test details
  - ✅ Print test reports
  - ✅ View batch list (read-only)
  - ✅ View barcodes
  - ✅ Print barcodes
- **Cannot Do**:
  - ❌ Create batches
  - ❌ Service cases

### 4. **Service**
- **Access**: Service and Maintenance
- **Can Do**:
  - ✅ Create service cases
  - ✅ View service list
  - ✅ View service details
  - ✅ Edit service cases (unless completed/cancelled)
  - ✅ Print service reports
  - ✅ Export service data
  - ✅ View service history
- **Cannot Do**:
  - ❌ Batch management
  - ❌ Product testing

## Implementation Details

### Model Changes (inventory/models.py)

```python
class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('batch', 'Batch Generation'),
        ('tester', 'Tester'),
        ('service', 'Service'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tester')
```

### View Access Control

#### Barcode Module
- **Views**: `barcode_module`, `create_batch`, `batch_list`, `barcode_list`, `print_barcodes`
- **Access**: Admin, Batch Generation, Tester
- **Code**: `if request.user.role not in ['admin', 'batch', 'tester']:`

#### Testing Module
- **Views**: `testing_module`, `new_test`, `test_results`, `test_detail`, `print_test_report`
- **Access**: Admin, Tester
- **Code**: `if request.user.role not in ['admin', 'tester']:`

#### Service Module
- **Views**: `service_module`, `create_service_case`, `service_list`, `service_detail`, `print_service_report`, `print_service_case_detail`
- **Access**: Admin, Service
- **Code**: `if request.user.role not in ['admin', 'service']:`

### Dashboard Visibility

The dashboard shows modules based on user role:

1. **Generate Barcode Card**: Visible to Admin, Batch Generation, Tester
2. **Product Testing Card**: Visible to Admin, Tester
3. **Service & Maintenance Card**: Visible to Admin, Service

## Migration

A migration file was created: `0009_update_role_choices.py`

This adds the new 'batch' role choice to the CustomUser model.

## How to Use

### Creating Users with Different Roles

```python
# Admin user
user = CustomUser.objects.create_user(username='admin_user', password='pass', role='admin')

# Batch Generation user
user = CustomUser.objects.create_user(username='batch_user', password='pass', role='batch')

# Tester user
user = CustomUser.objects.create_user(username='tester_user', password='pass', role='tester')

# Service user
user = CustomUser.objects.create_user(username='service_user', password='pass', role='service')
```

### Django Admin Panel

1. Access Django Admin at `/admin/`
2. Go to "Users" section
3. Select user and change their role from the dropdown

### API Response Format

```python
# User string representation
"{username} ({Role Display Name})"
# Example: "john_doe (Batch Generation)"
```

## Security Notes

- All views use `@login_required` decorator
- Access control checked at view level before processing
- Views redirect unauthorized users to dashboard
- No frontend-only security (all checks server-side)
- Session timeout: 15 minutes with warning at 13 minutes

## Files Modified

1. **inventory/models.py** - Added 'batch' role choice
2. **inventory/views.py** - Updated access control for all views
3. **templates/inventory/dashboard.html** - Role-based module visibility
4. **inventory/migrations/0009_update_role_choices.py** - Database migration

## Testing Checklist

- [ ] Admin can access all modules
- [ ] Batch Generation can create batches and barcodes
- [ ] Batch Generation cannot access testing or service modules
- [ ] Tester can perform all testing operations
- [ ] Tester can view batch list and barcodes
- [ ] Tester cannot create batches or access service module
- [ ] Service can perform all service operations
- [ ] Service cannot access batch generation or testing modules
- [ ] Dashboard shows correct modules based on role
- [ ] Unauthorized access redirects to dashboard

## Future Enhancements

Potential improvements for consideration:
1. Add more granular permissions (e.g., Tester can create but not delete tests)
2. Add role hierarchy (e.g., Admin > Batch Generation > Tester)
3. Add permission groups for combining roles
4. Add audit logging for role changes
5. Add two-factor authentication for admin users
