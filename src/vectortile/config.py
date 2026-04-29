"""Configuration for project media handling."""

import os
from pathlib import Path

# File upload limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".txt",
    ".zip",
}

# Directory configuration
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))
MEDIA_DIR_STR = str(MEDIA_DIR).replace("\\", "/")

# Validation messages
INVALID_FILE_SIZE = f"File size must not exceed {MAX_FILE_SIZE / (1024*1024):.0f}MB"
INVALID_EXTENSION = (
    f"File extension not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
)
MISSING_FILENAME = "Filename is missing from upload"
