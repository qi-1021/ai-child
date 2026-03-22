#!/usr/bin/env python3
"""
交互式对话客户端 - 直接与 AI Child 对话
"""
import asyncio
import httpx
import json
from typing import Optional
import sys

SERVER_URL = "http://localhost:8000"

class AIChildClient:
    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.user_id = "console_user"

    async def send_message(self, text: str) -> dict:
        """发送文本消息并获取回复"""
        try:
            response = await self.client.post(
                f"{self.server_url}/chat/text",
                json={
                    "chat_id": self.user_id,
                    "text": text,
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_history(self, limit: int = 5) -> list:
        """获取对话历史"""
        try:
            response = await self.client.get(
                f"{self.server_url}/chat/history",
                params={"chat_id": self.user_id, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_questions(self) -> list:
        """获取 AI 的主动问题"""
        try:
            response = await self.client.get(
                f"{self.server_url}/teach/questions",
                params={"chat_id": self.user_id}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def teach(self, topic: str, content: str) -> dict:
        """教 AI 一个事实"""
        try:
            response = await self.client.post(
                f"{self.server_url}/teach/",
                json={
                    "chat_id": self.user_id,
                    "topic": topic,
                    "content": content,
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()

async def main():
    """交互式对话循环"""
    client = AIChildClient()

    print("\n" + "="*60)
    print("🤖 AI Child 交互式对话客户端")
    print("="*60)
    print("\n命令:")
    print("  /q      - 显示 AI 的主动问题")
    print("  /h      - 显示对话历史")
    print("  /teach  - 教 AI 一个事实 (格式: /teach 话题 | 内容)")
    print("  /exit   - 退出程序")
    print("\n" + "="*60 + "\n")

    try:
        while True:
            try:
                # 获取用户输入
                user_input = input("你: ").strip()

                if not user_input:
                    continue

                # 处理特殊命令
                if user_input.lower() == "/exit":
                    print("\n👋 再见！")
                    break

                elif user_input.lower() == "/q":
                    print("\n📋 获取 AI 的问题...")
                    questions = await client.get_questions()
                    if isinstance(questions, dict) and "error" in questions:
                        print(f"❌ 错误: {questions['error']}")
                    elif questions:
                        print("\n🤔 AI 的问题:")
                        for q in questions:
                            print(f"  - {q}")
                    else:
                        print("暂没有主动问题")
                    print()
                    continue

                elif user_input.lower() == "/h":
                    print("\n📜 获取对话历史...")
                    history = await client.get_history()
                    if isinstance(history, dict) and "error" in history:
                        print(f"❌ 错误: {history['error']}")
                    elif history:
                        print("\n对话历史:")
                        for item in history:
                            print(f"  用户: {item.get('user_message', 'N/A')}")
                            print(f"  AI:   {item.get('assistant_message', 'N/A')}\n")
                    else:
                        print("暂无对话历史")
                    print()
                    continue

                elif user_input.lower().startswith("/teach"):
                    parts = user_input[6:].strip().split("|")
                    if len(parts) == 2:
                        topic = parts[0].strip()
                        content = parts[1].strip()
                        print(f"\n📚 教 AI: {topic} → {content}")
                        result = await client.teach(topic, content)
                        if "error" in result:
                            print(f"❌ 错误: {result['error']}")
                        else:
                            print(f"✅ 已记录!")
                    else:
                        print("格式错误。使用: /teach 话题 | 内容")
                    print()
                    continue

                # 发送普通消息
                print(f"\n✉️  发送消息...")
                response = await client.send_message(user_input)

                if "error" in response:
                    print(f"❌ 错误: {response['error']}\n")
                else:
                    print(f"\n🤖 AI: {response.get('reply', 'N/A')}\n")

                    # 显示主动问题（如果有）
                    question = response.get('proactive_question')
                    if question:
                        print(f"🤔 AI 问你: {question}\n")

            except KeyboardInterrupt:
                print("\n\n👋 再见！")
                break
            except Exception as e:
                print(f"❌ 出错: {e}\n")

    finally:
        await client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 再见！")
        sys.exit(0)
