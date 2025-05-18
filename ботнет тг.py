import os
import asyncio
import logging
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonPornography,
    InputReportReasonChildAbuse,
    InputReportReasonOther,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    UserNotMutualContactError,
    UserAlreadyParticipantError,
    SessionRevokedError,
    AuthKeyUnregisteredError,
)
from telethon.tl.functions.auth import SendCodeRequest, SignInRequest, CheckPasswordRequest
from telethon.tl.types import CodeSettings
from telethon.tl.custom import Button
import warnings
import re

logging.basicConfig(
    filename="telethon.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


warnings.filterwarnings("ignore", category=UserWarning)


API_ID = api_id
API_HASH = "your_api_hash"
BOT_TOKEN = "token"
ADMIN_IDS = {0123, 1000-7}
SESSIONS_FOLDER = "sessions"
SESSION_NAME = "bot"


bot = TelegramClient(SESSION_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN)

bot.__setattr__("state", "none")  


def load_sessions_from_folder():
    
    if not os.path.exists(SESSIONS_FOLDER):
        os.makedirs(SESSIONS_FOLDER)
        logger.info(f"Создана папка {SESSIONS_FOLDER}")
        return []

    session_files = [f for f in os.listdir(SESSIONS_FOLDER) if f.endswith(".session")]
    sessions = [os.path.join(SESSIONS_FOLDER, f) for f in session_files]
    logger.info(f"Найдено {len(sessions)} файлов сессий: {sessions}")
    return sessions


async def is_session_valid(session_file):
    
    client = None
    try:
        client = TelegramClient(session_file, API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning(f"Сессия {session_file} не авторизована")
            return False
        await client.get_me()
        logger.info(f"Сессия {session_file} валидна")
        return True
    except (SessionRevokedError, AuthKeyUnregisteredError) as e:
        logger.error(f"Недействительная сессия {session_file}: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки сессии {session_file}: {e}")
        return False
    finally:
        if client is not None:
            await client.disconnect()


async def ensure_user_entity(client, user_id=None, username=None):
    
    identifier = username if username else user_id
    logger.info(f"Получение сущности для {identifier}")
    try:
        peer = await client.get_input_entity(username or int(user_id))
        logger.info(f"Сущность для {identifier} найдена")
        return peer
    except Exception as e:
        logger.error(f"Ошибка получения сущности для {identifier}: {e}")
        return None


async def report_user(client, user_id=None, username=None):
    
    reasons = [
        InputReportReasonSpam(),
        InputReportReasonViolence(),
        InputReportReasonPornography(),
        InputReportReasonChildAbuse(),
        InputReportReasonOther(),
    ]
    success_count = fail_count = flood_count = 0
    identifier = username if username else user_id
    peer = await ensure_user_entity(client, user_id, username)
    if not peer:
        logger.error(f"Не удалось получить сущность для {identifier}")
        return 0, 1, 0

    for reason in reasons:
        try:
            await client(
                functions.account.ReportPeerRequest(
                    peer=peer, reason=reason, message="Автоматическая жалоба"
                )
            )
            success_count += 1
            logger.info(f"Жалоба на {identifier}: {reason.__class__.__name__}")
        except FloodWaitError as e:
            logger.warning(f"Ограничение на жалобу для {identifier}: {e.seconds} секунд")
            flood_count += 1
        except Exception as e:
            logger.error(f"Ошибка жалобы на {identifier}: {e}")
            fail_count += 1
    return success_count, fail_count, flood_count


async def report_message(client, chat_username, message_id):
    
    reasons = [
        InputReportReasonSpam(),
        InputReportReasonViolence(),
        InputReportReasonPornography(),
        InputReportReasonChildAbuse(),
        InputReportReasonOther(),
    ]
    success_count = fail_count = flood_count = 0
    try:
        peer = await client.get_input_entity(chat_username)
        for reason in reasons:
            try:
                await client(
                    functions.messages.ReportRequest(
                        peer=peer,
                        id=[int(message_id)],
                        reason=reason,
                        message="Автоматическая жалоба",
                    )
                )
                success_count += 1
                logger.info(f"Жалоба на сообщение {message_id} в {chat_username}: {reason.__class__.__name__}")
            except FloodWaitError as e:
                logger.warning(f"Ограничение на жалобу для сообщения {message_id}: {e.seconds} секунд")
                flood_count += 1
            except Exception as e:
                logger.error(f"Ошибка жалобы на сообщение {message_id}: {e}")
                fail_count += 1
        return success_count, fail_count, flood_count
    except Exception as e:
        logger.error(f"Не удалось найти чат {chat_username}: {e}")
        return 0, 1, 0


async def join_channel(client, link):
    
    try:
        invite_match = re.match(r"https://t\.me/\+([A-Za-z0-9_-]+)", link)
        if invite_match:
            invite_hash = invite_match.group(1)
            await client(ImportChatInviteRequest(hash=invite_hash))
            logger.info(f"Подписка на приватную ссылку {link}")
            return 1, 0, 0

        public_match = re.match(r"https://t\.me/([A-Za-z0-9_]+)", link)
        if public_match:
            channel_username = public_match.group(1)
            entity = await client.get_entity(channel_username)
            await client(JoinChannelRequest(entity))
            logger.info(f"Подписка на публичную ссылку {link}")
            return 1, 0, 0

        raise ValueError("Неверный формат ссылки")
    except UserAlreadyParticipantError:
        logger.info(f"Уже подписан на {link}")
        return 1, 0, 0
    except FloodWaitError as e:
        logger.warning(f"Ограничение на подписку для {link}: {e.seconds} секунд")
        return 0, 0, 1
    except Exception as e:
        logger.error(f"Ошибка подписки на {link}: {e}")
        return 0, 1, 0


async def interact_with_bot(client, bot_identifier):
    
    try:
        
        if bot_identifier.startswith("https://t.me/"):
            parts = bot_identifier.replace("https://t.me/", "").split("?")
            bot_username = parts[0].split("/")[0]
            
            start_param = None
            if len(parts) > 1:
                params = parts[1].split("&")
                for param in params:
                    if param.startswith("start="):
                        start_param = param.replace("start=", "")
                        break
        else:
            bot_username = bot_identifier.lstrip("@")
            start_param = None

        
        entity = await client.get_entity(bot_username)
        
        command = f"/start {start_param}" if start_param else "/start"
        await client(SendMessageRequest(peer=entity, message=command))
        logger.info(f"Отправлен {command} боту {bot_username}")
        return 1, 0, 0  
    except ValueError as e:
        logger.error(f"Неверный формат bot_identifier {bot_identifier}: {e}")
        return 0, 1, 0
    except FloodWaitError as e:
        logger.warning(f"Ограничение для бота {bot_username}: {e.seconds} секунд")
        return 0, 0, 1
    except Exception as e:
        logger.error(f"Ошибка взаимодействия с ботом {bot_username}: {e}")
        return 0, 1, 0


async def report_user_by_id(user_id=None, username=None, event=None, sessions=None):
    
    valid = ne_valid = flood = 0
    user_id_sender = event.sender_id
    identifier = username if username else user_id
    logger.info(f"Жалоба на {identifier} от {user_id_sender}")

    for session_file in sessions:
        client = None
        try:
            client = TelegramClient(session_file, API_ID, API_HASH)
            if not await is_session_valid(session_file):
                logger.warning(f"Сессия {session_file} недействительна")
                ne_valid += 1
                continue

            await client.connect()
            success, fail, flood_count = await report_user(client, user_id, username)
            valid += 1 if success > 0 else 0
            ne_valid += 1 if success == 0 else 0
            flood += flood_count
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка сессии {session_file}: {e}")
            ne_valid += 1
        finally:
            if client is not None:
                await client.disconnect()

    message = (
        f"{'Не удалось отправить жалобы' if valid == 0 else 'Жалобы отправлены'} на {identifier}!\n"
        f"Валидные сессии: {valid}\nНевалидные сессии: {ne_valid}\nОграничения: {flood}"
    )
    await event.reply(message, buttons=[Button.inline("Назад", b"back")])

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"Жалоба:\nID отправителя: {user_id_sender}\nЦель: {identifier}\n"
            f"Валидные: {valid}\nНевалидные: {ne_valid}\nОграничения: {flood}",
        )


async def report_by_link(chat_username, message_id, user_id, event, sessions):
    
    valid = ne_valid = flood = 0
    logger.info(f"Жалоба на https://t.me/{chat_username}/{message_id} от {user_id}")

    for session_file in sessions:
        client = None
        try:
            client = TelegramClient(session_file, API_ID, API_HASH)
            if not await is_session_valid(session_file):
                logger.warning(f"Сессия {session_file} недействительна")
                ne_valid += 1
                continue

            await client.connect()
            success, fail, flood_count = await report_message(client, chat_username, message_id)
            valid += 1 if success > 0 else 0
            ne_valid += 1 if success == 0 else 0
            flood += flood_count
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка сессии {session_file}: {e}")
            ne_valid += 1
        finally:
            if client is not None:
                await client.disconnect()

    message = (
        f"{'Не удалось отправить жалобы' if valid == 0 else 'Жалобы отправлены'} на https://t.me/{chat_username}/{message_id}!\n"
        f"Валидные сессии: {valid}\nНевалидные сессии: {ne_valid}\nОграничения: {flood}"
    )
    await event.reply(message, buttons=[Button.inline("Назад", b"back")])

    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"Жалоба:\nID отправителя: {user_id}\nСсылка: https://t.me/{chat_username}/{message_id}\n"
            f"Валидные: {valid}\nНевалидные: {ne_valid}\nОграничения: {flood}",
        )


def check_admin(sender_id):
    
    logger.info(f"Проверка администратора: sender_id={sender_id}")
    return sender_id in ADMIN_IDS


@bot.on(events.NewMessage(pattern="^/start$"))
async def start(event):
    
    logger.info(f"/start от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "none")
    buttons = [
        [Button.inline("Жалобы", b"jaloby"), Button.inline("Рефералы в бота", b"boty")],
        [Button.inline("Подписки на канал", b"podpiski")],
        [
            Button.inline("Добавить сессию", b"dobavit"),
            Button.inline("Добавить файл сессии", b"dobavit_file"),
            Button.inline("Проверить сессии", b"proverit"),
        ],
    ]
    await event.reply("Выберите действие:", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"back"))
async def back_callback(event):
    
    logger.info(f"Кнопка Назад от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "none")
    buttons = [
        [Button.inline("Жалобы", b"jaloby"), Button.inline("Рефералы в бота", b"boty")],
        [Button.inline("Подписки на канал", b"podpiski")],
        [
            Button.inline("Добавить сессию", b"dobavit"),
            Button.inline("Добавить файл сессии", b"dobavit_file"),
            Button.inline("Проверить сессии", b"proverit"),
        ],
    ]
    await event.edit("Выберите действие:", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"jaloby"))
async def reports_callback(event):
    
    logger.info(f"Кнопка Жалобы от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "awaiting_report")
    await event.reply(
        "Отправьте ссылку на сообщение, ID или @username для жалобы:",
        buttons=[Button.inline("Назад", b"back")],
    )


@bot.on(events.CallbackQuery(data=b"podpiski"))
async def subscriptions_callback(event):
    
    logger.info(f"Кнопка Подписки от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "awaiting_subscription")
    await event.reply(
        "Введите ссылку на канал (публичную или приватную), общее количество подписчиков, количество за интервал и интервал в минутах (через пробел):\nПример: https://t.me/chlen 20 3 1",
        buttons=[Button.inline("Назад", b"back")],
    )


@bot.on(events.CallbackQuery(data=b"boty"))
async def bots_callback(event):
    
    logger.info(f"Кнопка Рефералы от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "awaiting_referral")
    await event.reply(
        "Введите @юз или ссылку на бота, общее количество рефералов, количество за интервал и интервал в минутах (через пробел):\nПример: @Bot 20 3 1",
        buttons=[Button.inline("Назад", b"back")],
    )


@bot.on(events.CallbackQuery(data=b"dobavit"))
async def add_session_callback(event):
    
    logger.info(f"Кнопка Добавить сессию от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "adding_session")
    await event.reply(
        "Введите номер телефона (например, +79998882211):",
        buttons=[Button.inline("Назад", b"back")],
    )


@bot.on(events.CallbackQuery(data=b"dobavit_file"))
async def add_session_file_callback(event):
    
    logger.info(f"Кнопка Добавить файл сессии от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    bot.__setattr__("state", "awaiting_session_file")
    await event.reply(
        "Отправьте файл сессии (например, +79998882211.session):",
        buttons=[Button.inline("Назад", b"back")],
    )


@bot.on(events.CallbackQuery(data=b"proverit"))
async def check_sessions_callback(event):
    
    logger.info(f"Кнопка Проверить сессии от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    try:
        sessions = load_sessions_from_folder()
        valid_sessions = invalid_sessions = 0

        for session_file in sessions:
            if await is_session_valid(session_file):
                valid_sessions += 1
            else:
                invalid_sessions += 1

        await event.reply(
            f"Всего сессий: {len(sessions)}\nВалидных: {valid_sessions}\nНевалидных: {invalid_sessions}",
            buttons=[Button.inline("Назад", b"back")],
        )
    except Exception as e:
        logger.error(f"Ошибка проверки сессий: {e}")
        await event.reply(f"Ошибка проверки сессий: {str(e)}", buttons=[Button.inline("Назад", b"back")])


@bot.on(events.NewMessage)
async def handle_subscription_input(event):
    
    logger.info(f"Ввод подписок от {event.sender_id}: {event.raw_text}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "awaiting_subscription":
        return

    text = event.raw_text.strip()
    parts = text.split()
    if len(parts) != 4:
        await event.reply("Неверный формат! Введите ссылку, общее количество, количество за интервал и интервал в минутах (через пробел).")
        return

    link = parts[0]
    try:
        total_count = int(parts[1])
        per_interval = int(parts[2])
        interval_minutes = int(parts[3])
    except ValueError:
        await event.reply("Общее количество, количество за интервал и интервал должны быть числами!")
        return

    if total_count <= 0 or per_interval <= 0 or interval_minutes <= 0:
        await event.reply("Все числа должны быть больше 0!")
        return

    sessions = load_sessions_from_folder()
    if not sessions:
        await event.reply("Нет валидных сессий!")
        return

    total_success = total_fail = total_flood = 0
    used_sessions = set()
    remaining = total_count

    while remaining > 0:
        current_batch = min(per_interval, remaining)  
        logger.info(f"Обрабатываем {current_batch} подписчиков, осталось {remaining}")

        for session_file in sessions:
            if len(used_sessions) >= current_batch:
                break

            if session_file in used_sessions:
                continue

            client = None
            try:
                client = TelegramClient(session_file, API_ID, API_HASH)
                if not await is_session_valid(session_file):
                    logger.warning(f"Сессия {session_file} недействительна")
                    total_fail += 1
                    used_sessions.add(session_file)
                    continue

                await client.connect()
                success, fail, flood = await join_channel(client, link)
                total_success += success
                total_fail += fail
                total_flood += flood
                used_sessions.add(session_file)
                logger.info(f"Сессия {session_file}: успех={success}, неудача={fail}, ограничение={flood}")
            except Exception as e:
                logger.error(f"Ошибка сессии {session_file}: {e}")
                total_fail += 1
                used_sessions.add(session_file)
            finally:
                if client is not None:
                    await client.disconnect()

        remaining -= current_batch
        if remaining > 0:
            logger.info(f"Ожидание {interval_minutes} минут перед следующим циклом")
            await asyncio.sleep(interval_minutes * 60)

    bot.__setattr__("state", "none")
    await event.reply(
        f"Подписки завершены!\nУспешно: {total_success}\nНеуспешно: {total_fail}\nОграничения: {total_flood}",
        buttons=[Button.inline("Назад", b"back")],
    )
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"Подписки:\nСсылка: {link}\nУспешно: {total_success}\nНеуспешно: {total_fail}\nОграничения: {total_flood}",
        )


@bot.on(events.NewMessage)
async def handle_bot_input(event):
    
    logger.info(f"Ввод рефералов от {event.sender_id}: {event.raw_text}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "awaiting_referral":
        return

    text = event.raw_text.strip()
    parts = text.split()
    if len(parts) != 4:
        await event.reply("Неверный формат! Введите @username или ссылку, общее количество, количество за интервал и интервал в минутах (через пробел).")
        return

    bot_identifier = parts[0]
    try:
        total_count = int(parts[1])
        per_interval = int(parts[2])
        interval_minutes = int(parts[3])
    except ValueError:
        await event.reply("Общее количество, количество за интервал и интервал должны быть числами!")
        return

    if total_count <= 0 or per_interval <= 0 or interval_minutes <= 0:
        await event.reply("Все числа должны быть больше 0!")
        return

    sessions = load_sessions_from_folder()
    if not sessions:
        await event.reply("Нет валидных сессий!")
        return

    total_success = total_fail = total_flood = 0
    used_sessions = set()
    remaining = total_count

    while remaining > 0:
        current_batch = min(per_interval, remaining)  
        logger.info(f"Обрабатываем {current_batch} рефералов, осталось {remaining}")

        for session_file in sessions:
            if len(used_sessions) >= current_batch:
                break

            if session_file in used_sessions:
                continue

            client = None
            try:
                client = TelegramClient(session_file, API_ID, API_HASH)
                if not await is_session_valid(session_file):
                    logger.warning(f"Сессия {session_file} недействительна")
                    total_fail += 1
                    used_sessions.add(session_file)
                    continue

                await client.connect()
                success, fail, flood = await interact_with_bot(client, bot_identifier)
                total_success += success
                total_fail += fail
                total_flood += flood
                used_sessions.add(session_file)
                logger.info(f"Сессия {session_file}: успех={success}, неудача={fail}, ограничение={flood}")
            except Exception as e:
                logger.error(f"Ошибка сессии {session_file}: {e}")
                total_fail += 1
                used_sessions.add(session_file)
            finally:
                if client is not None:
                    await client.disconnect()

        remaining -= current_batch
        if remaining > 0:
            logger.info(f"Ожидание {interval_minutes} минут перед следующим циклом")
            await asyncio.sleep(interval_minutes * 60)

    bot.__setattr__("state", "none")
    await event.reply(
        f"Рефералы завершены!\nУспешно: {total_success}\nНеуспешно: {total_fail}\nОграничения: {total_flood}",
        buttons=[Button.inline("Назад", b"back")],
    )
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"Рефералы:\nБот: {bot_identifier}\nУспешно: {total_success}\nНеуспешно: {total_fail}\nОграничения: {total_flood}",
        )


@bot.on(events.NewMessage)
async def handle_report_input(event):
    
    logger.info(f"Ввод жалобы от {event.sender_id}: {event.raw_text}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "awaiting_report":
        return

    if event.raw_text.strip() == "/start":
        return

    sessions = load_sessions_from_folder()
    if not sessions:
        await event.reply("Нет валидных сессий!")
        return

    text = event.raw_text.strip()
    try:
        
        link_match = re.match(r"https://t\.me/([^\s/]+)/(\d+)", text)
        if link_match:
            chat_username = link_match.group(1)
            message_id = int(link_match.group(2))
            logger.info(f"Жалоба на ссылку: https://t.me/{chat_username}/{message_id}")
            await report_by_link(chat_username, message_id, event.sender_id, event, sessions)
            bot.__setattr__("state", "none")
            return

        
        username_match = re.match(r"@([A-Za-z0-9_]+)", text)
        if username_match:
            username = username_match.group(0)
            logger.info(f"Жалоба на username: {username}")
            await report_user_by_id(username=username, event=event, sessions=sessions)
            bot.__setattr__("state", "none")
            return

        
        if text.isdigit() and len(text) > 5:
            user_id = int(text)
            logger.info(f"Жалоба на ID: {user_id}")
            await report_user_by_id(user_id=user_id, event=event, sessions=sessions)
            bot.__setattr__("state", "none")
            return

        await event.reply("Неверный формат! Отправьте ссылку, ID (более 5 цифр) или @username.")
    except Exception as e:
        logger.error(f"Ошибка обработки жалобы: {e}")
        await event.reply(f"Ошибка: {str(e)}", buttons=[Button.inline("Назад", b"back")])
        bot.__setattr__("state", "none")


@bot.on(events.NewMessage(pattern=r"\+[0-9]+"))
async def handle_phone(event):
    
    logger.info(f"Ввод номера телефона от {event.sender_id}: {event.raw_text}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "adding_session":
        return

    phone = event.raw_text.strip()
    client = None
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent_code = await client(
            SendCodeRequest(
                phone_number=phone, api_id=API_ID, api_hash=API_HASH, settings=CodeSettings()
            )
        )
        await event.reply(
            f"Код отправлен на {phone}. Введите 5-значный код:",
            buttons=[Button.inline("Назад", b"back")],
        )
        bot.__setattr__("state", "awaiting_code")
        bot.__setattr__("last_phone", phone)
        bot.__setattr__("last_client", client)
        bot.__setattr__("last_phone_code_hash", sent_code.phone_code_hash)
    except Exception as e:
        logger.error(f"Ошибка отправки кода на {phone}: {e}")
        await event.reply(f"Ошибка отправки кода: {e}", buttons=[Button.inline("Назад", b"back")])
        bot.__setattr__("state", "none")
        if client is not None:
            await client.disconnect()


@bot.on(events.NewMessage(pattern=r"^\d{5}$"))
async def handle_code(event):
    
    logger.info(f"Ввод кода от {event.sender_id}: {event.raw_text}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "awaiting_code":
        return

    code = event.raw_text.strip()
    phone = getattr(bot, "last_phone", None)
    client = getattr(bot, "last_client", None)
    phone_code_hash = getattr(bot, "last_phone_code_hash", None)

    if not phone or not client or not phone_code_hash:
        await event.reply("Сначала введите номер телефона или произошла ошибка!")
        bot.__setattr__("state", "none")
        return

    try:
        await client(SignInRequest(phone_number=phone, phone_code_hash=phone_code_hash, phone_code=code))
        session_string = client.session.save()
        if not os.path.exists(SESSIONS_FOLDER):
            os.makedirs(SESSIONS_FOLDER)
        session_file = os.path.join(SESSIONS_FOLDER, f"{phone}.session")
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(session_string)
        await event.reply(
            f"Сессия для {phone} добавлена!",
            buttons=[Button.inline("Назад", b"back")],
        )
        bot.__setattr__("state", "none")
        bot.__setattr__("last_phone", None)
        bot.__setattr__("last_client", None)
        bot.__setattr__("last_phone_code_hash", None)
    except Exception as e:
        if "SESSION_PASSWORD_NEEDED" in str(e):
            await event.reply(
                f"Требуется двухфакторная аутентификация. Введите пароль:",
                buttons=[Button.inline("Назад", b"back")],
            )
            bot.__setattr__("state", "awaiting_2fa")
        else:
            logger.error(f"Ошибка входа для {phone}: {e}")
            await event.reply(f"Ошибка: {e}", buttons=[Button.inline("Назад", b"back")])
            bot.__setattr__("state", "none")
    finally:
        if client is not None:
            await client.disconnect()


@bot.on(events.NewMessage)
async def handle_2fa_password(event):
    
    logger.info(f"Ввод пароля 2FA от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "awaiting_2fa":
        return

    password = event.raw_text.strip()
    phone = getattr(bot, "last_phone", None)
    client = getattr(bot, "last_client", None)
    phone_code_hash = getattr(bot, "last_phone_code_hash", None)

    if not phone or not client or not phone_code_hash:
        await event.reply("Данные сессии отсутствуют!")
        bot.__setattr__("state", "none")
        return

    try:
        await client(CheckPasswordRequest(password=password))
        session_string = client.session.save()
        if not os.path.exists(SESSIONS_FOLDER):
            os.makedirs(SESSIONS_FOLDER)
        session_file = os.path.join(SESSIONS_FOLDER, f"{phone}.session")
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(session_string)
        await event.reply(
            f"Сессия для {phone} с 2FA добавлена!",
            buttons=[Button.inline("Назад", b"back")],
        )
        bot.__setattr__("state", "none")
        bot.__setattr__("last_phone", None)
        bot.__setattr__("last_client", None)
        bot.__setattr__("last_phone_code_hash", None)
    except Exception as e:
        logger.error(f"Ошибка 2FA для {phone}: {e}")
        await event.reply(f"Ошибка 2FA: {e}", buttons=[Button.inline("Назад", b"back")])
        bot.__setattr__("state", "none")
    finally:
        if client is not None:
            await client.disconnect()


@bot.on(events.NewMessage)
async def handle_session_file(event):
   
    logger.info(f"Получен файл от {event.sender_id}")
    if not check_admin(event.sender_id):
        await event.reply("Доступ запрещён!")
        return
    if bot.state != "awaiting_session_file":
        return

    if not event.document:
        await event.reply("Пожалуйста, отправьте файл сессии (.session)!")
        return

    file_name = event.document.attributes[0].file_name if event.document.attributes else None
    if not file_name or not file_name.endswith(".session"):
        await event.reply("Файл должен иметь расширение .session и имя в формате +79991234567.session!")
        bot.__setattr__("state", "none")
        return

    if not re.match(r"\+[0-9]+\.session", file_name):
        await event.reply("Имя файла должно быть в формате +79991234567.session!")
        bot.__setattr__("state", "none")
        return

    client = None
    try:
        if not os.path.exists(SESSIONS_FOLDER):
            os.makedirs(SESSIONS_FOLDER)
        session_file = os.path.join(SESSIONS_FOLDER, file_name)
        await event.download_media(file=session_file)

        with open(session_file, "r", encoding="utf-8") as f:
            session_string = f.read().strip()
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        if await is_session_valid(client.session.filename):
            await event.reply(
                f"Сессия {file_name} успешно добавлена!",
                buttons=[Button.inline("Назад", b"back")],
            )
        else:
            os.remove(session_file)
            await event.reply(
                f"Сессия {file_name} недействительна!",
                buttons=[Button.inline("Назад", b"back")],
            )
    except Exception as e:
        logger.error(f"Ошибка обработки файла сессии {file_name}: {e}")
        await event.reply(f"Ошибка обработки файла: {e}", buttons=[Button.inline("Назад", b"back")])
    finally:
        bot.__setattr__("state", "none")
        if client is not None:
            await client.disconnect()


async def main():
    
    await bot.run_until_disconnected()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    finally:
        loop.close()