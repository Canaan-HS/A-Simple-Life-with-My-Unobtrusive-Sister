import io
import csv
from pathlib import Path

from init_loader import requests


class GetCsv:
    def __init__(self):
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
        respon = requests.get(url)
        return respon if respon.status_code != 200 else self.__parse(respon.html)


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
