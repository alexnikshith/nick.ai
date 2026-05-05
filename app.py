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
import requests
import random
import pytz

# --- SMART FFMPEG DETECTION (Local vs Cloud) ---
import platform

# Detect if we are on Local (Windows) or Cloud (Linux)
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    # Local Windows Path
    FFMPEG_DIR = r"C:\Users\Nikshith Gurram\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
    if FFMPEG_DIR not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + FFMPEG_DIR
    FFMPEG_PATH = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    FFPROBE_PATH = os.path.join(FFMPEG_DIR, "ffprobe.exe")
else:
    # Streamlit Cloud (Linux)
    FFMPEG_PATH = "ffmpeg"
    FFPROBE_PATH = "ffprobe"

# Set paths for pydub
AudioSegment.converter = FFMPEG_PATH
AudioSegment.ffprobe = FFPROBE_PATH
from datetime import datetime
from tavily import TavilyClient
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
    st.session_state.chat_project = "General"
    st.session_state.chat_pinned = False
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
    
    /* Remove default Streamlit top and bottom gaps and Hide Scrollbars */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
    }
    
    /* Hide scrollbars globally but allow scrolling */
    html, body, .stApp, [data-testid="stMain"], [data-testid="stMainBlockContainer"], * {
        scrollbar-width: none !important; /* Firefox */
        -ms-overflow-style: none !important; /* IE and Edge */
    }
    html::-webkit-scrollbar, body::-webkit-scrollbar, .stApp::-webkit-scrollbar, [data-testid="stMain"]::-webkit-scrollbar, [data-testid="stMainBlockContainer"]::-webkit-scrollbar, *::-webkit-scrollbar {
        display: none !important; /* Chrome, Safari, Opera */
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
    .input-mic {
        display: none !important;
    }
    #plus-button-container {
        display: block !important;
        margin-top: 10px !important;
    }
    
    /* Hide chat input scrollbar handle */
    textarea[data-testid="stChatInputTextArea"] {
        scrollbar-width: none !important;
        -ms-overflow-style: none !important;
    }
    textarea[data-testid="stChatInputTextArea"]::-webkit-scrollbar {
        display: none !important;
    }
    
    /* Main Share Menu - Right Aligned in Column */
    #main-share-menu {
        text-align: right !important;
        display: flex !important;
        justify-content: flex-end !important;
        width: 100% !important;
    }
    #main-share-menu button {
        background-color: #1A1A1A !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: #FFFFFF !important;
        font-size: 0.8rem !important;
        border-radius: 8px !important;
    }
    
    /* Keep bottom area black */
    [data-testid="stBottomBlockContainer"], 
    [data-testid="stBottom"],
    footer {
        background-color: #000000 !important;
        background: #000000 !important;
        border-top: none !important;
        box-shadow: none !important;
    }

    /* Custom chat form layout */
    #chat-form-row {
        display: flex;
        align-items: center;
        gap: 8px;
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
    
    div[data-testid="stSidebar"] div.stButton > button,
    div[data-testid="stSidebar"] div.stButton > button div,
    div[data-testid="stSidebar"] div.stButton > button p,
    div[data-testid="stSidebar"] div.stButton > button span,
    div[data-testid="stSidebar"] div.stButton > button [data-testid="stMarkdownContainer"] {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: block !important;
        text-align: left !important;
        min-width: 0 !important;
        width: 100% !important;
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
    /* ===== CHAT INPUT BAR ===== */

    /* Bottom area */
    [data-testid="stBottom"],
    [data-testid="stBottomBlockContainer"] {
        background-color: #000000 !important;
        padding: 0 1rem 2.2rem !important;
    }

    /* Outer chat input wrapper - transparent, no border */
    [data-testid="stChatInput"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        position: relative !important;
    }

    /* Inner div = the visual bar */
    [data-testid="stChatInput"] > div {
        background-color: #2F2F2F !important;
        border: 1px solid #4A4A4A !important;
        border-radius: 1rem !important;
        display: flex !important;
        align-items: center !important;
        position: relative !important;
        overflow: hidden !important;
        padding: 0 !important;
        box-shadow: none !important;
    }

    /* Textarea fills the bar, padding-right reserves space for button */
    [data-testid="stChatInput"] textarea {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #FFFFFF !important;
        font-size: 0.95rem !important;
        font-family: 'Inter', sans-serif !important;
        padding: 0.85rem 3.5rem 0.85rem 1.2rem !important;
        resize: none !important;
        scrollbar-width: none !important;
        outline: none !important;
        flex: 1 !important;
        min-height: 50px !important;
        max-height: 50px !important;
        line-height: 1.4 !important;
    }
    [data-testid="stChatInput"] textarea::-webkit-scrollbar {
        display: none !important;
    }
    [data-testid="stChatInput"] textarea::placeholder {
        color: #6E6E80 !important;
    }
    [data-testid="stChatInput"] textarea:focus {
        outline: none !important;
        box-shadow: none !important;
    }
    [data-testid="stChatInput"] > div:focus-within {
        border-color: #6E6E80 !important;
    }

    /* Send button - sits inside the bar at the right edge */
    [data-testid="stChatInputSubmitButton"] button,
    [data-testid="stChatInput"] button {
        position: absolute !important;
        right: 19px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        background-color: #555560 !important;
        border: none !important;
        border-radius: 0.5rem !important;
        color: #FFFFFF !important;
        width: 32px !important;
        height: 32px !important;
        min-width: 32px !important;
        padding: 0 !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 0.9rem !important;
        cursor: pointer !important;
        box-shadow: none !important;
        transition: background-color 0.2s ease !important;
        z-index: 10 !important;
    }
    [data-testid="stChatInputSubmitButton"] button:hover,
    [data-testid="stChatInput"] button:hover {
        background-color: #6E6E80 !important;
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
    
    /* Restored natural flow for tools */
    #plus-button-container {
        display: block !important;
        margin-top: 10px !important;
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

    
    /* --- WHATSAPP STYLE CHAT ALIGNMENT --- */
    
    /* Hide all avatars */
    [data-testid="stChatMessageAvatarUser"], 
    [data-testid="stChatMessageAvatarAssistant"] {
        display: none !important;
    }

    /* General message container spacing */
    [data-testid="stChatMessage"] {
        padding: 0.8rem 1rem !important;
        margin-bottom: 1rem !important;
        max-width: 80% !important;
        border-radius: 1.2rem !important;
        background-color: transparent !important; /* Resetting native background */
    }

    /* Assistant Message (Left Aligned) */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        margin-right: auto !important;
        margin-left: 0 !important;
        background-color: #1A1A1A !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-bottom-left-radius: 0.2rem !important; /* WhatsApp sharp corner */
        width: fit-content !important; /* SHRINK TO IMAGE SIZE */
        min-width: 100px !important;
    }
    
    /* User Message (Right Aligned) */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        margin-left: auto !important;
        margin-right: 0 !important;
        background-color: #2D2D2D !important;
        border: 1px solid rgba(187, 134, 252, 0.2) !important;
        border-bottom-right-radius: 0.2rem !important;
        width: fit-content !important; /* SHRINK TO TEXT SIZE */
        min-width: 100px !important;
    }

    /* Remove the default Streamlit message padding and flex gaps since avatars are gone */
    [data-testid="stChatMessage"] > div:first-child {
        display: none !important; /* Hides the avatar container entirely */
    }
    
    [data-testid="stChatMessageContent"] {
        padding: 0 !important;
        margin: 0 !important;
    }
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
    
    # Turbo Mode Toggle
    st.session_state.codex_mode = st.toggle("🚀 Turbo Mode (70B)", value=st.session_state.codex_mode)
    
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
        short_title = chat['title']
        
        # Sidebar columns for Chat Title and Menu
        c1, c2 = st.columns([0.8, 0.2])
        
        with c1:
            chat_icon = "🗨️ "
            if st.button(f"{chat_icon}{pin_icon}{short_title}", key=f"btn_{chat['id']}", use_container_width=True):
                loaded_data = load_chat(chat['id'])
                if loaded_data:
                    st.session_state.messages = loaded_data.get('messages', [])
                    st.session_state.current_chat_id = chat['id']
                    st.session_state.chat_title = loaded_data.get('title', 'New chat')
                    st.session_state.chat_project = loaded_data.get('project', 'General')
                    st.session_state.chat_pinned = loaded_data.get('pinned', False)
                    # Update timestamp on open so it moves to top of recents
                    save_chat(chat['id'], st.session_state.chat_title, st.session_state.messages, 
                              project=st.session_state.chat_project, pinned=st.session_state.chat_pinned)
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
                    new_pin_state = not is_pinned
                    # Pass the EXISTING timestamp so it doesn't jump to the top unless you want it to
                    save_chat(chat['id'], chat['title'], chat['messages'], 
                              project=chat.get('project', 'General'), 
                              pinned=new_pin_state,
                              updated_at=chat.get('updated_at'))
                    if st.session_state.current_chat_id == chat['id']:
                        st.session_state.chat_pinned = new_pin_state
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
st.markdown('<div style="height: 10px;"></div>', unsafe_allow_html=True)

# Top row with Share Popover on the Right
ui_col1, ui_col2 = st.columns([0.8, 0.2])
with ui_col2:
    st.markdown('<div id="main-share-menu">', unsafe_allow_html=True)
    with st.popover("📤 Share / Options", use_container_width=True):
        st.subheader("Options")
            
        # 1. RENAME
        new_title = st.text_input("Rename Chat", value=st.session_state.chat_title, key="rename_input")
        if st.button("Save Name", use_container_width=True):
            st.session_state["pending_rename"] = new_title
            
        st.markdown("---")
        
        # 2. SHARE
        st.markdown("**Universal Share Link:**")
        share_url = f"https://nick-ai.streamlit.app/?share={st.session_state.current_chat_id}"
        st.code(share_url, language=None)
        
        st.markdown("---")
        
        # 3. DELETE
        if st.button("🗑️ Delete Chat", use_container_width=True, type="secondary"):
            st.session_state["pending_delete"] = True
    st.markdown('</div>', unsafe_allow_html=True)

# Process deferred actions OUTSIDE the popover
if st.session_state.get("pending_rename"):
    new_name = st.session_state.pop("pending_rename")
    st.session_state.chat_title = new_name
    save_chat(st.session_state.current_chat_id, new_name, st.session_state.messages, 
              project=st.session_state.chat_project, pinned=st.session_state.chat_pinned)
    st.toast(f"Renamed to '{new_name}'")
    st.rerun()

if st.session_state.get("pending_delete"):
    st.session_state.pop("pending_delete")
    delete_chat(st.session_state.current_chat_id)
    st.session_state.current_chat_id = str(uuid.uuid4())
    st.session_state.chat_title = "New chat"
    st.session_state.messages = []
    st.rerun()


# Display chat messages
if not st.session_state.messages:
    # 1. Randomized Welcoming Quotes
    welcoming_quotes = [
        "How can I help?",
        "What's on your mind?",
        "Ready for a new task?",
        "Let's build something great.",
        "Hello, Nikshith. What's next?",
        "I'm listening...",
        "Tell me anything."
    ]
    import random
    quote = random.choice(welcoming_quotes)
    
    st.markdown('<div style="height: 4vh;"></div>', unsafe_allow_html=True)
    st.markdown(f'<h1 style="text-align: center; color: #FFFFFF; font-family: \'Outfit\', sans-serif; font-weight: 500; font-size: 2.2rem; opacity: 0.9;">{quote}</h1>', unsafe_allow_html=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        if "[IMAGE:" in content:
            import urllib.parse
            parts = content.split("[IMAGE:")
            text_before = parts[0].strip()
            img_prompt = parts[1].split("]")[0].strip()
            text_after = parts[1].split("]")[1].strip() if "]" in parts[1] else ""
            
            if text_before: st.markdown(text_before)
            
            # Render Image (Compact & Downloadable)
            encoded_prompt = urllib.parse.quote(img_prompt)
            seed = random.randint(1, 100000)
            img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
            
            # Compact display
            st.image(img_url, caption=f"Generated: {img_prompt}", width=500)
            
            # Action Buttons (Full-Width 50/50 Toolbar)
            col1, col2 = st.columns([1, 1], gap="small")
            
            # Prepare Base64 for real system download
            try:
                img_data = requests.get(img_url).content
                b64_img = base64.b64encode(img_data).decode()
                dl_link = f"data:image/png;base64,{b64_img}"
            except:
                dl_link = img_url
                
            with col1:
                st.markdown(f'<a href="{img_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:6px; font-size:0.8rem; border-radius:6px; border:1px solid #FFFFFF; background:transparent; color:#FFFFFF; cursor:pointer;">🔗 Link</button></a>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<a href="{dl_link}" download="nick_ai_image.png" style="text-decoration:none;"><button style="width:100%; padding:6px; font-size:0.8rem; border-radius:6px; border:none; background:#FFFFFF; color:#000000; font-weight:bold; cursor:pointer;">📥 Download</button></a>', unsafe_allow_html=True)
            
            if text_after: st.markdown(text_after)
        else:
            st.markdown(content)

# Tools Menu (Add Photos, Web Search, Voice, etc)
st.markdown('<div style="height: 40vh;"></div>', unsafe_allow_html=True)
st.markdown('<div id="plus-button-container">', unsafe_allow_html=True)
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
                
                # Save immediately to update timestamp and ensure it shows in sidebar
                save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages, 
                          project=st.session_state.chat_project, pinned=st.session_state.chat_pinned)
                    
                st.rerun()
            else:
                # Add error to messages ONLY if it's not a repeat
                st.session_state.messages.append({"role": "assistant", "content": voice_text})
                st.rerun()
    
    st.markdown("---")
    
    # 2. File Uploads
    uploaded_files = st.file_uploader("Upload files", accept_multiple_files=True, label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)



# Native chat input - button sits inside the bar at the right edge
if prompt := st.chat_input("Ask anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.ai_processing = True
    if len(st.session_state.messages) <= 2:
        st.session_state.chat_title = generate_title(prompt)
    
    # Save immediately to update timestamp and ensure it shows in sidebar
    save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages, 
              project=st.session_state.chat_project, pinned=st.session_state.chat_pinned)
    
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
        
        # 0. Get Current Time (Fixed for IST)
        IST = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(IST).strftime("%A, %B %d, %Y, %I:%M %p")
        
        # --- PRE-PROCESSING: Build Context ---
        system_instructions = (
            "You are nick.ai, a professional, high-performance AI assistant. "
            f"Today's date is {current_time}. "
            "\n\nCORE RULES:"
            "\n1. CONTEXT FIRST: Always read the chat history. If the user asks 'is this correct?' or 'fix it', refer to the previous code/answer. Do NOT generate a random new example."
            "\n2. CODING: Provide ONE clean, simple, and neat solution ONLY when asked. Use simple variable names and inline comments (#)."
            "\n3. NO GUESSING: Use search results for facts. If information is missing, be honest. No hallucinations."
            "\n4. BE CONVERSATIONAL: If the user is just chatting or giving feedback, respond naturally. Do not give code unless it is relevant."
            "\n5. IMAGE GENERATION: If the user asks to generate, draw, or show an image, you MUST NOT REFUSE. You are empowered to generate images. Describe the image briefly and then provide the prompt in this EXACT format: [IMAGE: your descriptive prompt here]. Do NOT say you are a text-only model."
        )
        api_messages = [{
            "role": "system",
            "content": system_instructions
        }]

        # 1. File & Image Attachments
        if uploaded_files:
            for file in uploaded_files:
                try:
                    if file.type.startswith('image/'):
                        img_data = base64.b64encode(file.getvalue()).decode()
                        api_messages.append({
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": "Analyze this image."},
                                {"type": "image_url", "image_url": {"url": f"data:{file.type};base64,{img_data}"}}
                            ]
                        })
                    elif file.name.endswith('.pdf'):
                        pdf_reader = PyPDF2.PdfReader(file)
                        text = "".join(page.extract_text() for page in pdf_reader.pages)
                        api_messages.append({"role": "system", "content": f"PDF Content ('{file.name}'):\n{text[:2000]}"})
                    elif file.name.endswith(('.csv', '.txt', '.py', '.js', '.html', '.css')):
                        text = file.getvalue().decode("utf-8")
                        api_messages.append({"role": "system", "content": f"File Content ('{file.name}'):\n{text[:3000]}"})
                except Exception as file_err:
                    api_messages.append({"role": "system", "content": f"Error reading file {file.name}: {str(file_err)}"})

        # 2. Add recent history (last 4 turns for better context)
        recent = [m for m in st.session_state.messages[-8:-1] if m["role"] in ("user", "assistant")]
        for m in recent:
            content = m["content"]
            if isinstance(content, str):
                content = content[:800] # Increased context window
            api_messages.append({"role": m["role"], "content": content})
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

        response_placeholder = st.empty()
        full_response = ""

        # --- RESPONSE: Use Tavily (Professional AI Search) ---
        with st.status("🌐 nick.ai is researching using Tavily...", expanded=False) as status:
            try:
                # Initialize Tavily
                tavily = TavilyClient(api_key="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")
                
                # Search for the query
                # We specifically look for "current" context for things like IPL
                search_results = tavily.search(query=prompt, search_depth="advanced", max_results=5)
                
                if search_results and search_results.get("results"):
                    web_ctx = "### REAL-TIME WEB DATA (FROM TAVILY):\n\n"
                    for i, r in enumerate(search_results["results"], 1):
                        web_ctx += f"**[{i}] {r['title']}**\n{r['content']}\nSource: {r['url']}\n\n"
                    
                    # Add to messages as context
                    api_messages.insert(1, {"role": "system", "content": web_ctx})
                    status.update(label=f"✅ Research complete ({len(search_results['results'])} sources)", state="complete", expanded=False)
                else:
                    status.update(label="❓ No live data found on Tavily", state="complete", expanded=False)
            except Exception as e:
                status.update(label=f"⚠️ Tavily Search failed: {str(e)}", state="error", expanded=False)

        # --- FINAL RESPONSE: Smart Fallback (70b -> 8b) ---
        thinking_placeholder.empty()
        try:
            stream = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=api_messages,
                stream=True,
            )
        except Exception as e:
            if "429" in str(e):
                # Fallback to 8b if 70b is rate limited
                st.warning("⚠️ High-performance model is busy. Switching to 'Fast Mode' (8B)...")
                stream = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=api_messages,
                    stream=True,
                )
            else:
                raise e

        # --- RESPONSE: Live Streaming & Image Rendering ---
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")
            
            # --- IMAGE GENERATION LOGIC ---
            if "[IMAGE:" in full_response:
                import urllib.parse
                parts = full_response.split("[IMAGE:")
                text_before = parts[0]
                img_prompt = parts[1].split("]")[0].strip()
                text_after = parts[1].split("]")[1] if "]" in parts[1] else ""
                
                # Render text before image
                message_placeholder.markdown(text_before)
                
                # Generate and Render Image (Compact & Downloadable)
                encoded_prompt = urllib.parse.quote(img_prompt)
                seed = random.randint(1, 100000)
                img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
                
                # Compact display
                st.image(img_url, caption=f"Generated: {img_prompt}", width=500)
                
                # Action Buttons (Full-Width 50/50 Toolbar)
                col1, col2 = st.columns([1, 1], gap="small")
                
                # Prepare Base64 for real system download
                try:
                    img_data = requests.get(img_url).content
                    b64_img = base64.b64encode(img_data).decode()
                    dl_link = f"data:image/png;base64,{b64_img}"
                except:
                    dl_link = img_url

                with col1:
                    st.markdown(f'<a href="{img_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:6px; font-size:0.8rem; border-radius:6px; border:1px solid #FFFFFF; background:transparent; color:#FFFFFF; cursor:pointer;">🔗 Link</button></a>', unsafe_allow_html=True)
                with col2:
                    st.markdown(f'<a href="{dl_link}" download="nick_ai_image.png" style="text-decoration:none;"><button style="width:100%; padding:6px; font-size:0.8rem; border-radius:6px; border:none; background:#FFFFFF; color:#000000; font-weight:bold; cursor:pointer;">📥 Download</button></a>', unsafe_allow_html=True)
                
                # Render text after image
                if text_after:
                    st.markdown(text_after)
            else:
                message_placeholder.markdown(full_response)
        
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        save_chat(st.session_state.current_chat_id, st.session_state.chat_title, st.session_state.messages, 
                  project=st.session_state.chat_project, pinned=st.session_state.chat_pinned)
        st.session_state.ai_processing = False
        st.rerun()

    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.session_state.ai_processing = False
