import test from 'node:test';
import assert from 'node:assert/strict';
import {readPage, acceptMessage, sendOutcome, memberName} from '../front/cat-state.mjs';

test('a POST overtaking another author does not advance the GET cursor or lose the intervening message', () => {
  let timeline = {messages:[{id:'a', seq:1}], cursor:1};
  timeline = acceptMessage(timeline, {id:'c', seq:3});
  assert.equal(timeline.cursor, 1);
  timeline = readPage(timeline, [{id:'b', seq:2}, {id:'c', seq:3}]);
  assert.deepEqual(timeline.messages.map(m => m.id), ['a','b','c']);
  assert.equal(timeline.cursor, 3);
  timeline = readPage(timeline, [{id:'a', seq:1}]);
  assert.equal(timeline.cursor, 3);
  assert.equal(timeline.messages.length, 3);
});

test('persisted message and reminder dispatch have separate user-visible outcomes', () => {
  const receipt = {ok:true, accepted:true, message:{id:'one'}};
  assert.match(sendOutcome({...receipt, dispatch:'queued'}).text, /已保存.*排队/);
  assert.doesNotMatch(sendOutcome({...receipt, dispatch:'queued'}).text, /已读|已处理|已唤醒/);
  assert.match(sendOutcome({...receipt, dispatch:'not_configured'}).text, /已保存.*未配置/);
  assert.equal(sendOutcome({...receipt, replayed:true, dispatch:'none'}).state, 'saved');
});

test('post timeout, broken response and server errors retain an unknown result; validation and failed join are definite', () => {
  for (const value of [{ok:false,error_code:'unreachable'}, {ok:false,error_code:'cli_result_unknown'},
    {ok:false,error_code:'cli_output_invalid'}, {ok:false,status:500}, undefined, {ok:true}]) {
    assert.equal(sendOutcome(value).state, 'unknown');
  }
  for (const value of [{ok:false,status:409}, {ok:false,error_code:'cat_not_configured'},
    {ok:false,error_code:'cli_start_failed'}, {ok:false,message_submitted:false}]) {
    assert.equal(sendOutcome(value).state, 'failed');
  }
});

test('names use the existing roster and the human never receives an agent signature', () => {
  const members = [{home_id:'3002-s036',label:'S052 Agent学习'}];
  assert.equal(memberName('3002-s036', members), 'S052 Agent学习');
  assert.equal(memberName('human', members), 'Human');
});
