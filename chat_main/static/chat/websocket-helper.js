// Функция для проверки, что сущность является объектом и не null
function isObject(obj) {
    return obj !== null && typeof obj === 'object';
}

// Функция для проверки, что WebSocket соединение существует и работает
function isWebSocketReady(ws) {
    return isObject(ws) && ws.readyState === WebSocket.OPEN;
}

// Функция для перезагрузки соединения
function reloadWebSocketConnection() {
    console.log('Перезагружаем страницу для восстановления соединения');
    window.location.reload();
}

// Глобальная функция для мониторинга WebSocket
function monitorWebSocket(ws, options = {}) {
    const defaults = {
        pingInterval: 30000,     // Интервал отправки пингов, ms
        pongTimeout: 10000,      // Время ожидания ответа на пинг, ms
        reconnectInterval: 5000, // Интервал переподключения, ms
        maxReconnectAttempts: 5, // Максимальное число попыток переподключения
        autoReload: true         // Автоматически перезагружать страницу при проблемах
    };
    
    const settings = {...defaults, ...options};
    let pingTimeout = null;
    let reconnectAttempts = 0;
    
    function heartbeat() {
        clearTimeout(pingTimeout);
        pingTimeout = setTimeout(() => {
            console.warn('Соединение WebSocket не отвечает');
            
            if (reconnectAttempts < settings.maxReconnectAttempts) {
                reconnectAttempts++;
                console.log(`Попытка переподключения ${reconnectAttempts}/${settings.maxReconnectAttempts}...`);
                
                // Запуск попытки переподключения через указанный интервал
                setTimeout(() => {
                    if (!isWebSocketReady(ws)) {
                        if (settings.onReconnect && typeof settings.onReconnect === 'function') {
                            settings.onReconnect(reconnectAttempts);
                        }
                    } else {
                        reconnectAttempts = 0;
                    }
                }, settings.reconnectInterval);
                
            } else if (settings.autoReload) {
                console.error('Исчерпано максимальное количество попыток переподключения');
                reloadWebSocketConnection();
            }
        }, settings.pongTimeout);
    }
    
    // Запуск периодического пинга WebSocket
    const pingInterval = setInterval(() => {
        if (isWebSocketReady(ws)) {
            ws.send(JSON.stringify({ type: 'ping', message: '_ping_' }));
            heartbeat();
        } else {
            console.warn('WebSocket не готов для отправки пинга');
            
            if (reconnectAttempts === 0 || reconnectAttempts >= settings.maxReconnectAttempts) {
                if (settings.autoReload) {
                    reloadWebSocketConnection();
                }
            }
        }
    }, settings.pingInterval);
    
    // Очистка интервалов при уходе со страницы
    window.addEventListener('beforeunload', () => {
        clearInterval(pingInterval);
        clearTimeout(pingTimeout);
    });
    
    return {
        stop: function() {
            clearInterval(pingInterval);
            clearTimeout(pingTimeout);
        }
    };
}