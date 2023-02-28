from init_loader import (
    shutil,
    zipfile,
    requests,
    parse_name,
    PATHS,
    CACHE_DIR,
    DATA_DIR,
    DOWNLOAD_URL,
)


def download_zip(url: str) -> None:
    """下載 zip 到 cache"""
    url = url.split("/edit?")[0] + "/export?format=zip"

    response = requests.get(url, stream=True)
    if response.status_code == 200:

        content_disp = response.headers.get("Content-Disposition", "")
        if "filename=" in content_disp:
            new_name = parse_name(content_disp)
            if new_name:
                PATHS["CACHE_ZIP"] = CACHE_DIR / new_name
                PATHS["DATA_ZIP"] = DATA_DIR / new_name

        with open(PATHS["CACHE_ZIP"], "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"已下載 zip 到: {PATHS["CACHE_ZIP"]}")
    else:
        print(f"下載失敗，狀態碼: {response.status_code}")


def unzip() -> bool:
    # 判斷是否有新 zip
    if not PATHS["CACHE_ZIP"].exists():
        return False

    # 移動並解壓覆蓋
    shutil.move(str(PATHS["CACHE_ZIP"]), str(PATHS["DATA_ZIP"]))

    with zipfile.ZipFile(PATHS["DATA_ZIP"], "r") as zip_ref:
        for member in zip_ref.namelist():
            target_path = DATA_DIR / member
            if target_path.exists():
                if target_path.is_dir():
                    shutil.rmtree(target_path)
                else:
                    target_path.unlink()
            zip_ref.extract(member, DATA_DIR)

    PATHS["DATA_ZIP"].unlink(missing_ok=True)
    return True


def get_html() -> bool:
    """獲取網頁 HTML"""
    download_zip(DOWNLOAD_URL)
    return unzip()


if __name__ == "__main__":
    get_html
