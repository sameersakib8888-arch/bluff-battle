# Publish BLUFF BATTLE on Render

This project is a Python HTTP + WebSocket web service. **Do not deploy it as a static website** (GitHub Pages or a static-only hosting service), because players need to share a live server.

## Browser-only publish method

1. Sign in to [GitHub](https://github.com/) and [Render](https://dashboard.render.com/).
2. Extract `bluff-battle-public-ready.zip`. On GitHub, create a repository called `bluff-battle` (private or public).
3. In your repository, choose **Add file > Upload files**. Upload the *contents* of the extracted ZIP, including `server.py`, `questions.py`, `requirements.txt`, `render.yaml`, and the `static/` folder. Commit the files to the repository's **root**. Do not upload the ZIP by itself or nest everything under a second `bluff-battle/` directory.
4. In Render, choose **New > Blueprint**. If prompted, authorize Render to access that GitHub repository. Pick `bluff-battle`, keep the Blueprint path as `render.yaml`, review, and choose **Deploy Blueprint**.
5. After the service shows **Live**, copy its actual `https://....onrender.com` URL from your Render dashboard. The subdomain might not be exactly `bluff-battle`.
6. Open the deployed site. Create a room on your computer, then open the **public URL** on a second device (preferably using mobile data) and join using the six-character code or invitation link.
7. Optionally, add a custom domain in your Render service's **Settings > Custom Domains** and follow Render's DNS instructions.

## Deployment settings already configured

The repository contains `render.yaml` with:
- A **Free** Python web service in Singapore (change region in `render.yaml` before first deploy if desired)
- Python 3.13.5
- Build command: `pip install -r requirements.txt`
- Start command: `python server.py`
- Health check: `/health`
- A single process with rooms held in memory

The game listens on the `PORT` provided by Render (or 8080 locally). The frontend uses the secure `wss://` WebSocket protocol automatically over HTTPS.

## Verify the live game

- `https://YOUR-ACTUAL-RENDER-URL/` should open the game.
- `https://YOUR-ACTUAL-RENDER-URL/health` should return JSON containing `"ok": true`.
- Create a room on one device and join from another with the code. Start the round; confirm synchronized questions, voting, and score reveal.

## Important limitations

**Free-plan cold starts:** Render spins down inactive Free web services after 15 minutes; waking one can take about a minute.

**Temporary rooms:** Rooms, scores, and player sessions are stored **only in server memory**. A service restart, redeploy, or spin-down clears them. Do not scale beyond one process/instance unless you implement shared state and messaging.

**Public use and abuse:** Room codes do not provide user accounts or strong access controls. Before high-volume public promotion, add rate limiting, abuse detection, persistent shared state, and operational monitoring.

**Costs:** This Blueprint requests Render's Free instance plan. Review service settings and the provider's current pricing before choosing any paid options.

**Troubleshooting:** If clients can't connect, check the service's Render Logs. Confirm you created a **Web Service** (not a Static Site), `python server.py` is the start command, and `/health` is accessible.

Official documentation:
- https://render.com/docs/infrastructure-as-code
- https://render.com/docs/blueprint-spec
- https://render.com/docs/web-services
- https://render.com/docs/free