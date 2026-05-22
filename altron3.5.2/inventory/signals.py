from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import SKU, Technician, TestTemplate, BatchSpecTemplate, SystemLog

@receiver(post_save, sender=SKU)
@receiver(post_save, sender=Technician)
@receiver(post_save, sender=TestTemplate)
@receiver(post_save, sender=BatchSpecTemplate)
def log_master_data_save(sender, instance, created, **kwargs):
    action = "Created" if created else "Updated"
    model_name = sender.__name__
    
    # Map model names to event types
    event_map = {
        'SKU': 'sku_managed',
        'Technician': 'tech_managed',
        'TestTemplate': 'template_managed',
        'BatchSpecTemplate': 'template_managed'
    }
    
    SystemLog.log_event(
        event_type=event_map.get(model_name, 'other'),
        title=f"{model_name} {action}",
        description=f"{model_name} '{instance}' was {action.lower()}.",
        level='info'
    )

@receiver(post_delete, sender=SKU)
@receiver(post_delete, sender=Technician)
@receiver(post_delete, sender=TestTemplate)
@receiver(post_delete, sender=BatchSpecTemplate)
def log_master_data_delete(sender, instance, **kwargs):
    model_name = sender.__name__
    
    event_map = {
        'SKU': 'sku_managed',
        'Technician': 'tech_managed',
        'TestTemplate': 'template_managed',
        'BatchSpecTemplate': 'template_managed'
    }
    
    SystemLog.log_event(
        event_type=event_map.get(model_name, 'other'),
        title=f"{model_name} Deleted",
        description=f"{model_name} '{instance}' was deleted.",
        level='warning'
    )
