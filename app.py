import streamlit as st
from openai import OpenAI
import os
import uuid
import json
import base64
import tempfile
import hashlib
import subprocess
import speech_recognition as sr
from pydub import AudioSegment
import io
from groq import Groq
import requests
import random
import urllib.parse
from datetime import datetime
import pytz
from tavily import TavilyClient
import PyPDF2

# --- APP CONFIG & SESSION STATE ---
st.set_page_config(page_title="nick.ai", page_icon="⚡", layout="wide")

# Initialize all session state variables
defaults = {
    "messages": [],
    "chat_title": "New chat",
    "current_chat_id": str(uuid.uuid4()),
    "user_display_name": "Alex Nikshith",
    "user_username": "alexnikshith",
    "chat_project": "General",
    "current_project": "All",
    "search_query": "",
    "chat_pinned": False,
    "kb_path": "",
    "voice_enabled": False,
    "codex_mode": False,
    "turbo_mode": False,
    "ai_processing": False
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- UTILS ---
def save_chat(chat_id, title, messages, project="General", pinned=False, updated_at=None):
    chat_dir = "chats"
    if not os.path.exists(chat_dir):
        os.makedirs(chat_dir)
    if not updated_at:
        updated_at = datetime.now().isoformat()
    chat_data = {
        "id": chat_id, "title": title, "messages": messages,
        "project": project, "pinned": pinned, "updated_at": updated_at
    }
    with open(f"{chat_dir}/{chat_id}.json", "w") as f:
        json.dump(chat_data, f)

def load_chat(chat_id):
    try:
        with open(f"chats/{chat_id}.json", "r") as f:
            return json.load(f)
    except: return None

def get_all_chats():
    chat_dir = "chats"
    if not os.path.exists(chat_dir): return []
    chats = []
    for filename in os.listdir(chat_dir):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(chat_dir, filename), "r") as f:
                    data = json.load(f)
                    if data: chats.append(data)
            except: continue # Skip corrupted files
    return chats

def delete_chat(chat_id):
    try: os.remove(f"chats/{chat_id}.json")
    except: pass

def transcribe_audio(audio_file):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file) as source:
            audio_data = r.record(source)
            return r.recognize_google(audio_data)
    except: return "Error: Could not transcribe audio."

def generate_title(prompt):
    words = prompt.split()[:5]
    return " ".join(words) + "..." if len(words) >= 5 else prompt

def new_chat():
    st.session_state.current_chat_id = str(uuid.uuid4())
    st.session_state.chat_title = "New chat"
    st.session_state.messages = []
    st.session_state.chat_project = "General"
    st.session_state.chat_pinned = False
    st.rerun()

# --- CSS (Premium Obsidian/WhatsApp Theme) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@700&display=swap');
    .stApp { background-color: #0F0F0F; color: #E0E0E0; font-family: 'Inter', sans-serif; }
    [data-testid="stChatMessage"] { padding: 0.8rem 1rem !important; margin-bottom: 1rem !important; max-width: fit-content !important; min-width: 100px !important; border-radius: 1.2rem !important; background-color: transparent !important; }
    [data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] { display: none !important; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) { margin-right: auto !important; margin-left: 0 !important; background-color: #1A1A1A !important; border: 1px solid rgba(255, 255, 255, 0.05) !important; border-bottom-left-radius: 0.2rem !important; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { margin-left: auto !important; margin-right: 0 !important; background-color: #2D2D2D !important; border: 1px solid rgba(187, 134, 252, 0.2) !important; border-bottom-right-radius: 0.2rem !important; }
    .bubble-role { font-size: 0.7rem; font-weight: 600; margin-bottom: 4px; opacity: 0.5; text-transform: uppercase; letter-spacing: 0.5px; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("## nick.ai")
    if st.button("＋ New Chat", use_container_width=True): new_chat()
    st.session_state.turbo_mode = st.toggle("🚀 Turbo Mode (70B)", value=st.session_state.turbo_mode, help="High-performance mode. Disable for simple chat to save tokens.")
    
    st.markdown("---")
    st.markdown("### Recents")
    all_chats = get_all_chats()
    all_chats.sort(key=lambda x: (x.get('pinned', False), x.get('updated_at', '')), reverse=True)
    for chat in all_chats:
        if st.button(f"💬 {chat['title'][:25]}", key=f"chat_{chat['id']}", use_container_width=True):
            data = load_chat(chat['id'])
            if data:
                st.session_state.messages = data['messages']
                st.session_state.current_chat_id = chat['id']
                st.session_state.chat_title = data['title']
                st.rerun()

    st.markdown("---")
    with st.popover(f"👤 {st.session_state.user_display_name}", use_container_width=True):
        st.session_state.user_display_name = st.text_input("Display Name", value=st.session_state.user_display_name)
        if st.button("Save Profile"): st.rerun()

# --- MAIN UI ---
st.title(st.session_state.chat_title)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(f'<div class="bubble-role">{msg["role"].upper()}</div>', unsafe_allow_html=True)
        content = msg["content"]
        if "[IMAGE:" in content:
            parts = content.split("[IMAGE:")
            text_before = parts[0].strip()
            img_prompt = parts[1].split("]")[0].strip()
            text_after = parts[1].split("]")[1].strip() if "]" in parts[1] else ""
            if text_before: st.markdown(text_before)
            img_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(img_prompt)}?width=1024&height=1024&seed={random.randint(1,100000)}&nologo=true"
            st.image(img_url, width=500)
            col1, col2 = st.columns([1, 1], gap="small")
            try:
                img_data = requests.get(img_url).content
                b64_img = base64.b64encode(img_data).decode()
                dl_link = f"data:image/png;base64,{b64_img}"
            except: dl_link = img_url
            with col1: st.markdown(f'<a href="{img_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:6px; font-size:0.8rem; border-radius:6px; border:1px solid #FFFFFF; background:transparent; color:#FFFFFF; cursor:pointer;">🔗 Link</button></a>', unsafe_allow_html=True)
            with col2: st.markdown(f'<a href="{dl_link}" download="nick_ai_image.png" style="text-decoration:none;"><button style="width:100%; padding:6px; font-size:0.8rem; border-radius:6px; border:none; background:#FFFFFF; color:#000000; font-weight:bold; cursor:pointer;">📥 Download</button></a>', unsafe_allow_html=True)
            if text_after: st.markdown(text_after)
        else: st.markdown(content)

# Input Toolbar
col_in, col_tools = st.columns([0.85, 0.15])
with col_tools:
    with st.popover("➕ Tools"):
        audio_file = st.audio_input("Speak", label_visibility="collapsed")
        if audio_file:
            voice_text = transcribe_audio(audio_file)
            if "Error" not in voice_text:
                st.session_state.messages.append({"role": "user", "content": voice_text})
                st.session_state.ai_processing = True
                st.rerun()
        uploaded_files = st.file_uploader("Upload", accept_multiple_files=True, label_visibility="collapsed")

if prompt := st.chat_input("Ask anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.ai_processing = True
    if len(st.session_state.messages) <= 2: st.session_state.chat_title = generate_title(prompt)
    save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages)
    st.rerun()

# AI Inference
if st.session_state.ai_processing:
    st.session_state.ai_processing = False
    prompt = st.session_state.messages[-1]["content"]
    IST = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(IST).strftime("%I:%M %p")
    
    sys_msg = f"You are nick.ai, a pro assistant. Time: {current_time}. If user asks for image, use [IMAGE: prompt]. Stay concise."
    api_msgs = [{"role": "system", "content": sys_msg}]
    
    # Restoring File Support
    if 'uploaded_files' in locals() and uploaded_files:
        for f in uploaded_files:
            try:
                if f.type.startswith('image/'):
                    img_b64 = base64.b64encode(f.getvalue()).decode()
                    api_msgs.append({"role": "user", "content": [{"type": "text", "text": "Analyze image"}, {"type": "image_url", "image_url": {"url": f"data:{f.type};base64,{img_b64}"}}]})
                elif f.name.endswith('.pdf'):
                    pdf = PyPDF2.PdfReader(f)
                    text = "".join(p.extract_text() for p in pdf.pages)
                    api_msgs.append({"role": "system", "content": f"File: {f.name}\nContent: {text[:2000]}"})
                else:
                    text = f.getvalue().decode()
                    api_msgs.append({"role": "system", "content": f"File: {f.name}\nContent: {text[:3000]}"})
            except: pass

    # Restoring Tavily Research
    with st.status("🌐 Researching...") as status:
        try:
            tavily = TavilyClient(api_key="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")
            res = tavily.search(query=prompt, max_results=3)
            if res.get("results"):
                web_ctx = "Web Data:\n" + "\n".join([f"- {r['title']}: {r['content'][:300]}" for r in res["results"]])
                api_msgs.append({"role": "system", "content": web_ctx})
        except: pass

    for m in st.session_state.messages[-6:-1]: api_msgs.append(m)
    api_msgs.append({"role": "user", "content": prompt})

    # Smart Model Selection
    is_simple = len(prompt) < 20
    initial_model = "llama-3.1-8b-instant" if (not st.session_state.turbo_mode or is_simple) else "llama-3.3-70b-versatile"

    with st.chat_message("assistant"):
        st.markdown('<div class="bubble-role">ASSISTANT</div>', unsafe_allow_html=True)
        placeholder = st.empty()
        full_res = ""
        try:
            client = Groq(api_key=st.secrets["GROQ_API_KEY"])
            stream = client.chat.completions.create(model=initial_model, messages=api_msgs, stream=True)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_res += chunk.choices[0].delta.content
                    placeholder.markdown(full_res + "▌")
            placeholder.markdown(full_res)
        except Exception as e:
            if "429" in str(e) and initial_model != "llama-3.1-8b-instant":
                st.warning("⚠️ High-performance model busy. Using Fast Mode.")
                stream = client.chat.completions.create(model="llama-3.1-8b-instant", messages=api_msgs, stream=True)
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        full_res += chunk.choices[0].delta.content
                        placeholder.markdown(full_res + "▌")
                placeholder.markdown(full_res)
            else: st.error(f"Error: {e}")

    st.session_state.messages.append({"role": "assistant", "content": full_res})
    save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages)
    st.rerun()
