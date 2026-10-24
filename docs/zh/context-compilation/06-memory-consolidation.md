# 記憶整理（Memory Consolidation）

除了用 Skill 把來源材料編譯成 Wiki、知識圖譜、日報等產物，`ov compile` 還有一種特殊模式：**記憶整理**。它不生成新的知識形態，而是把 OpenViking 裡**已有的記憶**就地整理乾淨——去重、合併、拆分、精簡，同時嚴格遵守每種記憶型別原本的 schema。

與普通 compile 不同，記憶整理**不使用 Skill 流水線**，而是用記憶框架完成。與所有 Compile 任務一樣，它是持久佇列工作，伺服器重啟後會重新執行。

## 什麼時候用

記憶隨著一次次會話不斷累積，時間久了會出現：

- **重複**：同一個人、同一件事被多次記錄，措辭略有不同；
- **同一實體多份**：模型在不同批次裡沒認出是同一個物件，拆成了多條（比如"阿珍"和"陳靜嫻"其實是同一個人）；
- **混雜**：一條記憶裡塞進了多個不相關的物件；
- **囉嗦**：同義反復、可以更緊湊。

這時對某個記憶目錄跑一次記憶整理，就能讓這類記憶集合重新變得乾淨、無冗餘，且不丟事實。

## 怎麼用

把 `--skill` 設為哨兵值 **`memory`**，`--to` 指向 **memories 根目錄或某個記憶型別目錄**即可：

```bash
# 整理 entities（就地去重 / 合併 / 規範化）
ov compile \
  --to viking://user/<user_id>/memories/entities \
  --skill memory \
  --instruction "合併明顯重複的實體，但不同實體不要合併；保留每個實體的獨立事實"
```

也可以整理其它記憶型別，比如偏好：

```bash
ov compile \
  --to viking://user/<user_id>/memories/preferences \
  --skill memory
```

一次整理所有已存在且已啟用的型別，使用同一個任務、同一個 ExtractLoop：

```bash
ov compile --to viking://user/<user_id>/memories --skill memory \
  --instruction "整理已有記憶，保留獨立事實，不要合併不同物件"
```

根目錄下已存在的 `profile.md`、`identity.md`、`soul.md` 也會納入；停用或未註冊的型別會跳過。使用者 memories 根目錄不包含 `peers/*/memories`，整理 peer 記憶需要明確指定該 peer 的 memories 根目錄。

命令同樣立即返回一個任務 ID，用 `ov task status <id>` 檢視結果、用 `ov task cancel <id>` 取消。

## 引數

| 引數 | 說明 |
|------|------|
| `--skill memory` | 固定的哨兵值，觸發記憶整理模式（不會被當作真實 Skill 解析）。 |
| `--to` | 必填，可為 **memories 根目錄**（`.../memories`）或**某個記憶型別目錄**（如 `.../memories/entities`）；不接受使用者根目錄。 |
| `--from` | 記憶模式下**不接受**——整理不引入外部來源，只處理 `--to` 空間內已有的記憶。 |
| `--instruction` | 可選。作為整理指令（軟提示）交給模型。用來點破模型自己判斷不出來的合併，比如"阿珍就是陳靜嫻，請合併"。 |

## 行為要點

- **類型範圍**：指定型別目錄時只加載該型別的 schema；指定 memories 根目錄時將該空間內所有已存在且已啟用的型別載入到同一個 ExtractLoop，各型別仍遵守自身 schema。若改名或合併影響已有 links/backlinks，系統仍會更新其它型別中的相鄰記憶檔案以維持引用完整性。
- **就地整理**：`--from` 與 `--to` 是同一空間，不引入外部來源，因此不存在跨身份空間的串號問題。整理的空間（當前使用者自己的 self 空間，還是某個 `peers/{peer_id}` 空間）由 `--to` 的 URI 決定。
- **保守合併**：預設只合並明顯是同一身份的記憶；不同實體即使話題、類別、屬性相近也不會被強行合併。模型從內容判斷不出來的合併（例如兩個不同名字其實是同一個人），必須通過 `--instruction` 明確點破才會執行。
- **不憑空創造**：只重組已有記憶，不會無中生有地新增事實。
- **保留事實**：合併、精簡時會保留每一條獨立的原子事實，只壓縮重複表述。
- **支援改名**：當 schema 允許修改參與 URI 的欄位時（例如 entity 的 `category` 或 `name`），整理會先寫入新 URI、遷移 links/backlinks，再刪除舊 URI；結果顯示為 `adds` 新 URI + `deletes` 舊 URI。
- **衝突不覆蓋**：如果改名後的目標 URI 已存在，整理會報衝突，不會覆蓋。模型必須先讀取兩份記憶，把獨立事實更新到明確的目標檔案，再用 replacement 關係刪除原始檔。

## 返回結果

記憶模式的任務結果裡包含本次整理的**變化檔案清單**，欄位沿用記憶歸檔 `memory_diff.json` 的語義：

| 欄位 | 含義 |
|------|------|
| `adds` / `total_adds` | 新建的記憶檔案（如拆分產生的新實體） |
| `updates` / `total_updates` | 被修改的記憶檔案（合併後的目標、原地精簡的檔案） |
| `deletes` / `total_deletes` | 被刪除/被合併掉的記憶檔案 |
| `trace_id` | 本次整理的 trace，用於排查 |
| `memory_types` | 本次選中的型別列表；`memory_type` 在型別目錄請求中為該型別，在根目錄請求中為 `null` |

清單中只包含檔案 URI，不含正文——一次整理可能觸及很多檔案，正文不隨結果返回。

若 `errors` 非空且沒有任何檔案變更成功，任務標記為 `failed`，並保留結果和 trace。部分成功仍為 `completed`，成功變更和失敗詳情分別保留在清單與 `errors` 中；呼叫方必須檢查 `errors`，不能只看任務狀態。無改動且無錯誤時正常標記為 `completed`。

一個典型的合併例子（把"阿珍"合併進"陳靜嫻"）：

```json
{
  "memory_type": "entities",
  "trace_id": "…",
  "adds": [],
  "updates": ["viking://user/xiaomei/memories/entities/person/陳靜嫻.md"],
  "deletes": ["viking://user/xiaomei/memories/entities/person/阿珍.md"],
  "total_adds": 0,
  "total_updates": 1,
  "total_deletes": 1,
  "errors": []
}
```

## 前置條件

- 一個正在執行的 OpenViking 服務（記憶整理在服務程序內執行，不需要額外啟用 Bot）。預設端點 `http://localhost:1933`；遠端使用需要 API Key，參見 [鑑權](../guides/04-authentication.md)。
- `ov` CLI 已配置好連線（`~/.openviking/ovcli.conf` 或 `OPENVIKING_*` 環境變數）。
- `--to` 指向的記憶目錄裡已經有記憶（一般由 session commit 從會話中抽取產生）。

## 相關文件

- [上下文編譯概覽](./01-overview.md) — `ov compile` 的整體介紹
- [Agent Runtime API](../api/23-agent-runtime.md) — 建立、查詢和取消 Compile 任務的完整參考
