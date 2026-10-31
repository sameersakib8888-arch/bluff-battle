"""Unit + real WebSocket integration tests for the game-night flow."""
import asyncio
import sys
from pathlib import Path

import pytest
from aiohttp import ClientSession
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402
from questions import QUESTIONS  # noqa: E402


def player(name, host=False):
    p = server.GameService.new_player(name, host)
    p.connected = True
    return p


def test_credit_duplicated_and_correct_bluffs_with_prepared_decoys():
    room = server.Room('ABCDEF')
    a, b = player('Alpha', True), player('Beta')
    room.players = {a.id: a, b.id: b}
    room.deck = [QUESTIONS[0]] * 8
    room.round_idx = 0
    room.start_bluff()
    room.submit_bluff(a, 'Aglet')  # exactly correct, must be replaced
    room.submit_bluff(b, 'Aglet')  # duplicate, also must be replaced
    room.make_options()
    assert len(room.options) == 4
    assert sum(bool(o['correct']) for o in room.options) == 1
    assert len({server.normalized(o['text']) for o in room.options}) == 4
    assert len([o for o in room.options if o['owner'] in (a.id, b.id)]) == 2
    assert all(o['text'].lower() != 'aglet' for o in room.options if not o['correct'])


def test_correct_guesses_plus_fooled_opponents_score_together():
    room = server.Room('AABBCC')
    alice, bob, cara = (player('Alice', True), player('Bob'), player('Cara'))
    room.players = {p.id: p for p in (alice, bob, cara)}
    room.deck = [QUESTIONS[0]] * 8
    room.round_idx = 0
    room.start_bluff()
    for p, lie in ((alice, 'Lacecap'), (bob, 'Tipper'), (cara, 'Cordlet')):
        room.submit_bluff(p, lie)
    room.make_options()
    room.set_phase('vote', 60)
    truth = next(o for o in room.options if o['correct'])
    alices_lie = next(o for o in room.options if o['owner'] == alice.id)
    room.submit_vote(alice, truth['id'])
    room.submit_vote(bob, alices_lie['id'])
    room.submit_vote(cara, alices_lie['id'])
    with pytest.raises(ValueError, match='already voted'):
        room.submit_vote(alice, truth['id'])
    room.resolve_round()
    assert alice.score == alice.earned == 2000
    assert bob.score == cara.score == 0


def test_cannot_vote_for_own_lie_and_secret_data_does_not_leak():
    room = server.Room('AABBCC')
    a, b = player('Aye', True), player('Bee')
    room.players = {a.id: a, b.id: b}
    room.deck = [QUESTIONS[0]] * 8
    room.round_idx = 0
    room.start_bluff()
    room.submit_bluff(a, 'Lacecap')
    room.submit_bluff(b, 'Tipper')
    early = room.snapshot(a)
    assert early['answers'] == []
    assert 'Aglet' not in str(early)
    room.make_options()
    room.set_phase('vote', 60)
    mid = room.snapshot(a)
    assert len(mid['answers']) == 4
    assert all('correct' not in entry and 'author' not in entry for entry in mid['answers'])
    a_option = next(o for o in room.options if o['owner'] == a.id)
    with pytest.raises(ValueError, match='own bluff'):
        room.submit_vote(a, a_option['id'])
    room.resolve_round()
    room.set_phase('reveal', 30)
    final = room.snapshot(a)
    assert sum(1 for o in final['answers'] if o['correct']) == 1
    assert all('author' in o for o in final['answers'])


async def until_type(ws, kind, *, timeout=4.0, predicate=None):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=max(.01, end - asyncio.get_running_loop().time()))
        if msg['type'] == 'error':
            pytest.fail(f"WebSocket error: {msg['message']}")
        if msg['type'] == kind and (predicate is None or predicate(msg)):
            return msg
    raise AssertionError(f'Missing message of type {kind}')


@pytest.mark.asyncio
async def test_two_real_websocket_clients_complete_match_and_host_transfer(monkeypatch):
    monkeypatch.setattr(server, 'BLUFF_SECONDS', .55)
    monkeypatch.setattr(server, 'VOTE_SECONDS', .55)
    monkeypatch.setattr(server, 'REVEAL_SECONDS', .18)
    monkeypatch.setattr(server, 'SCORES_SECONDS', .18)
    monkeypatch.setattr(server, 'SERVICE', server.GameService())
    async with TestServer(server.create_app()) as test_server:
        async with ClientSession() as client:
            host = await client.ws_connect(test_server.make_url('/ws'))
            guest = await client.ws_connect(test_server.make_url('/ws'))
            await host.send_json({'type': 'create', 'name': 'Alicia'})
            joined = await until_type(host, 'joined')
            code, host_token = joined['code'], joined['token']
            assert len(code) == 6
            await until_type(host, 'state', predicate=lambda s: s['phase'] == 'lobby')
            await guest.send_json({'type': 'join', 'code': code, 'name': 'Boris'})
            guest_joined = await until_type(guest, 'joined')
            await until_type(guest, 'state', predicate=lambda s: s['phase'] == 'lobby')
            await until_type(host, 'state', predicate=lambda s: len(s['players']) == 2)
            await host.send_json({'type': 'start'})
            start_host = await until_type(host, 'state', predicate=lambda s: s['phase'] == 'bluff')
            start_guest = await until_type(guest, 'state', predicate=lambda s: s['phase'] == 'bluff')
            assert start_host['question'] == start_guest['question']
            assert start_host['answers'] == []
            assert start_host['remainingMs'] <= 550
            await host.send_json({'type': 'bluff', 'answer': 'Fake from Alicia'})
            await guest.send_json({'type': 'bluff', 'answer': 'Fake from Boris'})
            host_vote = await until_type(host, 'state', predicate=lambda s: s['phase'] == 'vote')
            guest_vote = await until_type(guest, 'state', predicate=lambda s: s['phase'] == 'vote')
            assert len(host_vote['answers']) == 4
            assert all('correct' not in a for a in guest_vote['answers'])
            q = server.SERVICE.rooms[code].question
            truth = next(a for a in host_vote['answers'] if a['text'] == q['answer'])
            alice_lie = next(a for a in guest_vote['answers'] if a['text'] == 'Fake from Alicia')
            await host.send_json({'type':'vote', 'optionId': truth['id']})
            await guest.send_json({'type':'vote', 'optionId': alice_lie['id']})
            reveal = await until_type(host, 'state', predicate=lambda s: s['phase'] == 'reveal')
            assert reveal['you']['earned'] == 1500
            assert sum(bool(a['correct']) for a in reveal['answers']) == 1
            guest_reveal = await until_type(guest, 'state', predicate=lambda s: s['phase'] == 'reveal')
            assert guest_reveal['you']['earned'] == 0
            # Host disconnects mid-game; second player takes the host role.
            await host.close()
            transferred = await until_type(guest, 'state', predicate=lambda s: s['you']['host'])
            assert transferred['you']['host'] is True
            # Original host reconnects with same secret token and the same score.
            restored_ws = await client.ws_connect(test_server.make_url('/ws'))
            await restored_ws.send_json({'type':'resume', 'code': code, 'token': host_token})
            await until_type(restored_ws, 'joined')
            restored = await until_type(restored_ws, 'state')
            assert restored['you']['score'] == 1500
            assert restored['you']['host'] is False
            # Let the remaining seven short rounds expire. The game must finish.
            finished = await until_type(restored_ws, 'state', timeout=20,
                                        predicate=lambda s: s['phase'] == 'finished')
            assert finished['round'] == 8
            assert max(p['score'] for p in finished['players']) == 1500
            await restored_ws.close()
            await guest.close()
