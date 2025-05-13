"""
ASGI config for soundscape project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
# import django # Not strictly necessary here if get_asgi_application handles it
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soundscape.settings")

django_asgi_app = get_asgi_application()

# NOW it's safe to import modules that depend on Django's settings or models
from users.auth_middleware import CustomCookieAuthMiddlewareStack # MOVED HERE
from .routing import websocket_urlpatterns # MOVED HERE (if not already after)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": CustomCookieAuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})


