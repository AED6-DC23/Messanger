from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Групповой чат
    re_path(r'^ws/chat/(?P<room_name>[^/]+)/$', consumers.ChatConsumer.as_asgi()),


    # Личные сообщения
    re_path(r'ws/direct/(?P<conversation_id>[a-f0-9]{32})/$', consumers.DirectChatConsumer.as_asgi()),
]