import curses
import json
import time
import json
import requests


DEFAULT_URL = "http://192.168.2.1:8000"
REFRESH_INTERVAL = 0.5
READINESS_CONFIRMED = False

session = requests.Session()

def fetch_state(base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/"
    
    try:
        r = session.get(url, timeout=2)
    except:
        return {}

    return r.json()
    
def confirm_readiness(base_url: str):
    url = f"{base_url.rstrip('/')}/tui"
    data = {}

    r = session.post(url, data)

    if (r.status_code != 200):
        return False
    
    global READINESS_CONFIRMED
    READINESS_CONFIRMED = True
    return True


def draw_label(stdscr: curses.window, y: int, x: int, label: str, value: str, color: int) -> None:
    stdscr.addstr(y, x, label, curses.A_BOLD)
    stdscr.addstr(y, x + len(label), value, curses.color_pair(color))


def center_text(stdscr: curses.window, y: int, text: str, attr: int = 0) -> None:
    _, width = stdscr.getmaxyx()
    stdscr.addstr(y, max(0, (width - len(text)) // 2), text, attr)


def render_winner_screen(stdscr: curses.window, state: dict) -> None:
    height, width = stdscr.getmaxyx()

    red_score = int(state.get("red_score", 0))
    blue_score = int(state.get("blue_score", 0))
    red_auto = int(state.get("red_scored_auto", 0))
    blue_auto = int(state.get("blue_scored_auto", 0))
    red_teleop = int(state.get("red_scored_teleop", 0))
    blue_teleop = int(state.get("blue_scored_teleop", 0))

    if red_score > blue_score:
        winner_text = "RED WINS"
        winner_color = curses.color_pair(1) | curses.A_BOLD
    elif blue_score > red_score:
        winner_text = "BLUE WINS"
        winner_color = curses.color_pair(4) | curses.A_BOLD
    else:
        winner_text = "TIE MATCH"
        winner_color = curses.color_pair(3) | curses.A_BOLD

    stdscr.erase()
    center_text(stdscr, 1, "MATCH COMPLETE", curses.A_BOLD | curses.A_UNDERLINE)
    center_text(stdscr, 3, winner_text, winner_color)
    center_text(stdscr, 5, f"Final Score: Red {red_score} - Blue {blue_score}", curses.A_BOLD)

    center_text(stdscr, 8, f"Red Auto: {red_auto}   Red Teleop: {red_teleop}", curses.color_pair(1))
    center_text(stdscr, 9, f"Blue Auto: {blue_auto}   Blue Teleop: {blue_teleop}", curses.color_pair(4))
    
    center_text(stdscr, 11, f"Energized Red: {red_score}/360 {'✓' if red_score >= 360 else ' '}    Energized Blue: {blue_score}/360 {'✓' if blue_score >= 360 else ''}")
    center_text(stdscr, 12, f"Supercharged Red: {red_score}/500 {'✓' if red_score >= 500 else ' '}    Energized Blue: {blue_score}/500 {'✓' if blue_score >= 500 else ''}")

    center_text(stdscr, 15, "Press q to quit", curses.A_DIM)
    footer = "Winner is based on total score; breakdown shows auto and teleop points"
    center_text(stdscr, height - 2, footer[: max(0, width - 2)], curses.A_DIM)
    stdscr.refresh()


def render(stdscr: curses.window, base_url: str, state: dict | None, error: str | None) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    title = "Torque FMS"
    subtitle = f"Server: {base_url}    Press q to quit"
    stdscr.addstr(1, max(0, (width - len(title)) // 2), title, curses.A_BOLD | curses.A_UNDERLINE)
    stdscr.addstr(3, max(0, (width - len(subtitle)) // 2), subtitle)

    if error:
        stdscr.addstr(5, 4, f"Status: {error}", curses.color_pair(3) | curses.A_BOLD)
    elif not state:
        stdscr.addstr(5, 4, "Status: waiting for server...", curses.color_pair(3) | curses.A_BOLD)
    else:
        if int(state.get("match_time", 1)) <= 0 or state.get("current_phase") == "Match Ended":
            render_winner_screen(stdscr, state)
            return
        
        if (state.get("waiting_for_scorekeepers", True) == True):
            stdscr.addstr(5, 4, "Status: waiting for scorekeepers", curses.color_pair(3) | curses.A_BOLD)
        elif not READINESS_CONFIRMED:
            stdscr.addstr(5, 4, "Status: ready to start", curses.color_pair(3) | curses.A_BOLD)
        else:
            stdscr.addstr(5, 4, "Status: active", curses.color_pair(2) | curses.A_BOLD)


        draw_label(stdscr, 7, 4, "Phase: ", str(state.get("current_phase", "?")), 2)
        draw_label(stdscr, 8, 4, "Match Time: ", str(state.get("match_time", "?")), 2)
        draw_label(stdscr, 9, 4, "Phase Change Time: ", str(state.get("time_until_phase_change", "?")), 2)
        draw_label(stdscr, 11, 4, "Red Score: ", str(state.get("red_score", 0)), 1)
        draw_label(stdscr, 12, 4, "Blue Score: ", str(state.get("blue_score", 0)), 4)
        draw_label(stdscr, 13, 4, "Red Wasted: ", str(state.get("red_wasted", 0)), 1)
        draw_label(stdscr, 14, 4, "Blue Wasted: ", str(state.get("blue_wasted", 0)), 4)
        draw_label(stdscr, 16, 4, "Connected Scorekeepers: ", str(state.get("connected_scorekeepers", 0)), 2)
        draw_label(stdscr, 17, 4, "Counting Down: ", str(state.get("counting_down", False)), 2)

        red_active = state.get("red_active", False)
        blue_active = state.get("blue_active", False)
        draw_label(stdscr, 19, 4, "Red Active: ", str(red_active), 1 if red_active else 3)
        draw_label(stdscr, 20, 4, "Blue Active: ", str(blue_active), 4 if blue_active else 3)

    footer = "Refreshes automatically every 0.5s"
    stdscr.addstr(height - 2, max(0, (width - len(footer)) // 2), footer, curses.A_DIM)
    stdscr.refresh()


def run_tui(stdscr: curses.window) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_BLUE, -1)

    stdscr.nodelay(True)
    stdscr.timeout(100)

    state = None
    error = None
    last_fetch = 0.0

    while True:
        now = time.time()
        if now - last_fetch >= REFRESH_INTERVAL:
            try:
                state = fetch_state(DEFAULT_URL)
                error = None
            except (requests.HTTPError, requests.Timeout, TimeoutError, json.JSONDecodeError, OSError) as exc:
                state = None
                error = str(exc)
            last_fetch = now

        render(stdscr, DEFAULT_URL, state, error)

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break

        if key == ord(" "):
            confirm_readiness(DEFAULT_URL)


def main() -> None:
    curses.wrapper(run_tui)


if __name__ == "__main__":
    main()