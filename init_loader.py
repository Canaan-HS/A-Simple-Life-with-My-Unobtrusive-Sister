import re
import shutil
import hashlib
import zipfile
import requests
import pandas as pd
import urllib.parse

from lxml import html
from pathlib import Path

CURRENT_DIR = Path(__file__).parent

ZIP_NAME = "data.zip"
XLSX_NAME = "data.xlsx"

CACHE_DIR = CURRENT_DIR / "cache"
DATA_DIR = CURRENT_DIR / "data"

DOWNLOAD_URL = "https://docs.google.com/spreadsheets/d/1fDTga-dhWarmZjoPLGN9X85UqCQwDj1L9NpInVcVVLE/edit?pli=1"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

PATHS = {
    "CACHE_ZIP": CACHE_DIR / ZIP_NAME,  # 新數據
    "CACHE_XLSX": CACHE_DIR / XLSX_NAME,  # 新數據
    "DATA_ZIP": DATA_DIR / ZIP_NAME,  # 舊數據
    "DATA_XLSX": DATA_DIR / XLSX_NAME,  # 舊數據
}

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "avif", "heic", "svg"}


def parse_name(content: str) -> str:
    """解析檔案名稱"""
    filename = ""
    match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", content)

    if match:
        filename = urllib.parse.unquote(match.group(1))
    else:
        match = re.search(r'filename\s*=\s*"([^"]+)"', content)
        if match:
            filename = match.group(1)

    return filename
