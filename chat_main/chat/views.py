from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Max
from django.http import JsonResponse
from .forms import CustomUserCreationForm, RoomCreationForm, RoomInvitationForm, UserProfileForm, ProfileForm
from .models import Room, Profile, Friendship, DirectMessage, RoomInvitation, Message
import hashlib
import json
import string
import random
from django.utils.text import slugify
from django.utils.timezone import utc
from datetime import datetime

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('index')
    else:
        form = CustomUserCreationForm()
    return render(request, 'chat/register.html', {'form': form})

def generate_unique_slug(name):
    """Генерирует уникальный слаг из названия комнаты"""
    base_slug = slugify(name)
    if not base_slug:
        # Если название не может быть преобразовано в слаг
        base_slug = 'room'
    slug = base_slug
    
    # Проверяем уникальность и добавляем случайные символы при необходимости
    while Room.objects.filter(slug=slug).exists():
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        slug = f"{base_slug}-{random_str}"
        
    return slug

@login_required
def index(request):
    # Получаем последние диалоги пользователя
    user = request.user
    
    # Находим всех пользователей, с которыми есть переписка
    direct_messages = DirectMessage.objects.filter(
        Q(sender=user) | Q(receiver=user)
    ).values(
        'sender', 'receiver'
    ).annotate(
        last_msg=Max('timestamp')
    ).order_by('-last_msg')
    
    # Создаем словарь для хранения уникальных диалогов
    dialogs_dict = {}
    
    # Обрабатываем личные диалоги
    for dm in direct_messages:
        # Определяем другого пользователя (не текущего)
        other_user_id = dm['receiver'] if dm['sender'] == user.id else dm['sender']
        
        # Если этот пользователь уже в словаре или ID пустой, пропускаем
        if other_user_id in dialogs_dict or not other_user_id:
            continue
            
        # Получаем пользователя и последнее сообщение
        try:
            other_user = User.objects.get(id=other_user_id)
            
            # Получаем последнее сообщение между пользователями
            last_message = DirectMessage.objects.filter(
                Q(sender=user, receiver=other_user) | 
                Q(sender=other_user, receiver=user)
            ).order_by('-timestamp').first()
            
            # Считаем непрочитанные сообщения
            unread_count = DirectMessage.objects.filter(
                sender=other_user,
                receiver=user,
                is_read=False
            ).count()
            
            # Добавляем в словарь
            dialogs_dict[f"user_{other_user_id}"] = {
                'type': 'direct',
                'user': other_user,
                'last_message': last_message,
                'unread_count': unread_count,
                'timestamp': last_message.timestamp if last_message else None
            }
        except User.DoesNotExist:
            continue
    
    # Получаем групповые чаты пользователя
    group_rooms = Room.objects.filter(
        Q(creator=user) | Q(participants=user)
    ).distinct()
    
    # Обрабатываем групповые чаты
    for room in group_rooms:
        if not room:
            continue
            
        # Проверяем, что комната действительна
        try:
            room_id = room.id
            last_message = room.get_last_message()
            
            # Считаем непрочитанные сообщения (для реализации нужно добавить поле is_read в модель Message)
            unread_count = 0  # Заглушка, в реальности надо реализовать подсчет непрочитанных
            
            dialogs_dict[f"room_{room_id}"] = {
                'type': 'group',
                'room': room,
                'last_message': last_message,
                'unread_count': unread_count,
                'timestamp': last_message.timestamp if last_message else room.created_at
            }
        except (AttributeError, Exception) as e:
            print(f"Error processing room {room}: {e}")
            continue
    
    # Преобразуем словарь в список и сортируем по времени последнего сообщения
    dialogs = []
    for dialog_data in dialogs_dict.values():
        # Проверяем наличие всех необходимых полей
        if dialog_data['type'] == 'direct' and not dialog_data.get('user'):
            continue
        if dialog_data['type'] == 'group' and not dialog_data.get('room'):
            continue
            
        dialogs.append(dialog_data)
    
    # Сортируем диалоги по времени
    dialogs.sort(key=lambda x: x.get('timestamp') or datetime.min.replace(tzinfo=utc), reverse=True)
    
    # Получаем список друзей
    friends = User.objects.filter(
        Q(sent_friendships__receiver=user, sent_friendships__status='accepted') |
        Q(received_friendships__sender=user, received_friendships__status='accepted')
    ).distinct()
    
    # Получаем список запросов в друзья
    friend_requests = Friendship.objects.filter(
        receiver=user,
        status='pending'
    )
    
    # Получаем список приглашений в комнаты
    room_invitations = RoomInvitation.objects.filter(
        invited_user=user,
        status='pending'
    )
    
    # Форма для создания комнаты
    room_form = RoomCreationForm()
    
    if request.method == 'POST' and 'create_room' in request.POST:
        room_form = RoomCreationForm(request.POST)
        if room_form.is_valid():
            # Создаем комнату без сохранения
            room = room_form.save(commit=False)
            room.creator = user
            room.slug = generate_unique_slug(room.name)
            room.save()
            
            # Добавляем создателя как участника
            room.participants.add(user)
            
            messages.success(request, f'Комната "{room.name}" успешно создана!')
            return redirect('room_details', room_id=room.id)
    
    return render(request, 'chat/index.html', {
        'dialogs': dialogs,
        'friends': friends,
        'friend_requests': friend_requests,
        'room_invitations': room_invitations,
        'room_form': room_form
    })

@login_required
def accept_room_invitation(request, invitation_id):
    if request.method == 'POST':
        try:
            invitation = RoomInvitation.objects.get(id=invitation_id, invited_user=request.user, status='pending')
            room = invitation.room
            
            # Обновляем статус приглашения
            invitation.status = 'accepted'
            invitation.save()
            
            # Добавляем пользователя в комнату
            room.participants.add(request.user)
            room.save()
            
            messages.success(request, f'Вы присоединились к комнате "{room.name}"')
            return redirect('room', room_slug=room.slug)
        except RoomInvitation.DoesNotExist:
            messages.error(request, 'Приглашение не найдено или уже обработано')
    
    return redirect('index')

@login_required
def reject_room_invitation(request, invitation_id):
    if request.method == 'POST':
        try:
            invitation = RoomInvitation.objects.get(id=invitation_id, invited_user=request.user, status='pending')
            room_name = invitation.room.name
            
            # Обновляем статус приглашения
            invitation.status = 'rejected'
            invitation.save()
            
            messages.info(request, f'Вы отклонили приглашение в комнату "{room_name}"')
        except RoomInvitation.DoesNotExist:
            messages.error(request, 'Приглашение не найдено или уже обработано')
    
    return redirect('index')

@login_required
def room_invitation_response(request, invitation_id, action):
    """Обработка ответа на приглашение в комнату"""
    invitation = get_object_or_404(RoomInvitation, id=invitation_id, invited_user=request.user)
    
    if action == 'accept':
        invitation.status = 'accepted'
        invitation.save()
        
        # Добавляем пользователя в комнату
        invitation.room.add_participant(request.user)
        
        messages.success(request, f'Вы присоединились к комнате {invitation.room.name}')
        return redirect('room', room_name=invitation.room.slug)
    
    elif action == 'reject':
        invitation.status = 'rejected'
        invitation.save()
        
        messages.success(request, f'Вы отклонили приглашение в комнату {invitation.room.name}')
    
    return redirect('index')

@login_required
def room(request, room_slug):
    try:
        room = Room.objects.get(slug=room_slug)
        
        # Проверка доступа к приватной комнате
        if room.is_private:
            is_member = room.participants.filter(id=request.user.id).exists()
            if not is_member:
                messages.error(request, "У вас нет доступа к этой комнате.")
                return redirect('index')
        
        # Получаем все сообщения для комнаты и сортируем их по времени
        messages_list = list(Message.objects.filter(room=room).select_related('user').order_by('timestamp'))
        
        # Отмечаем сообщения как прочитанные
        for msg in messages_list:
            if request.user not in msg.read_by.all():
                msg.read_by.add(request.user)
        
        # Преобразуем сообщения в JSON для JavaScript
        messages_json = json.dumps([{
            'id': msg.id,
            'content': msg.content,
            'username': msg.user.username if msg.user else "Unknown",
            'user_id': msg.user.id if msg.user else None,
            'timestamp': msg.timestamp.isoformat() if msg.timestamp else None
        } for msg in messages_list], ensure_ascii=False)
        
        return render(request, 'chat/room.html', {
            'room': room,
            'messages': messages_list,
            'messages_json': messages_json,
            'is_creator': room.creator == request.user,
            'is_participant': room.participants.filter(id=request.user.id).exists()
        })
    except Room.DoesNotExist:
        messages.error(request, "Комната не найдена.")
        return redirect('index')
    except Exception as e:
        messages.error(request, f"Произошла ошибка: {str(e)}")
        return redirect('index')


@login_required
def view_profile(request, username=None):
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user
    
    # Получаем профиль пользователя
    try:
        profile = user.profile
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=user)
    
    # Получаем последние комнаты, в которых участвовал пользователь
    user_rooms = Room.objects.filter(
        messages__user=user
    ).distinct().order_by('-messages__timestamp')[:5]
    
    return render(request, 'chat/profile.html', {
        'profile_user': user,
        'profile': profile,
        'user_rooms': user_rooms,
        'is_own_profile': user == request.user
    })

@login_required
@transaction.atomic
def edit_profile(request):
    if request.method == 'POST':
        user_form = UserProfileForm(request.POST, instance=request.user)
        profile_form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Ваш профиль был успешно обновлен!')
            return redirect('view_profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        user_form = UserProfileForm(instance=request.user)
        try:
            profile_form = ProfileForm(instance=request.user.profile)
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user)
            profile_form = ProfileForm(instance=profile)
    
    return render(request, 'chat/edit_profile.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })

@login_required
def friends_list(request):
    user = request.user
    
    # Получаем всех друзей
    friends = User.objects.filter(
        Q(sent_friendships__receiver=user, sent_friendships__status='accepted') |
        Q(received_friendships__sender=user, received_friendships__status='accepted')
    ).distinct()
    
    # Получаем входящие запросы на дружбу
    incoming_requests = Friendship.objects.filter(
        receiver=user,
        status='pending'
    )
    
    # Получаем исходящие запросы на дружбу
    outgoing_requests = Friendship.objects.filter(
        sender=user,
        status='pending'
    )
    
    return render(request, 'chat/friends.html', {
        'friends': friends,
        'incoming_requests': incoming_requests,
        'outgoing_requests': outgoing_requests
    })

@login_required
def find_friends(request):
    query = request.GET.get('q', '')
    user = request.user
    
    if query:
        # Находим пользователей, соответствующих запросу
        users = User.objects.filter(
            Q(username__icontains=query) | 
            Q(first_name__icontains=query) | 
            Q(last_name__icontains=query) | 
            Q(email__icontains=query)
        ).exclude(id=user.id)
        
        # Исключаем тех, кто уже в друзьях
        friends_ids = Friendship.objects.filter(
            (Q(sender=user) | Q(receiver=user)),
            status='accepted'
        ).values_list('sender_id', 'receiver_id')
        
        flat_friends_ids = set()
        for sender_id, receiver_id in friends_ids:
            if sender_id != user.id:
                flat_friends_ids.add(sender_id)
            if receiver_id != user.id:
                flat_friends_ids.add(receiver_id)
        
        # Исключаем уже существующие запросы
        pending_ids = Friendship.objects.filter(
            (Q(sender=user) | Q(receiver=user)),
            status='pending'
        ).values_list('sender_id', 'receiver_id')
        
        pending_flat_ids = set()
        for sender_id, receiver_id in pending_ids:
            if sender_id != user.id:
                pending_flat_ids.add(sender_id)
            if receiver_id != user.id:
                pending_flat_ids.add(receiver_id)
        
        search_results = []
        for u in users:
            # Проверяем, есть ли уже дружба или запрос
            friendship_status = None
            
            if u.id in flat_friends_ids:
                friendship_status = 'accepted'
            elif u.id in pending_flat_ids:
                try:
                    friendship = Friendship.objects.get(
                        Q(sender=user, receiver=u) | Q(sender=u, receiver=user),
                        status='pending'
                    )
                    friendship_status = 'outgoing' if friendship.sender == user else 'incoming'
                except Friendship.DoesNotExist:
                    friendship_status = None
            
            search_results.append({
                'user': u,
                'friendship_status': friendship_status
            })
    else:
        search_results = []
    
    return render(request, 'chat/find_friends.html', {
        'search_results': search_results,
        'query': query
    })

@login_required
def search_users(request):
    query = request.GET.get('q', '')
    
    if query:
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).exclude(id=request.user.id)
        
        # Определяем статус дружбы для каждого пользователя
        for user in users:
            friendship = Friendship.objects.filter(
                (Q(sender=request.user, receiver=user) | Q(sender=user, receiver=request.user))
            ).first()
            
            if friendship:
                user.friendship_status = friendship.status
                user.friendship_id = friendship.id
            else:
                user.friendship_status = None
                user.friendship_id = None
    else:
        users = []
    
    return render(request, 'chat/find_friends.html', {
        'users': users,
        'query': query
    })


@login_required
def send_friend_request(request, user_id):
    if request.method == 'POST':
        receiver = get_object_or_404(User, id=user_id)
        
        # Проверяем, есть ли уже запрос или дружба
        if Friendship.objects.filter(
            Q(sender=request.user, receiver=receiver) |
            Q(sender=receiver, receiver=request.user)
        ).exists():
            messages.warning(request, 'Запрос уже существует или вы уже друзья')
        else:
            Friendship.objects.create(sender=request.user, receiver=receiver)
            messages.success(request, f'Запрос на дружбу отправлен пользователю {receiver.username}')
        
        return redirect('find_friends')
    
    return redirect('index')

@login_required
def accept_friend_request(request, request_id):
    if request.method == 'POST':
        friendship = get_object_or_404(Friendship, id=request_id, receiver=request.user, status='pending')
        friendship.status = 'accepted'
        friendship.save()
        messages.success(request, f'Вы приняли запрос на дружбу от {friendship.sender.username}')
        return redirect('friends_list')
    
    return redirect('index')

@login_required
def reject_friend_request(request, request_id):
    if request.method == 'POST':
        friendship = get_object_or_404(Friendship, id=request_id, receiver=request.user, status='pending')
        friendship.status = 'rejected'
        friendship.save()
        messages.success(request, f'Вы отклонили запрос на дружбу от {friendship.sender.username}')
        return redirect('friends_list')
    
    return redirect('index')

@login_required
def accept_friend(request):
    if request.method == 'POST':
        friendship_id = request.POST.get('friendship_id')
        if not friendship_id:
            messages.error(request, 'ID запроса не указан.')
            return redirect('index')
        
        try:
            friendship = Friendship.objects.get(id=friendship_id, receiver=request.user, status='pending')
            friendship.status = 'accepted'
            friendship.save()
            
            messages.success(request, f'Вы приняли запрос в друзья от {friendship.sender.username}.')
        except Friendship.DoesNotExist:
            messages.error(request, 'Запрос в друзья не найден или уже обработан.')
        
    return redirect('index')

@login_required
def reject_friend(request):
    if request.method == 'POST':
        friendship_id = request.POST.get('friendship_id')
        if not friendship_id:
            messages.error(request, 'ID запроса не указан.')
            return redirect('index')
        
        try:
            friendship = Friendship.objects.get(id=friendship_id, receiver=request.user, status='pending')
            friendship.status = 'rejected'
            friendship.save()
            
            messages.success(request, f'Вы отклонили запрос в друзья от {friendship.sender.username}.')
        except Friendship.DoesNotExist:
            messages.error(request, 'Запрос в друзья не найден или уже обработан.')
        
    return redirect('index')

@login_required
def cancel_friend_request(request, request_id):
    if request.method == 'POST':
        friendship = get_object_or_404(Friendship, id=request_id, sender=request.user, status='pending')
        friendship.delete()
        messages.success(request, f'Вы отменили запрос на дружбу к {friendship.receiver.username}')
        return redirect('friends_list')
    
    return redirect('index')

@login_required
def remove_friend(request, user_id):
    if request.method == 'POST':
        other_user = get_object_or_404(User, id=user_id)
        
        # Удаляем дружбу в обоих направлениях
        Friendship.objects.filter(
            (Q(sender=request.user, receiver=other_user) |
             Q(sender=other_user, receiver=request.user)),
            status='accepted'
        ).delete()
        
        messages.success(request, f'Вы удалили {other_user.username} из списка друзей')
        return redirect('friends_list')
    
    return redirect('index')

@login_required
def room_details(request, room_id):
    """Детали комнаты и управление участниками"""
    room = get_object_or_404(Room, id=room_id)
    user = request.user
    
    # Проверяем, имеет ли пользователь доступ к комнате
    if not room.is_participant(user):
        messages.error(request, 'У вас нет доступа к этой комнате')
        return redirect('index')
    
    # Получаем участников комнаты
    participants = list(room.participants.all())
    if room.creator not in participants:
        participants.append(room.creator)
    
    # Форма для приглашения пользователей
    invitation_form = None
    if room.is_creator(user):
        invitation_form = RoomInvitationForm(user=user, room=room)
        
        if request.method == 'POST' and 'invite_users' in request.POST:
            invitation_form = RoomInvitationForm(request.POST, user=user, room=room)
            if invitation_form.is_valid():
                invited_users = invitation_form.cleaned_data['users']
                
                for invited_user in invited_users:
                    # Создаем приглашение
                    RoomInvitation.objects.create(
                        room=room,
                        invited_by=user,
                        invited_user=invited_user
                    )
                
                messages.success(request, f'Приглашения отправлены {len(invited_users)} пользователям')
                return redirect('room_details', room_id=room.id)
    
    return render(request, 'chat/room_details.html', {
        'room': room,
        'participants': participants,
        'invitation_form': invitation_form,
        'is_creator': room.is_creator(user)
    })

@login_required
def leave_room(request, room_id):
    """Выход пользователя из комнаты"""
    room = get_object_or_404(Room, id=room_id)
    user = request.user
    
    # Проверяем, не является ли пользователь создателем комнаты
    if room.is_creator(user):
        messages.error(request, 'Создатель не может покинуть комнату. Вы можете удалить комнату.')
        return redirect('room_details', room_id=room.id)
    
    # Удаляем пользователя из комнаты
    if room.remove_participant(user):
        messages.success(request, f'Вы вышли из комнаты {room.name}')
    else:
        messages.error(request, 'Не удалось выйти из комнаты')
    
    return redirect('index')

@login_required
def remove_from_room(request, room_id, user_id):
    """Удаление пользователя из комнаты"""
    room = get_object_or_404(Room, id=room_id)
    user_to_remove = get_object_or_404(User, id=user_id)
    
    # Проверяем, является ли текущий пользователь создателем комнаты
    if not room.is_creator(request.user):
        messages.error(request, 'Только создатель комнаты может удалять участников')
        return redirect('room_details', room_id=room.id)
    
    # Проверяем, не пытается ли пользователь удалить себя (создателя)
    if user_to_remove == room.creator:
        messages.error(request, 'Вы не можете удалить создателя комнаты')
        return redirect('room_details', room_id=room.id)
    
    # Удаляем пользователя из комнаты
    if room.remove_participant(user_to_remove):
        messages.success(request, f'Пользователь {user_to_remove.username} удален из комнаты')
    else:
        messages.error(request, 'Не удалось удалить пользователя из комнаты')
    
    return redirect('room_details', room_id=room.id)

@login_required
def delete_room(request, room_id):
    """Удаление комнаты"""
    room = get_object_or_404(Room, id=room_id)
    
    # Проверяем, является ли пользователь создателем комнаты
    if not room.is_creator(request.user):
        messages.error(request, 'Только создатель комнаты может удалить её')
        return redirect('room_details', room_id=room.id)
    
    room_name = room.name
    room.delete()
    messages.success(request, f'Комната "{room_name}" удалена')
    
    return redirect('index')

@login_required
def direct_messages(request, user_id):
    # Получаем пользователя-собеседника
    other_user = get_object_or_404(User, id=user_id)
    user = request.user
    
    # Если пользователь пытается начать диалог с самим собой
    if user.id == other_user.id:
        messages.warning(request, "Вы не можете отправлять сообщения сами себе")
        return redirect('index')
    
    # Проверяем, являются ли пользователи друзьями
    is_friend = Friendship.objects.filter(
        (Q(sender=user, receiver=other_user) | Q(sender=other_user, receiver=user)),
        status='accepted'
    ).exists()
    
    # Генерируем идентификатор диалога для WebSocket
    user_ids = sorted([str(user.id), str(other_user.id)])
    conversation_id_raw = f"{user_ids[0]}_{user_ids[1]}"
    conversation_id = hashlib.md5(conversation_id_raw.encode()).hexdigest()
    
    # Логируем для отладки
    print(f"Generated conversation_id: {conversation_id} for users {user.id} and {other_user.id}")
    
    # Получаем сообщения между пользователями
    messages_list = DirectMessage.objects.filter(
        (Q(sender=user, receiver=other_user) | Q(sender=other_user, receiver=user))
    ).order_by('timestamp')
    
    # Помечаем непрочитанные сообщения как прочитанные
    DirectMessage.objects.filter(
        sender=other_user,
        receiver=user,
        is_read=False
    ).update(is_read=True)
    
    return render(request, 'chat/direct_messages.html', {
        'other_user': other_user,
        'messages': messages_list,
        'is_friend': is_friend,
        'conversation_id': conversation_id
    })

# API для работы с сообщениями через AJAX
@login_required
def send_direct_message(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            receiver_id = data.get('receiver_id')
            content = data.get('content')
            
            if not receiver_id or not content:
                return JsonResponse({'status': 'error', 'message': 'Неполные данные'}, status=400)
            
            receiver = get_object_or_404(User, id=receiver_id)
            
            # Проверяем, являются ли пользователи друзьями
            is_friend = Friendship.objects.filter(
                Q(sender=request.user, receiver=receiver, status='accepted') |
                Q(sender=receiver, receiver=request.user, status='accepted')
            ).exists()
            
            if not is_friend:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Вы не можете отправлять сообщения не-друзьям'
                }, status=403)
            
            # Создаем сообщение
            message = DirectMessage.objects.create(
                sender=request.user,
                receiver=receiver,
                content=content
            )
            
            return JsonResponse({
                'status': 'success',
                'message_id': message.id,
                'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Метод не разрешен'}, status=405)


@login_required
def get_unread_count(request):
    """API для получения количества непрочитанных сообщений"""
    user = request.user
    unread_count = DirectMessage.objects.filter(
        receiver=user,
        is_read=False
    ).count()
    
    return JsonResponse({
        'unread_count': unread_count
    })

@login_required
def mark_messages_read(request, user_id):
    """Отметить все сообщения от определенного пользователя как прочитанные"""
    if request.method == 'POST':
        try:
            sender = User.objects.get(id=user_id)
            updated = DirectMessage.objects.filter(
                sender=sender,
                receiver=request.user,
                is_read=False
            ).update(is_read=True)
            
            return JsonResponse({
                'status': 'success',
                'messages_read': updated
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': 'error',
        'message': 'Метод не разрешен'
    }, status=405)