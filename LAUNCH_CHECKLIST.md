╔═══════════════════════════════════════════════════════════════╗
║        🚀 AI Child 启动前检查清单 (2024-03-22)              ║
╚═══════════════════════════════════════════════════════════════╝

✅ 系统准备就绪
════════════════════════════════════════════════════════════════

【环境】
 ✓ Ollama 已安装
 ✓ Python 3 已安装
 ✓ 二级磁盘可访问

【本地模型 (自动注册完成)】
 ✓ Qwen 3.5-9B     (4.2 GB)  → 模型名: qwen-local
 ✓ Gemma 3 12B     (5.1 GB)  → 模型名: gemma-local
 ✓ Huihui Qwen VL  (8.7 GB)  → 模型名: huihui-qwen-local

【配置文件】
 ✓ server/.env     → LLM_PROVIDER=ollama
 ✓ bot/.env        → QQ_API_URL=http://localhost:5700
 ✓ .gitignore      → .env 文件被保护

【核心代码文件】
 ✓ server/main.py          → FastAPI 服务器
 ✓ bot/main.py             → 机器人网桥
 ✓ bot/adapters/qq_bot.py  → QQ 适配器
 ✓ setup_wizard.py         → 交互式配置

════════════════════════════════════════════════════════════════
📋 启动清单 (3 个终端)
════════════════════════════════════════════════════════════════

【终端 1: Ollama】
□ 打开新的终端
□ 运行: ollama serve
□ 等待看到: "Listening on [::]:11434"
□ 保持运行状态

【终端 2: AI Child 服务器】
□ 打开新的终端
□ 运行: cd /Volumes/mac第二磁盘/ai-child/server && python3 main.py
□ 等待看到: "Uvicorn running on http://0.0.0.0:8000"
□ 保持运行状态

【终端 3: QQ 机器人】
□ 打开新的终端
□ 前置条件: go-cqhttp 已安装并配置好（可选）
□ 运行: cd /Volumes/mac第二磁盘/ai-child/bot && python3 main.py qq
□ 等待看到: "QQ adapter running"
□ 保持运行状态

════════════════════════════════════════════════════════════════
🌐 启动后的访问点
════════════════════════════════════════════════════════════════

【Web UI 对话界面】
  URL: http://localhost:8000
  用途: 网页版聊天、查看历史、管理学习知识库

【API 文档】
  URL: http://localhost:8000/docs
  用途: 交互式查看所有可用 API 端点

【QQ 机器人】
  方式: 在 QQ 中直接对话
  前置: 需要 go-cqhttp 配置（可选）

════════════════════════════════════════════════════════════════
⚡ 验证命令 (启动后运行)
════════════════════════════════════════════════════════════════

# 1. 测试服务器是否运行
$ curl http://localhost:8000/health
# 预期输出: {"status":"ok"}

# 2. 列出所有可用的本地模型
$ ollama list
# 预期输出:
# NAME                  ID              SIZE    MODIFIED
# qwen-local           ...             4.2 GB   ...
# gemma-local          ...             5.1 GB   ...
# huihui-qwen-local    ...             8.7 GB   ...

# 3. 测试 Web UI 连接
$ open http://localhost:8000

# 4. 查看 API 文档
$ open http://localhost:8000/docs

# 5. 测试 QQ 机器人 (如果启用了)
# 在 QQ 中发送消息给配置的机器人账号

════════════════════════════════════════════════════════════════
🚨 故障排查
════════════════════════════════════════════════════════════════

【问题】Ollama 连接失败
助手:
  1. 确保运行了 'ollama serve'
  2. 等待 30 秒让 Ollama 完全启动
  3. 运行: curl http://localhost:11434/api/tags

【问题】服务器启动失败 (端口占用)
助手:
  1. 检查谁占用了端口: lsof -i :8000
  2. 修改 .env 中的 PORT 为其他端口
  3. 重新启动服务器

【问题】服务器启动失败 (依赖缺失)
助手:
  1. cd server && pip install -r requirements.txt
  2. cd ../bot && pip install -r requirements.txt
  3. cd .. && python3 main.py

【问题】模型看不到 (ollama list 为空)
助手:
  1. 运行: python3 setup_wizard.py
  2. 选择 Ollama 提供商
  3. 让向导自动检测和注册本地模型

【问题】QQ 机器人无感应
助手:
  1. 检查配置: cat bot/.env | grep QQ
  2. 验证 go-cqhttp 是否运行
  3. 查看机器人日志: tail -f bot.log

════════════════════════════════════════════════════════════════
💾 重要文件位置
════════════════════════════════════════════════════════════════

项目根目录:
  /Volumes/mac第二磁盤/ai-child/

配置文件 (不要上传!):
  server/.env      ← 服务器配置
  bot/.env         ← 机器人配置

本地模型目录 (11GB):
  /Volumes/mac第二磁盤/ollama/models/

日志文件 (可能的位置):
  server/debug.log
  bot/bot.log

════════════════════════════════════════════════════════════════
📝 系统配置摘要
════════════════════════════════════════════════════════════════

【LLM 设置】
  提供商: Ollama (本地)
  API地址: http://localhost:11434/v1
  模型: qwen-local (推荐) | gemma-local | huihui-qwen-local
  优点: 无需 API 密钥,完全本地,隐私安全

【服务器设置】
  框架: FastAPI + Uvicorn
  地址: http://0.0.0.0:8000
  项目路径: /Volumes/mac第二磁盘/ai-child/server

【机器人设置】
  主框架: Python AsyncIO
  启用的适配器: QQ (主), Telegram (可选), Webhook (可选)
  QQ API: go-cqhttp (http://localhost:5700)

【开发环境】
  Python版本: 3.12
  运行方式: 3 个独立终端
  启动时间: 总计 ~60 秒

════════════════════════════════════════════════════════════════
✨ 现在你可以:
════════════════════════════════════════════════════════════════

1. 按照上面的清单打开 3 个终端启动系统
2. 访问 http://localhost:8000 使用 Web 界面
3. 在 QQ 中与 AI 对话 (如果配置了 go-cqhttp)
4. 查看 API 文档并集成到其他应用
5. 教导 AI 新知识并观察它学习

════════════════════════════════════════════════════════════════
🎉 祝你使用愉快!
════════════════════════════════════════════════════════════════
