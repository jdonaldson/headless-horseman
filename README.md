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
| `HORSEMAN_SOUND`   | `~/.local/share/headless-horseman/horseman.wav`   | sound file to play; empty string disables |
| `HORSEMAN_TMUX`    | `/opt/homebrew/bin/tmux`                          | tmux binary                               |

## The sound

The default, `sounds/horseman.wav`, is a real horse neighing in a large dark room, followed
by a maniacal laugh as the neigh fades. Both parts are recordings with sox reverb; the
components and alternates ship in `sounds/`:

| File                                  | What it is                                                                 | License |
| ------------------------------------- | -------------------------------------------------------------------------- | ------- |
| `horseman.wav`                        | default: `neigh-reverb.wav` with `cackle.wav` starting 2.4 s in            | CC BY-SA 3.0 (via the cackle) |
| `neigh.wav`                           | "Horse Neighing #3" by Joseph Sardin, [BigSoundBank](https://bigsoundbank.com/horse-neighing-3-s0863.html), normalized. Original mp3 kept alongside. | CC0 |
| `neigh-reverb.wav`                    | the same with a long hall reverb                                           | CC0 |
| `cackle.wav`                          | "Evil laugh 2" by Ondra Krist, [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Evillaugh.ogg), mono, same reverb. Original oga kept alongside. | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| `cackle-alt-horror-laugh-klankbeeld.ogg` | alternate laugh by klankbeeld, [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Horror_laugh.ogg), unprocessed | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) |
| `cackle-alt-evil-laughter-stilgar.ogg` | alternate laugh by stilgar, [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Evil_laughter.ogg), 17 s, unprocessed | public domain |
| `neigh-wikimedia-wiehern.wav`         | alternate neigh by Hü, [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Wiehern.ogg), normalized | public domain |
| `neigh-synth.wav`                     | synthetic nightmare neigh from `tools/make_neigh.py` (stdlib only, deterministic, `make synth` regenerates it byte-for-byte) | none needed |

Pick one at install time with `make install SOUND=sounds/neigh-reverb.wav`, or point
`HORSEMAN_SOUND` at any wav, aiff or mp3 afterwards. To rebuild the processed files:

```
sox sounds/neigh.wav sounds/neigh-reverb.wav gain -4 pad 0 2.5 reverb 70 40 100 100 20 -1 channels 1 norm -1
sox sounds/cackle-evil-laugh-2-krist.oga sounds/cackle.wav channels 1 gain -4 pad 0 3 reverb 70 40 100 100 20 -1 channels 1 norm -1
sox -m sounds/neigh-reverb.wav "|sox sounds/cackle.wav -p pad 2.4" sounds/horseman.wav norm -1
```

## Logs

`~/Library/Logs/headless-horseman.log` records each fire and, per pane, whether the message
was sent or why it was skipped. launchd's own stdout/stderr goes to
`~/Library/Logs/headless-horseman.launchd.log`.
