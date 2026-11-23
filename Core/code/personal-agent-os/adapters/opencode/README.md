# PAOE context for OpenCode V2

The server plugin loads the current PAOE originals for each configured OpenCode session. It verifies the session against PAOE Contact. The plugin reuses the same original text while the phase inputs stay current and reads them again when a source changes or after native compaction. The OpenCode request keeps its native user input.

## Install for a selected session

Use the OpenCode server configuration for the selected Windows process. Add an entry to the existing `plugins` array. Set `package` to this directory in the paired Core. Enter the existing registered session ID, project and Home. Set `catUrl` to the paired CAT endpoint if the selected trial uses CAT.

```jsonc
{
  "plugins": [
    {
      "package": "D:/path/to/paired/Core/code/personal-agent-os/adapters/opencode",
      "options": {
        "installation": "D:/path/to/installation.selected.json",
        "catUrl": "http://127.0.0.1:18871",
        "sessions": {
          "ses_REPLACE_WITH_EXISTING_ID": {
            "project": "3004",
            "home": "S042",
            "recoverCapacity": true
          }
        }
      }
    }
  ]
}
```

- `installation` identifies the selected Core and the original PAOE Data. `python` is optional and defaults to `python`.
- Set `requiredSources` on a selected session when the trial explicitly requires additional originals. Values use the same locators as `paos context read --source`. The common command determines required and optional sources.
- Set `recoverCapacity` to true only for a trial that approves one PAOE-managed native compaction after a provider refusal. The default leaves that retry decision with the owner. If OpenCode has already started compaction for that input, its native recovery owns the attempt.
- CAT pairing requires the Core `context stop --presence-only` contract. A selected native turn can close its seat on failure, with STOP set, or without a Current Task. These cases authorize presence updates only. A newer execution cancels a pending update for the previous turn. A normal successful native turn delegates to `context stop` and applies at most one requested correction at that stop.

Start the designated process using its OpenCode configuration. The package imports the shared Core client from the adjacent `dsh` adapter directory. Check the exact Contact before the trial and verify the first `request_checked` entry in `<data_root>/runtime/opencode-context/<Home>/events.jsonl` after sending an approved input to the selected session. Entries record the session, input, hook name and original versions. When retiring the trial, remove the plugin entry from the designated process configuration and reopen that process.

## Scope of the check

The OpenCode `context` hook validates the visible request at its own position. The isolated provider verifies which bytes reached the model request. A later hook can change the request.

When a required original is missing, the plugin rejects the business request before transport. The public hooks in 2.0.32 and 2.3.2 expose the current request draft and estimated output budget. They lack an exact input token count for that draft after the plugin applies the originals. Capacity recovery therefore starts from an explicit supported provider refusal after native execution ends. The separate compaction request carries native history. The adapter looks up the actual completed compaction in the native session before re-reading originals and queuing a fresh continuation. A failed compaction, a changed task, STOP, or a previously attempted task leaves follow-up to the owner. The once-per-task recovery receipt lives in OpenCode plugin storage.

Run the regression with either exact Windows executable from the repository root.

```powershell
python -X utf8 -B Core/tests/opencode_context_native.py <path-to-opencode.exe> 2.0.32
python -X utf8 -B Core/tests/opencode_context_native.py <path-to-opencode-cli.exe> 2.3.2
```

The regression uses two disposable sessions, an isolated PAOE installation and a loopback model. It tests the request as received by that model, a later modifying hook, missing originals, native compaction, the once-per-task limit across host restarts, STOP during compaction and a single Stop correction. Pass the paired Core source directory as a third argument to verify the CAT seat after failure, STOP, or a turn without a Current Task. The CAT test also holds the old turn's room lookup open while the next native turn reaches the model.
