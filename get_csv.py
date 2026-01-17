import io
import csv
from types import SimpleNamespace

import httpx
from lxml import html


BROWSER_HEAD = {
    "Google": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
    },
    "Edge": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
    },
}


class Fetch:
    def __init__(self, headers: dict | str = "Google", cookies: dict = None) -> None:
        self.client = httpx.Client(http2=True, timeout=5)
        self.headers = (
            BROWSER_HEAD[headers.capitalize()]
            if isinstance(headers, str)
            else headers if isinstance(headers, dict) else None
        )
        self.cookies = cookies

    def __parse(self, respon, type) -> any:
        parse = {
            "none": lambda: respon,
            "text": lambda: respon.text,
            "content": lambda: respon.content,
            "status": lambda: respon.status_code,
            "html": lambda: html.fromstring(respon.text),
        }

        try:
            return parse.get(type)()
        except:
            return parse.get("none")()

    def http2_get(self, url: str, type: str = "text") -> any:
        """
        *   支援 http2 的 Get 請求
        >>> [ url ]
        要請求的連結

        >>> [ type ]
        要獲取的結果類型
        ("none" | "text" | "content" | "status" | "html")

        "none" => 無處理
        "html" => lxml 進行解析
        """
        try:
            return self.__parse(
                self.client.get(url, headers=self.headers, cookies=self.cookies), type
            )
        except httpx.ConnectTimeout:
            return SimpleNamespace(text="Request Timeout", status_code=408)


class GetCsv(Fetch):
    def __init__(self):
        super().__init__()
        self.url_template = "https://raw.githubusercontent.com/Canaan-HS/A-Simple-Life-with-My-Unobtrusive-Sister/refs/heads/main/data/{0}.html"

    def __parse(self, respon) -> str:
        headers = [th.text_content().strip() for th in respon.cssselect("thead th[id]")]
        rows = []

        for tr in respon.cssselect("tbody tr"):
            row_key = tr.cssselect("th")[0].text_content().strip()
            td = tr.cssselect("td")

            row = [row_key]
            for idx in range(len(headers)):
                value = td[idx].text_content().strip() if idx < len(td) else ""
                row.append(value)

            rows.append(row)

        output = io.StringIO()

        output.write("r=Row key\n")

        writer = csv.writer(output)
        writer.writerow(["r", *headers])
        writer.writerows(rows)

        return output.getvalue()

    def send(self, sheet: str) -> dict:
        url = self.url_template.format(sheet)
        respon = self.http2_get(url, "html")
        return self.__parse(respon)


if __name__ == "__main__":
    """
    公告-Notice
    SLG事件-Simulation
    RPG事件-Combat
    提示-Tips
    地圖-Map
    野外掉落-Drops
    武器-Weap
    裝甲-Gears
    道具-Items
    料理-Dish
    狀態-Status
    手機存檔-MobileArchive
    影音-Video
    獨立顯卡-dGPU
    """
    result = GetCsv().send("料理-Dish")
    print(result)
