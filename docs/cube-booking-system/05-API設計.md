# 05. API 設計（RESTful）

## 1. 通用約定

- Base URL：`/api/v1`
- 認證：JWT Bearer Token；商家端 Token 內含 `merchant_id` 與角色，後端強制注入租戶過濾
- 三端路徑前綴：用戶端 `/app`、商家端 `/biz`、平台管理端 `/admin`
- 分頁：`?page=1&size=20`，回傳 `{ data, total, page, size }`
- 錯誤格式：`{ code: "BOOKING_SLOT_TAKEN", message: "...", details? }`
- 冪等：建立預約、扣減等寫入 API 支援 `Idempotency-Key` header

## 2. 用戶端 API（/app）

### 認證與會員
| Method | Path | 說明 |
|---|---|---|
| POST | /auth/otp/send | 發送手機驗證碼 |
| POST | /auth/otp/verify | 驗證登入，回 JWT |
| POST | /auth/line | LINE 登入 |
| GET | /me | 個人資料 |
| GET | /me/memberships | 我的各商家會員卡 |
| GET | /me/wallets?merchant_id= | 我的資產（儲值/點數/堂數卡） |
| GET | /me/wallets/:id/ledger | 扣減明細帳 |

### 瀏覽與預約
| Method | Path | 說明 |
|---|---|---|
| GET | /merchants/:slug | 商家頁 |
| GET | /merchants/:slug/services | 預約項目列表 |
| GET | /merchants/:slug/staffs?service_id= | 可服務人員 |
| GET | /merchants/:slug/availability | **可預約時段**<br/>`?service_id=&date=&staff_id?=` |
| POST | /bookings | 建立預約 `{service_id, staff_id?, start_at, price_option_id}` |
| GET | /bookings?status=upcoming | 我的預約 |
| GET | /bookings/:id | 預約詳情（含商家聯絡方式；遲到/改期/取消請聯絡商家） |

## 3. 商家端 API（/biz）

### 設定
| Method | Path | 說明 |
|---|---|---|
| GET/PUT | /merchant | 商家基本資料、營業時間 |
| GET/PUT | /policies | 預約政策（全店） |
| GET/POST/PUT/DELETE | /services | 預約項目 CRUD（含時長/buffer/扣減方式） |
| PUT | /services/:id/policy | 項目覆寫政策 |
| GET/POST/PUT/DELETE | /pass-products | 卡/方案商品 CRUD |
| GET/POST/PUT/DELETE | /resources | 資源（房間/設備） |

### 人員與排班
| Method | Path | 說明 |
|---|---|---|
| GET/POST/PUT | /staffs | 員工管理與角色 |
| PUT | /staffs/:id/services | 指派可提供項目 |
| GET/PUT | /staffs/:id/shift-rules | 週期班表（工作時長） |
| POST/DELETE | /staffs/:id/shift-exceptions | 請假/調班/加班 |
| GET | /calendar?view=day&date=&staff_id?= | 行事曆聚合資料 |

### 預約操作
| Method | Path | 說明 |
|---|---|---|
| GET | /bookings?date=&staff_id=&status= | 預約查詢 |
| POST | /bookings | **代客預約**（會員或非會員，見下方範例） |
| POST | /bookings/recurring | 重複性預約批次建立 `{pattern, weeks, ...}` |
| POST | /bookings/:id/approve\|reject | 審核（審核制） |
| PUT | /bookings/:id/late-note | 遲到註記 `{note}`（行事曆顯示 ⏰） |
| GET | /bookings/:id/cancel-preview | 取消返還試算（依 cancel_rules） |
| POST | /bookings/:id/reschedule | 商家改期 `{new_start_at, staff_id?}` |
| POST | /bookings/:id/cancel | 商家取消 `{refund_pct?, reason?}`（調整試算需填原因） |
| POST | /bookings/:id/no-show | 標記爽約（自動套罰則，可調整） |
| POST | /bookings/:id/complete | 標記完成 |
| POST | /bookings/batch-complete | 批次標記完成 `{date, booking_ids?}` |

### 派工（指派員工）
| Method | Path | 說明 |
|---|---|---|
| GET | /bookings/unassigned?date= | 待指派預約列表 |
| GET | /bookings/:id/assign-candidates | 該時段可指派員工（含可用性/負載/不可用原因） |
| POST | /bookings/:id/assign | 指派員工 `{staff_id, notify_member?}` |
| POST | /bookings/:id/reassign | 改派換人 `{staff_id, reason}`（鎖定期內需 Owner） |
| POST | /bookings/auto-assign | 批次自動派工 `{date, strategy?}`，回傳建議供確認 |
| GET | /assignments?staff_id=&status=proposed | 員工的待確認指派 |
| POST | /assignments/:id/accept \| reject | 員工接受/拒絕指派 |

### 會員與扣減
| Method | Path | 說明 |
|---|---|---|
| GET | /members?tag=&q= | 會員列表/搜尋 |
| GET | /members/:id | 會員詳情（資產、預約史、爽約記錄） |
| POST | /members/:id/wallets | 販售/贈送卡、儲值 |
| POST | /wallets/:id/adjust | 手動調帳 `{change, note}`（留稽核） |

### 操作紀錄（稽核）
| Method | Path | 說明 |
|---|---|---|
| GET | /operation-logs?staff_id=&action=&from=&to= | **員工操作紀錄查詢**（依同事/動作/期間篩選） |
| GET | /bookings/:id/events | 單筆預約完整操作軌跡（誰建立/改期/報到） |

### 報表
| Method | Path | 說明 |
|---|---|---|
| GET | /reports/revenue?from=&to= | 營收 |
| GET | /reports/attendance | 出席率/爽約率 |
| GET | /reports/utilization | 人員稼動率 |
| GET | /reports/heatmap | 熱門時段熱力圖 |

## 4. 平台管理端 API（/admin）

| Method | Path | 說明 |
|---|---|---|
| GET/POST/PUT | /merchants | 商家管理、審核、上下架 |
| PUT | /merchants/:id/plan | 訂閱方案切換 |
| GET | /dashboard | 全平台指標 |
| GET | /audit-logs | 稽核日誌 |
| POST | /announcements | 系統公告 |

## 5. Webhook / 事件（供整合與通知模組訂閱）

| 事件 | 觸發 |
|---|---|
| booking.created / confirmed / rescheduled / cancelled | 預約生命週期 |
| booking.no_show / completed | 出席相關 |
| wallet.deducted / refunded / expiring | 扣減相關 |
| member.registered | 新會員 |

## 6. 關鍵 API 範例

**GET /app/merchants/cube/availability?service_id=svc_01&date=2026-07-15**

```json
{
  "date": "2026-07-15",
  "timezone": "Asia/Taipei",
  "service": { "id": "svc_01", "name": "60分鐘私人教練", "duration_min": 60 },
  "slots": [
    { "start_at": "2026-07-15T10:00:00+08:00", "staff_ids": ["stf_a", "stf_b"] },
    { "start_at": "2026-07-15T11:30:00+08:00", "staff_ids": ["stf_a"] }
  ]
}
```

**POST /biz/bookings（商家端代客預約）**

```json
// 幫非會員（電話客）建立，越過提前期限限制
{
  "guest_name": "陳先生",
  "guest_phone": "0912345678",
  "service_id": "svc_01",
  "staff_id": "stf_a",
  "start_at": "2026-07-10T18:00:00+08:00",
  "price_option_id": null,            // 到店付款
  "policy_override": true,
  "override_reason": "電話預約，客人1小時後到"
}
// Response 201：source=staff、created_by_staff_id 自動取自登入員工，
// 並寫入 booking_event 與 operation_log
```

**GET /biz/operation-logs?staff_id=stf_wang&from=2026-07-01**

```json
{
  "data": [
    {
      "staff": { "id": "stf_wang", "name": "王小明" },
      "action": "booking_create",
      "target": { "type": "booking", "id": "bk_456" },
      "detail": { "guest_name": "陳先生", "policy_override": true },
      "created_at": "2026-07-10T10:32:00+08:00"
    },
    {
      "staff": { "id": "stf_wang", "name": "王小明" },
      "action": "wallet_adjust",
      "target": { "type": "wallet_account", "id": "wa_789" },
      "detail": { "change": 1, "note": "系統誤扣補回" },
      "created_at": "2026-07-09T15:10:00+08:00"
    }
  ],
  "total": 2
}
```

**POST /app/bookings**

```json
// Request（Idempotency-Key: 7f3e...）
{
  "merchant_id": "mch_cube",
  "service_id": "svc_01",
  "staff_id": "stf_a",
  "start_at": "2026-07-15T10:00:00+08:00",
  "price_option_id": "po_pass10"
}
// Response 201
{
  "id": "bk_123",
  "status": "confirmed",
  "deduction": { "type": "pass", "units": 1, "balance_after": 7 },
  "policy_summary": {
    "cancel_rules": "24小時前全額返還，之內返還50%",
    "change_notice": "如需改期、取消或會遲到，請聯絡商家處理",
    "merchant_contact": { "phone": "02-12345678", "line": "@cube" }
  }
}
```
