# 斷言使用指南

本專案提供了多種斷言方式來驗證 OpenClaw 的響應。

## 斷言方法

### 1. 關鍵詞斷言

#### `assertKeywordsInResponse()`
斷言響應中包含指定的所有關鍵詞。

**引數：**
- `response`: 響應內容（字典或字串）
- `keywords`: 關鍵詞列表
- `require_all`: 是否要求所有關鍵詞都必須出現，預設 `True`
- `case_sensitive`: 是否區分大小寫，預設 `False`
- `msg`: 自定義錯誤資訊

**示例：**

```python
# 驗證響應中包含所有關鍵詞
self.assertKeywordsInResponse(
    response,
    ["小明", "30歲", "測試開發"],
    require_all=True,
    case_sensitive=False
)

# 驗證響應中包含任意一個關鍵詞
self.assertKeywordsInResponse(
    response,
    ["30", "三十"],
    require_all=False
)
```

---

### 2. 任意關鍵片語斷言

#### `assertAnyKeywordInResponse()`
斷言響應中包含任意一組關鍵詞中的任意一個。

**引數：**
- `response`: 響應內容
- `keyword_groups`: 關鍵片語列表（二維陣列）
- `case_sensitive`: 是否區分大小寫，預設 `False`
- `msg`: 自定義錯誤資訊

**示例：**

```python
# 驗證響應中包含姓名、年齡或職業中的任意一個
self.assertAnyKeywordInResponse(
    response,
    [
        ["小明", "小紅"],      # 第一組：姓名
        ["30", "25", "28"],   # 第二組：年齡
        ["測試開發", "產品經理"]  # 第三組：職業
    ],
    case_sensitive=False
)
```

---

### 3. 文本相似度斷言

#### `assertSimilarity()`
斷言響應文本與期望文本的相似度達到指定閾值。

**引數：**
- `response`: 響應內容
- `expected_text`: 期望的文本
- `min_similarity`: 最小相似度閾值，範圍 0.0-1.0，預設 0.6
- `msg`: 自定義錯誤資訊

**示例：**

```python
# 驗證響應文本與期望文本相似度 >= 70%
self.assertSimilarity(
    response,
    "你叫小明，今年30歲，住在華東區，職業是測試開發",
    min_similarity=0.7
)
```

---

## 實用技巧

### 組合使用斷言

```python
def test_some_scenario(self):
    # 傳送訊息
    response = self.send_and_log("我叫張三")
    self.wait_for_sync()
    
    # 驗證響應
    verify_resp = self.send_and_log("我是誰")
    
    # 方式1：關鍵詞斷言
    self.assertKeywordsInResponse(verify_resp, ["張三"])
    
    # 方式2：任意關鍵片語斷言（更靈活）
    self.assertAnyKeywordInResponse(
        verify_resp,
        [["張三", "小張"]]
    )
```

### 容錯性設計

```python
# 提供多種可能的表述方式
self.assertAnyKeywordInResponse(
    response,
    [
        ["30歲", "30", "三十歲", "三十"],  # 年齡的多種表述
        ["測試開發", "測試工程師", "QA"]      # 職業的多種表述
    ]
)
```

### 漸進式驗證

```python
# 先寫入資訊
self.send_and_log("我叫李四，今年35歲")
self.wait_for_sync()

# 逐項驗證
name_resp = self.send_and_log("我叫什麼？")
self.assertKeywordsInResponse(name_resp, ["李四"])

age_resp = self.send_and_log("我幾歲？")
self.assertKeywordsInResponse(age_resp, ["35", "三十五"])
```

---

## 直接使用 AssertionHelper

也可以直接使用 `AssertionHelper` 類進行斷言：

```python
from utils.assertions import AssertionHelper

helper = AssertionHelper()

# 提取響應文本
text = helper.extract_response_text(response)

# 計算相似度
similarity = helper.calculate_similarity(text1, text2)

# 關鍵詞檢查（返回布林值，不拋異常）
success = helper.assert_keywords_in_response(response, ["關鍵詞"])
```

---

## 響應格式支援

`extract_response_text()` 方法支援多種響應格式：

- 純字串
- `{"output": "..."}`
- `{"message": "..."}`
- `{"content": "..."}`
- `{"text": "..."}`
- OpenAI 格式：`{"choices": [{"message": {"content": "..."}}]}`
- 其他格式會自動轉為字串

如果你的響應格式不被支援，可以擴充 `extract_response_text()` 方法。
