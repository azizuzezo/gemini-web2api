import os

# ==========================================
# BALIKLAYAR AI BOT - KONFIGURASI INTI
# ==========================================

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Fallback: jika dijalankan manual tanpa 'set -a && . ./.env', baca langsung dari file .env
if not BOT_TOKEN and os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DISCORD_BOT_TOKEN="):
                    BOT_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", 1568182411068571698))

# ID Channel Resmi BalikLayar AI
CHANNEL_WELCOME = 1568203755768520794      # ╭・📌・welcome
CHANNEL_RULES = 1568183637092995154        # ┃・📜・rules
CHANNEL_ANNOUNCEMENT = 1568188365726023713 # ┃・📢・pengumuman
CHANNEL_ROLES = 1568203759375351908       # ╰・🛡️・verifikasi-kreator
CHANNEL_CHAT = 1568182411874017292        # ╭・💬・ngobrol-santai
CHANNEL_LOGS = 1568203782276382770        # ╰・📋・bot-logs

# ID Roles Resmi Server
ROLE_FOUNDER = 1568184248312275046         # 👑 Founder
ROLE_MODERATOR = 1568185534352859207       # 🛡️ Moderator
ROLE_POWER_USER = 1568186072956141678      # ⚡ Power User
ROLE_KREATOR = 1568187130419613776         # 🚀 Kreator
ROLE_UNVERIFIED = 1568211792432336919      # ⏳ Unverified

# ==========================================
# AI INTEGRATION (SAIRIHOST DUACINCIN / FALLBACK)
# ==========================================
# DuaCincin API lokal di SairiHost (Port 2014)
DUACINCIN_API_URL = os.getenv("DUACINCIN_API_URL", "http://127.0.0.1:2014/v1/chat/completions")
DUACINCIN_API_KEY = os.getenv("DUACINCIN_API_KEY", "sk-csportal")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash")

# Fallback opsional jika ingin menggunakan API Key cloud
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


