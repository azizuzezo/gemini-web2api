import os
import aiohttp
import json
import datetime
import config

SYSTEM_PROMPT = """Kamu adalah BalikLayar AI Assistant, asisten resmi komunitas kreator video AI dan affiliate duacincin.id / BalikLayar AI.

Keahlian & Karaktermu:
1. Sebagai Asisten Komunitas yang Pintar & Punya Ingatan Permanen:
   - Kamu memiliki akses ke Dokumen Knowledge Base Resmi dan Context Real-Time server.
   - Kamu mengingat semua instruksi atau ilmu yang diajarkan oleh Founder (Alfiqo) dan Moderator melalui command /train atau memori chat.
   - Kamu tahu informasi status server, jumlah member real-time, aturan server, rekomendasi tools, channel penting, dan profil Founder.
   - Jika ditanya "cek status", "status bot", "info server", atau pertanyaan seputar komunitas, jawab dengan ramah, akurat, dan percaya diri berdasarkan Knowledge Base.
2. Sebagai Mentor Kreator & Affiliate:
   - Menguasai ide konten video pendek (TikTok, Reels, Shorts), hook 3 detik pertama (pattern interrupt), retention, dan strategi affiliate marketing konversi tinggi.
   - Paham tools AI (CapCut, Midjourney, Kling, Runway, ElevenLabs, prompt engineering).

Gaya berkomunikasi:
- Ramah, antusias, berenergi positif, cerdas, dan suportif layaknya mentor kreator.
- Gunakan Bahasa Indonesia yang santai, luwes, dan berbobot.
- Format teks rapi (gunakan bullet points, bold `**`, atau emoji agar enak dibaca di Discord).
- Jangan melebihi 1800 karakter agar muat dalam satu pesan Discord.
"""

def get_knowledge_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "knowledge.md")

def get_knowledge_base() -> str:
    k_path = get_knowledge_path()
    if os.path.exists(k_path):
        try:
            with open(k_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def add_training_memory(topik: str, informasi: str, author_name: str) -> bool:
    """Menyimpan pengetahuan baru yang diajarkan Founder/Moderator ke knowledge.md secara permanen."""
    k_path = get_knowledge_path()
    now_str = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    entry = (
        f"\n\n### 🧠 [Ingatan Baru - {topik.strip()}]\n"
        f"- **Diajarkan oleh:** {author_name}\n"
        f"- **Waktu:** {now_str}\n"
        f"- **Pengetahuan:** {informasi.strip()}\n"
    )
    try:
        with open(k_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return True
    except Exception as e:
        print(f"Error saving training memory: {e}")
        return False

async def query_ai(prompt: str, user_name: str = "Kreator", server_context: str = "", chat_history: str = "") -> str:
    # Siapkan gabungan Knowledge Base, Server Context, dan Riwayat Obrolan
    k_data = get_knowledge_base()
    context_addon = ""
    if k_data:
        context_addon += f"\n\n[DOKUMEN KNOWLEDGE BASE RESMI & INGATAN PERMANEN]:\n{k_data}"
    if server_context:
        context_addon += f"\n\n[CONTEXT REAL-TIME SERVER BALIKLAYAR AI]:\n{server_context}"
    if chat_history:
        context_addon += f"\n\n[RIWAYAT CHAT SEBELUMNYA]:\n{chat_history}"

    full_user_content = f"Pertanyaan dari {user_name}:\n{prompt}{context_addon}"

    # 1. Coba DuaCincin (Local Gemini-Web2API Proxy) terlebih dahulu
    duacincin_url = getattr(config, "DUACINCIN_API_URL", "http://127.0.0.1:2014/v1/chat/completions")
    duacincin_key = getattr(config, "DUACINCIN_API_KEY", "sk-csportal")

    headers = {
        "Authorization": f"Bearer {duacincin_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": getattr(config, "AI_MODEL", "gemini-2.5-flash"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_user_content}
        ],
        "max_tokens": 850,
        "temperature": 0.7
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(duacincin_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "Maaf, respon kosong.")
    except Exception:
        pass

    # 2. Fallback ke Google AI Studio Gemini API jika GEMINI_API_KEY diset
    gemini_key = getattr(config, "GEMINI_API_KEY", "").strip()
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        payload_gemini = {
            "contents": [{"parts": [{"text": full_user_content}]}],
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {"maxOutputTokens": 850, "temperature": 0.7}
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload_gemini, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "Maaf, tidak ada respon.")
        except Exception:
            pass

    # 3. Fallback ke OpenAI API jika OPENAI_API_KEY diset
    openai_key = getattr(config, "OPENAI_API_KEY", "").strip()
    if openai_key:
        url_openai = "https://api.openai.com/v1/chat/completions"
        headers_openai = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url_openai, headers=headers_openai, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "Maaf, tidak ada respon.")
        except Exception:
            pass

    return (
        "🤖 **AI Sedang Memproses Informasi**\n\n"
        "Layanan AI lokal di SairiHost sedang bersiap. Coba ulangi pertanyaanmu dalam beberapa detik ya!"
    )
