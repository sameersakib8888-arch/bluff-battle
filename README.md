# BLUFF BATTLE 🎭

A genuinely networked, real-time party game for **2–8 players** using browser-based room codes. Players join from separate devices; the Python WebSocket server owns the room, the clock, the true answers, ballots, and scoring.

## Run locally

Requires **Python 3.10+**.

```bash
pip install -r requirements.txt
python server.py
```

Open **http://localhost:8080**. One person selects **Create a room** and shares its six-character code or invite link. Other players select **Join a room** on their own device. For local Wi-Fi play, open `http://<your-computer-LAN-IP>:8080` on each device (allow the port through your computer's firewall).

For online play across different networks, **deploy the server to a public HTTPS host**. The source code itself is not a hosted public game. See [Deployment](#deployment).

## Rules

- Exactly **8 rounds** per match; **2–8 players**; host presses Start.
- Bluff phase lasts **up to 35 seconds**. Players secretly submit a believable fake answer to a factual trivia question.
- Voting phase lasts **up to 25 seconds**. Each player selects one option from the shuffled real answer and player-authored bluffs. You cannot choose your own bluff.
- **+1,000** for voting for the real answer. **+500** for each opponent who votes for your bluff; both scoring methods stack. Wrong votes, missing submissions, and game-supplied decoys earn zero.
- To keep the voting fun with 2–3 people, the server adds unattributed fake answers until at least four choices exist. An answer matching the truth or another bluff is replaced by a curated, incorrect decoy and remains credited to the submitting player.
- The bluff and vote stages end as soon as all *currently connected* players have submitted (after a 1.5-second grace period) or when their stated time limit expires, whichever comes first.
- A **7-second reveal** and **5-second leaderboard** automatically precede the next round.
- The highest score after eight rounds wins; equal first-place scores are joint winners.
- The host can start a rematch. On disconnect, host privileges transfer to the first connected player. Rejoining with the same browser restores the player's slot and score.

## Project files

- `server.py` — HTTP and WebSocket server; private room management, server clock, authoritative submissions/votes/scoring, reconnect support, phase transitions.
- `questions.py` — 32 curated real-answer prompts with decoys.
- `static/index.html` — accessible single-page game shell.
- `static/style.css` — responsive game-show design.
- `static/app.js` — browser WebSocket client, state-based views, locally animated countdowns.
- `tests/test_game.py` — server and two-device integration tests.
- `Dockerfile`, `render.yaml`, `Procfile` — hosting support.

## Deployment

### Render (one instance)

1. Upload the project to a GitHub repository (the contents of the project directory, not a parent directory).
2. In [Render](https://render.com), create a **Web Service** linked to the repository, or use the included `render.yaml` Blueprint.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `python server.py`.
5. Open your deployment's HTTPS URL and share that URL with friends. Secure WebSocket connections (`wss://`) are used automatically.

### Docker (other hosts)

```bash
docker build -t bluff-battle .
docker run -p 8080:8080 --name bluff-battle bluff-battle
```

Your host must support long-lived WebSocket connections. Run **one server process/instance** because rooms live in process memory; do **not** enable multiple workers or autoscale to multiple replicas without first adding a shared state store and cross-instance event fan-out. Idle/empty rooms expire after six hours. A restart loses current rooms; this is a simple game-night service, not a database-backed production system. Protect public deployments with common web protections (rate limiting, abuse prevention) if you expect significant traffic.

### Environment configuration

| Variable | Default | Meaning |
|---|---:|---|
| `PORT` | `8080` | HTTP and WebSocket port |
| `BLUFF_SECONDS` | `35` | Maximum bluff phase length |
| `VOTE_SECONDS` | `25` | Maximum vote phase length |
| `REVEAL_SECONDS` | `7` | Reveal view time |
| `SCORES_SECONDS` | `5` | Leaderboard view time |

The match remains eight rounds under all configurations. Adjust timers only for testing or for a future custom-game mode.

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

The automated integration test creates a host and guest on **different WebSocket connections**, runs the round, validates a correct vote, tests a vote on an authored bluff, and checks host transfer / reconnect. It uses short test-only timers.