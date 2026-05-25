"""
============================================================================
TELEGRAM BOT — Приветственный бот с видео-контентом
============================================================================

УСТАНОВКА:
----------
  pip install -r requirements.txt

ЗАПУСК:
-------
  python bot.py

ТРЕБОВАНИЯ К НАСТРОЙКЕ:
-----------------------
  1. Заполни блок КОНФИГУРАЦИЯ ниже (токен, ID каналов, ссылки)
  2. Добавь бота в ОСНОВНОЙ КАНАЛ как АДМИНИСТРАТОРА
     (нужно право «видеть участников» / «Add Members»)
  3. Добавь бота в КАНАЛ С ВИДЕО как АДМИНИСТРАТОРА
     (нужно право читать сообщения)
  4. Пользователи ДОЛЖНЫ нажать /start в боте хотя бы раз,
     прежде чем бот сможет писать им в личку

КАК РАБОТАЕТ ВИДЕО:
--------------------
  Бот копирует видео напрямую из Telegram-канала по ID сообщений.
  Никаких локальных файлов не нужно — только укажи:
    VIDEO_SOURCE_CHANNEL  — username канала с видео
    VIDEO_NOTE_MSG_ID     — ID сообщения с кружочком
    PRIVATE_CHANNEL_MSG_ID, COPYTRADING_MSG_ID, FREE_LESSON_MSG_ID — ID видео

  Ссылка на сообщение: https://t.me/channel/123  →  message_id = 123
============================================================================
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey


# ============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# КОНФИГУРАЦИЯ — ВСТАВЬ СВОИ ДАННЫЕ
# ============================================================================

# Токен бота (получить у @BotFather)
BOT_TOKEN: str = "8909864249:AAGfDR-ookDxTpcCJ0a8Y1_XuFrWxbf8jCA"

# ID основного канала (формат: -100XXXXXXXXXX)
# Бот реагирует на подписку именно на этот канал
MAIN_CHANNEL_ID: int = -1002443521731

# === ССЫЛКА НА КАНАЛ С ОТЗЫВАМИ ===
REVIEWS_LINK: str = "https://t.me/krylaty_otzyv"

# === ССЫЛКА НА ЛИЧНЫЙ АККАУНТ ===
ADMIN_LINK: str = "https://t.me/krylaty_official"


# ============================================================================
# ВИДЕО — ИСТОЧНИК СООБЩЕНИЙ
# ============================================================================
#
# Бот копирует видео прямо из Telegram-канала методом copy_message.
# Никаких локальных файлов не нужно.
#
# КАК УЗНАТЬ ID СООБЩЕНИЯ:
#   Открой сообщение в канале → Поделиться → Копировать ссылку
#   Ссылка вида https://t.me/krylatyvideoxxfsd/5  →  message_id = 5
#

# Канал-источник видео (бот должен быть в нём администратором)
VIDEO_SOURCE_CHANNEL: str = "@krylatyvideoxxfsd"

# === ВСТАВЬ СВОЙ ВИДЕО-КРУЖОЧЕК ===
# https://t.me/krylatyvideoxxfsd/5
VIDEO_NOTE_MSG_ID: int = 5

# === ВСТАВЬ ВИДЕО ДЛЯ "Приватный канал" ===
# https://t.me/krylatyvideoxxfsd/2
PRIVATE_CHANNEL_MSG_ID: int = 2

# === ВСТАВЬ ВИДЕО ДЛЯ "Копитрейдинг" ===
# https://t.me/krylatyvideoxxfsd/3
COPYTRADING_MSG_ID: int = 3

# === ВСТАВЬ ВИДЕО ДЛЯ "Бесплатный видео-урок" ===
# https://t.me/krylatyvideoxxfsd/4
FREE_LESSON_MSG_ID: int = 4


# ============================================================================
# ID БОТА (извлекаем из токена — не требует API-запроса)
# ============================================================================
BOT_ID: int = int(BOT_TOKEN.split(":")[0])


# ============================================================================
# СОСТОЯНИЯ FSM (Finite State Machine)
# ============================================================================

class MenuStates(StatesGroup):
    """Возможные состояния пользователя в боте."""
    MAIN_MENU = State()      # Пользователь видит главное меню
    VIEWING_VIDEO = State()  # Пользователь смотрит видео из раздела


# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура главного меню — 5 кнопок.
    Кнопки 1–3: видео (callback), кнопки 4–5: внешние ссылки (url).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📺  Приватный канал",       callback_data="btn_private")],
            [InlineKeyboardButton(text="📈  Копитрейдинг",          callback_data="btn_copytrading")],
            [InlineKeyboardButton(text="🎓  Бесплатный видео-урок",  callback_data="btn_free_lesson")],
            [InlineKeyboardButton(text="⭐  Отзывы",                url=REVIEWS_LINK)],
            [InlineKeyboardButton(text="✉️  Написать мне",           url=ADMIN_LINK)],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с единственной кнопкой «← Назад в меню»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад в меню", callback_data="btn_back")]
        ]
    )


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

async def show_main_menu(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """
    Показывает главное меню: сначала видео-кружочек, затем текст с кнопками.
    Устанавливает состояние FSM в MAIN_MENU.

    Вызывается при:
      - команде /start
      - возврате через кнопку «← Назад в меню»
      - новой подписке на канал
    """
    await state.set_state(MenuStates.MAIN_MENU)

    # --- Шаг 1: копируем видео-кружочек из канала с материалами ---
    # === ВСТАВЬ СВОЙ ВИДЕО-КРУЖОЧЕК === (сообщение №VIDEO_NOTE_MSG_ID в VIDEO_SOURCE_CHANNEL)
    await bot.copy_message(
        chat_id=chat_id,
        from_chat_id=VIDEO_SOURCE_CHANNEL,
        message_id=VIDEO_NOTE_MSG_ID,
    )

    # --- Шаг 2: отправляем текст с клавиатурой главного меню ---
    await bot.send_message(
        chat_id=chat_id,
        text="Выбери интересующий раздел 👇",
        reply_markup=main_menu_keyboard(),
    )


async def send_section_video(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    message_id: int,
    section_name: str,
) -> None:
    """
    Копирует видео из канала-источника и отправляет его пользователю
    с кнопкой «← Назад в меню».
    Устанавливает состояние FSM в VIEWING_VIDEO.

    Параметры:
        message_id   — ID сообщения с видео в VIDEO_SOURCE_CHANNEL
        section_name — название раздела (только для логов)
    """
    await state.set_state(MenuStates.VIEWING_VIDEO)

    logger.info("Отправка видео «%s» (msg_id=%d) пользователю %d", section_name, message_id, chat_id)

    # Копируем сообщение из канала и сразу добавляем кнопку «Назад»
    await bot.copy_message(
        chat_id=chat_id,
        from_chat_id=VIDEO_SOURCE_CHANNEL,
        message_id=message_id,
        reply_markup=back_keyboard(),
    )


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ БОТА И ДИСПЕТЧЕРА
# ============================================================================

# MemoryStorage хранит FSM-состояния в оперативной памяти.
# При перезапуске бота состояния сбрасываются — это нормально для данного кейса.
storage = MemoryStorage()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)


# ============================================================================
# ОБРАБОТЧИК КОМАНДЫ /start
# ============================================================================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Обработчик команды /start.
    Показывает главное меню (кружочек + 5 кнопок).
    Работает всегда, независимо от текущего состояния.
    """
    logger.info("/start от пользователя %d (@%s)", message.from_user.id, message.from_user.username or "—")
    await show_main_menu(bot, message.chat.id, state)


# ============================================================================
# ОБРАБОТЧИК ПОДПИСКИ НА КАНАЛ
# ============================================================================

@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_new_subscriber(event: ChatMemberUpdated) -> None:
    """
    Срабатывает, когда пользователь подписывается на Telegram-канал.
    Автоматически отправляет приветственное меню в личные сообщения.

    Условия работы:
      - Бот должен быть АДМИНИСТРАТОРОМ канала
      - Пользователь должен хотя бы раз нажать /start в боте
        (иначе Telegram не позволит боту писать ему в личку)
    """
    # Реагируем только на наш основной канал
    if event.chat.id != MAIN_CHANNEL_ID:
        return

    user = event.new_chat_member.user

    # Игнорируем других ботов
    if user.is_bot:
        return

    logger.info(
        "Новый подписчик: id=%d, username=@%s, имя=%s",
        user.id,
        user.username or "—",
        user.full_name,
    )

    # Создаём FSM-контекст для личного чата пользователя.
    # В личке chat_id совпадает с user_id.
    private_state = FSMContext(
        storage=storage,
        key=StorageKey(
            bot_id=BOT_ID,
            chat_id=user.id,   # личный чат
            user_id=user.id,
        ),
    )

    try:
        await show_main_menu(bot, user.id, private_state)
        logger.info("Приветствие отправлено пользователю %d", user.id)
    except Exception as exc:
        # Самая частая причина ошибки — пользователь ещё не нажал /start в боте.
        # В таком случае бот физически не может написать в личку.
        logger.warning(
            "Не удалось написать пользователю %d: %s\n"
            "  → Убедись, что пользователь нажал /start в боте.",
            user.id,
            exc,
        )


# ============================================================================
# ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ
# ============================================================================

@dp.callback_query(F.data == "btn_private")
async def on_btn_private(callback: CallbackQuery, state: FSMContext) -> None:
    """Кнопка «Приватный канал» — отправляет видео и кнопку «Назад»."""
    await callback.answer()  # убираем «часики» с кнопки
    logger.info("Нажато 'Приватный канал' пользователем %d", callback.from_user.id)

    # === ВСТАВЬ ВИДЕО ДЛЯ "Приватный канал" ===
    await send_section_video(
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
        message_id=PRIVATE_CHANNEL_MSG_ID,
        section_name="Приватный канал",
    )


@dp.callback_query(F.data == "btn_copytrading")
async def on_btn_copytrading(callback: CallbackQuery, state: FSMContext) -> None:
    """Кнопка «Копитрейдинг» — отправляет видео и кнопку «Назад»."""
    await callback.answer()
    logger.info("Нажато 'Копитрейдинг' пользователем %d", callback.from_user.id)

    # === ВСТАВЬ ВИДЕО ДЛЯ "Копитрейдинг" ===
    await send_section_video(
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
        message_id=COPYTRADING_MSG_ID,
        section_name="Копитрейдинг",
    )


@dp.callback_query(F.data == "btn_free_lesson")
async def on_btn_free_lesson(callback: CallbackQuery, state: FSMContext) -> None:
    """Кнопка «Бесплатный видео-урок» — отправляет видео и кнопку «Назад»."""
    await callback.answer()
    logger.info("Нажато 'Бесплатный видео-урок' пользователем %d", callback.from_user.id)

    # === ВСТАВЬ ВИДЕО ДЛЯ "Бесплатный видео-урок" ===
    await send_section_video(
        bot=bot,
        chat_id=callback.message.chat.id,
        state=state,
        message_id=FREE_LESSON_MSG_ID,
        section_name="Бесплатный видео-урок",
    )


# ============================================================================
# ОБРАБОТЧИК КНОПКИ «← Назад в меню»
# ============================================================================

@dp.callback_query(F.data == "btn_back")
async def on_btn_back(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Кнопка «← Назад в меню».
    Удаляет текущее сообщение с видео и возвращает пользователя
    в главное меню (кружочек + 5 кнопок).
    """
    await callback.answer()
    logger.info("Возврат в меню от пользователя %d", callback.from_user.id)

    # Удаляем сообщение с видео (и кнопкой «Назад»), чтобы не засорять чат
    try:
        await callback.message.delete()
    except Exception:
        pass  # Сообщение уже удалено или нет прав — не критично

    # Показываем главное меню заново
    await show_main_menu(bot, callback.message.chat.id, state)


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

async def main() -> None:
    """Запуск бота в режиме long-polling."""
    me = await bot.get_me()
    logger.info("=" * 60)
    logger.info("Бот запущен:      @%s  (id=%d)", me.username, me.id)
    logger.info("Основной канал:   %d", MAIN_CHANNEL_ID)
    logger.info("Канал с видео:    %s", VIDEO_SOURCE_CHANNEL)
    logger.info("Отзывы:           %s", REVIEWS_LINK)
    logger.info("Админ:            %s", ADMIN_LINK)
    logger.info("=" * 60)

    # allowed_updates — явно указываем типы обновлений, которые нужны боту:
    #   message         — личные сообщения (команды /start и пр.)
    #   callback_query  — нажатия на inline-кнопки
    #   chat_member     — изменения статуса участника канала (подписка/отписка)
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query", "chat_member"],
    )


if __name__ == "__main__":
    asyncio.run(main())
