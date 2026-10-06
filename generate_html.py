from init_loader import (
    load_meta,
    CURRENT_DIR,
    IMAGE_EXTS,
    DATA_DIR,
)


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


def generate_html(meta: dict | None = None):
    img_resources = DATA_DIR / "resources"

    for file in img_resources.rglob("*"):
        if file.is_file() and file.suffix.lower().lstrip(".") in IMAGE_EXTS:
            try:
                file.unlink()  # 嘗試清理圖片類型文件
            except:
                pass

    if meta is None:
        meta = load_meta()
    sheet_names = meta["sheets"]
    name = meta["name"]

    generate_content(name, sheet_names)
    print("html 生成完成!")


if __name__ == "__main__":
    generate_html()
