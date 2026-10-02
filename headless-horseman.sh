#!/bin/bash
# Headless Horseman: a weekday closing-time reminder that rides through every Claude Code
# thread and tells it to start shutting down. Fired by launchd (io.jjd.headless-horseman);
# can also be run by hand.
#
#   headless-horseman.sh            fire everything
#   headless-horseman.sh --dry-run  show which tmux panes would get the message, send nothing
#
# Channels: macOS notification, a neigh, a banner in every tmux session, and a typed message
# into every tmux pane running Claude Code (submitted with Enter) so each thread starts its
# own shutdown routine. Panes whose foreground command is ssh are excluded: at a shell prompt
# the typed line would execute. Panes showing a permission or AskUserQuestion dialog are
# skipped, because keystrokes there select options instead of going into the input box.
#
# Settings (environment variables, all optional):
#   HORSEMAN_MESSAGE   text typed into each Claude pane and shown in the notification
#   HORSEMAN_SOUND     path to a wav/aiff/mp3 to play; empty string disables the sound
#   HORSEMAN_TMUX      path to the tmux binary

MSG="${HORSEMAN_MESSAGE:-Headless Horseman (automated closing-time reminder). Start shutting this thread down: list anything flagged as worth doing before shutdown or that should not wait until tomorrow, finish or explicitly defer each one, then update resume context for this thread.}"
SOUND="${HORSEMAN_SOUND-$HOME/.local/share/headless-horseman/horseman.wav}"
TMUX_BIN="${HORSEMAN_TMUX:-/opt/homebrew/bin/tmux}"   # not "TMUX": that env var is how tmux clients find the server socket
LOG="$HOME/Library/Logs/headless-horseman.log"
DRY=0
[ "$1" = "--dry-run" ] && DRY=1

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; [ "$DRY" = 1 ] && echo "$*"; }

log "fired dry_run=$DRY"

if [ "$DRY" = 0 ]; then
    /usr/bin/osascript -e "display notification \"$MSG\" with title \"Headless Horseman\"" 2>> "$LOG"
    if [ -n "$SOUND" ] && [ -r "$SOUND" ]; then
        /usr/bin/afplay -v 0.8 "$SOUND" 2>> "$LOG" &
    else
        log "sound not played: '$SOUND' missing or disabled"
    fi
fi

if ! "$TMUX_BIN" list-sessions >/dev/null 2>&1; then
    log "no tmux server; done"
    wait
    exit 0
fi

if [ "$DRY" = 0 ]; then
    for s in $("$TMUX_BIN" list-sessions -F '#S'); do
        "$TMUX_BIN" display-message -t "$s" -d 20000 "$MSG" 2>> "$LOG"
    done
fi

# A Claude Code pane reports its own version string as pane_current_command (e.g. 2.1.288),
# or "claude" during startup. That is the only signal used; titles are decorative.
"$TMUX_BIN" list-panes -a -F '#{pane_id} #{session_name}:#{window_index}.#{pane_index} #{pane_current_command} #{pane_title}' |
while read -r pane_id addr cmd title; do
    case "$cmd" in
        claude|[0-9]*.[0-9]*.[0-9]*) ;;
        *) continue ;;
    esac

    tail_text=$("$TMUX_BIN" capture-pane -p -t "$pane_id" -S -30 2>/dev/null)
    if printf '%s\n' "$tail_text" | grep -Eq 'Do you want to|^[[:space:]]*❯[[:space:]]*[0-9]+\.'; then
        log "skip  $addr ($title): dialog open"
        continue
    fi

    if [ "$DRY" = 1 ]; then
        log "would send  $addr ($title)"
        continue
    fi

    "$TMUX_BIN" send-keys -t "$pane_id" -l "$MSG" 2>> "$LOG"
    sleep 0.5
    "$TMUX_BIN" send-keys -t "$pane_id" Enter 2>> "$LOG"
    log "sent  $addr ($title)"
done

wait
