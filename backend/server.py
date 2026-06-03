from fastapi import FastAPI, APIRouter, Request, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Update, Message, CallbackQuery, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── MongoDB ─────────────────────────────────────────────────────────────────
mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

# ─── Bot config (from .env) ───────────────────────────────────────────────────
BOT_TOKEN            = os.environ.get('BOT_TOKEN', '')
MAIN_CHANNEL_ID      = int(os.environ.get('MAIN_CHANNEL_ID', '-1002443521731'))
VIDEO_SOURCE_CHANNEL = os.environ.get('VIDEO_SOURCE_CHANNEL', '@krylatyvideoxxfsd')
VIDEO_NOTE_MSG_ID    = int(os.environ.get('VIDEO_NOTE_MSG_ID', '5'))
PRIVATE_CHANNEL_MSG_ID = int(os.environ.get('PRIVATE_CHANNEL_MSG_ID', '2'))
COPYTRADING_MSG_ID   = int(os.environ.get('COPYTRADING_MSG_ID', '3'))
FREE_LESSON_MSG_ID   = int(os.environ.get('FREE_LESSON_MSG_ID', '4'))
REVIEWS_LINK         = os.environ.get('REVIEWS_LINK', 'https://t.me/krylaty_otzyv')
ADMIN_LINK           = os.environ.get('ADMIN_LINK', 'https://t.me/krylaty_official')
WEBHOOK_BASE_URL     = os.environ.get('WEBHOOK_BASE_URL', '')
BOT_ID               = int(BOT_TOKEN.split(':')[0]) if ':' in BOT_TOKEN else 0

# ─── FSM States ───────────────────────────────────────────────────────────────
class MenuStates(StatesGroup):
    MAIN_MENU     = State()
    VIEWING_VIDEO = State()

# ─── Keyboards ────────────────────────────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📺  Приватный канал",       callback_data="btn_private")],
        [InlineKeyboardButton(text="📈  Копитрейдинг",          callback_data="btn_copytrading")],
        [InlineKeyboardButton(text="🎓  Бесплатный видео-урок",  callback_data="btn_free_lesson")],
        [InlineKeyboardButton(text="⭐  Отзывы",                url=REVIEWS_LINK)],
        [InlineKeyboardButton(text="✉️  Написать мне",           url=ADMIN_LINK)],
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад в меню", callback_data="btn_back")]
    ])

# ─── Bot helpers ──────────────────────────────────────────────────────────────
async def show_main_menu(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Отправляет кружочек + клавиатуру главного меню.
    Сохраняет ID обоих сообщений в FSM, чтобы удалить их при открытии видео."""
    await state.set_state(MenuStates.MAIN_MENU)

    # Кружочек — copy_message возвращает MessageId с полем .message_id
    note_result = await bot.copy_message(
        chat_id=chat_id,
        from_chat_id=VIDEO_SOURCE_CHANNEL,
        message_id=VIDEO_NOTE_MSG_ID,
    )

    # Меню с 5 кнопками — send_message возвращает Message с .message_id
    menu_msg = await bot.send_message(
        chat_id=chat_id,
        text="Выбери интересующий раздел 👇",
        reply_markup=main_menu_keyboard(),
    )

    # Сохраняем ID обоих сообщений, чтобы удалить при переходе к видео
    await state.update_data(
        note_msg_id=note_result.message_id,
        menu_msg_id=menu_msg.message_id,
    )

async def send_section_video(bot: Bot, chat_id: int, state: FSMContext, message_id: int) -> None:
    """Копирует видео из канала и добавляет кнопку «Назад»."""
    await state.set_state(MenuStates.VIEWING_VIDEO)
    logger.info("copy_message: from=%s msg=%d to chat=%d", VIDEO_SOURCE_CHANNEL, message_id, chat_id)
    await bot.copy_message(
        chat_id=chat_id,
        from_chat_id=VIDEO_SOURCE_CHANNEL,
        message_id=message_id,
        reply_markup=back_keyboard(),
    )

# ─── Bot + Dispatcher ─────────────────────────────────────────────────────────
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=storage)

# ─── Handlers ─────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    logger.info("/start from user %d", message.from_user.id)

    # Удаляем саму команду /start чтобы не засорять чат
    try:
        await message.delete()
    except Exception:
        pass

    # Удаляем предыдущие сообщения бота (кружочек + меню) если они были
    state_data = await state.get_data()
    for key in ("note_msg_id", "menu_msg_id"):
        msg_id = state_data.get(key)
        if msg_id:
            try:
                await bot.delete_message(message.chat.id, msg_id)
            except Exception:
                pass

    await show_main_menu(bot, message.chat.id, state)


@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_new_subscriber(event: ChatMemberUpdated):
    """Срабатывает при подписке на основной канал → пишет в ЛС."""
    logger.info("chat_member update: chat_id=%d, expected=%d", event.chat.id, MAIN_CHANNEL_ID)
    if event.chat.id != MAIN_CHANNEL_ID:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return
    logger.info("New subscriber: %d (@%s)", user.id, user.username or "—")
    private_state = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=BOT_ID, chat_id=user.id, user_id=user.id),
    )
    try:
        await show_main_menu(bot, user.id, private_state)
    except Exception as exc:
        logger.warning("Cannot DM user %d: %s", user.id, exc)


@dp.callback_query()
async def handle_callbacks(callback: CallbackQuery, state: FSMContext):
    """Единый обработчик всех inline-кнопок."""
    data = callback.data
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    logger.info("Button pressed: data=%s  user=%d  chat=%d", data, user_id, chat_id)

    try:
        await callback.answer()
    except Exception:
        pass  # Не критично если query уже устарел

    try:
        if data in ("btn_private", "btn_copytrading", "btn_free_lesson"):
            # 1. Удаляем меню — callback.message это ВСЕГДА то сообщение,
            #    на кнопку которого нажали. Самый надёжный способ.
            try:
                await callback.message.delete()
            except Exception:
                pass

            # 2. Удаляем кружочек по сохранённому ID
            state_data = await state.get_data()
            note_msg_id = state_data.get("note_msg_id")
            if note_msg_id:
                try:
                    await bot.delete_message(chat_id, note_msg_id)
                except Exception:
                    pass

            # 3. Отправляем видео с кнопкой «Назад»
            if data == "btn_private":
                await send_section_video(bot, chat_id, state, PRIVATE_CHANNEL_MSG_ID)
            elif data == "btn_copytrading":
                await send_section_video(bot, chat_id, state, COPYTRADING_MSG_ID)
            elif data == "btn_free_lesson":
                await send_section_video(bot, chat_id, state, FREE_LESSON_MSG_ID)

        elif data == "btn_back":
            # Удаляем видео и возвращаем главное меню
            try:
                await callback.message.delete()
            except Exception:
                pass
            await show_main_menu(bot, chat_id, state)

    except Exception as exc:
        logger.error("Error handling button %s for user %d: %s", data, user_id, exc)
        try:
            await bot.send_message(chat_id, "Произошла ошибка. Попробуй ещё раз — /start")
        except Exception:
            pass


# ─── FastAPI ──────────────────────────────────────────────────────────────────
app = FastAPI()
api_router = APIRouter(prefix="/api")


# ─── Existing models ──────────────────────────────────────────────────────────
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str


# ─── Existing routes ──────────────────────────────────────────────────────────
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj  = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks


# ─── Telegram webhook ─────────────────────────────────────────────────────────
@api_router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Принимает обновления от Telegram и передаёт диспетчеру.
    Всегда возвращает 200 — иначе Telegram будет повторять запрос."""
    try:
        data   = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
    except Exception as exc:
        logger.error("Webhook processing error: %s", exc)
    return Response(status_code=200)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Startup / Shutdown ───────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    if BOT_TOKEN and WEBHOOK_BASE_URL:
        webhook_url = f"{WEBHOOK_BASE_URL}/api/webhook/telegram"
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "chat_member"],
        )
        logger.info("Telegram webhook registered: %s", webhook_url)
    else:
        logger.warning("BOT_TOKEN or WEBHOOK_BASE_URL missing — webhook not set")


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
    if BOT_TOKEN:
        try:
            await bot.delete_webhook()
            await bot.session.close()
        except Exception:
            pass
