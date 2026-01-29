#!/usr/bin/env python3
import os
import sys
import argparse
import toml
from google import genai
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

def load_config():
    config_path = os.path.expanduser("~/.config/gemini-cli.toml")
    if os.path.exists(config_path):
        try:
            return toml.load(config_path)
        except Exception:
            return {}
    return {}

def main():
    parser = argparse.ArgumentParser(description="Stream responses from Google Gemini AI.")
    parser.add_argument("prompt", nargs="?", help="Prompt to send to the model")
    parser.add_argument("-t", "--token", help="API token for authentication")
    parser.add_argument("-s", "--system", help="System context prompt")
    parser.add_argument("-m", "--model", default="gemini-flash-latest", help="Model name (default: gemini-flash-latest)")
    parser.add_argument("--stream", action="store_true", help="Stream output")
    parser.add_argument("--markdown", action="store_true", default=True, help="Output markdown format (default: True)")
    
    args = parser.parse_args()
    config = load_config()
    
    token = args.token or config.get("token") or os.environ.get("GEMINI_API_KEY")
    if not token:
        print("Error: API token not found. Set it in ~/.config/gemini-cli.toml or GEMINI_API_KEY environment variable.")
        sys.exit(1)
        
    client = genai.Client(api_key=token)
    
    prompt = args.prompt
    if not prompt:
        if sys.stdin.isatty():
            print("Interactive mode not fully implemented. Please provide a prompt.")
            sys.exit(0)
        else:
            prompt = sys.stdin.read()

    console = Console()
    
    try:
        if args.stream:
            response = client.models.generate_content_stream(
                model=args.model,
                contents=prompt,
                config={'system_instruction': args.system} if args.system else None
            )
            full_text = ""
            with Live(Markdown(""), refresh_per_second=4, console=console) as live:
                for chunk in response:
                    full_text += chunk.text
                    live.update(Markdown(full_text))
        else:
            response = client.models.generate_content(
                model=args.model,
                contents=prompt,
                config={'system_instruction': args.system} if args.system else None
            )
            if args.markdown:
                console.print(Markdown(response.text))
            else:
                print(response.text)
    except Exception as e:
        print(f"Error from Gemini API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
