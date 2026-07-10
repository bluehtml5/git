# 上手指南:把 iPad 變成你電腦的延伸螢幕

三種起步方式,由淺入深:

- **A. 五分鐘體驗(鏡像)** —— 什麼都不用裝驅動,先感受串流效果
- **B. 真正的延伸螢幕** —— 加一顆虛擬螢幕,視窗可以拖到 iPad 上
- **C. 往產品開發** —— 下一步的工程路線

事前準備(A、B 通用):

1. 電腦裝好 Python 3.10+([python.org](https://www.python.org/downloads/),
   Windows 安裝時勾選「Add python.exe to PATH」)
2. 電腦和 iPad 連**同一個 Wi-Fi**
3. 下載本 repo,安裝依賴:

   ```bash
   git clone https://github.com/bluehtml5/git.git desklite && cd desklite
   pip install -r prototype/requirements.txt
   ```

---

## A. 五分鐘體驗(鏡像模式)

```bash
python3 prototype/server.py
```

終端機會印出網址和 QR code。iPad 開 **Safari** 掃描(或直接輸入網址,例如
`http://192.168.1.20:8000`),點右上角「全螢幕」。
現在 iPad 上就是你的電腦畫面,手指點 iPad = 點電腦。

- **Windows** 第一次執行會跳出防火牆詢問 → 選「允許」(私人網路)。
- **macOS** 要授權兩個權限(系統設定 → 隱私權與安全性):
  「螢幕錄製」給畫面擷取用、「輔助使用」給觸控回傳用。
- 想串流指定螢幕:`--monitor 2`;調畫質/流暢度:`--quality 80 --fps 30`。

## B. 真正的延伸螢幕(視窗拖得過去)

「延伸」需要讓作業系統多認得一顆螢幕,再把那顆螢幕串流到 iPad:

### Windows(建議先做這條,生態最成熟)

1. 安裝開源虛擬螢幕驅動,二選一:
   - [Parsec VDD](https://github.com/nomi-san/parsec-vdd/releases) —— 下載
     `ParsecVDisplay` 安裝後,在它的介面按「Add Display」
   - [Virtual Display Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver/releases)
2. Windows 設定 → 系統 → 顯示器:確認多了一顆螢幕,模式選「延伸」,
   解析度建議設成 iPad 的比例(如 2360×1640 或 1280×800)
3. 串流那顆新螢幕(編號通常是 2,不確定就逐一試):

   ```bash
   python prototype/server.py --monitor 2
   ```

4. iPad Safari 掃 QR → 全螢幕。把任何視窗往那顆「螢幕」拖,就會出現在 iPad 上,
   在 iPad 上點按就是在操作那顆螢幕。

### macOS

1. 裝 [DeskPad](https://github.com/Stengo/DeskPad)(開源,`brew install deskpad`)
   或 [BetterDisplay](https://github.com/waydabber/BetterDisplay),建立一顆虛擬螢幕
2. 系統設定 → 顯示器:把它排列成延伸桌面
3. `python3 prototype/server.py --monitor 2`(裝了 DeskPad 後編號可能不同,逐一試)
4. iPad Safari 掃 QR → 全螢幕

### Linux

```bash
# X11:對主 GPU 輸出加一顆虛擬輸出(名稱依 xrandr 輸出而定)
xrandr --setmonitor VIRTUAL1 1280/300x800/190+1920+0 none
# 或乾脆用獨立的 Xvfb 當第二桌面
Xvfb :99 -screen 0 1280x800x24 &
python3 prototype/server.py --display :99
```

### 小技巧

- iPad 上「分享 → 加入主畫面」,之後點圖示就是全螢幕 App 體驗(無網址列)
- 有線更穩:iPad 用 USB 接電腦 + 開啟「個人熱點」共享,或兩台都接同一台路由器的 5GHz
- 畫面糊 → `--quality 85`;不夠順 → `--fps 60`(頻寬會上升)

### 疑難排解

| 症狀 | 原因/解法 |
|---|---|
| iPad 連不上 | 防火牆擋 8000 埠;或兩台不在同一網段(公司/宿舍 Wi-Fi 常隔離裝置,改用手機熱點測試) |
| 畫面全黑 | macOS 沒給「螢幕錄製」權限;或 `--monitor` 編號選錯 |
| 點了沒反應 | macOS 沒給「輔助使用」權限;Linux 下 DISPLAY 沒設對 |
| 延遲高 | 換 5GHz Wi-Fi;降 `--quality`;關掉省電模式 |

## C. 想繼續往「產品」開發?

按 [RESEARCH.md](RESEARCH.md) 的路線圖,建議的第一步工程順序:

1. **編碼升級**(影響最大):JPEG → H.264。伺服器端用 `ffmpeg`/PyAV 硬體編碼,
   iPad 端用 WebCodecs(Safari 16.4+ 支援)解碼,頻寬立刻降一個數量級
2. **連線體驗**:mDNS/Bonjour 自動探索(`zeroconf` 套件)、配對 token 進 QR code、TLS
3. **Windows 整合**:程式內建 Parsec VDD 的建立/銷毀(它有 CLI/API),
   做到「一鍵延伸」—— 這一步完成就是 MVP 產品了
4. 之後才是:原生 iPad App(VideoToolbox + Apple Pencil)、macOS CGVirtualDisplay、
   USB 有線、跨網段中繼
