from init_loader import (
    API_URL,
    PATHS,
    DATA_DIR,
    base64,
    json,
    load_meta,
    requests,
    save_meta,
    time,
    zipfile,
)
from generate_html import generate_html


def fetch_meta() -> dict | None:
    print("fetch_meta =>")

    for attempt in range(3):
        if attempt:
            time.sleep(2)

        try:
            response = requests.get(f"{API_URL}?action=get_meta", timeout=120)
            data = json.loads(response.text)
        except Exception as exc:
            print(f"get_meta 非 JSON 回應（第 {attempt + 1}/3 次）: {exc}")
            continue

        if "error" in data:
            detail = data.get("message") or data.get("retry_after")
            print(f"get_meta 錯誤: {data['error']}" + (f" ({detail})" if detail else ""))
            return None

        if not all(key in data for key in ("name", "hash", "sheets")):
            print(f"get_meta 欄位不足（第 {attempt + 1}/3 次）: {list(data)}")
            continue

        return data

    print("get_meta 失敗：已重試 3 次")
    return None


def fetch_zip() -> bytes | None:
    print("fetch_zip =>")

    for attempt in range(3):
        if attempt:
            time.sleep(2)

        try:
            response = requests.get(f"{API_URL}?action=export_zip", timeout=600)
            data = json.loads(response.text)
        except Exception as exc:
            print(f"export_zip 非 JSON 回應（第 {attempt + 1}/3 次）: {exc}")
            continue

        if "error" in data:
            detail = data.get("message") or data.get("retry_after")
            print(f"export_zip 錯誤: {data['error']}" + (f" ({detail})" if detail else ""))
            return None

        if "zip_base64" not in data:
            print(f"export_zip 欄位不足（第 {attempt + 1}/3 次）: {list(data)}")
            continue

        content = base64.b64decode(data["zip_base64"])
        if content[:2] != b"PK":
            print(f"export_zip 非 zip 內容（第 {attempt + 1}/3 次）")
            continue

        return content

    print("export_zip 失敗：已重試 3 次")
    return None


def extract_zip(content: bytes) -> bool:
    cache_zip = PATHS["CACHE_ZIP"]
    cache_zip.write_bytes(content)
    root = DATA_DIR.resolve()

    try:
        with zipfile.ZipFile(cache_zip) as zip_ref:
            for member in zip_ref.namelist():
                target = (DATA_DIR / member).resolve()
                if target != root and root not in target.parents:
                    continue
                if target.is_file():
                    target.unlink()
                zip_ref.extract(member, DATA_DIR)
    except zipfile.BadZipFile as exc:
        print(f"zip 解析失敗: {exc}")
        return False
    finally:
        cache_zip.unlink(missing_ok=True)

    return True


def main() -> None:
    local = load_meta()

    remote = fetch_meta()
    if remote is None:
        return

    if local and local.get("hash") == remote["hash"]:
        print("不需要更新")
        return

    content = fetch_zip()
    if content is None or not extract_zip(content):
        return

    generate_html(remote)
    save_meta(remote["name"], remote["hash"], remote["sheets"])


if __name__ == "__main__":
    main()
