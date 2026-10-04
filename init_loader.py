import re
import time
import json
import shutil
import hashlib
import zipfile
import urllib.parse

import httpx2
import openpyxl

from io import BytesIO
from typing import Iterator

from pathlib import Path
from selectolax.lexbor import LexborHTMLParser

CURRENT_DIR = Path(__file__).parent

ZIP_NAME = "data.zip"
META_NAME = "meta.json"

CACHE_DIR = CURRENT_DIR / "cache"
DATA_DIR = CURRENT_DIR / "data"

DOWNLOAD_URL = (
    "https://docs.google.com/spreadsheets/d/1vEwhXk3hnKIIV1fydbuR_gXMHufDQICj/edit?pli=1"
)

CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

PATHS = {
    "CACHE_ZIP": CACHE_DIR / ZIP_NAME,  # 新數據
    "DATA_ZIP": DATA_DIR / ZIP_NAME,  # 舊數據
    "META": DATA_DIR / META_NAME,  # 試算表語意快照
}

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "avif", "heic", "svg"}


class Response(httpx2.Response):
    @property
    def html(self):
        return LexborHTMLParser(self.text)

    def iter_content(self, chunk_size: int = 8192) -> Iterator[bytes]:
        yield from self.iter_bytes(chunk_size=chunk_size)


class HttpClient(httpx2.Client):
    @staticmethod
    def __elapsed_time(func):
        def wrapper(self, *args, **kwargs):
            start_time = time.perf_counter()
            result = func(self, *args, **kwargs)
            end_time = time.perf_counter()
            url = args[0] if args else kwargs.get("url", "Unknown URL")
            print(f"[{func.__name__.upper()}] {url}\n耗時: {end_time - start_time:.4f} 秒\n")
            return result
        return wrapper

    def send(self, request, **kwargs) -> Response:
        response = super().send(request, **kwargs)
        response.__class__ = Response
        return response

    @__elapsed_time
    def get(self, url, stream=False, **kwargs) -> Response:
        if stream:
            request = self.build_request("GET", url, **kwargs)
            return self.send(request, stream=True)

        return super().get(url, **kwargs)


requests = HttpClient(http2=True, follow_redirects=True)


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


def load_meta() -> dict:
    if not PATHS["META"].exists():
        return {}

    return json.loads(PATHS["META"].read_text(encoding="utf-8"))


def save_meta(name: str, digest: str, sheets: list) -> None:
    PATHS["META"].write_text(
        json.dumps(
            {"name": name, "hash": digest, "sheets": sheets},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    print(requests.get(DOWNLOAD_URL).html)
