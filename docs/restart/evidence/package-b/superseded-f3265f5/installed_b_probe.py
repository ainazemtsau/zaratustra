"""Wheel-only package B probe; fictional roots under the disposable install directory."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


allowed = [Path.cwd().resolve(), Path(sys.base_prefix).resolve(), Path(sys.prefix).resolve()]


def audit(event, args):
    if event.startswith('socket.') or event.startswith('subprocess.'):
        raise AssertionError('unexpected network/process: ' + event)
    if event in {'open', 'os.listdir', 'os.scandir', 'os.mkdir', 'sqlite3.connect'}:
        value = args[0]
        if isinstance(value, (str, bytes)):
            actual = Path(value).resolve()
            assert any(actual.is_relative_to(root) for root in allowed), str(actual)


sys.addaudithook(audit)
import zaratustra_core
import zaratustra_app

assert Path(zaratustra_core.__file__).is_relative_to(Path(sys.prefix))
assert Path(zaratustra_app.__file__).is_relative_to(Path(sys.prefix))
spec = importlib.util.spec_from_file_location('fictional_trace', Path.cwd() / 'independent_trace.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
Core, CoreError = zaratustra_core.Core, zaratustra_core.CoreError
Coordinator, Driver = zaratustra_app.Coordinator, zaratustra_app.Driver


def control(owner, action):
    work = Coordinator(owner).snapshot()['works'][0]
    return owner.call('control_work', {'work_id': 'work', 'revision': work['revision'],
                      'action': action}, action + str(work['revision']))


def tables(core):
    with sqlite3.connect(core.path) as db:
        db.row_factory = sqlite3.Row
        return {t: [dict(row) for row in db.execute('SELECT * FROM ' + t)]
                for t in ('works', 'attempts', 'actions', 'results', 'waits', 'tool_calls',
                          'conversations', 'intents', 'acceptance')}


core, owner, executor = support.fixture(Path('b-wheel-continuation'))
c = Coordinator(executor)
c.prepare('work', 'A1', support.PROFILE)
control(owner, 'pause')
control(owner, 'resume')
fresh = c.prepare('work', 'A2', support.PROFILE)
receiver = support.Receiver()
c.dispatch('A2', fresh['generation'], Driver(receiver))
reopened = Coordinator(Core(core.root).connect(executor.token))
first = reopened.recover('A2')
assert reopened.recover('A2') == first
support.ingest(owner, 'correction', 'Five minutes, corrected')
assert tables(core)['works'][0]['status'] == 'waiting'
support.ingest(owner, 'answer', 'Exact answer', {'id': 'W7', 'revision': 1})
next_attempt = reopened.prepare('work', 'A3', support.PROFILE)
assert next_attempt['pinned']['tool_ledger'][0]['receipt'] == 'A2:tool:create-activity'
assert [m['seq'] for m in next_attempt['pinned']['messages']] == [21, 22]
reopened.dispatch('A3', next_attempt['generation'], Driver(receiver))
assert reopened.recover('A3')['state'] == 'completed'
assert receiver.actions == ['A2:action', 'A3:action']
assert tables(core)['works'][0]['reserved'] == 4
assert not tables(core)['acceptance']

core2, owner2, executor2 = support.fixture(Path('b-wheel-exhaustion'))
c2 = Coordinator(executor2)
c2.prepare('work', 'A1', support.PROFILE)
executor2.call('claim_dispatch', {'attempt_id': 'A1', 'generation': 1, 'resource_upper': 4},
               'claim', action_id='A1:action')
control(owner2, 'pause')
executor2.call('observe_attempt', {'attempt_id': 'A1', 'event_id': 'proof', 'kind': 'reconcile',
               'evidence': {'action_id': 'A1:action', 'state': 'not_received',
                            'receiver_ref': 'fictional-proof/1'}}, 'proof')
try:
    control(owner2, 'resume')
except CoreError as error:
    assert error.code == 'resource_exhausted'
else:
    raise AssertionError('exhausted reserve resumed')
assert tables(core2)['works'][0]['status'] == 'paused'
assert tables(core2)['works'][0]['reserved'] == 4
print(json.dumps({'core_module': zaratustra_core.__file__, 'app_module': zaratustra_app.__file__,
                  'receiver_actions': receiver.actions, 'continuation': tables(core),
                  'exhaustion': tables(core2), 'network_process_forbidden': True}, indent=2))
