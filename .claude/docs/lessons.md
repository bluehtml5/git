# 教訓累積檔

> 格式與寫入規則見 `04-maintenance.md`。超過 25 條要歸併精簡。新條目加在最上面。

## 2026-07-03 WebFetch 單次回傳可達 73KB
- 情境：建制度時查官方文件（code.claude.com/docs）。
- 坑：一次 WebFetch 回傳 73KB 被 harness 轉存成檔案；若直接 Read 全檔會塞爆 context。
- 規則：persisted-output 檔一律先用 Grep 抽關鍵行，不 Read 全檔；查文件類任務優先派 subagent。

## 2026-07-03 本環境沒有 gh CLI
- 情境：環境盤點。
- 坑：（預防性記錄）遠端環境沒有 `gh`/`hub`，直接呼叫會失敗。
- 規則：GitHub 操作一律用 `mcp__github__*` 工具，帶 `perPage: 5-10` 與 `minimal_output: true`。
