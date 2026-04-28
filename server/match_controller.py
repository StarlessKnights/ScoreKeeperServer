from server.states import ServerState, GameState
from server.config import Config
import asyncio
import time
import random

class MatchController:
    def __init__(self):
        self.state = ServerState()
        self.config = Config()
        
    def get_game_state(self) -> GameState:
        return self.state.game_state
    
    def update_score(self, alliance: str, points: int):
        with self.state.lock:
            current_phase = self.state.game_state.current_phase
            
            if (current_phase == "Waiting" or current_phase == "Intermission"):
                return
            
            if alliance == "red":
                if self.is_alliance_active("red"):
                    self.state.game_state.red_score += points
                    
                    if current_phase == "Auto":
                        self.state.red_scored_auto += points
                    else:
                        self.state.red_scored_teleop += points
                else:
                    self.state.game_state.red_wasted += points
                    
                return
            
            if alliance == "blue":
                if self.is_alliance_active("blue"):
                    self.state.game_state.blue_score += points
                    
                    if current_phase == "Auto":
                        self.state.blue_scored_auto += points
                    else:
                        self.state.blue_scored_teleop += points
                else:
                    self.state.game_state.blue_wasted += points
                    
                return
                
    def is_alliance_active(self, alliance: str) -> bool:
        current_phase = self.state.game_state.current_phase
        inactive_first = self.state.game_state.inactive_first
        
        if inactive_first == "":
            return True
        
        if alliance == inactive_first:
            return current_phase in ["Auto", "Transition", "Shift 2", "Shift 4", "Endgame"]
        else:
            return current_phase in ["Auto", "Transition", "Shift 1", "Shift 3", "Endgame"]
        
    def update_phase(self):
        match_time = self.state.game_state.match_time

        if match_time > 140:
            phase = "Auto"
        elif match_time > 130:
            if not self.state.auto_ended:
                self.announce_auto_winner()
                self.state.auto_ended = True
                
            phase = "Transition"
        elif match_time > 105:
            phase = "Shift 1"
        elif match_time > 80:
            phase = "Shift 2"
        elif match_time > 55:
            phase = "Shift 3"
        elif match_time > 30:
            phase = "Shift 4"
        else:
            phase = "Endgame"

        self.state.game_state.current_phase = phase
        
        self.update_alliance_active()

    def announce_auto_winner(self):
        red_auto = self.state.red_scored_auto
        blue_auto = self.state.blue_scored_auto
        
        if red_auto > blue_auto:
            self.state.game_state.inactive_first = "blue"
        elif blue_auto > red_auto:
            self.state.game_state.inactive_first = "red"
        else:
            self.state.game_state.inactive_first = random.choice(["red", "blue"])
            
    def update_time_until_phase_change(self):
        current_phase = self.state.game_state.current_phase
        match_time = self.state.game_state.match_time
        
        if (current_phase == "Auto"):
            self.state.game_state.time_until_phase_change = match_time - 140
        elif (current_phase == "Transition"):
            self.state.game_state.time_until_phase_change = match_time - 130
        elif (current_phase == "Shift 1"):
            self.state.game_state.time_until_phase_change = match_time - 105
        elif (current_phase == "Shift 2"):
            self.state.game_state.time_until_phase_change = match_time - 80
        elif (current_phase == "Shift 3"):
            self.state.game_state.time_until_phase_change = match_time - 55
        elif (current_phase == "Shift 4"):
            self.state.game_state.time_until_phase_change = match_time - 30
        elif (current_phase == "Endgame"):
            self.state.game_state.time_until_phase_change = match_time
            
    def update_alliance_active(self):
        self.state.game_state.red_active = self.is_alliance_active("red")
        self.state.game_state.blue_active = self.is_alliance_active("blue")
            
    async def broadcast_state(self):
        with self.state.lock:
            payload = self.get_game_state().__dict__.copy()

        async with self.state.ws_clients_lock:
            clients = list(self.state.ws_clients)

        stale_clients = []
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:
                stale_clients.append(client)

        if stale_clients:
            async with self.state.ws_clients_lock:
                for client in stale_clients:
                    self.state.ws_clients.discard(client)

    async def update_match_time(self):
        while True:
            with self.state.lock:
                if (
                    len(self.state.game_state.connected_scorekeepers)
                    == self.config.desired_scorekeepers
                ):
                    self.state.game_state.waiting_for_scorekeepers = False

                waiting_for_scorekeepers = self.state.game_state.waiting_for_scorekeepers
                display_ready = self.state.display_ready

            if not (waiting_for_scorekeepers or not display_ready):
                break

            await asyncio.sleep(0.1)

        with self.state.lock:
            self.state.game_state.current_phase = "Auto"
            self.state.auto_ended = False
            self.state.intermission_ended = False

        next_match_tick = time.monotonic() + 1.0

        await self.broadcast_state()

        while True:
            with self.state.lock:
                current_match_time = self.state.game_state.match_time

            if current_match_time <= 0:
                break

            sleep_for = next_match_tick - time.monotonic()

            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            else:
                next_match_tick = time.monotonic()

            intermission_started = False
            with self.state.lock:
                self.state.game_state.match_time = max(0, self.state.game_state.match_time - 1)

                self.update_phase()
                self.update_time_until_phase_change()
                self.update_alliance_active()

                if (
                    self.state.game_state.match_time == 140
                    and not self.state.intermission_ended
                ):
                    self.state.game_state.current_phase = "Intermission"
                    self.state.game_state.time_until_phase_change = 0
                    self.state.intermission_ended = True
                    intermission_started = True
                
            await self.broadcast_state()

            if intermission_started:
                transition_end = time.monotonic() + 3.0

                while time.monotonic() < transition_end:
                    await asyncio.sleep(0.1)

                with self.state.lock:
                    self.update_phase()
                    self.update_time_until_phase_change()

                await self.broadcast_state()

                next_match_tick = time.monotonic() + 1.0
                continue

            next_match_tick += 1.0

            await self.broadcast_state()

        with self.state.lock:
            self.state.game_state.current_phase = "Match Ended"
            self.state.game_state.time_until_phase_change = 0
            
            self.update_alliance_active()

        await self.broadcast_state()
                