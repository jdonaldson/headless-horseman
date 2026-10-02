# Headless Horseman

A weekday closing-time reminder for people who run several Claude Code threads in tmux and,
by late afternoon, forget which ones still have something worth doing before they shut down.

At a scheduled time (default 4pm Mon–Fri) a launchd job rides through the machine and:

1. posts a macOS notification,
2. plays a horse neigh,
3. shows a banner in every tmux session,
4. types a shutdown message into every tmux pane running Claude Code and submits it, so each
   thread starts its own shutdown routine: list anything flagged as worth doing before
   shutdown, finish or explicitly defer each item, then write the thread's resume context.

The point of step 4 is that the reminder lands inside the threads, not just on the human.
Tired-Friday working memory is the thing that fails; the threads still remember.

## Install

Requires macOS, tmux (Homebrew path assumed; override with `HORSEMAN_TMUX`), and Python 3
for the sound generator. No third-party packages.

```
git clone https://github.com/jdonaldson/headless-horseman
cd headless-horseman
make install            # 4pm weekdays
make install HOUR=17    # or 5pm
make dry-run            # which panes would get the message, without sending
make fire               # ride now
```

`make status` shows the launchd state and the log tail. `make uninstall` removes everything.
If the Mac is asleep at the scheduled time, launchd fires the job once after wake.

## How it finds Claude panes

A Claude Code pane reports its own version string (for example `2.1.288`) as tmux's
`pane_current_command`, or `claude` during startup. That is the only signal used. Panes
whose foreground command is `ssh` are excluded even if a remote Claude is running there,
because a typed line at a shell prompt would execute.

Why not Claude's session-to-session messaging? It only sees sessions on a recent build, so a
headless broadcast misses older threads. Typing into the pane works on any version.

## Safety guard

Before typing, the script captures each pane's last 30 lines and skips any pane showing a
permission prompt or an AskUserQuestion dialog, because keystrokes there select options
instead of going into the input box. Skipped panes are logged; the notification and banner
still fire, so you can deal with them by hand.

## Configuration

Environment variables read by `headless-horseman.sh` (set them in the plist, or export them
before `make fire`):

| Variable           | Default                                           | Meaning                                   |
| ------------------ | ------------------------------------------------- | ----------------------------------------- |
| `HORSEMAN_MESSAGE` | the shutdown message shown in the script          | text typed into each pane and notified    |
| `HORSEMAN_SOUND`   | `~/.local/share/headless-horseman/neigh.wav`      | sound file to play; empty string disables |
| `HORSEMAN_TMUX`    | `/opt/homebrew/bin/tmux`                          | tmux binary                               |

## The neigh

`sounds/neigh.wav` is synthesized by `tools/make_neigh.py` with the Python standard library
only: a trilled, descending whinny that drops into a pulsed, breathy nicker. It is
deterministic, so `make sound` regenerates the identical file, and nothing in the repo
carries a sample license. Swap in any wav or aiff via `HORSEMAN_SOUND` if you prefer a real
horse.

## Logs

`~/Library/Logs/headless-horseman.log` records each fire and, per pane, whether the message
was sent or why it was skipped. launchd's own stdout/stderr goes to
`~/Library/Logs/headless-horseman.launchd.log`.
