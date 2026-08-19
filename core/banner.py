# -*- coding: utf-8 -*-
"""
Console Banner Module for Starvell Assistant Bot
Author: gadacy
"""
import sys

# ANSI Colors
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
WHITE = "\033[97m"
BLUE = "\033[94m"

BOX_WIDTH = 65

STARVELL_ART = [
    r"  ____ _______  _    ____  __    __  _____ _     _    ",
    r" / ___||_   _| / \  |  _ \ \ \  / / | ____| |   | |   ",
    r" \___ \  | |  / _ \ | |_) | \ \/ /  |  _| | |   | |   ",
    r"  ___) | | | / ___ \|  _ <   \  /   | |___| |___| |___",
    r" |____/  |_|/_/   \_\_| \_\   \/    |_____|_____|_____|"
]

ASSISTANT_ART = [
    r"    _    ____ _____   ___  ______  _______   _    __   __  _____ ",
    r"   / \  / ___/ ____) |_ _|/ _____)|__   __| / \  |  \ |  ||_   _|",
    r"  / _ \ \___ \___  \  | | \___  \    | |   / _ \ |   \|  |  | |  ",
    r" / ___ \ ___) ___)  ) | |  ___)  )   | |  / ___ \| |\    |  | |  ",
    r"/_/   \_\\____|____/  |_| (_____/    |_| /_/   \_\_| \___|  |_|  "
]

INFO_ITEMS = [
    ("Bot Name", "STARVELL ASSISTANT BOT", WHITE),
    ("Author  ", "gadacy", GREEN),
    ("Channel ", "@starvell_assistant", CYAN),
    ("Version ", "1.0.0", YELLOW)
]

def _make_line(plain_text: str, colored_text: str = None, align: str = "center", use_color: bool = True) -> str:
    if colored_text is None or not use_color:
        colored_text = plain_text

    visible_len = len(plain_text)
    pad = BOX_WIDTH - visible_len
    if align == "center":
        left = pad // 2
        right = pad - left
    elif align == "left":
        left = 3
        right = pad - 3
    else:
        left = pad - 3
        right = 3

    b_char = f"{CYAN}{BOLD}║{RESET}" if use_color else "║"
    return b_char + (" " * left) + colored_text + (" " * right) + b_char

def generate_banner(use_color: bool = True) -> str:
    b_top = f"{CYAN}{BOLD}╔" + ("═" * BOX_WIDTH) + f"╗{RESET}" if use_color else "╔" + ("═" * BOX_WIDTH) + "╗"
    b_sep = f"{CYAN}{BOLD}╠" + ("═" * BOX_WIDTH) + f"╣{RESET}" if use_color else "╠" + ("═" * BOX_WIDTH) + "╣"
    b_bot = f"{CYAN}{BOLD}╚" + ("═" * BOX_WIDTH) + f"╝{RESET}" if use_color else "╚" + ("═" * BOX_WIDTH) + "╝"

    lines = [b_top, _make_line("", use_color=use_color)]

    for s in STARVELL_ART:
        colored_s = f"{CYAN}{BOLD}{s}{RESET}"
        lines.append(_make_line(s, colored_s, align="center", use_color=use_color))

    lines.append(_make_line("", use_color=use_color))

    for a in ASSISTANT_ART:
        colored_a = f"{GREEN}{BOLD}{a}{RESET}"
        lines.append(_make_line(a, colored_a, align="center", use_color=use_color))

    lines.append(_make_line("", use_color=use_color))
    lines.append(b_sep)

    for label, val, val_color in INFO_ITEMS:
        plain_info = f"[*] {label} : {val}"
        colored_info = f"{BLUE}[*]{RESET} {WHITE}{BOLD}{label}{RESET} : {val_color}{BOLD}{val}{RESET}"
        lines.append(_make_line(plain_info, colored_info, align="left", use_color=use_color))

    lines.append(b_bot)
    return "\n".join(lines)

def get_banner(use_color: bool = False) -> str:
    return generate_banner(use_color=use_color)

def print_banner():
    """Prints styled ASCII art logo to terminal with custom colors and perfect frame alignment."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("\n" + generate_banner(use_color=True) + "\n")

if __name__ == "__main__":
    print_banner()
