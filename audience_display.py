import curses
import json
import time
import json
import requests
import asyncio
import threading
import importlib
from urllib.parse import urlparse


DEFAULT_URL = "http://127.0.0.1:8000"
REFRESH_INTERVAL = 0.5
READINESS_CONFIRMED = False

session = requests.Session()


def build_ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/ws"


class LiveStateStream:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.latest_state: dict | None = None
        self.error: str | None = None
        self._ws_module = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run_thread, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()

    def snapshot(self) -> tuple[dict | None, str | None]:
        with self._lock:
            state = dict(self.latest_state) if self.latest_state else None
            return state, self.error

    def _set_state(self, state: dict | None, error: str | None) -> None:
        with self._lock:
            if state is not None:
                self.latest_state = state
            self.error = error

    def _run_thread(self) -> None:
        try:
            self._ws_module = importlib.import_module("websockets")
        except ImportError:
            self._set_state(None, "Install websockets package for live stream")
            return

        asyncio.run(self._run_forever())

    async def _run_forever(self) -> None:
        ws_module = self._ws_module
        if ws_module is None:
            self._set_state(None, "Install websockets package for live stream")
            return

        ws_url = build_ws_url(self.base_url)
        while not self._stop.is_set():
            try:
                async with ws_module.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    self._set_state(None, None)

                    while not self._stop.is_set():
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue

                        state = json.loads(message)
                        self._set_state(state, None)
            except Exception as exc:
                self._set_state(None, f"stream reconnecting: {exc}")
                await asyncio.sleep(1)

BIG_DIGITS = {
    "0": [
        " ### ",
        "#   #",
        "#   #",
        "#   #",
        " ### ",
    ],
    "1": [
        "  #  ",
        " ##  ",
        "  #  ",
        "  #  ",
        " ### ",
    ],
    "2": [
        " ### ",
        "    #",
        " ### ",
        "#    ",
        "#####",
    ],
    "3": [
        "#### ",
        "    #",
        " ### ",
        "    #",
        "#### ",
    ],
    "4": [
        "#   #",
        "#   #",
        "#####",
        "    #",
        "    #",
    ],
    "5": [
        "#####",
        "#    ",
        "#### ",
        "    #",
        "#### ",
    ],
    "6": [
        " ### ",
        "#    ",
        "#### ",
        "#   #",
        " ### ",
    ],
    "7": [
        "#####",
        "    #",
        "   # ",
        "  #  ",
        "  #  ",
    ],
    "8": [
        " ### ",
        "#   #",
        " ### ",
        "#   #",
        " ### ",
    ],
    "9": [
        " ### ",
        "#   #",
        " ####",
        "    #",
        " ### ",
    ],
    "-": [
        "     ",
        "     ",
        "#####",
        "     ",
        "     ",
    ],
    "?": [
        " ### ",
        "    #",
        "  ## ",
        "     ",
        "  #  ",
    ],
    ":": [
        "     ",
        "  #  ",
        "     ",
        "  #  ",
        "     ",
    ],
}


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


def get_display_time(state: dict) -> int:
    current_phase = str(state.get("current_phase", ""))
    raw_match_time = int(state.get("match_time", 0))

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
    center_text(stdscr, 5, f"Final Score: Red {red_score} - Blue {blue_score}", curses.A_BOLD)

    center_text(stdscr, 8, f"Red Auto: {red_auto}   Red Teleop: {red_teleop}", curses.color_pair(1))
    center_text(stdscr, 9, f"Blue Auto: {blue_auto}   Blue Teleop: {blue_teleop}", curses.color_pair(4))

    center_text(stdscr, 11, f"Energized Red: {red_score}/360 {'Y' if red_score >= 360 else ' '}    Energized Blue: {blue_score}/360 {'Y' if blue_score >= 360 else ' '}")
    center_text(stdscr, 12, f"Supercharged Red: {red_score}/500 {'Y' if red_score >= 500 else ' '}    Supercharged Blue: {blue_score}/500 {'Y' if blue_score >= 500 else ' '}")

    center_text(stdscr, 15, "Press q to quit", curses.A_DIM)
    stdscr.refresh()


def render(stdscr: curses.window, base_url: str, state: dict | None, error: str | None) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    title = "Torque FMS - Audience Display"
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

        center_text(stdscr, 7, f"Phase: {str(state.get('current_phase', '?'))}", curses.A_BOLD)

        display_time_value = get_display_time(state)
        center_text(stdscr, 8, "Match Time", curses.A_BOLD)

        match_time_text = format_match_time(display_time_value)
        match_time_width = len(make_big_text_rows(match_time_text)[0])
        match_time_x = max(2, (width - match_time_width) // 2)
        draw_big_text(stdscr, 10, match_time_x, match_time_text, 2)

        red_score = int(state.get("red_score", 0))
        blue_score = int(state.get("blue_score", 0))

        red_label = "RED"
        blue_label = "BLUE"
        stdscr.addstr(15, max(2, width // 4 - len(red_label) // 2), red_label, curses.color_pair(1) | curses.A_BOLD)
        stdscr.addstr(15, max(2, (3 * width) // 4 - len(blue_label) // 2), blue_label, curses.color_pair(4) | curses.A_BOLD)

        big_width_red = len(make_big_text_rows(str(red_score))[0])
        big_width_blue = len(make_big_text_rows(str(blue_score))[0])

        red_x = max(2, width // 4 - big_width_red // 2)
        blue_x = max(2, (3 * width) // 4 - big_width_blue // 2)

        draw_big_score(stdscr, 16, red_x, red_score, 1)
        draw_big_score(stdscr, 16, blue_x, blue_score, 4)

        center_text(
            stdscr,
            23,
            f"Red Wasted: {state.get('red_wasted', 0)}    Blue Wasted: {state.get('blue_wasted', 0)}    Scorekeepers: {state.get('connected_scorekeepers', 0)}",
            curses.A_BOLD,
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


def main() -> None:
    curses.wrapper(run_tui)


if __name__ == "__main__":
    main()
