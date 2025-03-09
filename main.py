import os
import json
import logging
import asyncio
from colorama import Fore, init, Style
from telethon import TelegramClient, events
from telethon.tl.functions.channels import CreateChannelRequest, CreateForumTopicRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, Updates, UpdateNewChannelMessage

# Авто сбрасывание цвета
init(autoreset=True)

# Настройки (заменить на свои) 
api_id = 'ID'
api_hash = 'HASH'
phone = 'NUMBER'
group_title = 'SCOH_ГКР'

# Черный список
blacklist = {1194911765, 'andr3y_scoh'} # Необходимо вставить свой или чужой айди/тег (тег, без "@") , для исключения логирования

# Максимальное количество тем в Telegram
MAX_TOPICS = 200

# Инициализация клиента
client = TelegramClient('session_name', api_id, api_hash)

# Файл соответствия ID пользователя и ID темы
topic_ids_file = 'topic_ids.json'

# Проверяем наличие файла, если его нет — создаем пустой JSON
if not os.path.exists(topic_ids_file):
    with open(topic_ids_file, 'w') as f:
        json.dump({}, f)

# Загружаем данные из JSON-файла
try:
    with open(topic_ids_file, 'r') as f:
        topic_ids = json.load(f)
        if not isinstance(topic_ids, dict):
            topic_ids = {}
except (json.JSONDecodeError, FileNotFoundError):
    topic_ids = {}

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Сохранение ID тем в файл
async def save_topic_ids():
    with open(topic_ids_file, 'w') as f:
        json.dump(topic_ids, f, indent=4)

# Проверка черного списка
async def is_blacklisted(user):
    return user.id in blacklist or (user.username and user.username.lower() in [u.lower() for u in blacklist if isinstance(u, str)]) or user.id == 1194911765

# Уведомление об удалении темы
async def notify_topic_removal(client, group_id, topic_title):
    message = f"⚠️ {Fore.YELLOW}Достигнут лимит тем ({MAX_TOPICS}). Пожалуйста, удалите старую тему: {topic_title}{Style.RESET_ALL}"
    await client.send_message(entity=group_id, message=message)
    logger.warning(Fore.YELLOW + message)

# Очистка старых тем из JSON (Telegram API не позволяет удалять темы)
async def check_and_cleanup_topics(client, group_id):
    if len(topic_ids) >= MAX_TOPICS:
        oldest_user_id = list(topic_ids.keys())[0]  # Берем самого первого добавленного пользователя
        topic_title = f"Тема для {oldest_user_id}"
        await notify_topic_removal(client, group_id, topic_title)
        topic_ids.pop(oldest_user_id)  # Удаляем запись из JSON
        await save_topic_ids()

# Создание темы для пользователя
async def create_topic_for_user(client, group_id, user_id, username):
    await check_and_cleanup_topics(client, group_id)  # Проверяем лимит перед созданием новой темы
    try:
        result = await client(CreateForumTopicRequest(
            channel=group_id,
            title=f"Тема для {username} ({user_id})"
        ))
        # Извлекаем ID темы из Updates
        if isinstance(result, Updates):
            for update in result.updates:
                if isinstance(update, UpdateNewChannelMessage):
                    topic_id = update.message.id
                    topic_ids[str(user_id)] = topic_id
                    await save_topic_ids()
                    logger.info(Fore.GREEN + f"Создана тема {topic_id} для пользователя {user_id}")
                    return topic_id
            logger.error(Fore.RED + "Не удалось найти ID темы в обновлениях")
            return None
        else:
            logger.error(Fore.RED + f"Неизвестный тип ответа: {type(result)}")
            return None
    except Exception as e:
        logger.error(Fore.RED + f"Ошибка при создании темы для {user_id}: {e}")
        return None

# Пересылка сообщений
async def forward_message(client, group_id, event, topic_id):
    try:
        await client.send_message(
            entity=group_id,
            message=event.message,
            reply_to=topic_id  # Используем reply_to вместо message_thread_id
        )
        logger.info(Fore.CYAN + f"Переслано сообщение в тему {topic_id}")
    except Exception as e:
        logger.error(Fore.RED + f"Ошибка пересылки в тему {topic_id}: {e}")

# Основная функция
async def main():
    await client.start(phone)
    logger.info(Fore.GREEN + "Клиент запущен.")

    # Поиск или создание группы
    group = None
    dialogs = await client(GetDialogsRequest(
        offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(), limit=100, hash=0
    ))
    for dialog in dialogs.chats:
        if hasattr(dialog, 'title') and dialog.title == group_title:
            group = dialog
            break

    if not group:
        result = await client(CreateChannelRequest(
            title=group_title, about='Группа для пересылки сообщений', megagroup=True
        ))
        group = result.chats[0]
        logger.info(Fore.GREEN + f"Создана группа: {group_title}")

    group_id = group.id

    # Обработчик сообщений
    @client.on(events.NewMessage)
    async def handler(event):
        if event.is_private:
            user = await event.get_sender()
            if user.bot or await is_blacklisted(user):
                return

            user_id = str(user.id)
            topic_id = topic_ids.get(user_id)

            if not topic_id:
                topic_id = await create_topic_for_user(client, group_id, user_id, user.username)
                if not topic_id:
                    return

            await forward_message(client, group_id, event, topic_id)

    logger.info(Style.DIM + "Скрипт запущен. Жду сообщений.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.RED + "Скрипт остановлен!")
