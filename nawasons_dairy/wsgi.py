"""
WSGI config for nawasons_dairy project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nawasons_dairy.settings')

application = get_wsgi_application()

# Enable WhiteNoise static file serving for simple deployments with Gunicorn
try:
    from whitenoise import WhiteNoise
    application = WhiteNoise(application, root=os.path.join(os.path.dirname(__file__), '..', 'staticfiles'))
except Exception:
    # If whitenoise isn't available at import time, app will still start; it's installed in the Docker image.
    pass

