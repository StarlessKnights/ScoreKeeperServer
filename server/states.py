from dataclasses import dataclass, field
import threading
from fastapi import WebSocket
import asyncio

@dataclass
class GameState:
    red_score: int = 0
    blue_score: int = 0
    red_wasted: int = 0
    blue_wasted: int = 0
    
    inactive_first: str = ""
    red_active: bool = True
    blue_active: bool = True
    
    current_phase: str = "Waiting"
    
    match_time: int = 160
    time_until_phase_change: int = 0
    
    connected_scorekeepers: list = field(default_factory=list)
    waiting_for_scorekeepers: bool = True
    
@dataclass
class ServerState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    
    game_state: GameState = field(default_factory=GameState)
    
    red_scored_auto: int = 0
    blue_scored_auto: int = 0
    
    red_scored_teleop: int = 0
    blue_scored_teleop: int = 0
    
    display_ready: bool = False
    
    auto_ended: bool = False
    intermission_ended: bool = False
    
    ws_clients: set[WebSocket] = field(default_factory=set)
    ws_clients_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
