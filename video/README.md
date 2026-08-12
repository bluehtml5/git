# 「您可能喜歡...」相關商品推薦　功能更新影片

CUBE.mo 開店平台的功能更新影片：手機商品頁新增的「您可能喜歡...」推薦區塊。
demo 畫面以平台上的商戶「歌謠 KOIO 1985」的商品頁為例，結尾接 CUBE 正式品牌片尾。
成品約 25 秒、1080×1920。

```
video/
├─ storyboard.md   分鏡、字卡文案、素材檢查表　← 先看這份
├─ mockup.html     可直接錄影的手機介面動畫（依實際商品頁重建）
├─ record.mjs      Playwright 自動錄影腳本（真實網站 / mockup 兩種模式）
├─ finish.sh       轉 mp4 並接上 CUBE 片尾
└─ assets/         放 cube-outro.mp4（品牌片尾，不進版控）
```

## 完整流程

```bash
npm i -D playwright && npx playwright install chromium

node video/record.mjs --mock                                          # 1. 錄 demo
./video/finish.sh video/out/page@*.webm video/assets/cube-outro.mp4   # 2. 轉檔 + 接片尾
# → video/out/final.mp4
```

`finish.sh` 會把兩段都正規化成 1080×1920 / 30fps / 有音軌再接起來——少了這步，
兩段規格不一致，concat 會對不上，或是把片尾的聲音丟掉（demo 本身沒有音軌）。
ffmpeg 不在 PATH 時用 `FFMPEG=/path/to/ffmpeg ./video/finish.sh ...`。

## 快速開始

**看動畫長什麼樣**

```bash
open video/mockup.html          # macOS
xdg-open video/mockup.html      # Linux
```

鍵盤：`space` 重播、`c` 隱藏說明文字（錄影模式）、`1` 切換半速預覽。

網址參數：

| 參數 | 作用 |
|---|---|
| `?clean=1` | 隱藏畫面外的操作說明 |
| `?once=1` | 播一輪就停在結尾卡（錄影用，避免截在循環回開頭） |
| `?frame=1` | 切回「深色底 + 手機外框」版本；**預設是全出血** |

**全出血是預設**：介面填滿整個 1080×1920，不留背景邊。做法是 app 視窗維持 390 寬
（字級、間距才跟真機一致），高度取 9:16 的 693.33，再等比放大 1.3846 倍。
字卡壓在畫面下方，用漸層壓底保證白字讀得到，並讓開底部 tab bar；
兩顆浮動鈕（查詢、回頂端）在全出血版往上移，避免壓到字卡。

手機外框版留著是因為有些場合（官網嵌入、簡報）需要「這是手機」的視覺提示，
但社群直式影片用全出血，畫面才不會有一大塊沒在用。

**錄真實網站**

```bash
node video/record.mjs --live https://koio.com/item/349671
```

推薦區塊自動找不到的話，用選擇器指定：

```bash
node video/record.mjs --live <url> --selector "section.product-recommendations"
```

輸出在 `video/out/*.webm`，接著跑 `finish.sh` 轉檔並接上片尾。

要自己配音樂與旁白（音樂壓到 -25 dB，整體響度標準化到 -14 LUFS）——注意片尾自帶原聲，
混音時要保留或另外處理：

```bash
ffmpeg -i recs.mp4 -i vo.wav -i music.mp3 \
  -filter_complex "[2:a]volume=-25dB[m];[1:a][m]amix=inputs=2:duration=first[a];\
[a]loudnorm=I=-14:TP=-1.5:LRA=11[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k recs_final.mp4
```

## 要換掉的東西

`mockup.html` 最上方的常數就是全部的內容：

| 位置 | 換成 |
|---|---|
| `PRODUCT` | 主商品：標題、價格、UPC、封面配色 |
| `PRODUCT_B` | 被點進去的推薦商品，**必須和分鏡中被點的卡片一致**（預設 `RECS[1]`） |
| `RECS` | 推薦卡片：標題、價格、`days`（預售倒數天數）、封面配色，`cassette:true` 畫成卡帶 |
| `<span class="logo">` | 品牌 logo（HTML 裡 2 處：頁首 + 結尾卡），建議換成真正的圖檔 |
| `play()` 裡的 `caption(...)` | 字卡文案 |

唱片封面是內嵌 SVG（`art()`）畫的**抽象幾何佔位圖**。換成真實商品照就把 `art(...)` 換成 `<img src="...">`。**照片請放本機或自家 CDN**，這份檔案設計成完全離線可用。

介面依實際商品頁重建：固定頁首、社群列、預售橘標、灰色倒數列（真的在走）、藍色加入購物車、
數量增減、紅色出貨日期框、標籤 chips、底部五格 tab bar、浮動查詢鈕、回頂端鈕。

## 為什麼分鏡是這樣排

- **前 2 秒不介紹功能，先給熟悉的畫面。** 觀眾要先認出「這是我的商品頁」，後面的改變才有對照。
- **推薦區塊出現時有高亮框閃一次。** 靜音自動播的情境下，視線需要被明確指到位置。框用**品牌藍**，讓它讀起來是後製標註，不是新的 UI 元件。
- **卡片上不加真實網站沒有的標籤。** 配對理由（同專輯其他版本／同歌手其他作品）用字卡講。影片會被逐格看，演示到不存在的功能是最傷的。
- **結尾收在購物車數字 0 → 1。** 功能影片要收在商業結果，不是收在介面。

## 已知的錄製陷阱

實際操作中，點推薦商品跳頁時會出現**整頁白底轉圈的載入畫面**。用 `--live` 錄真實網站時，
那一段要在剪輯時切掉或蓋轉場，否則影片會停一拍。mockup 版本用滑入轉場，沒有這個問題。
