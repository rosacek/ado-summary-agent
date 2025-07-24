"""
Central configuration for the ADO summary agent.

All parameters can be overridden with environment variables of the same
name to simplify local testing and to keep secrets out of source control.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from typing import List

# Azure DevOps Personal Access Token (optional; if unset, Azure CLI auth is used)
ADO_PAT: str = os.getenv("ADO_PAT", "")

# Azure DevOps configuration
ADO_URL: str = os.getenv("ADO_URL", "https://dev.azure.com/your_org")
ADO_PROJECT_NAME: str = os.getenv("ADO_PROJECT_NAME", "your_project")

# Work item configuration
try:
    work_item_str = os.getenv("WORK_ITEM_IDS", "1")
    # Clean up any extra characters and split
    clean_ids = [id_str.strip() for id_str in work_item_str.split(",")]
    # Filter out any non-numeric IDs and convert to int
    WORK_ITEM_IDS: List[int] = [int(id_str) for id_str in clean_ids if id_str.isdigit()]
    if not WORK_ITEM_IDS:
        WORK_ITEM_IDS = [1]  # fallback
except (ValueError, AttributeError):
    WORK_ITEM_IDS: List[int] = [1]  # fallback
WORK_ITEM_TYPE: str = os.getenv("WORK_ITEM_TYPE", "Scenario")

# Summarization settings
SUMMARY_LENGTH: int = int(os.getenv("SUMMARY_LENGTH", "15000"))  # Increased for comprehensive output

# Ollama Configuration - Optimized for Microsoft devbox
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "phi3.5:3.8b-mini-instruct-q4_K_M")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Alternative: AI Toolkit direct integration
USE_AI_TOOLKIT: bool = os.getenv("USE_AI_TOOLKIT", "false").lower() == "true"
AI_TOOLKIT_MODEL: str = os.getenv("AI_TOOLKIT_MODEL", "microsoft/Phi-3.5-mini-instruct")