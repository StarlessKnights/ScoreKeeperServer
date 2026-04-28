import curses
import json
import time
import json
import requests
from helper.live_state_stream import LiveStateStream
from helper.drawing_functions import (center_text, draw_big_score, draw_big_text, format_match_time, make_big_text_rows)
import os

DEFAULT_URL = "http://192.168.2.1:8000"
REFRESH_INTERVAL = 0.5
READINESS_CONFIRMED = False
READY_TO_ADVANCE = False

existing_files = [f for f in os.listdir("match_data") if f.startswith("match_") and f.endswith(".json")]

if existing_files:
    highest_match_number = max(int(f.split("_")[1].split(".")[0]) for f in existing_files)
else:
    highest_match_number = 0

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


def get_display_time(state: dict) -> int:
    current_phase = str(state.get("current_phase", ""))
    raw_match_time = int(state.get("match_time", 0))
    
    if (current_phase == "Waiting"):
        return 20

    if current_phase == "Auto" and raw_match_time > 140:
        return max(0, raw_match_time - 140)

    return max(0, raw_match_time)


def render_winner_screen(stdscr: curses.window, state: dict) -> None:
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
    center_text(stdscr, 5, f"Red {red_score} - Blue {blue_score}", curses.A_BOLD)

    center_text(stdscr, 8, f"Red Auto: {red_auto}   Red Teleop: {red_teleop}", curses.color_pair(1))
    center_text(stdscr, 9, f"Blue Auto: {blue_auto}   Blue Teleop: {blue_teleop}", curses.color_pair(4))

    center_text(stdscr, 11, f"Energized Red: {red_score}/360 {'✓' if red_score >= 360 else ' '}    Energized Blue: {blue_score}/360 {'✓' if blue_score >= 360 else ' '}")
    center_text(stdscr, 12, f"Supercharged Red: {red_score}/500 {'✓' if red_score >= 500 else ' '}    Supercharged Blue: {blue_score}/500 {'✓' if blue_score >= 500 else ' '}")

    center_text(stdscr, 15, "Press q to quit", curses.A_DIM)
    stdscr.refresh()


def draw_active_arrow(stdscr: curses.window, y: int, x: int, facingLeft: bool) -> None:
    arrow_attr = curses.color_pair(5) | curses.A_BOLD
    stdscr.addstr(y, x, "      ", arrow_attr)
    if facingLeft:
        stdscr.addstr(y + 1, x, "  <<  ", arrow_attr)
    else:
        stdscr.addstr(y + 1, x, "  >>  ", arrow_attr)
    stdscr.addstr(y + 2, x, "      ", arrow_attr)


def render(stdscr: curses.window, base_url: str, state: dict | None, error: str | None) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    title = "Torque FMS - Audience Display"
    subtitle = f"Practice Match {highest_match_number + 1}"
    stdscr.addstr(1, max(0, (width - len(title)) // 2), title, curses.A_BOLD | curses.A_UNDERLINE)
    stdscr.addstr(3, max(0, (width - len(subtitle)) // 2), subtitle)

    if error:
        stdscr.addstr(5, 4, f"Status: {error}", curses.color_pair(3) | curses.A_BOLD)
    elif not state:
        stdscr.addstr(5, 4, "Status: waiting for server...", curses.color_pair(3) | curses.A_BOLD)
    else:
        if (int(state.get("match_time", 1)) <= 0 or state.get("current_phase") == "Match Ended") and READY_TO_ADVANCE:
            render_winner_screen(stdscr, state)
            return

        if (state.get("waiting_for_scorekeepers", True) == True):
            stdscr.addstr(height - 2, 2, "Status: waiting for scorekeepers", curses.color_pair(3) | curses.A_BOLD)
        elif not READINESS_CONFIRMED:
            stdscr.addstr(height - 2, 2, "Status: ready to start", curses.color_pair(3) | curses.A_BOLD)
        else:
            stdscr.addstr(height - 2, 2, "Status: active", curses.color_pair(2) | curses.A_BOLD)

        center_text(stdscr, 5, f"Phase: {str(state.get('current_phase', '?'))}", curses.A_BOLD)

        display_time_value = get_display_time(state)

        match_time_text = format_match_time(display_time_value)
        match_time_width = len(make_big_text_rows(match_time_text)[0])
        match_time_x = max(2, (width - match_time_width) // 2)
        draw_big_text(stdscr, 7, match_time_x, match_time_text, 2)

        red_score = int(state.get("red_score", 0))
        blue_score = int(state.get("blue_score", 0))

        red_label = "RED"
        blue_label = "BLUE"
        stdscr.addstr(14, max(2, width // 4 - (len(red_label) + 1) // 2), red_label, curses.color_pair(1) | curses.A_BOLD)
        stdscr.addstr(14, max(2, (3 * width) // 4 - (len(blue_label) + 1) // 2), blue_label, curses.color_pair(4) | curses.A_BOLD)

        big_width_red = len(make_big_text_rows(str(red_score))[0])
        big_width_blue = len(make_big_text_rows(str(blue_score))[0])

        red_x = max(2, width // 4 - big_width_red // 2)
        blue_x = max(2, (3 * width) // 4 - big_width_blue // 2)

        if (state.get("blue_active", False) and not state.get("current_phase", "") == "Waiting"):
            blue_arrow_x = max(2, blue_x + (big_width_blue // 2) - 21)
            draw_active_arrow(stdscr, 17, blue_arrow_x, facingLeft=False)
            
        if (state.get("red_active", False) and not state.get("current_phase", "") == "Waiting"):
            red_arrow_x = max(2, red_x + (big_width_red // 2) + 14)
            draw_active_arrow(stdscr, 17, red_arrow_x, facingLeft=True)
        
        draw_big_score(stdscr, 16, red_x, red_score, 1)
        draw_big_score(stdscr, 16, blue_x, blue_score, 4)

        center_text(
            stdscr,
            23,
            f"Red Wasted: {state.get('red_wasted', 0)}    Blue Wasted: {state.get('blue_wasted', 0)}    Scorekeepers: {len(state.get('connected_scorekeepers', []))}",
        )

    stdscr.refresh()


def run_tui(stdscr: curses.window) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)
    curses.init_pair(4, curses.COLOR_BLUE, -1)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_YELLOW)

    stdscr.nodelay(True)
    stdscr.timeout(100)

    state = None
    error = None
    last_fetch = 0.0
    stream = LiveStateStream(DEFAULT_URL)
    stream.start()

    while True:
        now = time.time()

        stream_state, stream_error = stream.snapshot()
        if stream_state is not None:
            state = stream_state
            error = None

        if stream_state is None and now - last_fetch >= REFRESH_INTERVAL:
            try:
                state = fetch_state(DEFAULT_URL)
                error = None
            except (requests.HTTPError, requests.Timeout, TimeoutError, json.JSONDecodeError, OSError) as exc:
                state = None
                error = str(exc)
            last_fetch = now
        elif stream_error and state is None:
            error = stream_error

        render(stdscr, DEFAULT_URL, state, error)

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            stream.close()
            break

        if key == ord(" "):
            confirm_readiness(DEFAULT_URL)
            
        if key == ord("\n") and state and state.get("current_phase") == "Match Ended":
            global READY_TO_ADVANCE
            READY_TO_ADVANCE = not READY_TO_ADVANCE
            
        if (key == ord("s") or key == ord("S")) and state and state.get("current_phase") == "Match Ended":
            filename = f"match_data/match_{highest_match_number + 1}.json"

            with open(filename, "w") as f:
                state["saved_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                state["red_energized"] = state.get("red_score", 0) >= 360
                state["blue_energized"] = state.get("blue_score", 0) >= 360
                state["red_supercharged"] = state.get("red_score", 0) >= 500
                state["blue_supercharged"] = state.get("blue_score", 0) >= 500
                
                state["red_average_bps_auto"] = round(state.get("red_scored_auto", 0) / 20, 2)
                state["blue_average_bps_auto"] = round(state.get("blue_scored_auto", 0) / 20, 2)
                
                state["red_average_bps_teleop"] = round(state.get("red_scored_teleop", 0) / 90, 2)
                state["blue_average_bps_teleop"] = round(state.get("blue_scored_teleop", 0) / 90, 2)

                json.dump(state, f, indent=4)
                
def main() -> None:
    curses.wrapper(run_tui)


if __name__ == "__main__":
    main()
