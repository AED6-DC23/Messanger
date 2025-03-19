from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('profile/', views.view_profile, name='view_profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/<str:username>/', views.view_profile, name='view_profile_with_username'),
    
    # Маршруты для друзей
    path('friends/', views.friends_list, name='friends_list'),
    path('friends/find/', views.find_friends, name='find_friends'),
    path('friends/request/<int:user_id>/', views.send_friend_request, name='send_friend_request'),
    path('friends/search/', views.search_users, name='search_users'),
     path('friends/accept/', views.accept_friend, name='accept_friend'),
    path('friends/reject/', views.reject_friend, name='reject_friend'),
    
    path('friends/accept/<int:request_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friends/reject/<int:request_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('friends/cancel/<int:request_id>/', views.cancel_friend_request, name='cancel_friend_request'),
    path('friends/remove/<int:user_id>/', views.remove_friend, name='remove_friend'),
    
    # Маршруты для личных сообщений
    path('messages/<int:user_id>/', views.direct_messages, name='direct_messages'),
    path('messages/send/', views.send_direct_message, name='send_direct_message'),
    
    # Комнаты чата
    path('<str:room_name>/', views.room, name='room'),
    # Добавьте эти URL-маршруты в urlpatterns

    path('api/unread-count/', views.get_unread_count, name='get_unread_count'),
    path('api/mark-read/<int:user_id>/', views.mark_messages_read, name='mark_messages_read'),

    path('rooms/<int:room_id>/', views.room_details, name='room_details'),
    path('rooms/<int:room_id>/remove/<int:user_id>/', views.remove_from_room, name='remove_from_room'),
    path('rooms/<int:room_id>/leave/', views.leave_room, name='leave_room'),
    path('rooms/<int:room_id>/delete/', views.delete_room, name='delete_room'),
    path('room-invitation/<int:invitation_id>/<str:action>/', views.room_invitation_response, name='room_invitation_response'),
    
    path('room/invitation/accept/<int:invitation_id>/', views.accept_room_invitation, name='accept_room_invitation'),
    path('room/invitation/reject/<int:invitation_id>/', views.reject_room_invitation, name='reject_room_invitation'),
    path('chat/<str:room_slug>/', views.room, name='room'),
]