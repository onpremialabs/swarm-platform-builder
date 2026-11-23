import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isAbstainedEvent, isAbstainedDone, abstentionNotice, settleUnrunSteps,
} from './pipelineEvents.js';

test('reconoce el aviso y el cierre por abstención', () => {
  assert.equal(isAbstainedEvent({ type: 'abstained', agent: 'investigador' }), true);
  assert.equal(isAbstainedEvent({ type: 'done' }), false);
  assert.equal(isAbstainedDone({ type: 'done', outcome: 'abstained' }), true);
});

test('un done normal no es una abstención', () => {
  assert.equal(isAbstainedDone({ type: 'done' }), false);
  assert.equal(isAbstainedDone({ type: 'done', outcome: 'completed' }), false);
  assert.equal(isAbstainedDone({ type: 'abstained', outcome: 'abstained' }), false);
  assert.equal(isAbstainedDone(undefined), false);
});

test('el aviso lleva k/N y el mensaje', () => {
  const n = abstentionNotice({ type: 'done', outcome: 'abstained', message: 'Sube fuentes', verified_sources: 1, min_sources: 3 });
  assert.deepEqual(n, { kind: 'abstained', message: 'Sube fuentes', verified: 1, min: 3 });
});

test('solo los pasos en espera pasan a no ejecutado', () => {
  const out = settleUnrunSteps([
    { id: 'investigador', status: 'abstained' },
    { id: 'redactor', status: 'waiting' },
    { id: 'x', status: 'completed', output: 'o' },
  ]);
  assert.deepEqual(out.map((s) => s.status), ['abstained', 'not_run', 'completed']);
});
