// Keep the Human's input and locally ended receipts. Room facts come from CAT.
// Task-room slice: the explicit recipient selection (targets) is part of the draft,
// so an interrupted send or reload keeps the same selection.
const key = id => 'poe.cat.draft.' + id;

export function readDraft(storage, id) {
  const text = storage.getItem(key(id));
  if (!text) return {draft:'', reply:'', targets:[], pending:null, endedRequests:[]};
  const saved = JSON.parse(text);
  return {
    draft:saved.draft,
    reply:saved.reply,
    targets:Array.isArray(saved.targets) ? saved.targets.filter(item => typeof item === 'string') : [],
    // A reload cannot know whether an interrupted POST reached the server.
    pending:saved.pending ? {...saved.pending, sending:false} : null,
    endedRequests:saved.endedRequests || [],
  };
}

export function writeDraft(storage, state) {
  if (!state.draft && !state.reply && !state.targets?.length && !state.pending && !state.endedRequests?.length) {
    storage.removeItem(key(state.id));
    return;
  }
  storage.setItem(key(state.id), JSON.stringify({
    draft:state.draft, reply:state.reply, targets:state.targets || [], pending:state.pending, endedRequests:state.endedRequests || [],
  }));
}
