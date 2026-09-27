from init_loader import (
    re,
    Path,
    load_meta,
    LexborHTMLParser,
    CURRENT_DIR,
    IMAGE_EXTS,
    DATA_DIR,
)


def layout_rows(rows, ncol):
    """把每列 td 的實際起始欄算出來（跳過被上方 rowspan 占住的位置）。"""
    layouts, carry = [], [0] * ncol

    for row in rows:
        blocked = [n > 0 for n in carry]
        carry = [max(0, n - 1) for n in carry]
        placed, col = [], 0

        for td in row.css("td"):
            while col < ncol and blocked[col]:
                col += 1
            if col >= ncol:
                break

            colspan = min(int(td.attrs.get("colspan", 1)), ncol - col)
            rowspan = int(td.attrs.get("rowspan", 1))
            placed.append((td, col, colspan, rowspan))
            carry[col : col + colspan] = [rowspan - 1] * colspan
            col += colspan

        layouts.append(placed)

    return layouts


def shrink_span(td, name, lost):
    """colspan/rowspan 減去 lost，剩下 1 就移除屬性。"""
    value = int(td.attrs.get(name, 1)) - lost
    if value > 1:
        td.attrs[name] = str(value)
    elif name in td.attrs:
        del td.attrs[name]


def clean_table(tbody, thead):
    """清掉尾端全空的列與欄；欄位位置依 colspan/rowspan 實際還原。"""
    th_list = thead.css("th")[1:]  # 第一格是左上角空白，不算欄
    ncol = len(th_list)
    if ncol <= 0:
        return

    rows = tbody.css("tr")
    layouts = layout_rows(rows, ncol)

    # 尾端全空列：th 只有列編號，整列文字就等於 th 文字
    drop_rows, tail = set(), True
    for i in range(len(rows) - 1, -1, -1):
        row = rows[i]
        th = row.css_first("th")
        if tail and th is not None and th.text().strip() == row.text().strip():
            drop_rows.add(i)
        else:
            tail = False

    kept = [(i, placed) for i, placed in enumerate(layouts) if i not in drop_rows]

    # 有內容的儲存格占過的欄一律保留，同時修掉被刪列壓縮的 rowspan
    used = set()
    for i, placed in kept:
        for td, col, colspan, rowspan in placed:
            lost = sum(j in drop_rows for j in range(i + 1, i + rowspan))
            if lost:
                shrink_span(td, "rowspan", lost)
            if td.text().strip():
                used.update(range(col, col + colspan))

    for i in sorted(drop_rows, reverse=True):
        rows[i].remove()

    # 整欄全空、且不是整張表都空，才刪
    drop_cols = set(range(ncol)) - used
    if not 0 < len(drop_cols) < ncol:
        return

    for c in sorted(drop_cols, reverse=True):
        th_list[c].remove()

    for _, placed in kept:
        for td, col, colspan, _ in placed:
            lost = len(set(range(col, col + colspan)) & drop_cols)
            if lost == colspan:
                td.remove()
            elif lost:
                shrink_span(td, "colspan", lost)


def clean_html_file(filepath):
    filepath = Path(filepath)
    doc = LexborHTMLParser(filepath.read_text(encoding="utf-8"))

    for table in doc.css("table"):
        tbody, thead = table.css_first("tbody"), table.css_first("thead")
        if tbody is None or thead is None:
            continue
        clean_table(tbody, thead)

    # Google 匯出的是不含 DOCTYPE 的片段，缺少 DOCTYPE 會讓瀏覽器改以 quirks mode 渲染，影響表格與盒模型
    out = re.sub(r"\A\s*<!DOCTYPE[^>]*>\s*", "", doc.html, flags=re.IGNORECASE)
    filepath.write_text(f"<!DOCTYPE html>\n{out}", encoding="utf-8")


def generate_content(app_name, file_basenames):

    tabs_html = ""
    for basename in file_basenames:
        filename = f"./data/{basename}.html"
        tabs_html += f'\n\t<button class="tab-button" data-src="{filename}">{basename}</button>'

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" sizes="32x32" href="./icon/32x32.png">
    <link rel="icon" type="image/png" sizes="192x192" href="./icon/192x192.png">
    <link rel="icon" type="image/png" sizes="512x512" href="./icon/512x512.png">
    <link type="text/css" rel="stylesheet" href="./data/resources/sheet.css">
    <title>{app_name}</title>
    <style>
        :root {{
            --primary-color: #0d6efd;
            --secondary-color: #adb5bd;
            --dark-bg: #212529;
            --content-bg: #2c3034;
            --text-color: #dee2e6;
            --border-color: #495057;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            background-color: var(--dark-bg);
            color: var(--text-color);
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }}
        #tabs-container {{
            flex-shrink: 0;
            background-color: var(--dark-bg);
            padding: 0 0.5rem;
            border-bottom: 1px solid var(--border-color);
            overflow-x: auto;
            white-space: nowrap;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
        }}
        #tabs-container::-webkit-scrollbar {{
            display: none;
        }}
        .tab-button {{
            padding: 14px 20px;
            cursor: pointer;
            border: none;
            border-bottom: 2px solid transparent;
            background-color: transparent;
            color: var(--secondary-color);
            font-size: 1rem;
            transition: color 0.2s ease, border-color 0.2s ease;
            margin-bottom: -1px;
        }}
        .tab-button:hover {{
            color: var(--text-color);
        }}
        .tab-button.active {{
            color: var(--primary-color);
            border-bottom-color: var(--primary-color);
            font-weight: 500;
        }}
        .fetch-error {{
            color: red;
            font-size: 2rem;
            text-align: center;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100%;
        }}
        main {{
            flex-grow: 1;
            overflow: hidden;
            background-color: var(--content-bg);
        }}
        .main-frame {{
            border: none;
            width: 100%;
            height: 100%;
        }}
    </style>
</head>
<body>
    <nav id="tabs-container">{tabs_html}</nav>
    <main id="main-content"></main>
    <script>
        document.addEventListener('DOMContentLoaded', () => {{
            const tabsContainer = document.getElementById('tabs-container');
            const mainContent = document.getElementById('main-content');
            const firstButton = tabsContainer.querySelector('.tab-button');

            let currentActiveButton = null, currentController = null;

            tabsContainer.addEventListener('wheel', (evt) => {{
                evt.preventDefault();
                tabsContainer.scrollLeft += evt.deltaY;
            }}, {{ passive: false }});

            const switchTab = async (button) => {{
                if (!button || button === currentActiveButton) return;
                if (currentController) currentController.abort();

                const url = button.dataset.src;
                const activeButton = () => {{
                    if (currentActiveButton) currentActiveButton.classList.remove('active');
                    button.classList.add('active');
                    currentActiveButton = button;
                }};

                try {{
                    currentController = new AbortController();

                    const res = await fetch(url, {{ signal: currentController.signal }});
                    if (!res.ok) throw new Error(`${{res.status}}`);

                    const htmlText = await res.text();
                    mainContent.innerHTML = htmlText;

                    activeButton();
                }} catch (err) {{
                    if (err.name === 'AbortError') return;

                    mainContent.innerHTML = `
                        <p class="fetch-error">${{err.message}}</p>
                        <iframe class="main-frame" src="about:blank"></iframe>
                    `;

                    const iframe = mainContent.querySelector('iframe');
                    iframe.onload = () => {{
                        mainContent.querySelector('.fetch-error').remove();
                        activeButton();
                    }};

                    iframe.src = url;
                }} finally {{
                    currentController = null;
                }}
            }};

            tabsContainer.addEventListener('click', (evt) => {{
                const button = evt.target.closest('.tab-button');
                if (button) switchTab(button);
            }});

            if (firstButton) switchTab(firstButton);
        }});
    </script>
</body>
</html>
"""

    with open(CURRENT_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html_content)


def generate_html():
    img_resources = DATA_DIR / "resources"

    for file in img_resources.rglob("*"):
        if file.is_file() and file.suffix.lower().lstrip(".") in IMAGE_EXTS:
            try:
                file.unlink()  # 嘗試清理圖片類型文件
            except:
                pass

    meta = load_meta()
    sheet_names = meta["sheets"]
    name = meta["name"]

    print("清理文件格式...")
    for base_name in sheet_names:
        clean_html_file(DATA_DIR / f"{base_name}.html")

    generate_content(name, sheet_names)
    print("html 生成完成!")


if __name__ == "__main__":
    generate_html()
