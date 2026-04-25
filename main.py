import asyncio
import socket
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
import threading
import random

class ScoreData(BaseModel):
    identifier: str
    token: str
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
current_phase = "Waiting"
inactive_first = ""
auto_ended = False
counting_down = True
waiting_for_scorekeepers = True
connected_scorekeepers = []
batched_score = -1

red_scored_auto = 0
blue_scored_auto = 0
red_scored_teleop = 0
blue_scored_teleop = 0

tui_ready = False

DESIRED_SCOREKEEPERS = 1

async def update_match_time():
    global match_time, current_phase, counting_down, waiting_for_scorekeepers

    while (waiting_for_scorekeepers or not tui_ready):
        await asyncio.sleep(1)

        if (len(connected_scorekeepers) == DESIRED_SCOREKEEPERS):
            waiting_for_scorekeepers = False

    waiting_for_scorekeepers = False
    counting_down = True

    for i in range(5):
        print(f"Match starts in {5 - i} seconds...")
        await asyncio.sleep(1)

    counting_down = False

    current_phase = "Auto"

    while match_time > 0:
        await asyncio.sleep(1)
        match_time -= 1
        update_phase()

        if (match_time == 140):
            print("Auto phase ended")

            current_phase = "Intermission"

            for i in range(3):
                print(f"Transition starts in {3 - i} seconds...")
                await asyncio.sleep(1)

    if match_time == 0:
        print("Match ended")
        current_phase = "Match Ended"

        print(f"Final Score: Red {red_score} - Blue {blue_score}")

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

@app.get("/")
def read_root():
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
        "batched_score": batched_score
        }

@app.post("/tui")
def post_tui_ready():
    global tui_ready
    tui_ready = True

@app.post("/", status_code=201)
def change_score(data: ScoreData):
    response = update_score(data)
    
    if (response["ok"] == True):
        return {"message": response["message"]}
    else:
        return HTTPException(404, response["message"])

def update_score(data: ScoreData) -> dict:
    global red_score, blue_score, red_wasted, blue_wasted, batched_score
    
    batched_score = data.count

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