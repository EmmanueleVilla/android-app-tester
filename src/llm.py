import json
import re
import requests
from openai import OpenAI
from . import config
from .config import logger

# Lazily initialized OpenAI client
_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not config.OPENAI_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        logger.info(f"Initializing OpenAI client with base_url={config.OPENAI_BASE_URL}")
        _openai_client = OpenAI(
            api_key=config.OPENAI_KEY,
            base_url=config.OPENAI_BASE_URL
        )
    return _openai_client

OUTPUT_INSTRUCTIONS = """
Return ONLY valid JSON:
{"action":"tap","index":0}
or
{"action":"type_text","index":0,"text":"hello"}
or
{"action":"back"}
or
{"action":"swipe","x1":0,"y1":0,"x2":0,"y2":0}
or
{"action":"goal_completed"}
or
{"action":"test_failed","motivation":"reason for failure"}
"""

def ask_llm(clickable_nodes, static_labels, history, current_goal):
    """
    Sends the UI hierarchy, action history, and context to the configured LLM.
    Returns the raw string output from the LLM.
    """
    full_prompt = f"""
{config.EXPLORATION_PROMPT}

CURRENT GOAL:
{current_goal}

APP CONTEXT:
{config.APP_CONTEXT}

HISTORY:
{json.dumps(history[-15:], indent=2)}

CLICKABLE UI:
{json.dumps(clickable_nodes, indent=2)}

STATIC LABELS (CONTEXT):
{json.dumps(static_labels, indent=2)}

{OUTPUT_INSTRUCTIONS}
"""

    logger.info(f"Querying LLM (mode={config.MODE}, model={config.OLLAMA_MODEL if config.MODE == 'ollama' else config.OPENAI_MODEL})...")
    
    if config.MODE == "ollama":
        try:
            r = requests.post(
                config.OLLAMA_URL,
                json={
                    "model": config.OLLAMA_MODEL,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=120
            )
            r.raise_for_status()
            text = r.json()["response"]
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise
    elif config.MODE == "open-ai-compatible":
        try:
            client = get_openai_client()
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )
            text = response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI completion request failed: {e}")
            raise
    else:
        raise ValueError(f"Unknown mode: {config.MODE}")

    logger.debug(f"Raw model response: {text}")
    return text


def extract_json(text):
    """
    Attempts to extract and parse a JSON block from the raw LLM output text.
    """
    if not text:
        return None
        
    try:
        return json.loads(text.strip())
    except ValueError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except ValueError:
            return None

    return None
