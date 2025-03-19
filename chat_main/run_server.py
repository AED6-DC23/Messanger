import os
import sys
import django
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Исправлен путь к модулю настроек
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat_main.settings')
django.setup()

from chat.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns
            )
        )
    ),
})

if __name__ == "__main__":
    # Используем прямой вызов daphne через subprocess
    import subprocess
    
    try:
        print("Запуск Daphne сервера на 0.0.0.0:8000...")
        subprocess.run(
            ["daphne", "-b", "0.0.0.0", "-p", "8000", "run_server:application"],
            check=True
        )
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка запуска сервера: {e}")
    except FileNotFoundError:
        print("Ошибка: daphne не найден. Убедитесь, что он установлен:")
        print("pip install daphne")