# nick.ai — The Ultimate Local AI Assistant
## live link
https://nick-ai.streamlit.app/

**nick.ai** is a premium, high-performance AI platform built for total privacy and power. Unlike ChatGPT or Gemini, nick.ai runs **100% locally** on your hardware, ensuring your data never leaves your machine.

Created, developed, and trained by **Nikshith Gurram**.

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.9+-green.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B.svg)

## 🚀 Key Features

- **Total Privacy**: Built on top of Ollama and Llama 3.2. No API keys, no data tracking, and no subscriptions.
- **RAG (Knowledge Base)**: Feed the AI your local folders. It reads your private documents and provides answers based on your actual data.
- **Integrated Voice Mode**: A hands-free, auto-triggering microphone system for seamless audio interaction.
- **Live Web Search**: Combines the power of local AI with real-time internet data via DuckDuckGo.
- **Codex Mode**: A dedicated expert mode for developers with specialized prompts for clean, efficient code.
- **Premium UI/UX**: A custom-built, borderless onyx interface with "Thinking" animations and a bottom-pinned search bar.

## 🛠️ Tech Stack

- **Frontend**: Streamlit + Custom CSS (Onyx/Cyan Theme)
- **Engine**: Ollama (Local LLM Inference)
- **Model**: Llama 3.2 (Optimized for performance)
- **Integrations**: DuckDuckGo API (Search), OpenAI-compatible Local Server

## 📦 Installation & Setup

1. **Install Ollama**: Download and install from [ollama.com](https://ollama.com).
2. **Pull the Model**: Run `ollama pull llama3.2` in your terminal.
3. **Clone & Install**:
   ```bash
   git clone https://github.com/your-username/nick.ai.git
   cd nick.ai
   pip install -r requirements.txt
   ```
4. **Run the App**:
   ```bash
   streamlit run app.py
   ```

## 🧠 About the Project
This project was engineered to solve the "Privacy Gap" in modern AI. By leveraging local inference and Retrieval-Augmented Generation (RAG), **nick.ai** provides the utility of a world-class assistant while maintaining absolute data sovereignty.

---
