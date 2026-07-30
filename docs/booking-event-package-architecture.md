# 活動、預約、回數卷 — 系統統一方案探討

> 狀態：方案探討（未實作）
> 背景：現時有兩個入口 —
> - 預約系統：`/?booking=<hash>`（美容、課程、活動體驗預約，含回數卷）
> - 活動售票：`/ticket-sales/index.html`
>
> 兩者實際上係同一個系統，需要決定點樣統一。

---

## 1. 問題本質：三樣嘢唔係同一層抽象

|  | 活動 (Event) | 預約 (Appointment) | 回數卷 (Package / Pass) |
|---|---|---|---|
| 賣緊咩 | 已開好場次嘅**席位** | 資源在某時段嘅**佔用** | 將來兌換嘅**權利** |
| 時間來源 | 主辦方預先定，客揀場次 | 客揀時間，受資源可用性限制 | 冇時間，只有有效期 |
| 容量 | N 人 | 通常 1（資源獨佔） | 不適用 |
| 計價單位 | 席位 × 票種 | 時段 × 資源 | 次數 或 金額 |
| 取消行為 | 退票 / 退款 | 以改期為主 | 回退次數 |
| 收入確認 | 出席日 | 服務完成日 | **預收款（負債）**，兌換時先確認收入 |

### 兩個關鍵洞見

**洞見 1 — 活動係預約嘅特例。**
只要 booking 引擎支援「預先開好嘅場次 + capacity > 1」，活動就只係一種 session。
「活動體驗預約」呢個品類正正卡喺兩者中間，反過來證明呢個統一係啱嘅方向。

**洞見 2 — 回數卷唔應該同預約平排。**
回數卷係支付／權益層（entitlement），橫跨美容、課程、活動全部品類。
現時把它放喺預約系統內部，就係「活動用唔到卷」嘅結構性根源。
它應該同「錢」同一層，唔係同「預約」同一層。

---

## 2. 三個方案

### 方案 A — 維持雙系統，只共用會員與支付

**做法**：ticket-sales 同 booking 各自保留 schema，只抽出 customer / auth / payment /
notification 做共用模組。回數卷留喺 booking 側，活動唔支援回數卷（或做一個單向 bridge）。

- ✅ 改動最細、最快、風險最低
- ❌ 兩套後台、兩套日曆、兩套報表，長遠雙倍維護成本
- ❌ 回數卷跨品類兌換做唔到，或者要 hack
- ❌「活動體驗預約」呢種混合品類兩邊都唔啱位

**適用情境**：活動只係偶爾搞，唔係主營業務。

---

### 方案 B — 統一 Booking 引擎（活動 = 有容量嘅場次）

**做法**：一個 `product`（服務／課程／活動）→ 一個 `session`（帶 capacity）→ 一個
`booking`（帶 qty）。

- 預約類：session 由資源日曆動態生成或 on-demand 建立，`capacity = 1`
- 活動類：session 由主辦方預先開，`capacity = N`
- 課程類：介乎兩者 — 一期多堂（recurring sessions）

- ✅ 一套日曆、一套容量／超賣邏輯、一套 check-in、一套通知模板
- ⚠️ 抽象要做得準：活動嘅**票種**（成人／小童／早鳥）同預約嘅**資源指派**必須係兩個
  可以獨立開關嘅維度，唔好互相污染
- ❌ 回數卷仍然冇一個乾淨嘅位置擺

---

### 方案 C — 四層架構（建議目標）

```
┌─────────────────────────────────────────────────┐
│ 1. Catalog 目錄層                                │
│    product（服務／課程／活動）、price_tier、屬性    │
├─────────────────────────────────────────────────┤
│ 2. Scheduling 排程層                             │
│    resource（美容師／房／器材）、availability rule、 │
│    session、capacity                             │
├─────────────────────────────────────────────────┤
│ 3. Order 訂單層                                  │
│    cart → order → payment → refund（活動預約共用）  │
├─────────────────────────────────────────────────┤
│ 4. Entitlement 權益層                            │
│    回數卷、儲值、會籍、優惠券 → 統一 credit ledger   │
└─────────────────────────────────────────────────┘
```

- Booking 只係 order line 嘅一種 fulfillment
- 回數卷流程：買 package → 產生 credit（有 scope／有效期／餘額）→ 落單時 credit 作為
  一種 payment method → 取消時**寫一條回退 ledger entry**
- ✅ 最有擴展性：日後加「月費無限次會籍」、「套票組合」、「禮券」都唔使改 booking
- ✅ 財務可追溯（ledger 而唔係直接改 balance）
- ❌ 一次過重構成本最高，需要清楚定義 credit scope 規則

---

## 3. 建議

**目標架構取方案 C，但按方案 B 嘅次序落地。**

先將活動併入 booking 引擎（兩者最相似、收益最快），再把回數卷抽成獨立 entitlement 層。
唔好一次過重構晒。

---

## 4. 資料模型草稿

```sql
-- ── Catalog ──────────────────────────────────────────────
product (
  id, type,            -- service | course | event
  name, category,
  booking_mode,        -- resource_slot | fixed_session
  credit_cost          -- 一次要扣幾多次卷，預設 1
)
price_tier (product_id, name, price, min_qty, max_qty)
                       -- 成人／小童／早鳥／會員價

-- ── Scheduling ───────────────────────────────────────────
resource (id, type, name)                    -- staff | room | equipment
availability_rule (resource_id, weekday, start_time, end_time, valid_from, valid_to)
session (
  id, product_id, start_at, end_at,
  capacity, booked_count, status
)
  -- 預約類：由 rule 動態產生或 on-demand 建立，capacity = 1
  -- 活動類：預先建立，capacity = N
session_resource (session_id, resource_id)   -- 邊個做／邊間房

-- ── Order ────────────────────────────────────────────────
order (id, customer_id, status, total, paid_at)
order_item (order_id, product_id, price_tier_id, qty, amount, session_id)
booking (id, order_item_id, session_id, customer_id, qty, status, checkin_at)
payment (order_id, method, amount)           -- cash | card | credit | ...

-- ── Entitlement ──────────────────────────────────────────
package (
  id, name,
  credit_type,         -- times（次數卷）| amount（儲值卷）
  credits, price, validity_days
)
package_scope (package_id, product_id, category, product_type)
                       -- 可兌換範圍
customer_credit (id, customer_id, package_id, balance, expires_at, status)
credit_ledger (
  credit_id, delta,
  reason,              -- purchase | redeem | refund | expire | adjust
  booking_id, created_at
)
```

**重點**：`customer_credit.balance` 應該係 `credit_ledger` 嘅物化總和，任何變動都要有一條
ledger entry。唔好畀任何 code path 直接 UPDATE balance。

---

## 5. 一定要早期決定嘅細節

呢啲遲決定會好痛：

1. **回數卷可唔可以用喺活動？**
   活動固定價、預約按時間計，一張「1 次」卷對應活動邊個票種？
   → 建議兩種卷並存：**次數卷**（只限 scope 內同值服務）、**儲值卷**（按金額扣，最通用）。
   跨品類兌換一律用儲值卷。

2. **一次預約扣幾多次？** 90 分鐘 vs 60 分鐘
   → `product.credit_cost`，預設 1，可設 2。

3. **取消政策**：X 小時前取消回退 credit，之後照扣 — 一律經 ledger，唔好特事特辦。

4. **有效期／過期**：用排程 job 寫一條 expire ledger entry。
   唔好靠查詢時即時計算，否則報表永遠對唔到數。

5. **一張卷可唔可以幾個人共用**（家庭／朋友）
   → credit 綁 `customer` 定 `household`？呢個好難事後改。

6. **超賣／併發**：`session.booked_count` 必須 DB 層 atomic update + unique constraint。
   活動（多人搶同一場）尤其危險。

7. **財務分帳**：回數卷係預收負債，報表要分開睇「現金流」同「已確認收入」。

8. **前端路由統一**：
   現時 `/?booking=<hash>` 同 `/ticket-sales/index.html` 係兩套風格。
   建議統一為 `/booking/:token`、`/events/:slug`、`/me/credits`，共用 layout 同登入狀態 —
   用戶先會覺得係一個系統。

---

## 6. 分階段遷移路線

| Phase | 內容 | 風險 |
|---|---|---|
| 1 | 統一會員／登入／通知／支付抽象，活動同預約共用 customer 表 | 低 |
| 2 | 引入 order / order_item，兩邊落單都經同一條路徑 | 低 |
| 3 | 活動 session 併入 booking 引擎（引入 capacity 概念） | 中 |
| 4 | 回數卷改為 credit + ledger，開放跨品類兌換 | 中高（涉及錢） |
| 5 | 後台合併：一個日曆睇晒美容／課程／活動，一套報表 | 中 |

Phase 4 建議做雙寫 + 對數期，確認新舊餘額一致先切換。
