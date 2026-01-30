import io
import csv
from pathlib import Path
from types import SimpleNamespace

from curl_cffi import requests as curl
from curl_cffi.requests import exceptions
from selectolax.lexbor import LexborHTMLParser


class Fetch:
    def __init__(self) -> None:
        self.curl_session = curl.Session(impersonate="chrome120")

    def __parse(self, respon, type) -> any:
        parse = {
            "none": lambda: respon,
            "text": lambda: respon.text,
            "content": lambda: respon.content,
            "status": lambda: respon.status_code,
            "html": lambda: LexborHTMLParser(respon.text),
        }

        try:
            return parse.get(type)()
        except:
            return parse.get("none")()

    def curl_get(self, url: str, type: str = "html") -> any:
        """
        >>> type: "none" | "text" | "content" | "status" | "html"
        """
        try:
            return self.__parse(self.curl_session.get(url), type)
        except exceptions.Timeout:
            return SimpleNamespace(text="Request Timeout", status_code=408)
        except Exception as e:
            return SimpleNamespace(text=f"Request Error: {e}", status_code=-1)


class GetCsv(Fetch):
    def __init__(self):
        super().__init__()
        self.url_template = "https://raw.githubusercontent.com/Canaan-HS/A-Simple-Life-with-My-Unobtrusive-Sister/refs/heads/main/data/{0}.html"

    def __parse(self, respon) -> str:
        headers = [th.text().strip() for th in respon.css("thead th[id]")]
        rows = []

        for tr in respon.css("tbody tr"):
            row_key = tr.css("th")[0].text().strip()
            td = tr.css("td")

            row = [row_key]
            for idx in range(len(headers)):
                value = td[idx].text().strip() if idx < len(td) else ""
                row.append(value)

            rows.append(row)

        output = io.StringIO()

        writer = csv.writer(output)
        writer.writerow(["r", *headers])
        writer.writerows(rows)

        return output.getvalue()

    def send(self, sheet: str) -> dict:
        url = self.url_template.format(sheet)
        respon = self.curl_get(url)
        return respon if type(respon) is SimpleNamespace else self.__parse(respon)


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
    csv_text = GetCsv().send("SLG事件-Simulation")
    print(csv_text)

    # output = Path(__file__).parent / "test.csv"
    # output.write_text(csv_text, encoding="utf-8-sig")
