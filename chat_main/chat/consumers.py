import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q
from django.contrib.auth.models import User
from .models import Room, Message, DirectMessage, Friendship
from django.utils import timezone

# Настройка логирования
logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'
        
        # Подробное логирование
        logger.info(f"Попытка подключения к комнате {self.room_name} пользователем {self.scope['user']}")
        
        # Проверка аутентификации
        if self.scope['user'].is_anonymous:
            logger.error(f"Неаутентифицированный пользователь пытается подключиться к комнате {self.room_name}")
            await self.close(code=4001)
            return
            
        # Проверка существования комнаты
        room_exists = await self.check_room_exists()
        if not room_exists:
            logger.error(f"Комната {self.room_name} не существует")
            await self.close(code=4002)
            return
            
        # Проверка доступа к комнате
        has_access = await self.check_user_has_access()
        if not has_access:
            logger.error(f"Пользователь {self.scope['user'].username} не имеет доступа к комнате {self.room_name}")
            await self.close(code=4003)
            return
            
        logger.info(f"Пользователь {self.scope['user'].username} подключается к комнате {self.room_name}")
        
        # Присоединяемся к группе комнаты
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Принимаем соединение
        await self.accept()
        
        # Отправляем сообщение о подключении
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': f"{self.scope['user'].username} присоединился к чату",
                'username': 'System',
                'user_id': 0,
                'message_id': 0,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    async def disconnect(self, close_code):
        logger.info(f"Отключение пользователя {self.scope['user'].username} от комнаты {self.room_name} с кодом {close_code}")
        
        # Покидаем группу комнаты
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            
            # Отправляем сообщение о выходе пользователя
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': f"{self.scope['user'].username} покинул чат",
                    'username': 'System',
                    'user_id': 0,
                    'message_id': 0,
                    'timestamp': timezone.now().isoformat()
                }
            )
    
    # ВАЖНО: Только ОДНА функция receive
    async def receive(self, text_data):
        logger.debug(f"Получено сообщение: {text_data}")
        
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))
                logger.debug("Отправлен ответ pong")
                return
                
            if message_type == 'typing':
                is_typing = text_data_json.get('is_typing', False)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_typing',
                        'username': self.scope['user'].username,
                        'user_id': self.scope['user'].id,
                        'is_typing': is_typing
                    }
                )
                logger.debug(f"Отправлен статус печатания: {is_typing}")
                return
            
            # Получаем сообщение из данных
            message = text_data_json.get('message', '')
            if not message.strip():
                logger.warning("Получено пустое сообщение")
                return
                
            logger.info(f"Получено сообщение от {self.scope['user'].username} в комнате {self.room_name}: {message[:20]}...")
            
            # Сохраняем сообщение в БД
            try:
                message_data = await self.save_message(self.room_name, message)
                message_id = message_data['id']
                timestamp = message_data['timestamp']
            except Exception as e:
                logger.error(f"Не удалось сохранить сообщение: {str(e)}")
                # Используем временные значения, если сохранение не удалось
                message_id = 0
                timestamp = timezone.now().isoformat()
            
            # Отправляем сообщение в группу
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'message_id': message_id,
                    'username': self.scope['user'].username,
                    'user_id': self.scope['user'].id,
                    'timestamp': timestamp
                }
            )
        except json.JSONDecodeError:
            logger.error(f"Получено некорректное JSON-сообщение: {text_data[:50]}")
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {str(e)}", exc_info=True)
    
    async def chat_message(self, event):
        """Отправить сообщение клиенту"""
        logger.debug(f"Отправка сообщения клиенту: {event}")
        
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event.get('message_id', 0),
            'message': event.get('message', ''),
            'username': event.get('username', 'System'),
            'user_id': event.get('user_id', 0),
            'timestamp': event.get('timestamp', timezone.now().isoformat())
        }))
    
    async def user_typing(self, event):
        """Отправить уведомление о печатании пользователем"""
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'username': event['username'],
            'user_id': event['user_id'],
            'is_typing': event['is_typing']
        }))
    
    @database_sync_to_async
    def save_message(self, room_slug, content):
        """Сохранить сообщение в базе данных"""
        from .models import Room, Message
        
        try:
            # Получаем комнату по slug
            room = Room.objects.get(slug=room_slug)
            
            # Создаем сообщение
            message = Message.objects.create(
                room=room,
                user=self.scope['user'],
                content=content
            )
            
            # Добавляем текущего пользователя в список прочитавших
            message.read_by.add(self.scope['user'])
            
            # Обновляем last_activity комнаты
            room.last_activity = timezone.now()
            room.save()  # Сохраняем всю модель
            
            return {
                'id': message.id,
                'timestamp': message.timestamp.isoformat()
            }
        except Room.DoesNotExist:
            logger.error(f"Попытка сохранить сообщение в несуществующую комнату: {room_slug}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при сохранении сообщения: {str(e)}")
            raise
    
    @database_sync_to_async
    def check_room_exists(self):
        """Проверить существование комнаты"""
        from .models import Room
        return Room.objects.filter(slug=self.room_name).exists()
    
    @database_sync_to_async
    def check_user_has_access(self):
        """Проверить, имеет ли пользователь доступ к комнате"""
        from .models import Room
        try:
            room = Room.objects.get(slug=self.room_name)
            # Если комната не приватная, доступ разрешен всем
            if not room.is_private:
                return True
            
            # Если комната приватная, проверяем участие
            return room.participants.filter(id=self.scope['user'].id).exists()
        except Room.DoesNotExist:
            return False
class DirectChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            # Получаем conversation_id из URL
            self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
            # Создаем имя группы для этого разговора
            self.room_group_name = f'direct_{self.conversation_id}'
            # Получаем текущего пользователя
            self.user = self.scope["user"]
            
            # Логирование для отладки
            logger.info(f"[DirectChat] Connect attempt: {self.conversation_id} by user {self.user.username if self.user.is_authenticated else 'anonymous'}")
            
            # Проверка аутентификации
            if not self.user.is_authenticated:
                logger.warning(f"[DirectChat] Unauthenticated user tried to connect")
                await self.close()
                return
            
            # Присоединяемся к группе
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            logger.info(f"[DirectChat] User {self.user.username} joined group: {self.room_group_name}")
            
            # Принимаем соединение
            await self.accept()
            logger.info(f"[DirectChat] Connection accepted for user {self.user.username}")
            
        except Exception as e:
            logger.error(f"[DirectChat] Connection error: {str(e)}", exc_info=True)
            if hasattr(self, 'channel_name') and hasattr(self, 'room_group_name'):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
    
    async def disconnect(self, close_code):
        logger.info(f"[DirectChat] Disconnecting: {self.conversation_id}, code: {close_code}")
        try:
            # Покидаем группу
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"[DirectChat] Left group: {self.room_group_name}")
        except Exception as e:
            logger.error(f"[DirectChat] Disconnect error: {str(e)}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'message')
            
            # Обработка пингов
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'ping',
                    'status': 'ok'
                }))
                return
            
            # Обработка уведомлений о наборе текста
            if message_type == 'typing':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_notification',
                        'sender_id': self.user.id,
                        'sender_username': self.user.username
                    }
                )
                return
            
            # Обработка обычных сообщений
            message = data.get('message', '')
            receiver_id = data.get('receiver_id')
            
            if not message or not receiver_id:
                logger.warning(f"[DirectChat] Invalid data: missing message or receiver_id")
                return
            
            logger.info(f"[DirectChat] Message received: {message[:30]}...")
            
            # Проверяем, существует ли получатель
            receiver = await self.get_user(receiver_id)
            if not receiver:
                logger.warning(f"[DirectChat] Receiver {receiver_id} not found")
                return
            
            # Проверяем дружбу
            is_friend = await self.check_friendship(self.user.id, receiver_id)
            if not is_friend:
                logger.warning(f"[DirectChat] {self.user.username} tried to message non-friend {receiver.username}")
                return
            
            # Сохраняем сообщение
            message_obj = await self.save_direct_message(self.user.id, receiver_id, message)
            
            # Отправляем сообщение в группу
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'direct_message',
                    'message': message,
                    'sender_id': self.user.id,
                    'sender_username': self.user.username,
                    'timestamp': message_obj['timestamp']
                }
            )
            logger.info(f"[DirectChat] Message sent to group: {self.room_group_name}")
            
        except Exception as e:
            logger.error(f"[DirectChat] Receive error: {str(e)}", exc_info=True)
    
    async def direct_message(self, event):
        """Обработчик сообщений для группы"""
        try:
            # Отправляем данные в WebSocket
            await self.send(text_data=json.dumps({
                'message': event['message'],
                'sender_id': event['sender_id'],
                'sender_username': event['sender_username'],
                'timestamp': event['timestamp']
            }))
            logger.info(f"[DirectChat] Message forwarded to WebSocket for user {self.user.username}")
        except Exception as e:
            logger.error(f"[DirectChat] direct_message error: {str(e)}")
    
    async def typing_notification(self, event):
        """Обработчик уведомлений о печатании"""
        try:
            if event['sender_id'] != self.user.id:  # Не отправляем уведомление самому себе
                await self.send(text_data=json.dumps({
                    'type': 'typing',
                    'sender_id': event['sender_id'],
                    'sender_username': event['sender_username']
                }))
        except Exception as e:
            logger.error(f"[DirectChat] typing_notification error: {str(e)}")
    
    @database_sync_to_async
    def get_user(self, user_id):
        """Получение пользователя по ID"""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None
        
    @database_sync_to_async
    def get_room_by_slug(self, slug):
        """Получение комнаты по слагу"""
        try:
            return Room.objects.get(slug=slug)
        except Room.DoesNotExist:
            return None
            
    @database_sync_to_async
    def check_room_access(self, room_id, user_id):
        """Проверка доступа пользователя к комнате"""
        try:
            room = Room.objects.get(id=room_id)
            user = User.objects.get(id=user_id)
            return room.is_participant(user)
        except (Room.DoesNotExist, User.DoesNotExist):
            return False
    
    @database_sync_to_async
    def check_friendship(self, user1_id, user2_id):
        """Проверка существования дружбы между пользователями"""
        return Friendship.objects.filter(
            (Q(sender_id=user1_id, receiver_id=user2_id) |
             Q(sender_id=user2_id, receiver_id=user1_id)),
            status='accepted'
        ).exists()
    
    @database_sync_to_async
    def save_direct_message(self, sender_id, receiver_id, content):
        """Сохранение личного сообщения в базу данных"""
        try:
            sender = User.objects.get(id=sender_id)
            receiver = User.objects.get(id=receiver_id)
            
            message = DirectMessage.objects.create(
                sender=sender,
                receiver=receiver,
                content=content
            )
            
            return {
                'id': message.id,
                'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            logger.error(f"[DirectChat] save_direct_message error: {str(e)}")
            raise