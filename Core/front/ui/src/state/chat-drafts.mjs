// Keep only the Human's unfinished input. Room facts always come from CAT.
const key = id => 'poe.cat.draft.' + id;

export function readDraft(storage, id) {
  const text = storage.getItem(key(id));
  if (!text) return {draft:'', reply:'', pending:null};
  const saved = JSON.parse(text);
  return {
    draft:saved.draft,
    reply:saved.reply,
    // A reload cannot know whether an interrupted POST reached the server.
    pending:saved.pending ? {...saved.pending, sending:false} : null,
  };
}

export function writeDraft(storage, state) {
  if (!state.draft && !state.reply && !state.pending) {
    storage.removeItem(key(state.id));
    return;
  }
  storage.setItem(key(state.id), JSON.stringify({
    draft:state.draft, reply:state.reply, pending:state.pending,
  }));
}
