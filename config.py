import os
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv

load_dotenv()
# Config values can be overridden via environment variables
DB_PATH = os.getenv("CHROMA_DB_PATH", ".chroma_db")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "ptit_corpus")

FETCH_K = int(os.getenv("FETCH_K", "30"))
TOP_K = int(os.getenv("TOP_K", "10"))
MAX_CHARS_PER_DOC = int(os.getenv("MAX_CHARS_PER_DOC", "800"))

llm = AzureChatOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    api_version=os.getenv("AZURE_OPENAI_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    temperature=0.1,
)


# Reranker model name (Hugging Face)
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "Alibaba-NLP/gte-multilingual-reranker-base")

# Language options shown in the UI (default first entry is auto-detect)
LANG_OPTIONS = {
    "Auto-detect (match user)": None,
    "🇻🇳 Vietnamese": "vi",
    "en English": "en",
    "🇨🇳 Simplified Chinese (简体中文)": "zh-cn",
    "🇹🇼 Traditional Chinese": "zh-tw",
    "🇯🇵 Japanese": "ja",
    "🇰🇷 Korean": "ko",
    "🇫🇷 French": "fr",
    "de German": "de",
    "es Español": "es",
    "ru Русский": "ru",
    "th ไทย": "th",
    "id Bahasa Indonesia": "id",
}
