import streamlit as st
from openai import OpenAI
import os
import uuid
import json
import base64
import os
import tempfile
import hashlib
import subprocess
import speech_recognition as sr
from pydub import AudioSegment
import io
import os
from groq import Groq

# BULLETPROOF FIX for FFmpeg (WinError 2)
# Manually inject the FFmpeg path into the system environment for this session
FFMPEG_DIR = r"C:\Users\Nikshith Gurram\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
if FFMPEG_DIR not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + FFMPEG_DIR

# Tell pydub exactly where the executables are
FFMPEG_PATH = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
AudioSegment.converter = FFMPEG_PATH
AudioSegment.ffprobe = os.path.join(FFMPEG_DIR, "ffprobe.exe")
from datetime import datetime
from duckduckgo_search import DDGS
import PyPDF2
import streamlit.components.v1 as components
# Setup data directory to store chat histories
CHATS_DIR = "chats"
if not os.path.exists(CHATS_DIR):
    os.makedirs(CHATS_DIR)

# --- HELPER FUNCTIONS FOR CHAT HISTORY ---
def save_chat(chat_id, title, messages, project="General", pinned=False, updated_at=None):
    file_path = os.path.join(CHATS_DIR, f"{chat_id}.json")
    timestamp = updated_at if updated_at else datetime.now().isoformat()
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"id": chat_id, "title": title, "project": project, "pinned": pinned, "updated_at": timestamp, "messages": messages}, f)

def load_chat(chat_id):
    file_path = os.path.join(CHATS_DIR, f"{chat_id}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def get_all_chats():
    chats = []
    for filename in os.listdir(CHATS_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(CHATS_DIR, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    chats.append(data)
            except:
                pass
    # Sort by Pinned status first, then by most recent
    chats.sort(key=lambda x: (x.get("pinned", False), x.get("updated_at", "")), reverse=True)
    return chats

def generate_title(prompt):
    words = prompt.split()
    return " ".join(words[:4]).capitalize() + ("..." if len(words) > 4 else "")

def transcribe_audio(audio_file):
    """Industrial-strength transcription using direct FFmpeg engine calls."""
    temp_input = None
    temp_wav = None
    try:
        audio_bytes = audio_file.getvalue()
        if not audio_bytes:
            return "Error: No audio data captured."
            
        # 1. Save raw audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as f:
            f.write(audio_bytes)
            temp_input = f.name
            
        # 2. Convert using DIRECT FFmpeg (The "Proper" Way)
        # We normalize, boost by 20dB, and force 16kHz Mono
        temp_wav = temp_input + ".wav"
        
        ffmpeg_cmd = [
            FFMPEG_PATH,
            "-y", "-i", temp_input,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,volume=20dB", # Professional normalization + boost
            "-ar", "16000", "-ac", "1",
            temp_wav
        ]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error: Audio Engine failed to process recording.\nDetails: {result.stderr}"
            
        # 3. Transcribe the clean WAV
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 50 # Extreme sensitivity
        recognizer.dynamic_energy_threshold = True
        
        with sr.AudioFile(temp_wav) as source:
            audio = recognizer.record(source)
            try:
                # Optimized for accent-specific recognition
                return recognizer.recognize_google(audio, language="en-IN")
            except sr.UnknownValueError:
                return "Error: I heard you, but I couldn't distinguish the words. Please speak slightly slower."
            except sr.RequestError as e:
                return f"Error: Speech service failed ({e})"
                
    except Exception as e:
        import traceback
        return f"Error transcribing audio: {str(e)}\n\nDetails: {traceback.format_exc()}"
    finally:
        # Cleanup
        for tmp in [temp_input, temp_wav]:
            if tmp and os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass

def delete_chat(chat_id):
    file_path = os.path.join(CHATS_DIR, f"{chat_id}.json")
    if os.path.exists(file_path):
        os.remove(file_path)

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Local AI ChatGPT Clone", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# --- INITIALIZE SESSION STATE ---
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = str(uuid.uuid4())
    st.session_state.chat_title = "New chat"
    st.session_state.messages = []
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "codex_mode" not in st.session_state:
    st.session_state.codex_mode = False
if "accent_color" not in st.session_state:
    st.session_state.accent_color = "#00F2FF"
if "kb_path" not in st.session_state:
    st.session_state.kb_path = ""
if "voice_enabled" not in st.session_state:
    st.session_state.voice_enabled = False
if "web_search_enabled" not in st.session_state:
    st.session_state.web_search_enabled = False
if "deep_research_enabled" not in st.session_state:
    st.session_state.deep_research_enabled = False
if "thinking_enabled" not in st.session_state:
    st.session_state.thinking_enabled = False
if "ai_processing" not in st.session_state:
    st.session_state.ai_processing = False
if "current_project" not in st.session_state:
    st.session_state.current_project = "All"
if "chat_project" not in st.session_state:
    st.session_state.chat_project = "General"
if "user_display_name" not in st.session_state:
    st.session_state.user_display_name = "Nikshith Gurram"
if "user_username" not in st.session_state:
    st.session_state.user_username = "nikshithgurram2006"

# --- HANDLE SHARED LINKS ---
if "share" in st.query_params:
    share_id = st.query_params["share"]
    shared_data = load_chat(share_id)
    if shared_data:
        st.markdown(f"### 🔗 Shared Conversation: **{shared_data['title']}**")
        st.markdown("---")
        for msg in shared_data['messages']:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])
        st.info("This is a read-only shared view of the conversation.")
        if st.button("← Back to My AI"):
            st.query_params.clear()
            st.rerun()
        st.stop()

# --- CUSTOM CSS FOR A CLEANER LOOK ---
st.markdown("""
<style>
    /* Hide Streamlit default headers and footers */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Main container styling */
    .stApp {
        background-color: #000000;
        background-image: none;
    }
    
    /* Remove default Streamlit top and bottom gaps */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
    }
    
    /* Precise 5mm bottom gap for sidebar */
    [data-testid="stSidebarUserContent"] {
        padding-bottom: 1.2rem !important;
    }
    
    section[data-testid="stSidebar"] > div {
        padding-bottom: 1.2rem !important;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    
    /* Remove Sidebar top gap */
    div[data-testid="stSidebarUserContent"] {
        padding-top: 0rem !important;
        margin-top: 0rem !important; /* Reset negative margin */
    }
    [data-testid="stSidebarNav"] {
        padding-top: 0rem !important;
    }
    
    /* Force sidebar popovers to stay small and not overlap main area */
    div[data-testid="stPopoverBody"]    h1, h2, h3 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
    }
    /* Thinking Animation */
    @keyframes pulseDots {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 1; }
    }
    .thinking-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        background-color: #00F2FF !important;
        border-radius: 50%;
        margin-right: 3px;
        animation: pulseDots 1.4s infinite;
    }
    .thinking-dot:nth-child(2) { animation-delay: 0.2s; }
    .thinking-dot:nth-child(3) { animation-delay: 0.4s; }
    .input-mic, .input-tools {
        display: none !important;
    }
    
    /* Hide chat input scrollbar handle */
    textarea[data-testid="stChatInputTextArea"] {
        scrollbar-width: none !important;
        -ms-overflow-style: none !important;
    }
    textarea[data-testid="stChatInputTextArea"]::-webkit-scrollbar {
        display: none !important;
    }
    
    /* Bottom area - pure black */
    [data-testid="stBottomBlockContainer"], 
    [data-testid="stBottom"],
    footer {
        background-color: #000000 !important;
        background: #000000 !important;
        border-top: none !important;
        box-shadow: none !important;
    }

    /* Input pill exact color match */
    [data-testid="stChatInput"] > div {
        background-color: #1E1E1E !important;
        border-radius: 20px !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
    }

    /* Transparent Mic & Tools buttons */
    .input-mic button, .input-tools button {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #A0A0A0 !important;
        padding: 0 !important;
        height: 30px !important;
        width: 30px !important;
    }
    .input-mic button:hover, .input-tools button:hover {
        color: #00F2FF !important;
    }
    [data-testid="stSidebar"] [data-testid="stPopoverBody"] * {
        font-size: 0.85rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stPopoverBody"] h5 {
        font-size: 0.95rem !important;
        margin-bottom: 0.5rem !important;
    }
    /* Compact Popovers in Sidebar */
    div[data-testid="stSidebar"] [data-testid="stPopoverBody"] {
        width: 160px !important;
        padding: 5px !important;
        background-color: #1A1A1A !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    div[data-testid="stSidebar"] [data-testid="stPopoverBody"] button {
        padding: 0px 5px !important;
        font-size: 0.75rem !important;
        height: 25px !important;
    }
    div[data-testid="stSidebar"] [data-testid="stPopoverBody"] input {
        font-size: 0.75rem !important;
        height: 25px !important;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #0A0A0A;
        border-right: 1px solid rgba(187, 134, 252, 0.1);
    }
    
    /* Sidebar buttons */
    div[data-testid="stSidebar"] div.stButton > button {
        text-align: left;
        border: none;
        background-color: transparent;
        padding: 0.4rem 0.8rem; /* Smaller padding */
        border-radius: 0.5rem;
        color: #A0A0A0;
        width: 100%;
        font-size: 0.85rem; /* Smaller font */
        font-weight: 500;
        display: flex;
        justify-content: flex-start;
        align-items: center;
        transition: all 0.2s ease;
    }
    /* Accent Color */
    :root {
        --accent: #00F2FF;
    }
    
    div[data-testid="stSidebar"] div.stButton > button {
        background-color: transparent !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        color: #E0E0E0 !important;
        transition: all 0.3s ease !important;
    }
    
    div[data-testid="stSidebar"] div.stButton > button:hover {
        background-color: #1A1A1A !important;
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
    }
    
    /* Apply accent to primary elements */
    .stButton > button { border: 1px solid rgba(255, 255, 255, 0.1) !important; color: #E0E0E0 !important; }
    .stButton > button:hover { 
        background-color: #1A1A1A !important; 
        color: white !important; 
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
    }
    .stCheckbox > label { color: var(--accent) !important; }
    .stToggle > label { color: var(--accent) !important; }
    a { color: var(--accent) !important; }
    .stMarkdown strong { color: var(--accent) !important; }
    
    /* User Chat Bubble Border */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
/* Recents Header */
    div[data-testid="stSidebar"] h3 {
        color: #4D4D4D;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        padding-left: 0.5rem;
    }
    
    /* Main Chat Header */
    .chat-header {
        color: #FFFFFF;
        font-size: 1.5rem;
        font-weight: 800;
        padding: 1.5rem 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .chat-header span.version {
        color: #BB86FC;
        font-weight: 600;
        margin-left: 0.3rem;
        font-size: 1rem;
    }
    /* Make room inside the chat input for the Tools button */
    div[data-testid="stChatInput"] {
        background-color: transparent !important;
        padding-bottom: 0.8rem;
        border: none !important;
        box-shadow: none !important;
    }
    div[data-testid="stChatInput"] > div {
        border: none !important;
        box-shadow: none !important;
    }
    div[data-testid="stChatInput"] textarea {
        background-color: #121212 !important;
        border: 1px solid #333333 !important;
        border-radius: 1rem !important;
        color: white !important;
        padding: 1rem !important;
        transition: border-color 0.3s, box-shadow 0.3s;
    }
    div[data-testid="stChatInput"] textarea:focus {
        border-color: #BB86FC !important;
        box-shadow: 0 0 10px rgba(187, 134, 252, 0.2) !important;
    }
    
    /* Sidebar Branding (Fixed Header) - Forced to Top */
    .sidebar-branding {
        position: absolute;
        top: -55px; /* Aggressively pull into the top dead space */
        left: 0;
        right: 0;
        background-color: #0A0A0A;
        z-index: 1000;
        padding: 10px 20px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Create space for the absolute header */
    .sidebar-content-spacer {
        margin-top: 35px; /* Reduced to pull menu up */
    }
    
    /* User Profile (Fixed Footer) */
    .user-profile {
        position: sticky;
        bottom: -10px;
        background-color: #0A0A0A;
        z-index: 1000;
        display: flex;
        align-items: center;
        padding: 0.8rem;
        margin-top: 1rem;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
        cursor: pointer;
    }
    .user-profile:hover {
        background-color: #1A1A1A;
    }
    .avatar-circle {
        background: linear-gradient(135deg, #BB86FC 0%, #D0BCFF 100%);
        color: #000000;
        border-radius: 50%;
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        font-size: 1rem;
        margin-right: 0.8rem;
    }
    .user-name {
        color: #F5F5F5;
        font-size: 1rem;
        font-weight: 600;
    }
    
    /* Input tools container (We will use JS to move this into the chat input) */
    .input-tools {
        display: none; /* Hide initially to prevent flash */
    }
    
    /* Style the Popover Button to match the image */
    .input-tools div[data-testid="stPopover"] > button {
        background-color: transparent !important;
        border: 1px solid transparent !important;
        border-radius: 0.8rem !important;
        color: #A0A0A0 !important;
        padding: 0.4rem 0.8rem !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        transition: color 0.2s;
        box-shadow: none !important;
    }
    .input-tools div[data-testid="stPopover"] > button:hover {
        background-color: transparent !important;
        color: #BB86FC !important;
    }
    
    /* Image Sharpening for Clarity */
    img {
        image-rendering: -webkit-optimize-contrast !important;
        image-rendering: crisp-edges !important;
    }

    
    /* Chat Bubble Styling */
    [data-testid="stChatMessage"] {
        padding: 0.8rem 1rem !important;
        border-radius: 1.2rem !important;
        margin-bottom: 0.8rem !important;
        max-width: 85% !important;
    }
    
    /* Assistant Bubble (Left) */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
    [data-testid="stChatMessage"][data-testid="assistant"] {
        background-color: #1A1A1A !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-top-left-radius: 0.2rem !important;
    }
    
    /* User Bubble (Right) */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
    [data-testid="stChatMessage"][data-testid="user"] {
        background-color: #2D2D2D !important;
        border: 1px solid rgba(187, 134, 252, 0.2) !important;
        border-top-right-radius: 0.2rem !important;
    }
    div[data-testid="stChatInput"] textarea {
        background-color: #2F2F2F !important;
        border: 1px solid #4D4D4F !important;
        border-radius: 1.2rem !important;
        color: white !important;
        padding: 1rem !important;
    }
    div[data-testid="stChatInput"] textarea:focus {
        border-color: #8E8EA0 !important;
        box-shadow: none !important;
    }

    /* CUSTOM CHAT BUBBLES - REFINED & COMPACT */
    .chat-bubble {
        padding: 0.8rem 1.2rem;
        border-radius: 14px;
        margin-bottom: 0.8rem;
        max-width: 75%;
        line-height: 1.4;
        font-size: 0.95rem;
        color: #FFFFFF;
        font-family: 'Inter', sans-serif;
    }
    
    .user-bubble {
        background-color: #262626;
        margin-left: auto;
        border-bottom-right-radius: 2px;
        border: 1px solid rgba(187, 134, 252, 0.1);
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }
    
    .assistant-bubble {
        background-color: #1A1A1A;
        margin-right: auto;
        border-bottom-left-radius: 2px;
        border: 1px solid rgba(0, 242, 255, 0.05);
    }

    .bubble-role {
        font-size: 0.6rem;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin-bottom: 0.4rem;
        opacity: 0.35;
        font-weight: 700;
        color: #00F2FF;
    }
    
    .user-bubble .bubble-role {
        color: #BB86FC;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# Ready

# --- SIDEBAR UI (ChatGPT Style) ---
with st.sidebar:
    # Fixed Header Section
    logo_base64 = get_base64_image("logo.png")
    st.markdown(f"""
        <div class="sidebar-branding">
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="width: 40px; height: 40px;">
                    <img src="data:image/png;base64,{logo_base64}" width="40" style="border-radius: 8px;">
                </div>
                <div style="color: white; font-size: 1.6rem; font-weight: 800; letter-spacing: -0.5px;">nick.ai</div>
            </div>
        </div>
        <div class="sidebar-content-spacer"></div>
    """, unsafe_allow_html=True)
    
    # 1. TOP MENU ITEMS
    if st.button("New chat", use_container_width=True):
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.session_state.chat_title = "New chat"
        st.session_state.messages = []
        st.query_params.clear() # Clear any active shared link
        st.rerun()
        
    # Search chats functionality
    with st.popover("Search chats", use_container_width=True):
        st.session_state.search_query = st.text_input("Filter chats by title...", value=st.session_state.search_query)
        
    # Projects functionality
    with st.popover("Projects", use_container_width=True):
        st.markdown("### 📂 Filter by Project")
        all_chats_raw = get_all_chats()
        projects = sorted(list(set([c.get('project', 'General') for c in all_chats_raw])))
        projects = ["All"] + projects
        st.session_state.current_project = st.selectbox("Select Project", options=projects, index=projects.index(st.session_state.current_project))
        
        st.markdown("---")
        st.session_state.chat_project = st.text_input("Assign Current Chat to Project:", value=st.session_state.chat_project)
        if st.button("Update Project Tag"):
            save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages, project=st.session_state.chat_project)
            st.toast(f"Moved to {st.session_state.chat_project}")
            st.rerun()
    
    with st.expander("More Settings", expanded=False):
        st.markdown("### 🧠 Knowledge Base")
        st.session_state.kb_path = st.text_input("Local Folder Path", value=st.session_state.kb_path, placeholder="C:/Users/Documents/Notes")
        
        st.markdown("### 🎙️ Interaction")
        st.session_state.voice_enabled = st.toggle("Voice Feedback (TTS)", value=st.session_state.voice_enabled)
        
        st.markdown("---")
        if st.button("Clear App Cache"):
            st.cache_data.clear()
            st.toast("Cache cleared!")
    
    # Codex mode toggle moved to bottom
    st.session_state.codex_mode = st.toggle("Codex (Expert Mode)", value=st.session_state.codex_mode)
    
    # 2. RECENTS (Chat History)
    st.markdown("### Recents")
    all_chats = get_all_chats()
    
    # Filter by project
    if st.session_state.current_project != "All":
        all_chats = [c for c in all_chats if c.get('project', 'General') == st.session_state.current_project]
    
    # Filter by search query
    if st.session_state.search_query:
        all_chats = [c for c in all_chats if st.session_state.search_query.lower() in c.get('title', '').lower()]
    
    # Sort by Pinned status first, then by date
    all_chats.sort(key=lambda x: (x.get('pinned', False), x.get('updated_at', '')), reverse=True)
    
    if not all_chats:
        st.caption("No previous chats.")
        
    for chat in all_chats:
        is_pinned = chat.get('pinned', False)
        pin_icon = "📌 " if is_pinned else ""
        short_title = chat['title'][:20] + "..." if len(chat['title']) > 20 else chat['title']
        
        # Sidebar columns for Chat Title and Menu
        c1, c2 = st.columns([0.8, 0.2])
        
        with c1:
            if st.button(f"{pin_icon}{short_title}", key=f"btn_{chat['id']}", use_container_width=True):
                loaded_data = load_chat(chat['id'])
                if loaded_data:
                    st.session_state.current_chat_id = loaded_data['id']
                    st.session_state.chat_title = loaded_data['title']
                    st.session_state.messages = loaded_data['messages']
                    st.rerun()
        
        with c2:
            with st.popover("⋮", key=f"menu_{chat['id']}"):
                st.markdown("**Options**")
                
                # 1. Rename
                new_name = st.text_input("Name", value=chat['title'], key=f"ren_{chat['id']}", label_visibility="collapsed")
                if st.button("Save", key=f"save_{chat['id']}", use_container_width=True):
                    save_chat(chat['id'], new_name, chat['messages'], project=chat.get('project', 'General'), pinned=is_pinned)
                    if st.session_state.current_chat_id == chat['id']:
                        st.session_state.chat_title = new_name
                    st.rerun()

                # 1.5 Pin/Unpin
                pin_label = "Unpin Chat" if is_pinned else "Pin Chat"
                if st.button(pin_label, key=f"pin_{chat['id']}", use_container_width=True):
                    # Pass the EXISTING timestamp so it doesn't jump to the top
                    save_chat(chat['id'], chat['title'], chat['messages'], 
                              project=chat.get('project', 'General'), 
                              pinned=not is_pinned,
                              updated_at=chat.get('updated_at'))
                    st.rerun()
                
                # 2. Share
                share_url = f"http://localhost:8501/?share={chat['id']}"
                if st.button("🔗 Share Chat", key=f"share_btn_{chat['id']}", use_container_width=True):
                    st.session_state[f"show_link_{chat['id']}"] = True
                
                if st.session_state.get(f"show_link_{chat['id']}", False):
                    st.code(share_url, language=None)
                    st.caption("Anyone with this link can view the chat.")
                
                # 3. Delete
                if st.button("Delete", key=f"del_{chat['id']}", use_container_width=True):
                    delete_chat(chat['id'])
                    if st.session_state.current_chat_id == chat['id']:
                        st.session_state.current_chat_id = str(uuid.uuid4())
                        st.session_state.chat_title = "New chat"
                        st.session_state.messages = []
                    st.rerun()

    # User Profile at the bottom (Interactive)
    st.markdown("---")
    with st.popover(f"👤 {st.session_state.user_display_name}", use_container_width=True):
        st.markdown("### Edit profile")
        
        # Avatar Section
        col_a, col_b, col_c = st.columns([1, 2, 1])
        with col_b:
            st.markdown(f"""
                <div style="position: relative; width: 120px; height: 120px; margin: 0 auto;">
                    <div style="width: 120px; height: 120px; background-color: #7B61FF; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 2.5rem; font-weight: 700;">
                        {st.session_state.user_display_name[:1]}{st.session_state.user_display_name.split()[-1][:1] if ' ' in st.session_state.user_display_name else ''}
                    </div>
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Fields
        new_display_name = st.text_input("Display name", value=st.session_state.user_display_name)
        new_username = st.text_input("Username", value=st.session_state.user_username)
        
        st.caption("Your profile helps people recognize you in group chats.")
        
        # Actions
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("Cancel", use_container_width=True):
                st.rerun()
        with btn_col2:
            if st.button("Save", use_container_width=True, type="primary"):
                st.session_state.user_display_name = new_display_name
                st.session_state.user_username = new_username
                st.toast("Profile updated!")
                st.rerun()

# --- MAIN CHAT UI ---
col1, col2 = st.columns([0.85, 0.15])
with col1:
    st.markdown("""
    <div class="chat-header" style="padding-top: 0;">
        <div>nick.ai <span class="version">˅</span></div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.write("") # padding
    with st.popover("↑ Share &nbsp; •••", use_container_width=True):

        st.subheader("Options")
        
        # 1. RENAME
        new_title = st.text_input("Rename Chat", value=st.session_state.chat_title)
        if st.button("Save Name", use_container_width=True):
            st.session_state.chat_title = new_title
            save_chat(st.session_state.current_chat_id, new_title, st.session_state.messages)
            st.rerun()
            
        st.markdown("---")
        
        # 2. SHARE
        st.markdown("**Universal Share Link:**")
        share_url = f"http://localhost:8501/?share={st.session_state.current_chat_id}"
        st.code(share_url, language=None)
        
        st.markdown("---")
        
        # 3. DELETE
        if st.button("🗑️ Delete Chat", use_container_width=True, type="secondary"):
            delete_chat(st.session_state.current_chat_id)
            st.session_state.current_chat_id = str(uuid.uuid4())
            st.session_state.chat_title = "New chat"
            st.session_state.messages = []
            st.rerun()


# Display chat messages using CUSTOM UI
if not st.session_state.messages:
    import random
    quotes = [
        "What's on the agenda today?",
        "Ready when you are.",
        f"How can I help you today, {st.session_state.user_display_name.split()[0]}?",
        "What shall we create today?",
        "The future starts here.",
        "Ready for the next big idea?",
        "Let's build something amazing."
    ]
    welcome_quote = random.choice(quotes)
    st.markdown(f"""
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 50vh; opacity: 0; animation: fadeIn 1.2s ease-out forwards;">
            <h1 style="font-family: 'Outfit', sans-serif; font-size: 2.2rem; font-weight: 700; color: #FFFFFF; text-align: center; letter-spacing: -1px; margin-bottom: 8px;">
                {welcome_quote}
            </h1>
            <p style="color: rgba(255, 255, 255, 0.2); font-size: 0.9rem; letter-spacing: 2px; text-transform: uppercase;">nick.ai is ready</p>
        </div>
        <style>
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
        </style>
    """, unsafe_allow_html=True)

for msg in st.session_state.messages:
    role_label = "Nikshith" if msg["role"] == "user" else "nick.ai"
    bubble_class = "user-bubble" if msg["role"] == "user" else "assistant-bubble"
    
    st.markdown(f"""
        <div class="chat-bubble {bubble_class}">
            <div class="bubble-role">{role_label}</div>
            <div class="bubble-content">{msg["content"]}</div>
        </div>
    """, unsafe_allow_html=True)

# Tools Menu (Add Photos, Web Search, Voice, etc)
st.markdown('<div class="input-tools">', unsafe_allow_html=True)
with st.popover("➕"):
    st.markdown("#### Tools & Voice")
    
    # 1. Voice Input (Integrated & Auto-Trigger!)
    audio_file = st.audio_input("Speak to nick.ai", label_visibility="collapsed")
    if audio_file:
        # Prevent double-processing
        audio_bytes = audio_file.getvalue()
        current_audio_id = hashlib.sha256(audio_bytes).hexdigest()
        
        if "last_audio_id" not in st.session_state:
            st.session_state.last_audio_id = None
            
        if st.session_state.last_audio_id != current_audio_id:
            st.session_state.last_audio_id = current_audio_id
            
            with st.spinner("🎙️ nick.ai is listening..."):
                voice_text = transcribe_audio(audio_file)
                
            if "Error" not in voice_text:
                st.session_state.ai_processing = True
                st.session_state.messages.append({"role": "user", "content": voice_text})
                
                # Generate title for new chats
                if len(st.session_state.messages) <= 2:
                    st.session_state.chat_title = generate_title(voice_text)
                    
                st.rerun()
            else:
                # Add error to messages ONLY if it's not a repeat
                st.session_state.messages.append({"role": "assistant", "content": voice_text})
                st.rerun()
    
    st.markdown("---")
    
    # 2. File Uploads
    uploaded_files = st.file_uploader("Upload files", accept_multiple_files=True, label_visibility="collapsed")
    
    # 3. Switches
    st.session_state.web_search_enabled = st.toggle("🌐 Web Search", value=st.session_state.web_search_enabled)
st.markdown('</div>', unsafe_allow_html=True)



# Native User Input (Stays at the bottom)
if prompt := st.chat_input("Ask anything..."):
    # Add to messages immediately to prevent vanishing
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.ai_processing = True
    
    # Generate title for new chats
    if len(st.session_state.messages) <= 2:
        st.session_state.chat_title = generate_title(prompt)
    
    st.rerun()

# Trigger AI response
if st.session_state.get('ai_processing', False):
    # Process the last message
    prompt = st.session_state.messages[-1]["content"]
    
    if not prompt:
        st.session_state.ai_processing = False
        st.rerun()

    try:
        # Groq Cloud Client
        if "GROQ_API_KEY" not in st.secrets:
            st.error("❌ Missing Groq API Key! Please add it to your secrets.")
            st.session_state.ai_processing = False
            st.stop()
            
        client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        
        # --- PRE-PROCESSING: Build Context ---
        api_messages = [{"role": "system", "content": "You are nick.ai, an extremely smart AI assistant created, developed, and trained by Nikshith Gurram. Keep replies professional yet friendly."}]
        
        # 1. Handle Web Search
        if st.session_state.web_search_enabled:
            search_limit = 3
            with st.spinner("🌐 Searching the web..."):
                try:
                    results = DDGS().text(prompt, max_results=search_limit)
                    search_context = "Web Search Results:\n"
                    for res in results:
                        search_context += f"- {res['title']}: {res['body']}\n"
                    api_messages.append({"role": "system", "content": search_context})
                except: pass

        # 2. Handle File & Image Attachments
        if uploaded_files:
            for file in uploaded_files:
                try:
                    if file.type.startswith('image/'):
                        img_data = base64.b64encode(file.getvalue()).decode()
                        api_messages.append({
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": "I have attached an image. Please analyze it."},
                                {"type": "image_url", "image_url": {"url": f"data:{file.type};base64,{img_data}"}}
                            ]
                        })
                    elif file.name.endswith('.pdf'):
                        pdf_reader = PyPDF2.PdfReader(file)
                        text = "".join(page.extract_text() for page in pdf_reader.pages)
                        api_messages.append({"role": "system", "content": f"Context from attached PDF '{file.name}':\n{text[:3000]}"})
                except: pass

        # 3. Add History
        for m in st.session_state.messages[-5:-1]:
            api_messages.append(m)
        api_messages.append({"role": "user", "content": prompt})

        # --- RESPONSE: Thinking Animation ---
        thinking_placeholder = st.empty()
        with thinking_placeholder.container():
             st.markdown("""
                <div class="chat-bubble assistant-bubble">
                    <div class="bubble-role">nick.ai</div>
                    <div style="display: flex; align-items: center; gap: 8px; padding: 5px 0;">
                        <span style="color: #00F2FF; font-size: 0.9rem; font-weight: 500;">nick.ai is thinking</span>
                        <div class="thinking-dot"></div>
                        <div class="thinking-dot"></div>
                        <div class="thinking-dot"></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # --- RESPONSE: Live Streaming into Custom Bubble ---
        response_placeholder = st.empty()
        full_response = ""
        
        # Groq-powered Llama 3
        stream = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=api_messages,
            stream=True,
        )
        
        thinking_placeholder.empty()

        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
                response_placeholder.markdown(f"""
                    <div class="chat-bubble assistant-bubble">
                        <div class="bubble-role">nick.ai</div>
                        <div class="bubble-content">{full_response}▌</div>
                    </div>
                """, unsafe_allow_html=True)
        
        # Final render and save
        response_placeholder.markdown(f"""
            <div class="chat-bubble assistant-bubble">
                <div class="bubble-role">nick.ai</div>
                <div class="bubble-content">{full_response}</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages, st.session_state.chat_project)
        st.session_state.ai_processing = False
        st.rerun()

    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.session_state.ai_processing = False
