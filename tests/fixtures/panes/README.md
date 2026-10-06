# Pane captures

What `tmux capture-pane -p -J` printed for a Claude Code session, the text the kit's
`watch_workers.sh` and `spawn_worker.sh` read. The rules in
`overlays/claude-code/files/scripts/waiting_patterns.txt` marked VERIFIED were written from
these files.

| File | What | Source |
|---|---|---|
| `trust.txt` | the folder-trust dialog | real capture, Claude Code 2.1.285, a fresh temporary folder |
| `permission.txt` | a Bash permission prompt in manual mode | real capture, 2.1.285, one model turn |
| `question.txt` | a question asked with the question tool | real capture, 2.1.285, one model turn |
| `idle.txt` | the input box after the prompt was refused | real capture, 2.1.285 |
| `working.txt` | the model at work (spinner above the input box) | real pane text, 2.1.285, trailing blanks lost |
| `working-auto.txt` | the bottom of a working pane in auto mode | real pane text from a project using the kit, 2.1.285 |
| `quoted-output.txt` | a worker's OUTPUT quoting a prompt above an idle input box | made up from the lines above, to keep the watcher from a false alarm |

Scrubbed: the question's text and options were translated into English; the session and
branch names in `working-auto.txt` were replaced with `a-worker`. The temporary folder's
name (`/tmp/tmp.*`) is left as captured; no capture holds a home directory, an e-mail
address or an account id. A new Claude Code version can change any of this: add its
captures beside these, with the version in the table.
