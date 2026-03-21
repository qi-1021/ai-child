#!/usr/bin/env python3
"""实时 WebSocket 对话客户端 — 与 AI Child 交互"""

import asyncio
import json


async def main():
    """主函数"""
    try:
        import websockets
    except ImportError:
        print("❌ 缺少 websockets 库，请运行：pip install websockets")
        return

    uri = "ws://localhost:8000/api/ws"

    try:
        async with websockets.connect(uri, close_timeout=None) as websocket:
            print("\n✅ 已连接到 AI Child")
            print("=" * 60)
            print("💬 实时对话已启动")
            print("输入你的消息，或输入 'quit' 退出")
            print("=" * 60)

            while True:
                try:
                    user_input = input("\n👤 你: ").strip()

                    if not user_input:
                        print("⏭️ (空消息已跳过)")
                        continue

                    if user_input.lower() in ["quit", "exit", "q"]:
                        print("\n👋 再见！")
                        break

                    print("⏳ 正在思考...")

                    message = {
                        "user_text": user_input,
                        "content_type": "text",
                    }

                    await websocket.send(json.dumps(message))
                    response = await websocket.recv()
                    data = json.loads(response)

                    if data.get("status") == "error":
                        print(f"⚠️ 错误: {data.get('error', '未知错误')}")
                        continue

                    ai_message = data.get("message", {})
                    content = ai_message.get("content", "")

                    # 显示 AI 回复
                    print("\n🤖 AI 回复:")
                    print("-" * 40)
                    print(content)
                    print("-" * 40)

                    # 显示附加信息
                    if ai_message.get("name"):
                        print(f"💫 AI 的名字: {ai_message.get('name')}")

                    if ai_message.get("proactive_question"):
                        print(
                            f"\n❓ AI 的好奇心: {ai_message.get('proactive_question')}"
                        )

                except KeyboardInterrupt:
                    print("\n\n👋 对话已中断")
                    break
                except Exception as e:
                    print(f"❌ 错误: {e}")
                    break

    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print(f"请检查服务器是否运行在 {uri}")


if __name__ == "__main__":
    print("🚀 AI Child 实时对话客户端")
    print("=" * 60)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 已退出")
