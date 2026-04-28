import asyncio
import socket
import time
import math
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from pydantic import BaseModel
import threading
import random

class ScoreData(BaseModel):
    alliance: str
    count: int

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(udp_discovery_server())
    asyncio.create_task(update_match_time())
    yield

app = FastAPI(lifespan=lifespan)
lock = threading.Lock()

red_score = 0
blue_score = 0
red_wasted = 0
blue_wasted = 0
match_time = 160
time_until_phase_change = 0
current_phase = "Waiting"
inactive_first = ""
auto_ended = False
counting_down = True
waiting_for_scorekeepers = True
connected_scorekeepers = []

red_scored_auto = 0
blue_scored_auto = 0
red_scored_teleop = 0
blue_scored_teleop = 0

tui_ready = False

DESIRED_SCOREKEEPERS = 2
ws_clients: set[WebSocket] = set()
ws_clients_lock = asyncio.Lock()


def build_state_payload() -> dict:
    return {
        "red_score": red_score,
        "blue_score": blue_score,
        "current_phase": current_phase,
        "match_time": match_time,
        "red_active": is_alliance_active("Red"),
        "blue_active": is_alliance_active("Blue"),
        "red_wasted": red_wasted,
        "blue_wasted": blue_wasted,
        "counting_down": counting_down,
        "connected_scorekeepers": connected_scorekeepers,
        "red_scored_auto": red_scored_auto,
        "blue_scored_auto": blue_scored_auto,
        "red_scored_teleop": red_scored_teleop,
        "blue_scored_teleop": blue_scored_teleop,
        "waiting_for_scorekeepers": waiting_for_scorekeepers,
        "tui_ready": tui_ready,
        "time_until_phase_change": time_until_phase_change,
    }


async def broadcast_state() -> None:
    payload = build_state_payload()
    async with ws_clients_lock:
        clients = list(ws_clients)

    stale_clients: list[WebSocket] = []
    for client in clients:
        try:
            await client.send_json(payload)
        except Exception:
            stale_clients.append(client)

    if stale_clients:
        async with ws_clients_lock:
            for client in stale_clients:
                ws_clients.discard(client)

async def update_match_time():
    global match_time, current_phase, counting_down, waiting_for_scorekeepers, red_score, blue_score
    global time_until_phase_change, auto_ended

    while (waiting_for_scorekeepers or not tui_ready):
        await asyncio.sleep(0.1)

        if (len(connected_scorekeepers) == DESIRED_SCOREKEEPERS):
            waiting_for_scorekeepers = False

    waiting_for_scorekeepers = False
    counting_down = False

    current_phase = "Auto"
    auto_ended = False
    
    await broadcast_state()

    match_end_deadline = time.monotonic() + match_time
    next_match_tick = time.monotonic() + 1.0
    intermission_done = False

    while match_time > 0:
        sleep_for = next_match_tick - time.monotonic()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
        else:
            next_match_tick = time.monotonic()

        match_time = max(0, match_time - 1)
        if match_time > 0:
            update_phase()
            update_time_until_phase_change()
            
        await broadcast_state()

        if (match_time == 140 and not intermission_done):
            print("Auto phase ended")
            current_phase = "Intermission"
            time_until_phase_change = 0
            await broadcast_state()

            transition_end = time.monotonic() + 3
            transition_last_announce = None
            while True:
                transition_remaining = max(0, math.ceil(transition_end - time.monotonic()))
                if transition_remaining != transition_last_announce and transition_remaining > 0:
                    print(f"Transition starts in {transition_remaining} seconds...")
                    transition_last_announce = transition_remaining
                if transition_remaining == 0:
                    break
                await asyncio.sleep(0.05)

            intermission_done = True
            match_end_deadline += 3
            update_phase()
            update_time_until_phase_change()
            await broadcast_state()
            next_match_tick = time.monotonic() + 1.0
            continue

        next_match_tick += 1.0

    print("Match ended")
    current_phase = "Match Ended"
    time_until_phase_change = 0
    await broadcast_state()
    print(f"Red {red_score} - Blue {blue_score}")

async def udp_discovery_server():
    global connected_scorekeepers

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(('', 4210))
    server.setblocking(False)
    loop = asyncio.get_event_loop()
    
    print("UDP Discovery Server started...")
    while True:
        data, addr = await loop.sock_recvfrom(server, 1024)
        if data == b"DISCOVER_SCOREKEEPER":
            server.sendto(b"SCOREKEEPER_HERE", addr)
            
            print(f"Discovered by {addr}")
            
            if (addr not in connected_scorekeepers):
                connected_scorekeepers.append(addr)
                await broadcast_state()
                
                if (len(connected_scorekeepers) == DESIRED_SCOREKEEPERS):
                    global waiting_for_scorekeepers
                    waiting_for_scorekeepers = False

@app.get("/")
def read_root():
    return build_state_payload()

@app.post("/tui")
async def post_tui_ready():
    global tui_ready
    tui_ready = True
    await broadcast_state()
    return {"message": "tui readiness confirmed"}

@app.post("/", status_code=201)
async def change_score(data: ScoreData):
    response = update_score(data)
    await broadcast_state()
    
    if (response["ok"] == True):
        return {"message": response["message"]}
    else:
        return HTTPException(404, response["message"])


@app.websocket("/ws")
async def websocket_state(websocket: WebSocket):
    await websocket.accept()
    async with ws_clients_lock:
        ws_clients.add(websocket)

    try:
        await websocket.send_json(build_state_payload())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with ws_clients_lock:
            ws_clients.discard(websocket)

def update_score(data: ScoreData) -> dict:
    global red_score, blue_score, red_wasted, blue_wasted

    with lock:
        if current_phase == "Waiting" or current_phase == "Intermission":
            return {"ok": True, "message": "No score updates allowed in intermediary phases"}

        if data.alliance.lower() == "red":
            if (is_alliance_active("Red")):
                red_score += data.count

                if current_phase in ["Auto"]:
                    global red_scored_auto
                    red_scored_auto += data.count
                else:
                    global red_scored_teleop
                    red_scored_teleop += data.count
            else:
                red_wasted += data.count

            return {"ok": True, "message": "Score updated for red"}
        elif data.alliance.lower() == "blue":
            if (is_alliance_active("Blue")):
                blue_score += data.count

                if current_phase in ["Auto"]:
                    global blue_scored_auto
                    blue_scored_auto += data.count
                else:
                    global blue_scored_teleop
                    blue_scored_teleop += data.count
            else:
                blue_wasted += data.count

            return {"ok": True, "message": "Score updated for blue"}
        else:
            print(f"Invalid alliance: {data.alliance}")
            return {"ok": False, "message": "Invalid alliance"}

def update_phase():
    global current_phase, match_time, auto_ended
    if match_time > 140:
        current_phase = "Auto"
    elif match_time > 130:
        if not auto_ended:
            announce_auto_winner()
            auto_ended = True
        current_phase = "Transition"
    elif match_time > 105:
        current_phase = "Shift 1"
    elif match_time > 80:
        current_phase = "Shift 2"
    elif match_time > 55:
        current_phase = "Shift 3"
    elif match_time > 30:
        current_phase = "Shift 4"
    else:
        current_phase = "Endgame"

def announce_auto_winner():
    global red_score, blue_score, inactive_first
    with lock:
        if red_score > blue_score:
            inactive_first = "Red"
            print(f"Red wins auto {red_score} - {blue_score}")
        elif blue_score > red_score:
            inactive_first = "Blue"
            print(f"Blue wins auto {red_score} - {blue_score}")
        else:
            inactive_first = random.choice(["Red", "Blue"])
            print(f"Auto is a tie {red_score} - {blue_score}, randomly choosing {inactive_first} to be inactive first")

def is_alliance_active(alliance: str) -> bool:
    if inactive_first == "":
        return True
    if alliance.lower() == inactive_first.lower():
        return current_phase in ["Auto", "Transition", "Shift 2", "Shift 4", "Endgame"]
    else:
        return current_phase in ["Auto", "Transition", "Shift 1", "Shift 3", "Endgame"]
    
def update_time_until_phase_change():
    global time_until_phase_change
    
    if (current_phase == "Auto"):
        time_until_phase_change = match_time - 140
    elif (current_phase == "Transition"):
        time_until_phase_change = match_time - 130
    elif (current_phase == "Shift 1"):
        time_until_phase_change = match_time - 105
    elif (current_phase == "Shift 2"):
        time_until_phase_change = match_time - 80
    elif (current_phase == "Shift 3"):
        time_until_phase_change = match_time - 55
    elif (current_phase == "Shift 4"):
        time_until_phase_change = match_time - 30
    elif (current_phase == "Endgame"):
        time_until_phase_change = match_time