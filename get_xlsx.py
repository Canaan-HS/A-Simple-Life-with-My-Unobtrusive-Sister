from init_loader import (
    shutil,
    zipfile,
    hashlib,
    requests,
    parse_name,
    PATHS,
    CACHE_DIR,
    DATA_DIR,
    DOWNLOAD_URL,
)

from get_html import get_html


def download_xlsx(url: str) -> None:
    """下載 xlsx 到 cache"""
    url = url.split("/edit?")[0] + "/export?format=xlsx"

    response = requests.get(url, stream=True)
    if response.status_code == 200:

        content_disp = response.headers.get("Content-Disposition", "")
        if "filename=" in content_disp:
            new_name = parse_name(content_disp)
            if new_name:
                PATHS["CACHE_XLSX"] = CACHE_DIR / new_name
                PATHS["DATA_XLSX"] = DATA_DIR / new_name

        with open(PATHS["CACHE_XLSX"], "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"已下載 xlsx 到: {PATHS['CACHE_XLSX']}")
    else:
        print(f"下載失敗，狀態碼: {response.status_code}")


def calc_xlsx_hash(path) -> str:
    """計算 xlsx 內容的穩定哈希值（忽略 metadata）"""
    sha = hashlib.sha256()

    with zipfile.ZipFile(path, "r") as z:
        # 找出所有 worksheet 檔案
        sheets = sorted(
            [n for n in z.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml")]
        )
        for sheet in sheets:
            with z.open(sheet) as f:
                data = f.read()
                sha.update(sheet.encode())
                sha.update(data)

    return sha.hexdigest()


def verify_xlsx():
    """驗證舊版 xlsx 是否需要更新"""

    # 判斷是否有新 xlsx
    if not PATHS["CACHE_XLSX"].exists():
        return False

    # 判斷是否有舊 xlsx
    if PATHS["DATA_XLSX"].exists():
        old_hash = calc_xlsx_hash(PATHS["DATA_XLSX"])
        new_hash = calc_xlsx_hash(PATHS["CACHE_XLSX"])
        if old_hash == new_hash:
            # 哈希相同 → 刪除 cache 版本
            PATHS["CACHE_XLSX"].unlink(missing_ok=True)
            return False

    # 若不同或沒有舊檔 → 移動並下載 html
    shutil.move(str(PATHS["CACHE_XLSX"]), str(PATHS["DATA_XLSX"]))
    return get_html()


def get_xlsx() -> bool:
    """獲取 xlsx"""
    download_xlsx(DOWNLOAD_URL)
    return verify_xlsx()


if __name__ == "__main__":
    get_xlsx
