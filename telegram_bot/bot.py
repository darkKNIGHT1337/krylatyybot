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
  1. Заполни блок КОНФИГУРАЦИЯ ниже (токен, ID канала, ссылки)
  2. Добавь бота в основной канал как АДМИНИСТРАТОРА
     (нужно право «видеть участников» / «Add Members»)
  3. Положи видео-файлы в папку videos/ (или вставь file_id)
  4. Пользователи ДОЛЖНЫ нажать /start в боте хотя бы раз,
     прежде чем бот сможет писать им в личку

КАК ПОЛУЧИТЬ file_id СВОЕГО ВИДЕО:
------------------------------------
  1. Запусти бота: python bot.py
  2. Отправь видео боту в личные сообщения
  3. Бот выведет file_id в консоль (лог INFO)
  4. Скопируй file_id и вставь в нужную переменную ниже

СТРУКТУРА ПАПОК:
-----------------
  bot.py
  requirements.txt
  videos/
      greeting_note.mp4   ← видео-кружочек
      private_channel.mp4 ← видео для кнопки «Приватный канал»
      copytrading.mp4     ← видео для кнопки «Копитрейдинг»
      free_lesson.mp4     ← видео для кнопки «Бесплатный видео-урок»
============================================================================
"""

import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
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
# ВИДЕО-ФАЙЛЫ
# ============================================================================
#
# Для каждого видео — два способа задать источник:
#   1. FILE_ID (строка вида "DQACAgI...") — самый быстрый, рекомендуется
#   2. PATH (путь к файлу) — для первой загрузки
#
# Если FILE_ID задан — PATH игнорируется.
# Если файл не найден — бот отправит текстовую заглушку с описанием.
#
# ФОРМАТ КРУЖОЧКА (video note):
#   - MP4, квадратное видео (например 512×512), длина до 1 минуты
#

# === ВСТАВЬ СВОЙ ВИДЕО-КРУЖОЧЕК ===
VIDEO_NOTE_FILE_ID: Optional[str] = None               # Вставь сюда file_id кружочка
VIDEO_NOTE_PATH: str = "videos/greeting_note.mp4"      # Или путь к файлу

# === ВСТАВЬ ВИДЕО ДЛЯ "Приватный канал" ===
PRIVATE_CHANNEL_FILE_ID: Optional[str] = None
PRIVATE_CHANNEL_PATH: str = "videos/private_channel.mp4"

# === ВСТАВЬ ВИДЕО ДЛЯ "Копитрейдинг" ===
COPYTRADING_FILE_ID: Optional[str] = None
COPYTRADING_PATH: str = "videos/copytrading.mp4"

# === ВСТАВЬ ВИДЕО ДЛЯ "Бесплатный видео-урок" ===
FREE_LESSON_FILE_ID: Optional[str] = None
FREE_LESSON_PATH: str = "videos/free_lesson.mp4"


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
    # Переключаем состояние в «главное меню»
    await state.set_state(MenuStates.MAIN_MENU)

    # --- Шаг 1: отправляем видео-кружочек ---
    if VIDEO_NOTE_FILE_ID:
        # Если уже знаем file_id — используем его (мгновенно, без загрузки)
        await bot.send_video_note(chat_id=chat_id, video_note=VIDEO_NOTE_FILE_ID)
    else:
        try:
            # === ВСТАВЬ СВОЙ ВИДЕО-КРУЖОЧЕК (путь к файлу) ===
            file = FSInputFile(VIDEO_NOTE_PATH)
            sent = await bot.send_video_note(chat_id=chat_id, video_note=file)
            # Сохрани этот file_id в переменную VIDEO_NOTE_FILE_ID,
            # чтобы не загружать файл каждый раз
            logger.info("Кружочек загружен. file_id: %s", sent.video_note.file_id)
        except FileNotFoundError:
            # ЗАГЛУШКА — файл не найден, отправляем текст
            logger.warning("Файл кружочка не найден: %s", VIDEO_NOTE_PATH)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🎥 *[Здесь будет видео-кружочек]*\n\n"
                    "_Положи файл в папку `videos/` или вставь `VIDEO_NOTE_FILE_ID` в коде_"
                ),
                parse_mode="Markdown",
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
    file_id: Optional[str],
    file_path: str,
    section_name: str,
) -> None:
    """
    Отправляет обычное видео (не кружочек) для выбранного раздела,
    с кнопкой «← Назад в меню» под ним.
    Устанавливает состояние FSM в VIEWING_VIDEO.

    Параметры:
        file_id      — Telegram file_id (если уже загружено, иначе None)
        file_path    — путь к файлу на диске
        section_name — название раздела (для логов и заглушки)
    """
    await state.set_state(MenuStates.VIEWING_VIDEO)

    if file_id:
        # Используем сохранённый file_id
        await bot.send_video(
            chat_id=chat_id,
            video=file_id,
            reply_markup=back_keyboard(),
        )
    else:
        try:
            file = FSInputFile(file_path)
            sent = await bot.send_video(
                chat_id=chat_id,
                video=file,
                reply_markup=back_keyboard(),
            )
            # Сохрани этот file_id в соответствующую переменную
            logger.info("Видео «%s» загружено. file_id: %s", section_name, sent.video.file_id)
        except FileNotFoundError:
            # ЗАГЛУШКА — файл не найден
            logger.warning("Файл видео не найден: %s", file_path)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎬 *[Видео «{section_name}»]*\n\n"
                    f"_Файл не найден: `{file_path}`\n"
                    "Положи файл в папку `videos/` или вставь нужный `file_id` в коде_"
                ),
                parse_mode="Markdown",
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
        file_id=PRIVATE_CHANNEL_FILE_ID,
        file_path=PRIVATE_CHANNEL_PATH,
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
        file_id=COPYTRADING_FILE_ID,
        file_path=COPYTRADING_PATH,
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
        file_id=FREE_LESSON_FILE_ID,
        file_path=FREE_LESSON_PATH,
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
# ВСПОМОГАТЕЛЬНЫЙ ХЭНДЛЕР: получить file_id отправленного видео
# ============================================================================

@dp.message(F.video)
async def on_video_received(message: Message) -> None:
    """
    Вспомогательный обработчик: выводит file_id любого видео,
    которое пользователь отправляет боту напрямую.
    Используй это, чтобы узнать file_id своих видео.
    """
    file_id = message.video.file_id
    logger.info("Получено видео. file_id: %s", file_id)
    await message.reply(
        f"✅ file_id этого видео:\n`{file_id}`\n\n"
        "Скопируй и вставь в нужную переменную в конфигурации бота.",
        parse_mode="Markdown",
    )


@dp.message(F.video_note)
async def on_video_note_received(message: Message) -> None:
    """
    Вспомогательный обработчик: выводит file_id кружочка.
    Отправь боту кружочек — и он вернёт file_id.
    """
    file_id = message.video_note.file_id
    logger.info("Получен кружочек. file_id: %s", file_id)
    await message.reply(
        f"✅ file_id этого кружочка:\n`{file_id}`\n\n"
        "Скопируй и вставь в переменную `VIDEO_NOTE_FILE_ID`.",
        parse_mode="Markdown",
    )


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

async def main() -> None:
    """Запуск бота в режиме long-polling."""
    me = await bot.get_me()
    logger.info("=" * 60)
    logger.info("Бот запущен:  @%s  (id=%d)", me.username, me.id)
    logger.info("Канал:        %d", MAIN_CHANNEL_ID)
    logger.info("Отзывы:       %s", REVIEWS_LINK)
    logger.info("Админ:        %s", ADMIN_LINK)
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
