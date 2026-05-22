from django.utils import timezone
from .models import SystemLog
import logging

logger = logging.getLogger(__name__)

class UserActivityMiddleware:
    """
    Middleware to log user navigation and "clicks" (requests).
    Filters out noisy background requests.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log for authenticated users
        if request.user.is_authenticated:
            path = request.path
            
            # Skip noisy or background requests
            skip_paths = [
                '/keep-alive/', 
                '/auto_save_test/', 
                '/static/', 
                '/media/', 
                '/api/test_draft/',
                '/admin/jsi18n/'
            ]
            
            if not any(path.startswith(p) for p in skip_paths):
                # Determine event type
                event_type = 'action_click' if request.method == 'POST' else 'navigation'
                
                # Title based on method and path
                title = f"{request.method} {path}"
                
                # Log the movement
                SystemLog.log_event(
                    event_type=event_type,
                    title=title,
                    description=f"User visited {path} via {request.method}",
                    level='info',
                    user=request.user,
                    request=request,
                    details={
                        'path': path,
                        'method': request.method,
                        'query_params': dict(request.GET),
                        'is_ajax': request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    }
                )

        return response
