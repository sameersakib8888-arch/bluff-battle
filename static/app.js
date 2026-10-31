(() => {
  'use strict';

  const root = document.querySelector('#app');
  const liveDot = document.querySelector('#liveDot');
  const connectionLabel = document.querySelector('#connectionLabel');
  const connectionBanner = document.querySelector('#connectionBanner');
  const dialog = document.querySelector('#rulesDialog');
  const letters = 'ABCDEFGH';
  const queryRoom = new URLSearchParams(location.search).get('room')?.replace(/[^a-z0-9]/gi, '').slice(0, 6).toUpperCase() || '';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const format = value => Number(value || 0).toLocaleString('en-US');
  const readLocal = key => { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } };
  const saveLocal = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };
  const deleteLocal = key => { try { localStorage.removeItem(key); } catch {} };

  let socket, connected = false, game = null;
  let session = readLocal('bluff_battle_session');
  let shouldResume = !!session && (!queryRoom || session.code === queryRoom);
  let reconnectDelay = 1000, reconnectTimer = null, lastKey = '';
  let joinMode = queryRoom ? 'join' : 'create';
  let displayName = readLocal('bluff_battle_name') || '';
  let codeDraft = queryRoom;
  let bluffDraft = '';
  let lastRound = -1;
  let timeReceivedAt = Date.now(), lastRemaining = null;
  let toastTimeout;

  function toast(message) {
    const elem = document.querySelector('#toast');
    elem.textContent = message;
    elem.classList.add('show');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => elem.classList.remove('show'), 3500);
  }

  function send(data) {
    if (!connected || socket.readyState !== WebSocket.OPEN) {
      toast('Reconnecting. Please try again in a moment.');
      return false;
    }
    socket.send(JSON.stringify(data));
    return true;
  }

  function connect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${protocol}//${location.host}/ws`);
    socket.onopen = () => {
      connected = true;
      reconnectDelay = 1000;
      setConnectionUI();
      if (shouldResume && session) {
        send({type: 'resume', code: session.code, token: session.token});
      }
    };
    socket.onmessage = ({data}) => {
      let msg;
      try { msg = JSON.parse(data); } catch { return; }
      if (msg.type === 'joined') {
        session = {code: msg.code, token: msg.token};
        saveLocal('bluff_battle_session', session);
        shouldResume = true;
        if (location.search !== `?room=${msg.code}`) history.replaceState({}, '', `?room=${msg.code}`);
        lastKey = '';
      } else if (msg.type === 'state') {
        if (msg.round !== lastRound) {
          bluffDraft = '';
          lastRound = msg.round;
        }
        game = msg;
        lastRemaining = msg.remainingMs;
        timeReceivedAt = Date.now();
        render();
      } else if (msg.type === 'error') {
        toast(msg.message);
        if (/previous session|room not found/i.test(msg.message) && !game && shouldResume) {
          session = null;
          shouldResume = false;
          deleteLocal('bluff_battle_session');
          history.replaceState({}, '', '/');
          lastKey = '';
          render();
        }
      } else if (msg.type === 'left') {
        // The client resets state immediately after requesting leave.
      }
    };
    socket.onclose = () => {
      connected = false;
      setConnectionUI();
      reconnectTimer = setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(8000, reconnectDelay * 1.7);
    };
    socket.onerror = () => {};
  }

  function setConnectionUI() {
    liveDot.classList.toggle('online', connected);
    connectionLabel.textContent = connected ? 'SERVER ONLINE' : 'RECONNECTING';
    connectionBanner.classList.toggle('hidden', connected || !game);
  }

  function roomBar() {
    return `<div class="game-top"><div class="room-info">
        <span class="mini-label">ROOM CODE</span>
        <button class="room-code" data-action="copy-code" title="Copy room code">${esc(game.code)} <span style="font-size:15px;letter-spacing:0">⧉</span></button>
        <button class="text-btn" data-action="invite">Copy invite link ↗</button>
      </div><div class="room-info"><span class="room-stat">● <b>${game.players.filter(p=>p.connected).length}</b> / 8 online</span><span class="tag tag-purple">${game.you.host ? '★ YOU ARE HOST' : 'PLAYER'}</span></div></div>`;
  }

  function renderLanding() {
    return `<section class="landing"><div class="home-grid">
        <div class="hero-copy"><div class="eyebrow">THE ULTIMATE GAME NIGHT TEST</div>
          <h1 class="hero-title"><span>BLUFF</span><span class="title-bottom"><em>BATTLE.</em><span class="starburst" aria-hidden="true">✳</span></span></h1>
          <p class="hero-sub">Can you sell a convincing lie? <strong>Fool your friends, find the truth, and steal the spotlight.</strong> No downloads. No mercy.</p>
          <div class="feature-chips"><span class="chip"><b>●</b> LIVE MULTIPLAYER</span><span class="chip">◈ 2–8 PLAYERS</span><span class="chip">⚡ 8 ROUNDS</span></div>
          <div class="squiggle" aria-hidden="true"><div class="lie-card"><div class="lie-label">YOUR BLUFF</div><div class="lie-word">Totally true.</div></div><div class="truth-card"><div class="truth-eyebrow">ACTUALLY...</div><div class="truth-word">Gotcha! ✳</div></div></div>
        </div>
        <div class="join-panel"><div class="panel-intro"><span class="small-label">LET THE GAMES BEGIN</span><span class="star-icon">✳</span></div>
          <h2 class="join-title">Ready to get away with it?</h2><p class="join-description">Get your friends in a room and see who's the most convincing liar.</p>
          <div class="switch"><button type="button" class="${joinMode==='create'?'selected':''}" data-action="mode-create">CREATE A ROOM</button><button type="button" class="${joinMode==='join'?'selected':''}" data-action="mode-join">JOIN A ROOM</button></div>
          <form id="joinForm"><div class="form-field"><label for="nameInput" class="form-label">YOUR NICKNAME</label><input class="field" id="nameInput" type="text" maxlength="18" minlength="2" placeholder="e.g. The Bluff Master" autocomplete="nickname" required value="${esc(displayName)}" /></div>
          ${joinMode==='join' ? `<div class="form-field"><label for="codeInput" class="form-label">6-CHARACTER ROOM CODE</label><input class="field code-field" id="codeInput" type="text" maxlength="6" minlength="6" placeholder="ABC123" autocomplete="off" autocapitalize="characters" spellcheck="false" required value="${esc(codeDraft)}" /></div>` : ''}
          <button class="btn btn-primary btn-full" type="submit">${joinMode==='create'?'CREATE MY ROOM':'JOIN THE PARTY'} <span>↗</span></button></form>
          <p class="privacy-note">🔒 Private rooms · No account required · Browser-based</p>
        </div>
      </div><div class="how-bar"><div class="how-item"><span class="how-num">01.</span><div><strong>CREATE OR JOIN</strong><p>Share a room code with 2–8 friends.</p></div></div><div class="how-item"><span class="how-num">02.</span><div><strong>MAKE STUFF UP</strong><p>Write lies good enough to sound real.</p></div></div><div class="how-item"><span class="how-num">03.</span><div><strong>FOOL EVERYONE</strong><p>Guess the truth and cash in on bluffs.</p></div></div></div></section>`;
  }

  function avatar(p) { return `<span class="avatar">${esc((p.name || '?').slice(0, 1).toUpperCase())}</span>`; }
  function lobby() {
    const players = [...game.players];
    const seatHtml = Array.from({length:8}, (_, i) => {
      const p = players[i];
      if (!p) return `<div class="seat empty"><span class="empty-icon">+</span><div><div class="seat-name">Open seat</div><div class="seat-role">Waiting for player...</div></div></div>`;
      return `<div class="seat">${avatar(p)}<div style="min-width:0"><div class="seat-name">${esc(p.name)}${p.id===game.you.id?' (you)':''}</div><div class="seat-role">${p.host?'★ Party host':'Player'} ${p.connected?'· Online':'· Offline'}</div></div></div>`;
    }).join('');
    const onlineCount = players.filter(p=>p.connected).length;
    return `<section class="game-area">${roomBar()}
      <div class="eyebrow">WELCOME TO THE PARTY</div><h1 class="page-heading" style="margin-top:17px">The suspects<br><em>are gathering.</em></h1>
      <p class="page-lede">Invite your people. When everyone's here, the host starts eight rounds of glorious misinformation.</p>
      <div class="lobby-grid"><div class="game-card"><div class="section-head"><h3>THE GUEST LIST</h3><small>${onlineCount} / 8 joined</small></div><div class="seats">${seatHtml}</div></div>
      <div class="game-card"><div class="section-head"><h3>TONIGHT'S GAME</h3><span class="tag tag-pink">CLASSIC MODE</span></div>
      <div class="game-settings"><div class="setting-row"><span>Game mode</span><strong>Bluff & Deception</strong></div><div class="setting-row"><span>Total rounds</span><strong>08 Rounds</strong></div><div class="setting-row"><span>Bluffing time</span><strong>35 Seconds</strong></div><div class="setting-row"><span>Voting time</span><strong>25 Seconds</strong></div></div>
      <div class="score-pitch"><p>GET THE TRUTH RIGHT</p><strong>+1,000 pts</strong><small>PLUS +500 for every person who picks your lie.</small></div>
      <div class="host-actions">${game.you.host ? `<button class="btn btn-primary btn-full" data-action="start" ${onlineCount<2?'disabled':''}>START THE BATTLE <span>↗</span></button><p class="host-hint">${onlineCount<2?'You need at least one more player to begin.':'Everyone ready? Hit start when you are.'}</p>` : `<div class="waiting"><span class="pulse"></span>Waiting for the host to start…</div>`}
      <button class="btn btn-outline btn-full" style="margin-top:13px" data-action="leave">LEAVE ROOM</button></div></div></div>
      </section>`;
  }

  function progressHeader() {
    return `${roomBar()}<div class="round-progress">${Array.from({length:8},(_,i)=>`<span class="round-segment ${i<game.round-1?'done':i===game.round-1?'active':''}"></span>`).join('')}</div>`;
  }
  function roundHeader(eyebrow, title, description) {
    return `<div class="round-head"><div><div class="eyebrow">ROUND ${String(game.round).padStart(2,'0')} / 08 · ${eyebrow}</div><h1 class="round-heading">${title}</h1><p class="round-caption">${description}</p></div>
      <div class="timer"><span class="timer-title">TIME LEFT</span><span class="timer-value" id="timeValue">${Math.ceil((game.remainingMs||0)/1000)}s</span></div></div>`;
  }
  function question() {
    return `<section class="question-card"><span class="question-caption">✳ THE QUESTION</span><h2>${esc(game.question)}</h2></section>`;
  }
  function progressLine(phase) {
    const online = game.players.filter(p=>p.connected);
    const count = online.filter(p=>phase==='bluff'?p.submitted:p.voted).length;
    const label = phase==='bluff'?'bluffs submitted':'votes cast';
    return `<div class="progress-text"><span class="pulse"></span><span id="progressLabel">${count} of ${online.length} ${label}</span></div><div class="thin-track"><div class="thin-fill" id="submissionBar" style="width:${online.length ? 100*count/online.length : 0}%"></div></div>`;
  }
  function bluffPhase() {
    return `<section class="game-area">${progressHeader()}${roundHeader('MAKE IT BELIEVABLE','Invent a good lie.','Write an answer so believable your friends will fall for it.')}
      ${question()}<div class="action-card">${game.you.submitted ? `<div class="submitted-card"><div class="check-circle">✓</div><div><strong>Bluff locked in!</strong><p>“${esc(game.you.bluff)}”</p></div></div><p class="action-sub" style="margin:13px 0 0">Nice work. Wait for the other players or the timer to run out.</p>` : `<div class="action-title">YOUR FAKE ANSWER</div><p class="action-sub">Be crafty, not obvious. Don't enter the real answer—correct or duplicate bluffs will be swapped with a game decoy.</p><form id="bluffForm"><label for="bluffInput" class="mini-label" style="display:block;margin-bottom:10px">MAKE SOMETHING UP</label><textarea class="bluff-input" id="bluffInput" maxlength="70" minlength="2" placeholder="Type your most convincing lie..." required>${esc(bluffDraft)}</textarea><div class="action-bottom"><span class="counter"><span id="charsLeft">${70-bluffDraft.length}</span> characters remaining</span><button class="btn btn-primary" type="submit">LOCK IN MY BLUFF <span>↗</span></button></div></form>`}${progressLine('bluff')}</div>
    </section>`;
  }
  function votePhase() {
    const options = game.answers.map((o,i) => {
      const selected = game.you.voteId===o.id;
      return `<button class="vote-option ${o.mine?'is-mine':''} ${selected?'selected':''}" type="button" data-action="vote" data-id="${esc(o.id)}" ${game.you.voted||o.mine?'disabled':''}>
        <span class="option-letter">${letters[i]}</span><span><span class="option-name">${esc(o.text)}</span><span class="option-desc">${o.mine?'YOUR BLUFF — CAN\'T VOTE':selected?'✓ YOUR VOTE':game.you.voted?'VOTING CLOSED':'TAP TO SELECT'}</span></span></button>`;
    }).join('');
    return `<section class="game-area">${progressHeader()}${roundHeader('SPOT THE REAL ONE','Truth or total nonsense?','One answer is real. The others are trying to fool you.')}${question()}
      <div class="voting-grid">${options}</div><p class="voting-note">${game.you.voted?'✓ Your choice is locked. Time to see who you fooled.':'Pick one answer before the timer runs out. You cannot vote for your own bluff.'}</p>${progressLine('vote')}</section>`;
  }
  function answerReveal() {
    const all = game.answers.map((o,i) => `<div class="reveal-item ${o.correct?'true':''} ${game.you.voteId===o.id?'your-choice':''}">
      <div class="reveal-title"><strong>${letters[i]}. ${esc(o.text)}</strong>${o.correct?'<span class="reveal-truth">✓ THE TRUTH</span>':''}</div>
      <div class="reveal-author">${o.correct?'The actual answer':`By ${esc(o.author)}`}${game.you.voteId===o.id?' · ★ YOUR PICK':''}</div>
      <div class="voter-line">${o.votes?`<strong>${o.votes} vote${o.votes===1?'':'s'}</strong> · ${esc(o.voters.join(', '))}`:'Nobody fell for this one'}</div></div>`).join('');
    return `<section class="game-area">${progressHeader()}${roundHeader('THE BIG REVEAL','The truth is out.','Find out who had you completely fooled.')}${question()}<div class="reveal-list">${all}</div><div class="points-banner"><small>YOUR ROUND SCORE</small><strong>+${format(game.you.earned)} PTS ✳</strong></div></section>`;
  }
  function leaderboard() {
    const players = [...game.players].sort((a,b)=>b.score-a.score || a.name.localeCompare(b.name));
    return `<div class="leaderboard">${players.map((p,i)=>`<div class="leader-row ${p.id===game.you.id?'me':''}"><span class="rank ${i===0?'first':''}">${i===0?'♛':`#${i+1}`}</span><span class="small-avatar">${esc(p.name.slice(0,1).toUpperCase())}</span><div><div class="leader-name">${esc(p.name)}${p.id===game.you.id?' (you)':''}</div><div class="leader-extra">${p.host?'★ Host · ':''}${p.connected?'Online':'Offline'}</div></div><span class="delta">${p.earned?'+'+format(p.earned):'—'}</span><span class="leader-score">${format(p.score)}</span></div>`).join('')}</div>`;
  }
  function scorePhase() {
    return `<section class="game-area">${progressHeader()}${roundHeader('ROUND COMPLETE','Here’s the damage.','Every good lie leaves a mark on the scoreboard.')}
      ${leaderboard()}<div class="between-card"><div><strong>${game.round === 8?'THE FINAL VERDICT IS NEXT':'UP NEXT: ANOTHER CHANCE TO BLUFF'}</strong><p>${game.round===8?'The final winner will be crowned shortly.':'Everyone will get a fresh weird question.'}</p></div><div class="next-count"><span id="nextValue">${Math.ceil((game.remainingMs||0)/1000)}</span>s →</div></div></section>`;
  }
  function finished() {
    const players = [...game.players].sort((a,b)=>b.score-a.score || a.name.localeCompare(b.name));
    const winners = players.filter(p=>p.score===players[0].score);
    const name = winners.length===1?winners[0].name:winners.map(p=>p.name).join(' & ');
    return `<section class="game-area">${roomBar()}<div class="champion"><div class="eyebrow" style="justify-content:center">EIGHT ROUNDS. ONE FINAL VERDICT.</div><span class="trophy">🏆</span><span class="tag tag-lime">${winners.length>1?'JOINT WINNERS':'CHAMPION OF DECEPTION'}</span><h2>${esc(name)}<br><em>takes the crown!</em></h2><p>${winners.length>1?'A perfect tie. The room has more than one master of deception.':'Nobody saw that coming. Or did they?'}</p><div class="winner-points">${format(players[0].score)} POINTS</div><div class="end-actions">${game.you.host?'<button class="btn btn-primary" data-action="rematch">PLAY AGAIN <span>↗</span></button>':'<span class="tag tag-purple">Waiting for the host to start a rematch</span>'}<button class="btn btn-dark" data-action="leave">LEAVE ROOM</button></div></div><div class="section-head"><h3>FINAL STANDINGS</h3><small>8 ROUNDS PLAYED</small></div>${leaderboard()}</section>`;
  }

  function keyForGame() {
    if (!game) return `landing-${joinMode}`;
    if (game.phase==='lobby') return `lobby-${game.players.map(p=>p.id+String(p.connected)+String(p.host)).join('-')}`;
    return [game.phase,game.round,game.you.id,game.you.host,game.you.submitted,game.you.voted].join('-');
  }

  function render() {
    const key = keyForGame();
    if (key!==lastKey) {
      if (!game) root.innerHTML = renderLanding();
      else if (game.phase==='lobby') root.innerHTML = lobby();
      else if (game.phase==='bluff') root.innerHTML = bluffPhase();
      else if (game.phase==='vote') root.innerHTML = votePhase();
      else if (game.phase==='reveal') root.innerHTML = answerReveal();
      else if (game.phase==='scores') root.innerHTML = scorePhase();
      else if (game.phase==='finished') root.innerHTML = finished();
      lastKey = key;
    }
    updateProgress();
    updateTimer();
  }

  function updateProgress() {
    if (!game) return;
    const label = document.querySelector('#progressLabel');
    const bar = document.querySelector('#submissionBar');
    if (!label) return;
    const online = game.players.filter(p=>p.connected);
    const count = online.filter(p => game.phase==='bluff'?p.submitted:p.voted).length;
    label.textContent = `${count} of ${online.length} ${game.phase==='bluff'?'bluffs submitted':'votes cast'}`;
    if (bar) bar.style.width = `${online.length?100*count/online.length:0}%`;
  }

  function updateTimer() {
    if (lastRemaining == null || !game) return;
    const timeLeft = Math.max(0, lastRemaining - (Date.now() - timeReceivedAt));
    const seconds = Math.ceil(timeLeft / 1000);
    const label = document.querySelector('#timeValue');
    if (label) {
      label.textContent = `${seconds}s`;
      label.closest('.timer')?.classList.toggle('urgent', seconds <= 7);
    }
    const next = document.querySelector('#nextValue');
    if (next) next.textContent = seconds;
  }

  root.addEventListener('input', e => {
    if (e.target.id === 'nameInput') displayName = e.target.value;
    else if (e.target.id === 'codeInput') { codeDraft = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0,6); e.target.value = codeDraft; }
    else if (e.target.id === 'bluffInput') { bluffDraft = e.target.value; document.querySelector('#charsLeft').textContent = 70 - bluffDraft.length; }
  });
  root.addEventListener('submit', e => {
    e.preventDefault();
    if (e.target.id === 'joinForm') {
      const name = displayName.trim().replace(/\s+/g,' ').slice(0,18);
      if (name.length < 2) { toast('Please enter a nickname with at least two characters.'); return; }
      saveLocal('bluff_battle_name', name);
      if (joinMode==='create') send({type:'create', name});
      else {
        if (codeDraft.length!==6) { toast('Enter the six-character room code.'); return; }
        send({type:'join', name, code:codeDraft});
      }
    } else if (e.target.id === 'bluffForm') {
      const answer = bluffDraft.trim();
      if (answer.length<2) { toast('Make your fake answer at least two characters long.'); return; }
      send({type:'bluff',answer});
    }
  });
  root.addEventListener('click', async e => {
    const btn = e.target.closest('[data-action]');
    if (!btn || btn.disabled) return;
    const action = btn.dataset.action;
    if (action==='mode-create' || action==='mode-join') {
      joinMode=action==='mode-create'?'create':'join';lastKey='';render();
    } else if (action==='copy-code' || action==='invite') {
      const text = action==='copy-code'?game.code:`${location.origin}/?room=${encodeURIComponent(game.code)}`;
      try { await navigator.clipboard.writeText(text); toast(action==='copy-code'?'Room code copied!':'Invite link copied!'); }
      catch { toast(`Copy this ${action==='copy-code'?'room code':'invite link'}: ${text}`); }
    } else if (action==='start' || action==='rematch') {
      send({type:action});
    } else if (action==='leave') {
      send({type:'leave'});
      game=null;session=null;shouldResume=false;lastKey='';lastRound=-1;
      deleteLocal('bluff_battle_session');
      history.replaceState({}, '', '/');render();
    } else if (action==='vote') {
      send({type:'vote', optionId:btn.dataset.id});
    }
  });

  document.querySelector('#helpBtn').addEventListener('click', () => dialog.showModal());
  document.querySelector('#closeRules').addEventListener('click', () => dialog.close());
  document.querySelector('#gotItBtn').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target===dialog) dialog.close(); });
  window.setInterval(updateTimer, 100);
  render();
  connect();
})();
