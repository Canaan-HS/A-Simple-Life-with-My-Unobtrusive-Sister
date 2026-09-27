from init_loader import (
    hashlib,
    BytesIO,
    openpyxl,
    parse_name,
    load_meta,
    save_meta,
    requests,
    Path,
    DOWNLOAD_URL,
)

from get_html import get_html


def style_signature(cell) -> str:
    """取得儲存格樣式的語意特徵，排除會被重新編號的 style 索引"""
    return (
        f"{cell.number_format}"
        f"\x00{cell.font.name},{cell.font.sz},{cell.font.b},{cell.font.i},"
        f"{cell.font.color and cell.font.color.rgb}"
        f"\x00{cell.fill.fgColor.rgb if cell.fill and cell.fill.fgColor else None},"
        f"{cell.fill.patternType if cell.fill else None}"
        f"\x00{cell.alignment.horizontal},{cell.alignment.vertical},"
        f"{cell.alignment.wrapText}"
    )


def calc_xlsx_hash(data: bytes) -> tuple[str, list[str]]:
    """計算 xlsx 內容的穩定哈希值，並一併回傳工作表名稱與順序

    Google 每次匯出都會重新編號 shared string 與 style 索引，即使內容未變
    也會產生不同位元組，因此比對解析後的語意，而非 XML 原始位元組。
    """
    sha = hashlib.sha256()
    sheet_titles = []
    workbook = openpyxl.load_workbook(BytesIO(data), data_only=True)
    style_cache = {}

    for sheet in workbook.worksheets:
        sheet_titles.append(sheet.title)
        sha.update(sheet.title.encode())

        for row in sheet.iter_rows():
            for cell in row:
                # 空但有樣式的儲存格仍會影響 HTML 的 class
                if cell.value is None and not cell.has_style:
                    continue

                # 樣式僅按解析後的語意快取，索引本身不參與雜湊
                style_key = tuple(cell._style) if cell._style is not None else ()
                style = style_cache.get(style_key)
                if style is None:
                    style = style_cache[style_key] = style_signature(cell)

                sha.update(f"{cell.coordinate}\x00{cell.value!r}\x00{style}".encode())

        for idx, dim in sorted(sheet.row_dimensions.items()):
            sha.update(f"row{idx}={dim.height}".encode())

        for key, dim in sorted(sheet.column_dimensions.items()):
            sha.update(f"col{key}={dim.width}".encode())

        sha.update(str(sorted(str(r) for r in sheet.merged_cells.ranges)).encode())

    workbook.close()
    return sha.hexdigest(), sheet_titles


def get_xlsx() -> bool:
    """取得 xlsx 並驗證試算表內容是否需要更新"""
    url = DOWNLOAD_URL.split("/edit?")[0] + "/export?format=xlsx"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"取得 xlsx 失敗，狀態碼: {response.status_code}")
        return False

    print(f"已取得 xlsx -> {len(response.content) / 1024 ** 2:.2f} MB")
    name = parse_name(response.headers.get("Content-Disposition", ""))
    new_hash, sheets = calc_xlsx_hash(response.content)

    # 獲取 meta.json 中的值，比對哈希
    if load_meta().get("hash") == new_hash:
        return False

    # 若不同或沒有 meta → 下載 html，成功才繼續
    if not get_html():
        return False

    save_meta(Path(name).stem, new_hash, sheets)
    return True


if __name__ == "__main__":
    get_xlsx()
