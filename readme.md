# DeskLite — 把 iPad 變成電腦第二螢幕(研究 + 原型)

研究 [DeskIn 延伸螢幕功能](https://deskin.io/zh/resource/blog/turn-ipad-into-a-second-monitor-for-windows-and-mac-computers)
後做的可行性分析與可運行原型。

- 🏁 **上手指南**:[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) ——
  Windows/macOS/Linux 各平台從鏡像體驗到真正延伸螢幕的步驟
- 📄 **研究報告**:[docs/RESEARCH.md](docs/RESEARCH.md) —— DeskIn 功能拆解、
  五大子系統技術原理(虛擬顯示器/擷取/編碼/傳輸/客戶端)、開源生態、可行性與路線圖
- 🚀 **原型**:[prototype/](prototype/) —— iPad 開 Safari 掃 QR code 即可當第二螢幕,
  免安裝 App,觸控會回傳電腦(Windows/macOS/Linux 皆支援)

## 快速開始

```bash
pip install -r prototype/requirements.txt
python3 prototype/server.py            # 串流目前的螢幕
# iPad 掃終端機的 QR code(或開啟顯示的網址)
```

Linux 上要「延伸」而不是「鏡像」時,先建一顆虛擬螢幕:

```bash
Xvfb :99 -screen 0 1280x800x24 &       # 或 xrandr 加 VIRTUAL 輸出
python3 prototype/server.py --display :99
```

## 測試

```bash
Xvfb :99 -screen 0 1280x800x24 &
DISPLAY=:99 python3 prototype/server.py &
DISPLAY=:99 python3 prototype/tests/e2e_test.py
```

實測:畫面串流與色彩正確、觸控注入命中預期座標、迴路延遲約 21ms。
