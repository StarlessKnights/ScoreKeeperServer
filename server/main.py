import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from server.match_controller import MatchController
from server.udp_discovery_server import DiscoveryProtocol
from server.udp_score_server import ScoreProtocol

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(udp_discovery_server())
    asyncio.create_task(udp_score_server())
    asyncio.create_task(update_match_time())
    yield

app = FastAPI(lifespan=lifespan)
match_controller = MatchController()

async def udp_discovery_server():
    loop = asyncio.get_running_loop()
    
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: DiscoveryProtocol(match_controller=match_controller),
        local_addr=('0.0.0.0', 4211)
    )
    
    return transport, protocol
                    
async def udp_score_server():
    loop = asyncio.get_running_loop()
    
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: ScoreProtocol(match_controller=match_controller),
        local_addr=('0.0.0.0', 4212)
    )

    return transport, protocol

async def update_match_time():
    await match_controller.update_match_time()

@app.get("/")
def read_root():
    return match_controller.get_game_state().__dict__.copy()

@app.post("/tui")
async def post_tui_ready():
    with match_controller.state.lock:
        match_controller.state.display_ready = True
        
    await match_controller.broadcast_state()
    
    return {"message": "display readiness confirmed"}

@app.websocket("/ws")
async def websocket_state(websocket: WebSocket):
    await websocket.accept()
    try:
        async with match_controller.state.ws_clients_lock:
            match_controller.state.ws_clients.add(websocket)
            
        await websocket.send_json(match_controller.get_game_state().__dict__.copy())

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with match_controller.state.ws_clients_lock:
            match_controller.state.ws_clients.discard(websocket)
        
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)