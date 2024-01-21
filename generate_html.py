from init_loader import (
    pd,
    html,
    CURRENT_DIR,
    IMAGE_EXTS,
    DATA_DIR,
    PATHS,
)


def clean_html_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        doc = html.parse(f)

    # ? 目前要避免直接顯示圖片, 可能非全年齡
    for img in doc.findall(".//img"):
        img.getparent().remove(img)

    for table in doc.findall(".//table"):
        tbody, thead = table.find(".//tbody"), table.find(".//thead")
        if tbody is None or thead is None:
            continue

        rows = tbody.findall(".//tr")
        allow_delete, clear_box = True, {}

        for row in reversed(rows):
            th = row.find(".//th")
            if th is None:
                continue
            idx, content = th.text_content().strip(), row.text_content().strip()
            if allow_delete and idx == content:
                row.getparent().remove(row)
            else:
                allow_delete = False
                clear_box[th.get("id")] = [td.text_content().strip() for td in row.findall(".//td")]

        arr = list(clear_box.values())
        if not arr or not arr[0]:
            continue

        remove_indices = [
            i
            for i in range(-1, -len(arr[0]) - 1, -1)
            if all((r[i] if len(r) >= abs(i) else "") == "" for r in arr)
        ]
        th_list = thead.findall(".//th")

        for i in remove_indices:
            idx = len(th_list) + i
            if 0 <= idx < len(th_list):
                th_list[idx].getparent().remove(th_list[idx])

    doc.write(filepath, encoding="utf-8", method="html")


def generate_spa(app_name, file_basenames):
    tabs_html = ""
    for basename in file_basenames:
        filename = f"./data/{basename}.html"
        tabs_html += f'<button class="tab-button" data-src="{filename}">{basename}</button>\n'

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

    xls = pd.ExcelFile(PATHS["DATA_XLSX"])
    sheet_names = xls.sheet_names

    name = PATHS["DATA_XLSX"].stem

    print("清理文件格式...")
    for base_name in sheet_names:
        filename = CURRENT_DIR / f"data/{base_name}.html"
        clean_html_file(filename)

    generate_spa(name, sheet_names)
    print("html 生成完成!")


if __name__ == "__main__":
    # 臨時測試用
    PATHS["DATA_XLSX"] = DATA_DIR / "存在感薄い妹との簡単生活(0.82E).xlsx"
    generate_html()
