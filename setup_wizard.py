#!/usr/bin/env python3
"""
AI Child Setup Wizard 🚀

Interactive setup tool to help users configure AI Child for the first time.
Supports both local (Ollama) and cloud (OpenAI, DashScope) deployments.
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any


class Colors:
    """ANSI color codes for terminal output"""
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_step(num: int, text: str) -> None:
    """Print a numbered step"""
    print(f"{Colors.BOLD}{Colors.BLUE}[{num}]{Colors.RESET} {text}")


def print_success(text: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")


def print_warning(text: str) -> None:
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.RESET}")


def print_error(text: str) -> None:
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")


def prompt_choice(prompt: str, choices: list[str], default: int = 0) -> int:
    """Prompt user to choose from a list"""
    print(f"\n{Colors.BOLD}{prompt}{Colors.RESET}")
    for i, choice in enumerate(choices, 1):
        marker = f"{Colors.GREEN}→{Colors.RESET}" if i - 1 == default else " "
        print(f"  {marker} {i}. {choice}")

    while True:
        try:
            selection = input(f"\n{Colors.BOLD}Choose (1-{len(choices)}) [{default + 1}]: {Colors.RESET}").strip()
            if not selection:
                return default
            idx = int(selection) - 1
            if 0 <= idx < len(choices):
                return idx
            print_error("Invalid choice. Please try again.")
        except ValueError:
            print_error("Please enter a number.")


def prompt_text(prompt: str, default: str = "", required: bool = False) -> str:
    """Prompt user for text input"""
    while True:
        default_str = f" [{default}]" if default else ""
        user_input = input(f"{Colors.BOLD}{prompt}{default_str}: {Colors.RESET}").strip()

        if not user_input:
            if default:
                return default
            if not required:
                return ""
            print_error("This field is required.")
            continue
        return user_input


def check_command(cmd: str) -> bool:
    """Check if a command is available"""
    result = subprocess.run(["which", cmd], capture_output=True)
    return result.returncode == 0


def check_ollama() -> bool:
    """Check if Ollama is installed and running"""
    if not check_command("ollama"):
        return False

    # Try to connect to Ollama API
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/tags"],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False


def setup_llm_provider() -> Dict[str, Any]:
    """Setup LLM provider configuration"""
    print_header("🤖 LLM Provider Setup")

    choices = [
        "Ollama (Local, Recommended - No API key needed)",
        "OpenAI (Cloud, Requires API key)",
        "DashScope/阿里云 (Cloud, Requires API key)"
    ]

    choice_idx = prompt_choice(
        "Which LLM provider would you like to use?",
        choices,
        default=0
    )

    config = {}

    if choice_idx == 0:  # Ollama
        print_step(1, "Checking Ollama installation...")

        if not check_command("ollama"):
            print_warning("Ollama is not installed.")
            print(f"\n📥 Please install Ollama from: https://ollama.com")
            print(f"   macOS: Download from https://ollama.com/download/mac")
            print(f"   Linux: curl https://ollama.ai/install.sh | sh")
            print(f"   Windows: Download installer from https://ollama.com/download")

            install_now = prompt_choice(
                "Would you like to open the Ollama download page?",
                ["Yes, open download page", "No, I'll do it manually"],
                default=0
            )

            if install_now == 0:
                subprocess.run(["open", "https://ollama.com"] if sys.platform == "darwin" else ["xdg-open", "https://ollama.com"])

            print_warning("Please install Ollama and run this wizard again.")
            sys.exit(0)

        print_success("Ollama is installed.")

        if not check_ollama():
            print_warning("Ollama is not running. Please start it with: ollama serve")
            input(f"\n{Colors.BOLD}Press Enter after starting Ollama...{Colors.RESET}")

            if not check_ollama():
                print_error("Cannot connect to Ollama. Please check your installation.")
                sys.exit(1)

        print_success("Connected to Ollama.")

        # List available models
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True
            )
            print(f"\n📚 Available models:\n{result.stdout}")
        except Exception:
            pass

        model = prompt_text(
            "Which Ollama model would you like to use?",
            default="qwen2",
            required=True
        )

        config = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": "http://localhost:11434/v1",
            "OLLAMA_MODEL": model
        }

    elif choice_idx == 1:  # OpenAI
        print_step(1, "Getting OpenAI configuration...")
        api_key = prompt_text(
            "Enter your OpenAI API key",
            required=True
        )
        model = prompt_text(
            "Which model? (default: gpt-4)",
            default="gpt-4"
        )

        config = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": model
        }

    elif choice_idx == 2:  # DashScope
        print_step(1, "Getting DashScope/阿里云 configuration...")
        api_key = prompt_text(
            "Enter your DashScope API key",
            required=True
        )
        model = prompt_text(
            "Which model? (default: qwen3.5-35b-a3b)",
            default="qwen3.5-35b-a3b"
        )

        config = {
            "LLM_PROVIDER": "dashscope",
            "DASHSCOPE_API_KEY": api_key,
            "DASHSCOPE_MODEL": model,
            "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1"
        }

    return config


def setup_bot_adapters() -> Dict[str, Any]:
    """Setup bot adapters (Telegram, QQ, etc.)"""
    print_header("🤖 Bot Adapters Setup")

    config = {
        "SERVER_URL": "http://localhost:8000"
    }

    # Telegram
    enable_telegram = prompt_choice(
        "Enable Telegram bot?",
        ["Yes", "No"],
        default=1
    )

    if enable_telegram == 0:
        print(f"\n📱 To set up Telegram:")
        print(f"   1. Talk to @BotFather on Telegram")
        print(f"   2. Create a new bot and get the token")
        token = prompt_text("Enter your Telegram bot token")
        if token:
            config["TELEGRAM_TOKEN"] = token

    # QQ
    enable_qq = prompt_choice(
        "Enable QQ bot?",
        ["Yes", "No"],
        default=0
    )

    if enable_qq == 0:
        print(f"\n🎮 To set up QQ bot:")
        print(f"   1. Install go-cqhttp: https://github.com/Mrs4s/go-cqhttp")
        print(f"   2. Start go-cqhttp on port 5700")
        print(f"   3. Configure HTTP API in go-cqhttp config")

        qq_url = prompt_text(
            "QQ API URL (default: http://localhost:5700)",
            default="http://localhost:5700"
        )
        config["QQ_API_URL"] = qq_url

        qq_token = prompt_text(
            "QQ API token (optional, leave blank if not needed)"
        )
        if qq_token:
            config["QQ_API_TOKEN"] = qq_token

    return config


def setup_server_settings() -> Dict[str, Any]:
    """Setup general server settings"""
    print_header("⚙️  Server Settings")

    config = {
        "HOST": "0.0.0.0",
        "PORT": "8000",
        "SECRET_KEY": "change-this-in-production",
        "SLEEP_ENABLED": "true",
        "SLEEP_HOUR": "22",
        "WAKE_HOUR": "7",
        "AI_TIMEZONE": "Asia/Shanghai"
    }

    # Allow customization of key settings
    port = prompt_text(
        "Server port (default: 8000)",
        default="8000"
    )
    if port:
        config["PORT"] = port

    timezone = prompt_text(
        "AI timezone (default: Asia/Shanghai)",
        default="Asia/Shanghai"
    )
    if timezone:
        config["AI_TIMEZONE"] = timezone

    return config


def write_env_file(filepath: Path, config: Dict[str, Any]) -> None:
    """Write configuration to .env file"""
    lines = [
        "# AI Child Configuration - Auto-generated by setup wizard",
        "# Generated on: import datetime; print(datetime.datetime.now().isoformat())",
        ""
    ]

    for key, value in config.items():
        if value is not None and value != "":
            lines.append(f"{key}={value}")

    filepath.write_text("\n".join(lines) + "\n")
    print_success(f"Configuration written to {filepath}")


def verify_setup(project_root: Path) -> bool:
    """Verify the setup is working"""
    print_header("🔍 Verifying Setup")

    print_step(1, "Checking prerequisites...")

    # Check Python
    print("  • Python version:", end=" ")
    python_version = subprocess.run(
        [sys.executable, "--version"],
        capture_output=True,
        text=True
    )
    print(python_version.stdout.strip())

    # Check server dependencies
    print("  • Checking dependencies...", end=" ")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list"],
            capture_output=True,
            text=True,
            cwd=project_root / "server"
        )
        if "fastapi" in result.stdout and "SQLAlchemy" in result.stdout:
            print_success("Found")
        else:
            print_warning("Some packages may be missing. Run: pip install -r requirements.txt")
    except Exception as e:
        print_warning(f"Could not verify: {e}")

    print("\n" + Colors.GREEN + "✅ Setup complete!" + Colors.RESET)
    return True


def main():
    """Main setup wizard flow"""
    try:
        # Determine project root
        project_root = Path(__file__).parent

        print(f"\n{Colors.BOLD}{Colors.BLUE}")
        print("╔════════════════════════════════════════════════════════════╗")
        print("║          🚀 AI Child Setup Wizard 🚀                       ║")
        print("║    Interactive configuration for first-time users          ║")
        print("╚════════════════════════════════════════════════════════════╝")
        print(Colors.RESET)

        # Step 1: LLM Provider
        llm_config = setup_llm_provider()

        # Step 2: Server Settings
        server_config = setup_server_settings()

        # Step 3: Bot Adapters
        bot_config = setup_bot_adapters()

        # Step 4: Write config files
        print_header("📝 Writing Configuration Files")

        # Server .env
        server_env_path = project_root / "server" / ".env"
        server_full_config = {**server_config, **llm_config}
        write_env_file(server_env_path, server_full_config)

        # Bot .env
        bot_env_path = project_root / "bot" / ".env"
        write_env_file(bot_env_path, bot_config)

        # Step 5: Verify
        verify_setup(project_root)

        # Step 6: Quick start guide
        print_header("🎯 Quick Start Guide")
        print(f"""
{Colors.BOLD}Terminal 1 - Start Ollama (if using local):${Colors.RESET}
  ollama serve

{Colors.BOLD}Terminal 2 - Start AI Child Server:${Colors.RESET}
  cd {project_root / 'server'}
  python3 main.py

{Colors.BOLD}Terminal 3 - Start Bot(s):${Colors.RESET}
  cd {project_root / 'bot'}
  python3 main.py  # Start all adapters
  # or
  python3 main.py qq  # Start only QQ bot
  python3 main.py telegram  # Start only Telegram

{Colors.BOLD}Access the Web UI:${Colors.RESET}
  http://localhost:8000

{Colors.BOLD}API Documentation:${Colors.RESET}
  http://localhost:8000/docs
""")

        # Final message
        print(f"\n{Colors.GREEN}{Colors.BOLD}✨ Setup successful! Happy chatting! ✨{Colors.RESET}\n")

        # Offer to display secrets
        if llm_config.get("OPENAI_API_KEY") or llm_config.get("DASHSCOPE_API_KEY"):
            print_warning("Your API keys are stored in .env files:")
            print(f"  • {server_env_path}")
            print(f"  • Make sure these files are in .gitignore")
            print(f"  • Never commit them to version control!")

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled.{Colors.RESET}\n")
        sys.exit(1)
    except Exception as e:
        print_error(f"Setup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
