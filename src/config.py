import os
import sys
import logging

# Try to load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# Ensure handlers aren't duplicated if imported multiple times
logger = logging.getLogger("android_agent")
logger.setLevel(LOG_LEVEL)
if not logger.handlers:
    # Console Handler
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(c_handler)
    
    # File Handler
    try:
        f_handler = logging.FileHandler("agent.log", encoding="utf-8")
        f_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(f_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not create agent.log file: {e}\n")

# Extract and validate options from environment variables (with defaults)
MODE = os.getenv("EXPLORATION_MODE", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

PACKAGE = os.getenv("TARGET_PACKAGE", "com.shadowings.gero")

# Defaults are updated to point to the prompts/ directory
APP_CONTEXT_FILE = os.getenv("APP_CONTEXT_FILE", "prompts/APP_CONTEXT.md")
EXPLORATION_PROMPT_FILE = os.getenv("EXPLORATION_PROMPT_FILE", "prompts/EXPLORATION_PROMPT.md")
GOALS_DIR = os.getenv("GOALS_DIR", "goals")


def load_file(path):
    """Loads text from a path with UTF-8 encoding. Exits on failure."""
    if not os.path.exists(path):
        logger.critical(f"Required context/prompt file not found at: '{path}'")
        logger.critical("Please check your environment variables or file placement.")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.critical(f"Error reading file '{path}': {e}")
        sys.exit(1)


# Pre-load context and prompt templates
APP_CONTEXT = load_file(APP_CONTEXT_FILE)
EXPLORATION_PROMPT = load_file(EXPLORATION_PROMPT_FILE)

# Validate config based on mode
if MODE == "open-ai-compatible" and not OPENAI_KEY:
    logger.critical("OPENAI_API_KEY environment variable is required when EXPLORATION_MODE is 'open-ai-compatible'.")
    logger.critical("Please set it in your .env file or system environment.")
    sys.exit(1)
elif MODE not in ("ollama", "open-ai-compatible"):
    logger.critical(f"Unsupported EXPLORATION_MODE '{MODE}'. Must be 'ollama' or 'open-ai-compatible'.")
    sys.exit(1)
