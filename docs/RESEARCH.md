# DeskIn「iPad 第二螢幕」研究與可行性分析

> 研究對象:<https://deskin.io/zh/resource/blog/turn-ipad-into-a-second-monitor-for-windows-and-mac-computers>
> 結論:**可行**。核心技術每一塊都有成熟的開源實作可參考,本 repo 已附上可運行的原型(`prototype/`)。

## 1. DeskIn 是什麼

DeskIn 是一套遠端桌面軟體,「延伸螢幕(Extend Screen)」是它的招牌功能之一:
在電腦和 iPad 上都裝 DeskIn、登入同一帳號,電腦端選「延伸螢幕」、挑選目標 iPad,
之後就能把任何視窗拖到 iPad 上,把 iPad 當成第二顆螢幕用。

官方宣傳的規格與賣點:

| 項目 | 規格 |
|---|---|
| 畫質 | 4K@60fps 或 2K@144fps |
| 色彩 | 4:4:4 True Color(無色度抽樣,文字/設計工作不糊) |
| 延遲 | ≤ 40ms |
| 連線 | 掃 QR code 或選擇裝置,即建立無線連結 |
| 平台 | Windows、macOS、iOS、Android 互通 |
| 安全 | 256-bit AES 端對端加密、隱私螢幕模式(遠端螢幕變黑) |
| 加值 | 內建語音通話、協作白板 |

同類產品:Duet Display、Luna Display、Apple Sidecar(僅 Mac+iPad)、
Spacedesk(Windows)、superdisplay 等。

## 2. 技術原理拆解

做一套「iPad 第二螢幕」軟體,本質上是五個子系統:

```
┌─────────────────── 電腦端 ───────────────────┐      ┌──── iPad 端 ────┐
│ ①虛擬顯示器 → ②畫面擷取 → ③視訊編碼 ─┐      │      │ ⑤解碼 + 顯示     │
│      ↑                                └─④傳輸─┼──────┤                 │
│ 滑鼠/鍵盤事件注入 ←──────────────── ④傳輸 ←──┼──────┤ 觸控/Pencil 事件 │
└──────────────────────────────────────────────┘      └─────────────────┘
```

### ① 虛擬顯示器 —— 最難、也最關鍵的一塊

要讓 OS「真的以為多接了一顆螢幕」(這樣視窗才能拖過去、延伸桌面才成立),
必須建立虛擬顯示裝置:

- **Windows**:官方支援的 **IddCx(Indirect Display Driver)** 框架。
  開源參考:[parsec-vdd](https://github.com/nomi-san/parsec-vdd)(支援 4K@240Hz)、
  [Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver)
  (IddCx 1.10、HDR、自訂 EDID)、virtual-display-rs(Rust)。
  難點:驅動需要 **WHQL/EV 憑證簽章** 才能發佈給一般使用者。
- **macOS**:沒有公開 API,業界(BetterDisplay、DeskPad、Duet)都用私有 API
  **CGVirtualDisplay**。開源參考:[DeskPad](https://github.com/Stengo/DeskPad)、
  [SimpleDisplay](https://simpledisplay.app/)、
  [OpenDisplay](https://github.com/peetzweg/opendisplay)(完整的開源 Sidecar 替代品!)。
  風險:私有 API 隨 macOS 更新可能變動;舊式 kernel extension 做法已被 Apple 封殺
  (Duet 曾因此中斷),CGVirtualDisplay 是目前唯一不用外接假 dongle 的路。
- **Linux**:最簡單 —— `xrandr` 的 VIRTUAL 輸出、Xvfb、或 evdi/DisplayLink。

> 替代捷徑:不做虛擬顯示器,只做「鏡像」或用 HDMI 假負載(dummy plug)騙出第二顆螢幕
> —— Deskreen 目前就是這樣,體驗打折但完全不用寫驅動。

### ② 畫面擷取

- Windows:**Desktop Duplication API**(DXGI,GPU 內直接拿框,零拷貝)
- macOS:**ScreenCaptureKit**(可指定只擷取虛擬顯示器)
- Linux:X11 XShm / PipeWire(Wayland)
- 跨平台起步:Python `mss`、Electron `desktopCapturer`(本原型用 mss)

### ③ 視訊編碼 —— 決定「4K60 / ≤40ms」能不能達成

- 必須用**硬體編碼**:NVENC(NVIDIA)、Quick Sync(Intel)、AMF(AMD)、
  VideoToolbox(Mac)。CPU 軟編到 1080p60 就吃滿了。
- 低延遲設定:H.264/HEVC low-latency preset、無 B-frame、intra-refresh、
  動態碼率 + 掉幀背壓(back-pressure)+ 關鍵幀恢復。
- DeskIn 的「4:4:4 True Color」= 編碼時不做色度抽樣(H.264 High 4:4:4 profile
  或 HEVC RExt),文字邊緣不會糊,這是遠端桌面產品的高級選配。

### ④ 傳輸

- **WebRTC**(UDP、內建 DTLS-SRTP 加密、NAT 穿透、擁塞控制)—— Deskreen 的選擇,
  也是瀏覽器客戶端唯一的選擇;或自訂 UDP/QUIC 協定(延遲控制更細)。
- 區域網路探索:**mDNS/Bonjour**;跨網段則需要中繼伺服器(這是 DeskIn 收訂閱費的部分)。
- iOS 有線連線:透過 **usbmuxd** 走 Lightning/USB-C,延遲更穩(Duet 的起家做法)。
- QR code 配對:QR 裡就是 `http://<區網IP>:<port>/#<一次性金鑰>`,本原型已實作。

### ⑤ iPad 客戶端

兩條路:

| | 原生 App | 瀏覽器(免安裝) |
|---|---|---|
| 解碼 | VideoToolbox 硬解 + `AVSampleBufferDisplayLayer` | WebCodecs / MSE / WebRTC |
| 延遲 | 最低 | 稍高但可接受 |
| Apple Pencil | 完整(壓力、傾斜) | Pointer Events 有 pressure/tilt,堪用 |
| 上架 | 要 App Store 審核 | 掃 QR 即用 |

Deskreen 選瀏覽器路線(任何裝置都能當第二螢幕),Duet/DeskIn 選原生 App。

## 3. 可以站在肩膀上的開源專案

| 專案 | 語言 | 它解決了什麼 |
|---|---|---|
| [Deskreen](https://github.com/pavlobu/deskreen) | TypeScript/Electron | 完整產品:WebRTC 串流到任何瀏覽器 + E2E 加密 |
| [Weylus](https://github.com/H-M-H/Weylus) | Rust | 平板變繪圖板/觸控螢幕,含觸控與手寫筆事件回傳 |
| [OpenDisplay](https://github.com/peetzweg/opendisplay) | Swift | Mac 專用開源 Sidecar:CGVirtualDisplay + H.264 + USB/WiFi + 觸控 |
| [parsec-vdd](https://github.com/nomi-san/parsec-vdd) | C | Windows IddCx 虛擬顯示驅動 |
| [Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver) | C++ | 社群維護的 Windows 虛擬螢幕驅動 |
| [DeskPad](https://github.com/Stengo/DeskPad) | Swift | macOS 虛擬顯示器(CGVirtualDisplay 用法範本) |
| [Sunshine](https://github.com/LizardByte/Sunshine)/Moonlight | C++ | 硬體編碼 + 低延遲串流管線的最佳範本 |

## 4. 可行性評估與路線圖

**難度分級:**

- 🟢 簡單(1–2 週):畫面擷取、JPEG/WebSocket 串流、瀏覽器客戶端、QR 配對、觸控回傳
  —— 即本 repo 原型,已完成
- 🟡 中等(1–2 月):WebRTC + 硬體 H.264、mDNS 探索、Windows IddCx 驅動整合(拿現成開源驅動)、原生 iPad App
- 🔴 較難(2–3 月+):macOS CGVirtualDisplay(私有 API 逆向維護)、Windows 驅動簽章(EV 憑證 + 微軟硬體開發者帳號)、4:4:4 編碼、跨網段中繼、≤40ms 端到端調優

**建議路線:**

1. **MVP(Deskreen 模式)**:鏡像/延伸現有螢幕 → 瀏覽器客戶端。零驅動、全平台。
2. **v1(單平台真延伸)**:先做 Windows(IddCx 生態最成熟、開源驅動可直接用),
   WebRTC + NVENC/QSV,iPad 走瀏覽器。
3. **v2(對標 DeskIn)**:macOS CGVirtualDisplay、原生 iPad App(VideoToolbox +
   Apple Pencil)、USB 連線、帳號系統與跨網段中繼。

**商業/法務注意:** Windows 驅動簽章費用與流程、macOS 私有 API 的 App Store 上架風險
(DeskIn/BetterDisplay 都是網站直售而非 MAS)、iOS App 上架審核。

## 5. 本 repo 的原型(DeskLite)

`prototype/` 是一個約 500 行的可運行原型,走 Deskreen 路線(iPad 免安裝 App):

- `server.py`:mss 擷取螢幕 → 變更偵測(CRC 跳過靜止畫面)→ JPEG →
  WebSocket 廣播;接收觸控事件用 XTest 注入滑鼠;啟動時印 QR code。
- `static/index.html`:iPad Safari 客戶端 —— canvas 顯示、Pointer Events
  (支援觸控/Apple Pencil 壓力)回傳、全螢幕、fps/延遲 HUD、斷線自動重連。
- `tests/e2e_test.py`:端對端測試(config → 畫面正確性 → 觸控注入後游標位置驗證)。

實測(容器內 Xvfb 1280×800 虛擬顯示器 + Chromium):畫面串流正確、
觸控注入命中預期座標、迴路延遲 **21ms**。

限制(原型定位,非產品):JPEG 而非 H.264(頻寬高 ~10 倍)、無加密與配對驗證、
輸入注入僅支援 X11、不含虛擬顯示器驅動(Linux 上用 Xvfb/xrandr 充當)。
下一步優先順序:WebCodecs + H.264 → mDNS 探索 → TLS + 配對 token → Windows IddCx 整合。
