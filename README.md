Скачайте файлы проекта

Перейдите в папку chat_main

Пропишите команду создания виртуального окружения python -m venv venv и активируйте его venv\scripts\activate

Выполните команду pip install -r requirements.txt для установки зависимостей из файла requirements.txt

Выполните команду создания базы данных python manage.py makemigratons и примите миграции python manage.py migrate

Установите на ПК приложение Docker. Пропишите в другом терминале редактора кода команду docker run --name my-redis -d -p 6379:6379 redis для создания контейнера. 

Далее команду docker exec -it my-redis redis-cli ping для установки соединения (в консоли должно быть прописано PONG)

Запустите приложение с помощью команды python run_server 

Откройте 2 браузера и введите адрес проекта http://localhost:8000/chat

В обоих браузерах выполните регистрацию и добавьте друг друга в друзья, чтобы начать общение
