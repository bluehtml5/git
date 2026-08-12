# 相關商品推薦　功能更新影片

錄一支 16 秒直式影片，說明手機商品頁新增的「相關商品推薦」區塊。

```
video/
├─ storyboard.md   分鏡、字卡文案、素材檢查表　← 先看這份
├─ mockup.html     可直接錄影的手機介面動畫（16.5 秒循環）
└─ record.mjs      Playwright 自動錄影腳本（真實網站 / mockup 兩種模式）
```

## 快速開始

**看動畫長什麼樣**

```bash
open video/mockup.html          # macOS
xdg-open video/mockup.html      # Linux
```

鍵盤：`space` 重播、`c` 隱藏說明文字（錄影模式）、`1` 切換半速預覽。

**直接輸出影片檔**

```bash
npm i -D playwright && npx playwright install chromium

node video/record.mjs --mock                    # 錄 mockup
node video/record.mjs --live https://你的網站/item/315537
```

推薦區塊自動找不到的話，用選擇器指定：

```bash
node video/record.mjs --live <url> --selector "section.product-recommendations"
```

輸出在 `video/out/*.webm`。轉成社群平台吃的 mp4：

```bash
ffmpeg -i video/out/xxx.webm \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,\
pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0c0d10,fps=30" \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p \
  -movflags +faststart video/out/recs.mp4
```

配上音樂與旁白（音樂壓到 -25 dB，整體響度標準化到 -14 LUFS）：

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
| `PRODUCT` / `PRODUCT_B` | 主商品與被點進去的推薦商品（名稱、價格、配色） |
| `RECS` | 推薦卡片，`tag` 是配對理由標籤 |
| `<span class="wordmark">BRAND</span>` | 品牌字樣（HTML 裡，共 1 處 + 結尾卡 1 處） |
| `SHOTS` 區塊的 `caption(...)` | 字卡文案 |

鞋子插圖是內嵌 SVG（`sneaker()`），要換成真實商品照就把 `<div class="hero">` 和 `.thumb` 裡的 `sneaker(...)` 換成 `<img>`。**照片請放本機或自家 CDN**，這份檔案設計成完全離線可用。

## 為什麼分鏡是這樣排

- **前 2 秒不介紹功能，先給熟悉的畫面。** 觀眾要先認出「這是我的商品頁」，後面的改變才有對照。
- **推薦區塊出現時有高亮外框閃一次。** 靜音自動播的情境下，觀眾的視線需要被明確指到位置。
- **卡片上的標籤（同系列／相似材質／常一起購買）比區塊本身重要。** 那是這次更新真正的賣點——不是「多了一排商品」，是「配得準」。
- **結尾有加購動作與購物袋數字變化。** 功能影片要收在商業結果，不是收在介面。
