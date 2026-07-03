# CLAUDE.md

這個 repo 除了程式碼，還存放一套「工作制度」（`.claude/docs/`），目的是讓每個 session 的模型——不論大小——都用同一套經過驗證的做法。**規則本體在各檔案裡，這裡只放路由。**

## 開工前 30 秒 checklist（每個 session 都做）

1. `git branch --show-current` 確認在指定分支上。
2. 這個環境是暫時性 container：**沒 push 的工作等於沒做**。每完成一個邏輯單位就 commit + push。
3. 看一眼 `.claude/docs/lessons.md`，避免重踩已記錄的坑。

## 路由表：做 X 之前，先讀 Y

| 你正要做的事 | 先讀 |
|---|---|
| 掃 repo、讀多個檔案、查網頁、批次改檔（任何會吐大量原始資料進對話的事） | `.claude/docs/01-delegation.md` — 派 subagent，不要自己下場 |
| 派 subagent（選模型、寫派工 prompt、收回報） | `.claude/docs/01-delegation.md` ＋ 模板在 `.claude/docs/03-prompt-templates.md` |
| 判斷「做完了沒」「該不該問使用者」「該不該換做法」「該不該升級模型」 | `.claude/docs/02-judgment.md` |
| 驗收任何產出（自己的或 subagent 的） | `.claude/docs/02-judgment.md` 品質底線一節；驗收一律派 fresh-context agent，不自驗 |
| 修改 `.claude/docs/` 底下任何制度檔 | `.claude/docs/04-maintenance.md` — 先看哪些可自改、哪些要問使用者 |
| 踩了坑、學到教訓 | 寫進 `.claude/docs/lessons.md`，格式見 `04-maintenance.md` |
| 剛接手 session、想了解這個環境的背景 | `.claude/docs/00-diagnosis.md`（環境弱點）＋ `.claude/docs/05-letter.md`（前任交接信） |

## 三條不可協商的硬規則

1. **隨做隨 push**：每個邏輯單位完成即 commit + push 到指定分支。判準：如果現在斷線，這個 commit 單獨存在仍有意義。
2. **同一做法失敗 2 次就停**：第 3 次行動必須換路、升級模型、或報告使用者。不准原樣重試第三次。
3. **驗證不自驗**：宣稱「完成」之前，驗收要由沒看過製作過程的 fresh-context agent 做（`.claude/agents/verifier.md`），或用測試／實跑證明。自己看一遍不算驗證。

## 環境事實（查證過，不要憑印象覆蓋）

- 遠端 Claude Code 環境，container 閒置即回收；唯一持久層是這個 repo。
- 沒有 `gh` CLI；GitHub 操作用 `mcp__github__*` 工具，一律 `perPage: 5-10`，能用 `minimal_output: true` 就用。
- 等外部事件用 `subscribe_pr_activity` / `send_later`，禁止 sleep 輪詢。
- Subagent 可用 `model` 參數指定 `haiku`/`sonnet`/`opus`（`fable` 在枚舉中但不保證可用，失敗就退 `opus`）；自訂 agent 的 frontmatter 另支援 `effort`。細節與依據在 `01-delegation.md`。
