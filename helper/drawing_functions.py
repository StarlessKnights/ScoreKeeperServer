import curses

from helper.digits import BIG_DIGITS

def draw_label(stdscr: curses.window, y: int, x: int, label: str, value: str, color: int) -> None:
    stdscr.addstr(y, x, label, curses.A_BOLD)
    stdscr.addstr(y, x + len(label), value, curses.color_pair(color))
    
def center_text(stdscr: curses.window, y: int, text: str, attr: int = 0) -> None:
    _, width = stdscr.getmaxyx()
    stdscr.addstr(y, max(0, (width - len(text)) // 2), text, attr)
    
def make_big_text_rows(text: str) -> list[str]:
    rows = ["", "", "", "", ""]
    for ch in text:
        glyph = BIG_DIGITS.get(ch, BIG_DIGITS["?"])
        for i in range(5):
            rows[i] += glyph[i] + "  "
    return rows

def draw_big_score(stdscr: curses.window, top_y: int, x: int, score: int, color: int) -> None:
    rows = make_big_text_rows(str(score))
    for offset, row in enumerate(rows):
        stdscr.addstr(top_y + offset, x, row, curses.color_pair(color) | curses.A_BOLD)

def draw_big_text(stdscr: curses.window, top_y: int, x: int, text: str, color: int) -> None:
    rows = make_big_text_rows(text)
    for offset, row in enumerate(rows):
        stdscr.addstr(top_y + offset, x, row, curses.color_pair(color) | curses.A_BOLD)

def format_match_time(seconds_value: int) -> str:
    safe_seconds = max(0, seconds_value)
    minutes = safe_seconds // 60
    seconds = safe_seconds % 60
    return f"{minutes}:{seconds:02d}"