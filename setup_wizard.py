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


def prompt_choice(prompt: str, choices: list[str], default: int = 0, descriptions: list[str] = None) -> int:
    """Prompt user to choose from a list"""
    print(f"\n{Colors.BOLD}{prompt}{Colors.RESET}")
    for i, choice in enumerate(choices, 1):
        marker = f"{Colors.GREEN}→{Colors.RESET}" if i - 1 == default else " "
        print(f"  {marker} {i}. {choice}")
        if descriptions and i - 1 < len(descriptions):
            print(f"     {Colors.YELLOW}{descriptions[i-1]}{Colors.RESET}")

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


def prompt_text(prompt: str, default: str = "", required: bool = False, help_text: str = "") -> str:
    """Prompt user for text input"""
    while True:
        if help_text:
            print(f"{Colors.YELLOW}(💡 Tip: {help_text}){Colors.RESET}")

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


def setup_ollama_models() -> None:
    """Helper to register local GGUF models with Ollama"""
    print_step(1, "Checking for local GGUF models...")

    models_dir = Path.home().parent / "mac第二磁盘" / "ollama" / "models"
    if not models_dir.exists():
        return

    # Find all GGUF files
    gguf_files = list(models_dir.rglob("*.gguf"))
    if not gguf_files:
        return

    print(f"✅ Found {len(gguf_files)} local GGUF models:")
    for gguf in gguf_files:
        print(f"   • {gguf.parent.name} ({gguf.stat().st_size / (1024**3):.1f} GB)")

    register = prompt_choice(
        "\nWould you like to register these models with Ollama?",
        ["Yes, register them", "No, I'll do it manually"],
        default=0
    )

    if register == 0:
        print_step(2, "Registering models...")

        # Create Modelfiles for each local model
        modelfiles = {
            "Qwen3.5-9B-GGUF": {
                "model": "Qwen3.5-9B-GGUF/qwen3.5-9b-gguf.gguf",
                "name": "qwen-local"
            },
            "gemma-3-12b-it-abliterated-GGUF": {
                "model": "gemma-3-12b-it-abliterated-GGUF/gemma-3-12b-it-abliterated.q3_k_m.gguf",
                "name": "gemma-local"
            },
            "Huihui-Qwen3-VL-8B": {
                "model": "Huihui-Qwen3-VL-8B/ggml-model-Q4_K_M.gguf",
                "name": "huihui-qwen-local"
            }
        }

        for model_dir, model_info in modelfiles.items():
            model_path = models_dir / model_info["model"]
            if not model_path.exists():
                continue

            # Create Modelfile
            modelfile_content = f"""FROM {model_path}
TEMPLATE "[INST] {{{{ .Prompt }}}} [/INST]"
SYSTEM You are a helpful AI assistant.
"""

            modelfile_path = Path(f"/tmp/Modelfile-{model_info['name']}")
            modelfile_path.write_text(modelfile_content)

            # Register with ollama create
            print(f"  📝 Creating {model_info['name']}...", end=" ")
            try:
                result = subprocess.run(
                    ["ollama", "create", model_info["name"], "-f", str(modelfile_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    print_success("Done")
                else:
                    print_warning(f"(already exists or skipped)")
            except Exception as e:
                print_warning(f"(error: {str(e)[:30]})")

            modelfile_path.unlink(missing_ok=True)


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
        default=0,
        descriptions=[
            "Your own models, no API key needed, fast startup",
            "Use powerful cloud models, requires API key",
            "Use Alibaba Qwen models, requires API key"
        ]
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

        # Try to register local models
        try:
            setup_ollama_models()
        except Exception as e:
            print_warning(f"Could not register local models: {e}")

        print()

        # List available models
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                print(f"📚 Available Ollama models:\n")
                for line in result.stdout.strip().split('\n'):
                    print(f"   {line}")
                print()
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

    print(f"""{Colors.BOLD}Bot adapters let you chat with AI on different platforms.{Colors.RESET}
You can enable none, one, or multiple adapters.
""")

    config = {
        "SERVER_URL": "http://localhost:8000"
    }

    # Telegram
    enable_telegram = prompt_choice(
        "Enable Telegram bot?",
        ["Yes, enable Telegram", "No, skip Telegram"],
        default=1,
        descriptions=[
            "Chat with AI in Telegram, requires bot token from @BotFather",
            ""
        ]
    )

    if enable_telegram == 0:
        print(f"\n{Colors.BOLD}📱 Setting up Telegram bot:{Colors.RESET}")
        print(f"""
  1. Open Telegram and find @BotFather
  2. Send: /newbot
  3. Follow the prompts to create your bot
  4. Copy the token from the response
  5. Paste it below
""")
        token = prompt_text(
            "Enter your Telegram bot token",
            help_text="Looks like: 123456:ABC-DEF1234..."
        )
        if token:
            config["TELEGRAM_TOKEN"] = token
            print_success("Telegram configured")

    # QQ
    enable_qq = prompt_choice(
        "Enable QQ bot?",
        ["Yes, enable QQ", "No, skip QQ"],
        default=0,
        descriptions=[
            "Chat with AI in QQ groups/private chats, requires go-cqhttp",
            ""
        ]
    )

    if enable_qq == 0:
        print(f"\n{Colors.BOLD}🎮 Setting up QQ bot:{Colors.RESET}")
        print(f"""
  1. Download go-cqhttp from: https://github.com/Mrs4s/go-cqhttp/releases
  2. Run go-cqhttp and complete the setup
  3. Edit config.yml to enable HTTP API (usually port 5700)
  4. Start go-cqhttp before running AI Child bot
""")

        qq_url = prompt_text(
            "QQ API URL",
            default="http://localhost:5700",
            help_text="go-cqhttp HTTP API, usually on port 5700"
        )
        config["QQ_API_URL"] = qq_url

        qq_token = prompt_text(
            "QQ API token (optional, leave blank if not set in go-cqhttp)"
        )
        if qq_token:
            config["QQ_API_TOKEN"] = qq_token

        if qq_url:
            print_success("QQ configured")

    if not config.get("TELEGRAM_TOKEN") and not config.get("QQ_API_URL"):
        print_warning("No bot adapters enabled. You can still use the web UI to chat.")

    return config


def setup_server_settings() -> Dict[str, Any]:
    """Setup general server settings"""
    print_header("⚙️  Server Settings")

    print(f"""{Colors.BOLD}These settings control how the AI Child server runs.{Colors.RESET}
Most users can use the defaults.
""")

    config = {
        "HOST": "0.0.0.0",
        "PORT": "8000",
        "SECRET_KEY": "change-this-in-production",
        "SLEEP_ENABLED": "true",
        "SLEEP_HOUR": "22",
        "WAKE_HOUR": "7",
        "AI_TIMEZONE": "Asia/Shanghai"
    }

    # Customization
    port = prompt_text(
        "Web server port",
        default="8000",
        help_text="Where to access the web UI: http://localhost:PORT"
    )
    if port:
        config["PORT"] = port

    timezone = prompt_text(
        "AI timezone",
        default="Asia/Shanghai",
        help_text="For sleep/wake scheduling. Examples: Asia/Shanghai, US/Eastern, Europe/London"
    )
    if timezone:
        config["AI_TIMEZONE"] = timezone

    # Sleep schedule
    enable_sleep = prompt_choice(
        "Enable sleep/wake schedule?",
        ["Yes, AI sleeps at night", "No, AI is always active"],
        default=0,
        descriptions=[
            "AI will be less active during sleep hours (saves resources)",
            ""
        ]
    )

    if enable_sleep == 1:
        config["SLEEP_ENABLED"] = "false"
    else:
        sleep_hour = prompt_text(
            "Sleep time (0-23)",
            default="22",
            help_text="When AI goes to sleep. 22 = 10 PM"
        )
        wake_hour = prompt_text(
            "Wake time (0-23)",
            default="7",
            help_text="When AI wakes up. 7 = 7 AM"
        )
        if sleep_hour:
            config["SLEEP_HOUR"] = sleep_hour
        if wake_hour:
            config["WAKE_HOUR"] = wake_hour

    print_success("Server settings configured")
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
    print(Colors.GREEN + python_version.stdout.strip() + Colors.RESET)

    # Check server dependencies
    print("  • Checking server dependencies...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list"],
            capture_output=True,
            text=True,
            cwd=project_root / "server",
            timeout=10
        )
        missing = []
        for pkg in ["fastapi", "sqlalchemy", "pydantic"]:
            if pkg.lower() not in result.stdout.lower():
                missing.append(pkg)

        if not missing:
            print(Colors.GREEN + "✓" + Colors.RESET)
        else:
            print(Colors.YELLOW + f"Missing: {', '.join(missing)}" + Colors.RESET)
            print(f"     Run: cd {project_root}/server && pip install -r requirements.txt")
    except Exception as e:
        print(Colors.YELLOW + f"Could not verify: {str(e)[:40]}" + Colors.RESET)

    # Check bot dependencies
    print("  • Checking bot dependencies...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list"],
            capture_output=True,
            text=True,
            cwd=project_root / "bot",
            timeout=10
        )
        if "httpx" in result.stdout.lower():
            print(Colors.GREEN + "✓" + Colors.RESET)
        else:
            print(Colors.YELLOW + "Incomplete" + Colors.RESET)
            print(f"     Run: cd {project_root}/bot && pip install -r requirements.txt")
    except Exception as e:
        print(Colors.YELLOW + f"Could not verify: {str(e)[:40]}" + Colors.RESET)

    print()
    print(Colors.GREEN + "✅ Setup verification complete!" + Colors.RESET)
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

        # Step 6: Verify
        verify_setup(project_root)

        # Step 7: Quick start guide
        print_header("🎯 What's Next?")
        print(f"""
{Colors.BOLD}Your AI Child system is configured! Follow these steps to start:{Colors.RESET}

{Colors.BOLD}Step 1: Start Ollama (if using local){Colors.RESET}
  Open a terminal and run:
    {Colors.YELLOW}ollama serve{Colors.RESET}

{Colors.BOLD}Step 2: Start the AI Child server{Colors.RESET}
  Open another terminal and run:
    {Colors.YELLOW}cd {project_root}/server{Colors.RESET}
    {Colors.YELLOW}python3 main.py{Colors.RESET}
  Wait for: "Uvicorn running on http://0.0.0.0:8000"

{Colors.BOLD}Step 3: Start the bot(s){Colors.RESET}
  Open a third terminal and run:
    {Colors.YELLOW}cd {project_root}/bot{Colors.RESET}
""")

        if bot_config.get("TELEGRAM_TOKEN"):
            print(f"    {Colors.YELLOW}python3 main.py telegram  # Telegram only{Colors.RESET}")
        if bot_config.get("QQ_API_URL"):
            print(f"    {Colors.YELLOW}python3 main.py qq  # QQ only{Colors.RESET}")
        print(f"    {Colors.YELLOW}python3 main.py  # All adapters{Colors.RESET}")

        print(f"""
{Colors.BOLD}Then access the UI:{Colors.RESET}
  Browser: {Colors.BOLD}http://localhost:8000{Colors.RESET}
  API Docs: {Colors.BOLD}http://localhost:8000/docs{Colors.RESET}

{Colors.BOLD}Configuration files (keep these safe!):{Colors.RESET}
  - {Colors.YELLOW}{server_env_path}{Colors.RESET}
  - {Colors.YELLOW}{bot_env_path}{Colors.RESET}
  (These files are in .gitignore and should NOT be shared)
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
