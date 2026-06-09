from aiogram import Dispatcher

dp = Dispatcher()

# Include handlers at import time — guarantees they're registered
# before any webhook request is processed, regardless of ready() state.
try:
    from .handlers import router as _router
    dp.include_router(_router)
except Exception:
    pass  # aiogram not installed; webhook.py will log and skip
