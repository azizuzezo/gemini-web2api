import os
import re
import aiohttp
import json
import datetime
import config

SYSTEM_PROMPT = """Kamu adalah BalikLayar AI, rekan dan asisten resmi komunitas kreator video AI & affiliate duacincin.id / BalikLayar AI.

ATURAN GAYA BAHASA (MUTLAK & KETAT):
1. DILARANG KERAS menggunakan salam pembuka apa pun! (JANGAN PERNAH tulis "Halo", "Hai", "Halo kak", "Halo Kak [nama]", "Halo Sobat", "Selamat pagi/siang/malam", atau format CS lainnya).
2. DILARANG menyebut nama penanya di awal kalimat.
3. KATA PERTAMA DARI JAWABANMU HARUS LANGSUNG MENJAWAB INTI PERSOALAN! Bicaralah selayaknya manusia sesama kreator yang sedang ngobrol di Discord: santai, cerdas, solutif, percaya diri, dan to-the-point.
4. Gunakan istilah praktis kreator (hook, retention, FYP, CTR, affiliate, workflow, prompt, visual cue).

ATURAN MENTION / TAG DISCORD (WAJIB & LANGSUNG EKSEKUSI):
- Jika pengguna menyuruhmu me-mention atau men-tag seseorang (misalnya: "tag founder", "mention mas fiqo", "panggil admin", "tag penanya", "mention saya", dll.):
  * KAMU WAJIB LANGSUNG MENULISKAN MENTION TERSEBUT DALAM PESANMU!
  * DILARANG MENOLAK, DILARANG RAGU-RAGU, DAN DILARANG MEMBUAT ALASAN (seperti "biar nggak salah sambung", "takut mengganggu", dll.).
  * Tulis tag mention Discord yang valid langsung di kalimatmu:
    - Founder / Pemilik (Mas Alfiqo): <@799987598726135818>
    - Penanya: gunakan tag mention penanya sesuai data di context (<@ID_PENANYA>)
    - Role Kreator: <@&1568187130419613776>
    - Role Moderator: <@&1568185534352859207>

PENGETAHUAN & INGATAN:
- Kamu memiliki akses ke Dokumen Knowledge Base Resmi (`knowledge.md`) dan Context Real-Time server.
- Kamu mengingat semua instruksi atau ilmu yang diajarkan oleh Founder (Alfiqo) dan Moderator.
- Jika ditanya "cek status", "status server", atau "status bot", berikan ringkasan status operasional server, jumlah member, dan DuaCincin API secara jelas dan to-the-point.
- Format teks rapi (gunakan bullet points atau bold `**` jika perlu).
- Maksimal 1800 karakter agar muat dalam satu pesan Discord.
"""

def clean_ai_response(text: str) -> str:
    """Membersihkan sapaan kaku/robotik seperti Halo Kak [nama] jika AI masih mencoba memunculkannya."""
    if not text:
        return text
    cleaned = text.strip()
    # Hapus salam pembuka di awal baris pertama beserta emoji/tanda baca yang menyertainya
    pattern = r'^(?:(?:halo|hai|hey|hello|selamat\s+(?:pagi|siang|sore|malam))\b(?:\s+(?:kakak|kak|om|bang|bro|gan|min|sobat|teman-teman))?(?:\s+[^\n!.,?:]{1,35})?)[\s!,.:\-\?]*[^\w\s\n]*[\s!,.:\-\?]*\n*'
    res = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
    if res and len(res) > 1:
        res = res[0].upper() + res[1:]
    return res if res else cleaned

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

    # Langsung teruskan prompt tanpa prefix 'Pesan dari [nama]' agar AI tidak latah menyapa nama
    full_user_content = f"{prompt}{context_addon}"

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
                        raw_reply = choices[0].get("message", {}).get("content", "Maaf, respon kosong.")
                        return clean_ai_response(raw_reply)
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
                                raw_reply = parts[0].get("text", "Maaf, tidak ada respon.")
                                return clean_ai_response(raw_reply)
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
                            raw_reply = choices[0].get("message", {}).get("content", "Maaf, tidak ada respon.")
                            return clean_ai_response(raw_reply)
        except Exception:
            pass

    return (
        "Layanan AI lokal sedang memproses antrean. Coba ulangi pertanyaanmu dalam beberapa detik ya!"
    )
