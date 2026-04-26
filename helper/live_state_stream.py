import threading
import asyncio
import json
import importlib
from urllib.parse import urlparse

def build_ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"ws://{parsed.netloc}/ws"

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