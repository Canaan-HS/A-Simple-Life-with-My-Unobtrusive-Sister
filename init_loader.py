import base64
import json
import time
import zipfile

import httpx2

from typing import Iterator

from pathlib import Path
from selectolax.lexbor import LexborHTMLParser

CURRENT_DIR = Path(__file__).parent

ZIP_NAME = "data.zip"
META_NAME = "meta.json"

CACHE_DIR = CURRENT_DIR / "cache"
DATA_DIR = CURRENT_DIR / "data"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

PATHS = {
    "CACHE_ZIP": CACHE_DIR / ZIP_NAME,  # 新數據
    "META": DATA_DIR / META_NAME,  # 試算表語意快照
}

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "avif", "heic", "svg"}
API_URL = "https://script.google.com/macros/s/AKfycbwEkIv5gAqj7_DYqPtG2G8gTGQD4I-zLHyNsgxW-6mWta5xJokmVC9TkuR6RirII8kp/exec"


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
    pass
