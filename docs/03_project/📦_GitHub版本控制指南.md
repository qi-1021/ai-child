# AI Child - 版本控制配置指南
# Version Control Configuration Guide

## 📋 应该提交到 Git ✅

```
✅ 应提交 (Should commit to Git):
├─ /server/ai/personality_memory.py       # 新增：人格记忆管理
├─ /server/i18n/__init__.py              # 新增：本地化系统
├─ /server/i18n/messages.py              # 新增：翻译字典
├─ /export_personality.py                # 工具：导出档案
├─ /import_personality.py                # 工具：导入档案
├─ /📘_人格隔离本地化指南.md             # 文档：完整指南
├─ /⚡_人格本地化快速参考.md             # 文档：快速参考
├─ 修改的 server/models/__init__.py      # 扩展：新表定义
├─ 修改的 start_ai_child.py              # 更新：启动脚本
└─ personality-backups/                  # 人格档案备份（重要！）
```

## 📁 不应该提交到 Git ❌

```
❌ 不提交 (Should NOT commit):
├─ server/ai_child.db                    # 数据库（包含用户数据）
├─ server/.env                           # 环境变量（包含 API Key）
├─ server/.venv/                         # 虚拟环境
├─ __pycache__/                          # Python 缓存
├─ *.pyc                                 # 编译文件
├─ .eggs/
├─ *.egg-info/
└─ personality_profile.json              # 本地快照（使用 backups/ 替代）
```

## 🔑 GitHub 推荐工作流

### 第一次设置

```bash
# 1. 确保 .gitignore 正确
cat > .gitignore << 'EOF'
# 数据库
*.db
*.sqlite
*.sqlite3

# 环境
.env
.env.local
server/.venv/

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo

# 本地备份快照（使用 git 跟踪 personality-backups/ 替代）
personality_profile.json
EOF

git add .gitignore
git commit -m "Update gitignore for personality system"

# 2. 创建人格备份目录用于版本控制
mkdir -p personality-backups
touch personality-backups/.gitkeep
git add personality-backups/
git commit -m "Create personality backups directory"

# 3. 导出初始人格档案
python export_personality.py --backup-dir personality-backups

# 4. 提交档案
git add personality-backups/
git commit -m "Add initial AI personality profile"

git push origin main
```

### 日常工作流

```bash
# 每天/每周导出一次人格档案
python export_personality.py --backup-dir personality-backups

# 检查是否有变化
git status

# 如果人格有变化，提交
if git status | grep personality-backups; then
    git add personality-backups/
    git commit -m "Update AI personality snapshot"
    git push origin main
fi
```

### 恢复工作流

```bash
# 在新环境中恢复 AI 人格
git clone [repo-url]
cd ai-child

# 从最新的备份恢复人格
python import_personality.py personality-backups/personality_profile_*.json

# 启动服务器
python start_ai_child.py --server
```

## 🔐 安全策略

### 敏感信息不提交

**❌ 这些 NEVER 提交：**
```
OPENAI_API_KEY=sk-...                    # API 密钥
DATABASE_PASSWORD=...                     # 数据库密码
TELEGRAM_TOKEN=...                        # Bot 令牌
ai_child.db                               # 包含用户对话
.env 文件                                 # 环境变量
```

### .gitignore 模板

```bash
# 推荐的 .gitignore 内容
cat >> .gitignore << 'EOF'

# ========== 敏感信息 ==========
.env
.env.local
.env.*.local
secrets/

# ========== 数据库和用户数据 ==========
*.db
*.sqlite
*.sqlite3
*.db-journal
/data/
/logs/

# ========== 虚拟环境 ==========
.venv/
venv/
env/
ENV/

# ========== IDE 和编辑器 ==========
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# ========== Python ==========
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.pytest_cache/

# ========== 个人笔记 ==========
notes.txt
TODO.md
personal_*.md
EOF
```

## 📊 推荐的目录结构（Git 视图）

```
ai-child/                           ← Git 根目录
├── .git/                          ← Git 数据库
├── .gitignore                     ← 版本控制规则 ✅
│
├── server/
│   ├── ai/
│   │   ├── personality_memory.py  ✅ 新文件，提交
│   │   ├── sleep.py
│   │   └── ...
│   ├── i18n/
│   │   ├── __init__.py            ✅ 新文件，提交
│   │   └── messages.py            ✅ 新文件，提交
│   ├── models/__init__.py         ✅ 修改，提交
│   ├── config.py
│   ├── main.py
│   ├── .venv/                     ❌ 不提交（.gitignore）
│   ├── ai_child.db                ❌ 不提交（.gitignore）
│   └── .env                       ❌ 不提交（.gitignore）
│
├── personality-backups/           ✅ 提交档案
│   ├── personality_profile_20260321_100000.json
│   ├── personality_profile_20260320_100000.json
│   └── .gitkeep
│
├── export_personality.py          ✅ 新文件，提交
├── import_personality.py          ✅ 新文件，提交
├── start_ai_child.py              ✅ 修改，提交
│
├── 📘_人格隔离本地化指南.md       ✅ 新文档，提交
├── ⚡_人格本地化快速参考.md       ✅ 新文档，提交
│
└── README.md                      ✅ 文档，提交
```

## 🔄 多环境同步

### 场景：在不同的机器上维护 AI

```bash
# === 机器 A（主开发环境）===
python export_personality.py --backup-dir personality-backups
git add personality-backups/
git commit -m "AI learned new skills"
git push origin main

# === 机器 B（新开发环境/生产环境）===
git pull origin main
python import_personality.py personality-backups/personality_profile_*.json
python start_ai_child.py --server
# AI 自动加载之前的人格档案！
```

## ⚙️ GitHub Actions 自动备份（可选）

### 创建 `.github/workflows/backup-personality.yml`

```yaml
name: Auto-backup AI Personality

on:
  schedule:
    - cron: '0 2 * * *'  # Every day at 2 AM UTC
  workflow_dispatch:

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Export personality
        run: |
          pip install -q -r server/requirements.txt
          python export_personality.py --backup-dir personality-backups
      
      - name: Commit and push
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add personality-backups/
          git diff --quiet && git diff --staged --quiet || \
            git commit -m "Auto-backup: AI personality at $(date)"
          git push origin main
```

## 📈 版本控制命令快速参考

```bash
# 查看各文件的版本控制状态
git status

# 只看 personality 相关的变化
git status | grep personality

# 查看 personality 档案的历史
git log --oneline personality-backups/

# 比较两个人格档案版本
git diff personality-backups/personality_profile_*.json

# 恢复到某个人格档案的版本
git checkout <commit-hash> -- personality-backups/

# 查看完整的提交历史（带人格数据变化）
git log --stat -- personality-backups/
```

## 🎯 提交信息最佳实践

```bash
# ✅ 好的提交信息
git commit -m "Personality: Add curiosity trait to AI identity"
git commit -m "i18n: Add Chinese translations for core messages"
git commit -m "Backup: Personality snapshot after 2 weeks of learning"

# ❌ 不好的提交信息
git commit -m "update"
git commit -m "fix"
git commit -m "changes"
```

## 🚀 完整示例：第一次提交

```bash
# 1. 克隆或初始化仓库
git clone https://github.com/username/ai-child.git
cd ai-child

# 2. 添加新的本地化文件
git add server/i18n/
git add export_personality.py
git add import_personality.py
git add 📘_人格隔离本地化指南.md
git add ⚡_人格本地化快速参考.md

# 3. 导出初始人格档案
python export_personality.py --backup-dir personality-backups

# 4. 添加人格档案
git add personality-backups/

# 5. 验证要提交的文件
git status

# 6. 一次性提交
git commit -m "feat: Add personality isolation and localization system

- Separate personality memories from regular conversations
- Add complete i18n support (en-US, zh-CN)
- Implement personality export/import for GitHub sync
- Add PersonalityMemory table for permanent identity storage
- Include Chinese and English system prompts
- Add export_personality.py and import_personality.py tools"

# 7. 推送到 GitHub
git push origin main
```

---

**关键点总结**：
- ✅ **提交**: 新增代码、文档、personality-backups/
- ❌ **不提交**: .env、*.db、.venv/
- 🔄 **工作流**: 导出 → 提交 → 同步
- 🔐 **安全**: 敏感信息永远不提交
