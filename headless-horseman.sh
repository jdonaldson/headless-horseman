#!/bin/bash
# Weekday 4pm shutdown reminder. Fired by launchd (io.jjd.shutdown-reminder); can also be run by hand.
#
#   shutdown-reminder.sh            fire everything
#   shutdown-reminder.sh --dry-run  show which tmux panes would get the message, send nothing
#
# Four channels, so a tired Friday cannot miss it:
#   1. macOS notification (with its own sound)
#   2. a bell sound through the speakers
#   3. a banner in every tmux session
#   4. a typed message into every tmux pane that is running Claude Code, submitted with Enter,
#      so each thread starts its own shutdown routine
#
# Why typing into panes rather than Claude's session-to-session messaging: only sessions on a
# recent build register as peers, so a headless `claude -p` broadcast misses older threads.
# Typing works on any version. The ssh pane for a remote Claude is deliberately excluded:
# if that pane were sitting at a shell prompt, the typed line would run as a command.
#
# Guard: a pane whose last lines show a permission or AskUserQuestion dialog is skipped,
# because keystrokes there select options instead of going into the input box.

MSG="4pm shutdown reminder (automated). Start shutting this thread down: list anything flagged as worth doing before shutdown or that should not wait until tomorrow, finish or explicitly defer each one, then update resume context for this thread."
LOG="$HOME/Library/Logs/shutdown-reminder.log"
TMUX_BIN=/opt/homebrew/bin/tmux   # not "TMUX": that env var is how tmux clients find the server socket
DRY=0
[ "$1" = "--dry-run" ] && DRY=1

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; [ "$DRY" = 1 ] && echo "$*"; }

log "fired dry_run=$DRY"

if [ "$DRY" = 0 ]; then
    /usr/bin/osascript -e "display notification \"$MSG\" with title \"Shutdown reminder\" sound name \"Glass\"" 2>> "$LOG"
    /usr/bin/afplay -v 0.5 "$HOME/.config/kitty/bells/book-close.wav" 2>> "$LOG" &
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
