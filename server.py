"""BLUFF BATTLE — authoritative, room-based WebSocket multiplayer server.

Run: python server.py
Requires: aiohttp (see requirements.txt).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import WSMsgType, web

from questions import QUESTIONS

TOTAL_ROUNDS = 8
BLUFF_SECONDS = float(os.getenv("BLUFF_SECONDS", "35"))
VOTE_SECONDS = float(os.getenv("VOTE_SECONDS", "25"))
REVEAL_SECONDS = float(os.getenv("REVEAL_SECONDS", "7"))
SCORES_SECONDS = float(os.getenv("SCORES_SECONDS", "5"))
MAX_ROOMS = 1000
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
STATIC = Path(__file__).resolve().parent / "static"


def normalized(value: str) -> str:
    return re.sub(r"[^\w\d]+", "", value.casefold().strip(), flags=re.UNICODE)


def clipped(value: object, size: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:size]


@dataclass
class Player:
    id: str
    token: str
    name: str
    host: bool = False
    score: int = 0
    connected: bool = False
    ws: web.WebSocketResponse | None = None
    bluff: str | None = None
    vote_id: str | None = None
    earned: int = 0


@dataclass
class Room:
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    phase: str = "lobby"
    round_idx: int = -1
    deck: list[dict] = field(default_factory=list)
    options: list[dict] = field(default_factory=list)
    deadline: float | None = None
    touched: float = field(default_factory=time.monotonic)

    @property
    def question(self) -> dict | None:
        return self.deck[self.round_idx] if self.round_idx >= 0 else None

    def current_connected(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]

    def touch(self) -> None:
        self.touched = time.monotonic()

    def set_phase(self, phase: str, seconds: float | None) -> None:
        self.phase = phase
        self.deadline = time.monotonic() + seconds if seconds is not None else None
        self.touch()

    def start_game(self) -> None:
        if self.phase not in {"lobby", "finished"}:
            raise ValueError("A game is already in progress.")
        if len(self.current_connected()) < 2:
            raise ValueError("At least two connected players are needed to start.")
        for p in self.players.values():
            p.score = p.earned = 0
            p.bluff = p.vote_id = None
        self.deck = random.sample(QUESTIONS, TOTAL_ROUNDS)
        self.round_idx = 0
        self.start_bluff()

    def start_bluff(self) -> None:
        for p in self.players.values():
            p.bluff = None
            p.vote_id = None
            p.earned = 0
        self.options = []
        self.set_phase("bluff", BLUFF_SECONDS)

    def submit_bluff(self, player: Player, answer: object) -> None:
        if self.phase != "bluff":
            raise ValueError("The bluffing phase has ended.")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ValueError("Time is up for bluffs.")
        if player.bluff is not None:
            raise ValueError("You already submitted your bluff.")
        answer = clipped(answer, 70)
        if len(answer) < 2:
            raise ValueError("Enter a bluff with at least 2 characters.")
        player.bluff = answer
        self.touch()
        self.shorten_when_ready("bluff")

    def submit_vote(self, player: Player, option_id: object) -> None:
        if self.phase != "vote":
            raise ValueError("Voting is not open.")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ValueError("Time is up for voting.")
        if player.vote_id is not None:
            raise ValueError("You already voted.")
        option = next((o for o in self.options if o["id"] == option_id), None)
        if option is None:
            raise ValueError("That option is not available.")
        if option["owner"] == player.id:
            raise ValueError("You cannot vote for your own bluff.")
        player.vote_id = option["id"]
        self.touch()
        self.shorten_when_ready("vote")

    def shorten_when_ready(self, phase: str) -> None:
        online = self.current_connected()
        if not online or self.deadline is None:
            return
        complete = all((p.bluff is not None if phase == "bluff" else p.vote_id is not None) for p in online)
        if complete:
            self.deadline = min(self.deadline, time.monotonic() + 1.5)

    def make_options(self) -> None:
        q = self.question
        assert q is not None
        taken = {normalized(q["answer"])}
        opts = [{"id": secrets.token_urlsafe(10), "text": q["answer"], "owner": None, "correct": True}]
        backup = list(q["decoys"])
        random.shuffle(backup)

        def fresh_decoy() -> str:
            while backup:
                choice = backup.pop()
                key = normalized(choice)
                if key and key not in taken:
                    taken.add(key)
                    return choice
            raise RuntimeError("Not enough distinct prepared decoys for this prompt.")

        for player in self.players.values():
            if player.bluff is None:
                continue
            answer = player.bluff
            if normalized(answer) in taken:
                answer = fresh_decoy()
            else:
                taken.add(normalized(answer))
            opts.append({"id": secrets.token_urlsafe(10), "text": answer, "owner": player.id, "correct": False})

        while len(opts) < 4:
            opts.append({"id": secrets.token_urlsafe(10), "text": fresh_decoy(), "owner": None, "correct": False})

        random.shuffle(opts)
        self.options = opts

    def resolve_round(self) -> None:
        by_id = {o["id"]: o for o in self.options}
        for p in self.players.values():
            p.earned = 0
        for voter in self.players.values():
            choice = by_id.get(voter.vote_id)
            if choice is None:
                continue
            if choice["correct"]:
                voter.earned += 1000
            elif choice["owner"] is not None:
                owner = self.players[choice["owner"]]
                owner.earned += 500
        for p in self.players.values():
            p.score += p.earned

    def advance_if_due(self) -> bool:
        if self.deadline is None or time.monotonic() < self.deadline:
            return False
        if self.phase == "bluff":
            self.make_options()
            self.set_phase("vote", VOTE_SECONDS)
        elif self.phase == "vote":
            self.resolve_round()
            self.set_phase("reveal", REVEAL_SECONDS)
        elif self.phase == "reveal":
            self.set_phase("scores", SCORES_SECONDS)
        elif self.phase == "scores":
            if self.round_idx + 1 >= TOTAL_ROUNDS:
                self.set_phase("finished", None)
            else:
                self.round_idx += 1
                self.start_bluff()
        else:
            return False
        return True

    def snapshot(self, viewer: Player) -> dict:
        now = time.monotonic()
        show_question = self.phase in {"bluff", "vote", "reveal", "scores"}
        round_players = list(self.players.values())
        state = {
            "type": "state",
            "code": self.code,
            "phase": self.phase,
            "round": self.round_idx + 1 if self.round_idx >= 0 else 0,
            "totalRounds": TOTAL_ROUNDS,
            "remainingMs": max(0, round((self.deadline - now) * 1000)) if self.deadline else None,
            "question": self.question["question"] if show_question else None,
            "players": [
                {"id": p.id, "name": p.name, "score": p.score, "host": p.host,
                 "connected": p.connected, "submitted": p.bluff is not None, "voted": p.vote_id is not None,
                 "earned": p.earned if self.phase in {"reveal", "scores", "finished"} else None}
                for p in round_players
            ],
            "you": {
                "id": viewer.id, "name": viewer.name, "host": viewer.host,
                "score": viewer.score, "submitted": viewer.bluff is not None,
                "voted": viewer.vote_id is not None, "bluff": viewer.bluff,
                "voteId": viewer.vote_id, "earned": viewer.earned,
            },
            "answers": [],
        }
        if self.phase in {"vote", "reveal", "scores"}:
            revealing = self.phase in {"reveal", "scores"}
            state["answers"] = [
                {"id": o["id"], "text": o["text"], "mine": o["owner"] == viewer.id,
                 **({"correct": o["correct"],
                     "author": self.players[o["owner"]].name if o["owner"] else ("The truth" if o["correct"] else "Game decoy"),
                     "voters": [p.name for p in round_players if p.vote_id == o["id"]],
                     "votes": sum(1 for p in round_players if p.vote_id == o["id"])} if revealing else {})}
                for o in self.options
            ]
        return state


class GameService:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def new_room(self, name: str) -> tuple[Room, Player]:
        if len(self.rooms) >= MAX_ROOMS:
            raise ValueError("Too many rooms are active. Please try again later.")
        for _ in range(100):
            code = "".join(secrets.choice(ALPHABET) for _ in range(6))
            if code not in self.rooms:
                break
        else:
            raise RuntimeError("Could not allocate a unique room code")
        room = Room(code)
        player = self.new_player(name, host=True)
        room.players[player.id] = player
        self.rooms[code] = room
        return room, player

    @staticmethod
    def new_player(name: str, host: bool = False) -> Player:
        return Player(id=secrets.token_urlsafe(9), token=secrets.token_urlsafe(28), name=name, host=host)

    def join_room(self, code: str, name: str | None = None, token: str | None = None) -> tuple[Room, Player]:
        room = self.rooms.get(code.upper())
        if room is None:
            raise ValueError("Room not found. Check the six-character code.")
        if token:
            for p in room.players.values():
                if secrets.compare_digest(p.token, token):
                    return room, p
            raise ValueError("Your previous session is no longer available.")
        if room.phase != "lobby":
            raise ValueError("This match has already started. Ask the host to create a new room.")
        if len(room.players) >= 8:
            raise ValueError("This room is full (8 players maximum).")
        if name is None:
            raise ValueError("Enter a nickname to join.")
        if any(p.name.casefold() == name.casefold() for p in room.players.values()):
            raise ValueError("That nickname is taken in this room.")
        player = self.new_player(name)
        room.players[player.id] = player
        room.touch()
        return room, player

    @staticmethod
    def repair_host(room: Room) -> None:
        if any(p.connected and p.host for p in room.players.values()):
            return
        for p in room.players.values():
            p.host = False
        online = room.current_connected()
        if online:
            online[0].host = True

    @staticmethod
    async def broadcast(room: Room) -> None:
        for player in room.players.values():
            if player.connected and player.ws and not player.ws.closed:
                try:
                    await player.ws.send_json(room.snapshot(player))
                except (ConnectionError, RuntimeError):
                    pass


SERVICE = GameService()


async def send_error(ws: web.WebSocketResponse, error: Exception | str) -> None:
    await ws.send_json({"type": "error", "message": str(error)})


async def index_handler(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "activeRooms": len(SERVICE.rooms)})


async def socket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=25, max_msg_size=4096)
    await ws.prepare(request)
    room: Room | None = None
    player: Player | None = None
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
                if not isinstance(data, dict):
                    raise ValueError("Invalid message.")
                action = data.get("type")
                if action in {"create", "join", "resume"}:
                    if room is not None:
                        raise ValueError("You are already in a room.")
                    if action == "create":
                        name = clipped(data.get("name"), 18)
                        if len(name) < 2:
                            raise ValueError("Nickname must be at least 2 characters.")
                        room, player = SERVICE.new_room(name)
                    else:
                        code = clipped(data.get("code"), 6).upper()
                        if len(code) != 6:
                            raise ValueError("Enter a valid six-character room code.")
                        token = data.get("token") if action == "resume" else None
                        name = clipped(data.get("name"), 18) if action == "join" else None
                        if action == "join" and len(name or "") < 2:
                            raise ValueError("Nickname must be at least 2 characters.")
                        room, player = SERVICE.join_room(code, name, token)
                    old_ws = player.ws
                    # Claim the session before closing the older connection: its
                    # disconnect callback must not remove the newly attached player.
                    player.ws = ws
                    player.connected = True
                    if old_ws and old_ws is not ws and not old_ws.closed:
                        await old_ws.close(code=1000, message=b"Rejoined from another tab")
                    SERVICE.repair_host(room)
                    room.touch()
                    await ws.send_json({"type": "joined", "code": room.code,
                                        "token": player.token, "playerId": player.id})
                    await SERVICE.broadcast(room)
                elif action == "ping":
                    await ws.send_json({"type": "pong"})
                else:
                    if room is None or player is None:
                        raise ValueError("Join a room first.")
                    if action == "start" or action == "rematch":
                        if not player.host:
                            raise ValueError("Only the host can start a match.")
                        room.start_game()
                    elif action == "bluff":
                        room.submit_bluff(player, data.get("answer"))
                    elif action == "vote":
                        room.submit_vote(player, data.get("optionId"))
                    elif action == "leave":
                        if room.phase == "lobby":
                            room.players.pop(player.id, None)
                        else:
                            player.connected = False
                        room.touch()
                        SERVICE.repair_host(room)
                        await SERVICE.broadcast(room)
                        room = player = None
                        await ws.send_json({"type": "left"})
                        continue
                    else:
                        raise ValueError("Unknown action.")
                    await SERVICE.broadcast(room)
            except (ValueError, TypeError, json.JSONDecodeError) as e:
                await send_error(ws, e)
    finally:
        if room is not None and player is not None and player.ws is ws:
            player.connected = False
            player.ws = None
            if room.phase == "lobby":
                room.players.pop(player.id, None)
            SERVICE.repair_host(room)
            room.touch()
            await SERVICE.broadcast(room)
    return ws


async def ticker(app: web.Application) -> None:
    while True:
        await asyncio.sleep(0.2)
        now = time.monotonic()
        for code, room in list(SERVICE.rooms.items()):
            if now - room.touched > 6 * 60 * 60 and not room.current_connected():
                SERVICE.rooms.pop(code, None)
                continue
            if room.advance_if_due():
                await SERVICE.broadcast(room)


async def background(app: web.Application):
    task = asyncio.create_task(ticker(app))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> web.Application:
    app = web.Application(client_max_size=4096)
    app.router.add_get("/", index_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ws", socket_handler)
    app.router.add_static("/assets", STATIC, show_index=False)
    app.cleanup_ctx.append(background)
    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    print(f"BLUFF BATTLE listening on http://0.0.0.0:{port}")
    web.run_app(create_app(), host="0.0.0.0", port=port, access_log=None)
