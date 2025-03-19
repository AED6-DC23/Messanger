from django.utils import timezone
import hashlib
from django.db import models
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db.models import Q

class Room(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Добавляем поля для создателя и участников
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rooms')
    participants = models.ManyToManyField(User, related_name='joined_rooms')
    # Опциональное описание комнаты
    description = models.TextField(blank=True, null=True)
    # Флаг для приватных комнат (доступны только по приглашению)
    is_private = models.BooleanField(default=False)
    last_activity = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ['-last_activity']

    def __str__(self):
        return self.name
    
    def is_member(self, user):
        """Проверить, является ли пользователь участником комнаты"""
        return self.participants.filter(id=user.id).exists()

    def get_last_message(self):
        """Получить последнее сообщение в комнате"""
        try:
            return self.messages.order_by('-timestamp').first()
        except Exception:
            return None
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('room', kwargs={'room_name': self.slug})
        
    def add_participant(self, user):
        """Добавить пользователя в комнату"""
        if user not in self.participants.all():
            self.participants.add(user)
            return True
        return False
            
    def remove_participant(self, user):
        """Удалить пользователя из комнаты"""
        if user in self.participants.all() and user != self.creator:
            self.participants.remove(user)
            return True
        return False
            
    def is_participant(self, user):
        """Проверить, является ли пользователь участником комнаты"""
        return user in self.participants.all() or user == self.creator
            
    def is_creator(self, user):
        """Проверить, является ли пользователь создателем комнаты"""
        return user == self.creator
            
    def get_last_message(self):
        """Получить последнее сообщение в комнате"""
        return self.messages.order_by('-timestamp').first()

class RoomInvitation(models.Model):
    """Модель для приглашений в групповой чат"""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_room_invitations')
    invited_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_room_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    STATUS_CHOICES = (
        ('pending', 'В ожидании'),
        ('accepted', 'Принято'),
        ('rejected', 'Отклонено'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    class Meta:
        unique_together = ('room', 'invited_user')
        
    def __str__(self):
        return f"Приглашение в {self.room.name} для {self.invited_user.username}"

class Message(models.Model):
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    # Добавляем поле для отслеживания, кто прочитал сообщение
    read_by = models.ManyToManyField(User, related_name='read_messages', blank=True)

    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f'{self.user.username}: {self.content[:20]}'
        
    def mark_as_read(self, user):
        """Отметить сообщение как прочитанное пользователем"""
        if user != self.user and user not in self.read_by.all():
            self.read_by.add(user)
            
    def is_read_by(self, user):
        """Проверить, прочитал ли пользователь сообщение"""
        return user in self.read_by.all()
    

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True, verbose_name='О себе')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Аватар')
    birth_date = models.DateField(null=True, blank=True, verbose_name='Дата рождения')
    last_seen = models.DateTimeField(auto_now=True, verbose_name='Последний вход')

    def __str__(self):
        return f'Профиль пользователя {self.user.username}'

# Сигналы для автоматического создания и обновления профиля
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance)


class Friendship(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_friendships')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_friendships')
    STATUS_CHOICES = (
        ('pending', 'В ожидании'),
        ('accepted', 'Принято'),
        ('rejected', 'Отклонено'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('sender', 'receiver')
        verbose_name = 'Дружба'
        verbose_name_plural = 'Дружеские отношения'

    def __str__(self):
        return f"{self.sender.username} - {self.receiver.username} ({self.status})"

# Модель для личных сообщений
class DirectMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']
        verbose_name = 'Личное сообщение'
        verbose_name_plural = 'Личные сообщения'

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username}: {self.content[:20]}"

    @staticmethod
    def get_conversation_id(user1, user2):
        """Создает уникальный идентификатор для чата между двумя пользователями."""
        users = sorted([str(user1.id), str(user2.id)])
        conversation_id = f"{users[0]}_{users[1]}"
        return hashlib.md5(conversation_id.encode()).hexdigest()

    @staticmethod
    def get_conversation_id(user1, user2):
        """Создает уникальный идентификатор для чата между двумя пользователями."""
        users = sorted([str(user1.id), str(user2.id)])
        conversation_id = f"{users[0]}_{users[1]}"
        return hashlib.md5(conversation_id.encode()).hexdigest()

    @staticmethod
    def get_conversation_messages(user1, user2):
        """Получает все сообщения между двумя пользователями."""
        return DirectMessage.objects.filter(
            (Q(sender=user1, receiver=user2) | 
             Q(sender=user2, receiver=user1))
        ).order_by('timestamp')