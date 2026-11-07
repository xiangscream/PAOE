// Keep the Human's input and locally ended receipts. Room facts come from CAT.
const key = id => 'poe.cat.draft.' + id;

export function readDraft(storage, id) {
  const text = storage.getItem(key(id));
  if (!text) return {draft:'', reply:'', pending:null, endedRequests:[]};
  const saved = JSON.parse(text);
  return {
    draft:saved.draft,
    reply:saved.reply,
    // A reload cannot know whether an interrupted POST reached the server.
    pending:saved.pending ? {...saved.pending, sending:false} : null,
    endedRequests:saved.endedRequests || [],
  };
}

export function writeDraft(storage, state) {
  if (!state.draft && !state.reply && !state.pending && !state.endedRequests?.length) {
    storage.removeItem(key(state.id));
    return;
  }
  storage.setItem(key(state.id), JSON.stringify({
    draft:state.draft, reply:state.reply, pending:state.pending, endedRequests:state.endedRequests || [],
  }));
}
