from get_xlsx import get_xlsx
from generate_html import generate_html

if __name__ == "__main__":
    update = get_xlsx()
    if update:
        generate_html()
    else:
        print("不需要更新")
