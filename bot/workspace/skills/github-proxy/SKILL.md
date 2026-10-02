---
name: github-proxy
description: GitHub 國內訪問加速 skill，使用 githubproxy.cc 代理加速 GitHub 倉庫克隆、檔案下載、Raw 檔案訪問等操作。使用場景：(1) 需要 git clone GitHub 倉庫時加速，(2) 下載 GitHub Release 檔案、Raw 檔案、Archive 壓縮包時加速，(3) 任何需要訪問 GitHub 資源但速度慢的場景
---

# GitHub 國內代理加速 Skill

使用 githubproxy.cc 代理服務，為國內訪問 GitHub 提供加速支援。

## 代理服務

當前使用的代理服務：
- **主要服務**: githubproxy.cc (測試有效，加速約 3 倍)
- **備用服務**: ghfast.top

## 使用方法

### 1. Git Clone 加速

將 GitHub 倉庫連結前加上 `https://githubproxy.cc/` 字首：

```bash
# 原始連結
git clone https://github.com/username/repo.git

# 加速連結
git clone https://githubproxy.cc/https://github.com/username/repo.git
```

### 2. 檔案下載加速

支援以下型別的 GitHub 資源加速：

- **Raw 文件**: `https://raw.githubusercontent.com/...`
- **Release 檔案**: 專案釋出的附件
- **Archive 壓縮包**: 倉庫打包下載
- **Gist 文件**: `gist.github.com` 或 `gist.githubusercontent.com`

```bash
# 原始連結
wget https://raw.githubusercontent.com/username/repo/main/file.txt

# 加速連結
wget https://githubproxy.cc/https://raw.githubusercontent.com/username/repo/main/file.txt
```

### 3. 使用輔助指令碼

使用 `scripts/convert_url.py` 自動轉換 GitHub 連結：

```bash
python scripts/convert_url.py "https://github.com/username/repo.git"
```

## 連結轉換規則

| 原始連結格式 | 轉換後格式 |
|-------------|-----------|
| `https://github.com/username/repo.git` | `https://githubproxy.cc/https://github.com/username/repo.git` |
| `https://raw.githubusercontent.com/...` | `https://githubproxy.cc/https://raw.githubusercontent.com/...` |
| `https://github.com/.../releases/download/...` | `https://githubproxy.cc/https://github.com/.../releases/download/...` |
| `https://github.com/.../archive/...` | `https://githubproxy.cc/https://github.com/.../archive/...` |

## 注意事項

- 本服務僅供學習研究使用，請勿濫用
- 如果 githubproxy.cc 不可用，請嘗試備用服務 ghfast.top
- 不支持 SSH Key 方式的 git clone
- Push、PR、Issue 等操作建議直接使用官方 GitHub 地址
