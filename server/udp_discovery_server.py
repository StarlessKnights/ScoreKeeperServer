import asyncio
from typing import Any

from server.match_controller import MatchController

class DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, match_controller: MatchController) -> None:
        super().__init__()
        
        self.match_controller = match_controller

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        print("UDP discovery server started")
        
    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        msg = data.decode()
        
        if msg == "DISCOVER":
            self.transport.sendto("HERE".encode(), addr)
            
            with self.match_controller.state.lock:
                if addr not in self.match_controller.state.game_state.connected_scorekeepers:
                    self.match_controller.state.game_state.connected_scorekeepers.append(addr)
                    _ = asyncio.create_task(self.match_controller.broadcast_state())