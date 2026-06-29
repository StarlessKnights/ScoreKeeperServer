import asyncio
from typing import Any

from server.match_controller import MatchController


class ScoreProtocol(asyncio.DatagramProtocol):
    def __init__(self, match_controller: MatchController) -> None:
        super().__init__()

        self.match_controller = match_controller

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        print("UDP score server started")

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        msg = data.decode()

        try:
            identifier, alliance, score_str = msg.split("|")
        except:
            print(f"Received malformed message from {addr}: {msg}")
            return

        self.match_controller.update_score(alliance, int(score_str))
        asyncio.create_task(self.match_controller.broadcast_state())

        print(
            f"Received score update from {addr}: {alliance} scored {score_str} points"
        )

        ack = f"ACK|{identifier}"
        self.transport.sendto(ack.encode(), addr)
