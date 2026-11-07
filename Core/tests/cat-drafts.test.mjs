import test from 'node:test';
import assert from 'node:assert/strict';
import {readDraft, writeDraft} from '../front/ui/src/state/chat-drafts.mjs';

function storage() {
  const values=new Map();
  return {getItem:key=>values.get(key)||null, setItem:(key,value)=>values.set(key,value), removeItem:key=>values.delete(key)};
}

test('navigation or reload keeps the original in-flight request and makes it check-only', () => {
  const disk=storage();
  const state={id:'room-one',draft:'原正文',reply:'quoted',pending:{id:'human-original',body:'原正文',reply:'quoted',sending:true},messages:[{body:'不得缓存'}]};
  writeDraft(disk,state);
  const restored=readDraft(disk,state.id);
  assert.deepEqual(restored,{draft:'原正文',reply:'quoted',pending:{id:'human-original',body:'原正文',reply:'quoted',sending:false},endedRequests:[]});
  assert.deepEqual(readDraft(disk,'room-two'),{draft:'',reply:'',pending:null,endedRequests:[]});
  assert.equal('messages' in restored,false);
});

test('confirming a saved message clears only its own composer', () => {
  const disk=storage();
  writeDraft(disk,{id:'one',draft:'a',reply:'',pending:null});
  writeDraft(disk,{id:'two',draft:'b',reply:'q',pending:null});
  writeDraft(disk,{id:'one',draft:'',reply:'',pending:null});
  assert.deepEqual(readDraft(disk,'one'),{draft:'',reply:'',pending:null,endedRequests:[]});
  assert.equal(readDraft(disk,'two').draft,'b');
});
