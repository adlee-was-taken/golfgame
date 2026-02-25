"""Entry point: python -m tui_client [--server HOST] [--no-tls]

Reads defaults from ~/.config/golf-tui.conf (create with --save-config).
"""

import argparse
import sys

from tui_client.config import load_config, save_config, CONFIG_PATH


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Golf Card Game TUI Client")
    parser.add_argument(
        "--server",
        default=cfg.get("server", "golfcards.club"),
        help=f"Server host[:port] (default: {cfg.get('server', 'golfcards.club')})",
    )
    parser.add_argument(
        "--no-tls",
        action="store_true",
        default=cfg.get("tls", "true").lower() != "true",
        help="Use ws:// and http:// instead of wss:// and https://",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to tui_debug.log",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help=f"Save current options as defaults to {CONFIG_PATH}",
    )
    args = parser.parse_args()

    if args.save_config:
        save_config({
            "server": args.server,
            "tls": str(not args.no_tls).lower(),
        })
        print(f"Config saved to {CONFIG_PATH}")
        print(f"  server = {args.server}")
        print(f"  tls = {str(not args.no_tls).lower()}")
        return

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG, filename="tui_debug.log")

    from tui_client.app import GolfApp
    app = GolfApp(server=args.server, use_tls=not args.no_tls)
    app.run()


if __name__ == "__main__":
    main()
