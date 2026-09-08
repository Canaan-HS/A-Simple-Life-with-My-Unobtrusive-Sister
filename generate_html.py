from init_loader import (
    pd,
    html,
    CURRENT_DIR,
    IMAGE_EXTS,
    DATA_DIR,
    PATHS,
)


def expand_row(row, ncol):
    cells = [None] * ncol
    pos = 0

    for td in row.findall(".//td"):
        if pos >= ncol:
            break
        span = min(int(td.get("colspan", 1)), ncol - pos)
        text = td.text_content().strip()
        for k in range(span):
            cells[pos + k] = text
        pos += span

    return cells


def shrink_span(td, name, lost):
    left = int(td.get(name, 1)) - lost

    if left <= 1:
        td.attrib.pop(name, None)
    else:
        td.set(name, str(left))


def clean_table(tbody, thead):
    th_list = thead.findall(".//th")
    ncol = len(th_list) - 1
    if ncol <= 0:
        return

    all_rows = tbody.findall(".//tr")

    drop_rows, allow_delete = set(), True
    for i in range(len(all_rows) - 1, -1, -1):
        row = all_rows[i]
        th = row.find(".//th")
        if th is None:
            allow_delete = False
        elif allow_delete and th.text_content().strip() == row.text_content().strip():
            drop_rows.add(i)
        else:
            allow_delete = False

    for i, row in enumerate(all_rows):
        if i in drop_rows:
            continue
        for td in row.findall(".//td"):
            rowspan = int(td.get("rowspan", 1))
            if rowspan <= 1:
                continue
            lost = sum(
                1
                for j in range(i + 1, min(i + rowspan, len(all_rows)))
                if j in drop_rows
            )
            if lost:
                shrink_span(td, "rowspan", lost)

    for i in sorted(drop_rows, reverse=True):
        all_rows[i].getparent().remove(all_rows[i])

    rows = tbody.findall(".//tr")
    if not rows:
        return

    grid = [expand_row(row, ncol) for row in rows]
    spanned = {c for cells in grid for c, text in enumerate(cells) if text is None}

    drop_cols = {
        c
        for c in range(ncol)
        if c not in spanned and all(cells[c] == "" for cells in grid)
    }

    if not drop_cols or len(drop_cols) == ncol:
        return

    for c in sorted(drop_cols, reverse=True):
        th = th_list[c + 1]
        if th.getparent() is not None:
            th.getparent().remove(th)

    for row in rows:
        pos = 0
        for td in list(row.findall(".//td")):
            if pos >= ncol:
                break
            span = min(int(td.get("colspan", 1)), ncol - pos)
            covered = set(range(pos, pos + span))
            lost = len(covered & drop_cols)
            if lost == span:
                row.remove(td)
            elif lost:
                shrink_span(td, "colspan", lost)
            pos += span


def clean_html_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        doc = html.parse(f)

    for table in doc.findall(".//table"):
        tbody, thead = table.find(".//tbody"), table.find(".//thead")
        if tbody is None or thead is None:
            continue
        clean_table(tbody, thead)

    doc.write(filepath, encoding="utf-8", method="html")


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

    xls = pd.ExcelFile(PATHS["DATA_XLSX"])
    sheet_names = xls.sheet_names

    name = PATHS["DATA_XLSX"].stem

    print("清理文件格式...")
    for base_name in sheet_names:
        filename = CURRENT_DIR / f"data/{base_name}.html"
        clean_html_file(filename)

    generate_content(name, sheet_names)
    print("html 生成完成!")


if __name__ == "__main__":
    # 臨時測試用
    PATHS["DATA_XLSX"] = DATA_DIR / "存在感薄い妹との簡単生活(1.2.0).xlsx"
    generate_html()
