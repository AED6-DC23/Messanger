// Функция для периодической проверки непрочитанных сообщений
function setupNotificationsCheck() {
    let unreadCount = 0;
    let notificationsInterval;
    
    // Получение количества непрочитанных сообщений с сервера
    function checkUnreadMessages() {
        fetch('/chat/api/unread-count/')
            .then(response => response.json())
            .then(data => {
                if (data.unread_count !== unreadCount) {
                    unreadCount = data.unread_count;
                    updateNotificationBadge(unreadCount);
                    
                    // Если появились новые сообщения, отправляем уведомление
                    if (unreadCount > 0 && Notification.permission === 'granted') {
                        showNotification(`У вас ${unreadCount} новых сообщений`);
                    }
                }
            })
            .catch(error => {
                console.error('Ошибка при проверке новых сообщений:', error);
            });
    }
    
    // Обновление значка уведомлений в заголовке страницы
    function updateNotificationBadge(count) {
        const badgeElement = document.getElementById('notification-badge');
        
        if (count > 0) {
            if (badgeElement) {
                badgeElement.textContent = count;
                badgeElement.style.display = 'inline-flex';
            } else {
                const badge = document.createElement('span');
                badge.id = 'notification-badge';
                badge.className = 'notification-badge';
                badge.textContent = count;
                
                const usernameElement = document.querySelector('.username');
                if (usernameElement) {
                    usernameElement.appendChild(badge);
                }
            }
            
            // Обновляем заголовок страницы
            document.title = `(${count}) Чат-мессенджер`;
        } else {
            if (badgeElement) {
                badgeElement.style.display = 'none';
            }
            document.title = 'Чат-мессенджер';
        }
    }
    
    // Показать уведомление в браузере
    function showNotification(message) {
        if (Notification.permission === 'granted') {
            new Notification('Чат-мессенджер', {
                body: message,
                icon: '/static/chat/notification-icon.png'
            });
        }
    }
    
    // Запрос разрешения на отправку уведомлений
    function requestNotificationPermission() {
        if ('Notification' in window) {
            if (Notification.permission !== 'granted' && Notification.permission !== 'denied') {
                Notification.requestPermission();
            }
        }
    }
    
    // Инициализация проверки уведомлений
    function init() {
        // Запрашиваем разрешение на уведомления
        requestNotificationPermission();
        
        // Первоначальная проверка непрочитанных сообщений
        checkUnreadMessages();
        
        // Устанавливаем интервал для проверки непрочитанных сообщений (каждые 30 секунд)
        notificationsInterval = setInterval(checkUnreadMessages, 30000);
        
        // Очистка интервала при уходе со страницы
        window.addEventListener('beforeunload', () => {
            clearInterval(notificationsInterval);
        });
    }
    
    return {
        init: init,
        checkNow: checkUnreadMessages
    };
}

// Добавляем CSS стили для значка уведомлений
function addNotificationStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .notification-badge {
            background-color: #f44336;
            color: white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            font-size: 12px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-left: 5px;
            position: relative;
            top: -2px;
        }
    `;
    document.head.appendChild(style);
}

// Запуск проверки уведомлений при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    addNotificationStyles();
    const notifications = setupNotificationsCheck();
    notifications.init();
    
    // Добавляем ссылку на notifications в глобальную область
    window.chatNotifications = notifications;
});