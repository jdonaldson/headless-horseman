#!/bin/bash
# Headless Horseman: a weekday closing-time reminder that rides through every Claude Code
# session on this machine and tells it to start shutting down. Fired by launchd
# (io.jjd.headless-horseman); can also be run by hand.
#
#   headless-horseman.sh            fire everything
#   headless-horseman.sh --dry-run  list the Claude sessions that would be messaged, send nothing
#
# Channels: macOS notification, a neigh and a laugh, a banner in every tmux session, and a
# message delivered to every other Claude Code session through Claude's own session-to-session
# messaging (a headless `claude -p` run calls ListAgents, then SendMessage per peer).
#
# Compatibility: only sessions on a recent Claude Code build register as peers (verified on
# 2.1.288; threads still running 2.1.286 and 2.1.287 were invisible). Older threads get the
# notification, sound and tmux banner but not the message. A session in a different permission
# mode from the headless run may hold the message for its user's approval instead of acting.
#
# Settings (environment variables, all optional):
#   HORSEMAN_MESSAGE   text delivered to each session and shown in the notification
#   HORSEMAN_SOUND     path to a wav/aiff/mp3 to play; empty string disables the sound
#   HORSEMAN_TMUX      path to the tmux binary
#   HORSEMAN_CLAUDE    path to the claude binary
#   HORSEMAN_MODEL     model for the headless messenger run (it only calls two tools)

MSG="${HORSEMAN_MESSAGE:-Headless Horseman (automated closing-time reminder). Start shutting this thread down: list anything flagged as worth doing before shutdown or that should not wait until tomorrow, finish or explicitly defer each one, then update resume context for this thread.}"
SOUND="${HORSEMAN_SOUND-$HOME/.local/share/headless-horseman/horseman.wav}"
TMUX_BIN="${HORSEMAN_TMUX:-/opt/homebrew/bin/tmux}"   # not "TMUX": that env var is how tmux clients find the server socket
CLAUDE_BIN="${HORSEMAN_CLAUDE:-$HOME/.local/bin/claude}"
MODEL="${HORSEMAN_MODEL:-haiku}"
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
    if "$TMUX_BIN" list-sessions >/dev/null 2>&1; then
        for s in $("$TMUX_BIN" list-sessions -F '#S'); do
            "$TMUX_BIN" display-message -t "$s" -d 20000 "$MSG" 2>> "$LOG"
        done
    fi
fi

if [ ! -x "$CLAUDE_BIN" ]; then
    log "claude binary not found at $CLAUDE_BIN; no sessions messaged"
    wait
    exit 1
fi

# The messenger is a throwaway headless Claude session. It is told exactly which two tools
# to call and nothing else; its printed report goes to the log, one line per peer.
if [ "$DRY" = 1 ]; then
    PROMPT="Call ListAgents once and print its result verbatim. Do nothing else."
    TOOLS="ListAgents"
else
    PROMPT="You are the Headless Horseman, an automated closing-time reminder. Call ListAgents once. For every peer session it lists (never yourself), call SendMessage with 'to' set to that session's exact name as printed and 'message' set to exactly the text between the markers below. After all sends, print one line per peer in the form 'sent <name>' or 'failed <name>: <reason>'. Do nothing else.
---BEGIN MESSAGE---
$MSG
---END MESSAGE---"
    TOOLS="ListAgents,SendMessage"
fi

printf '%s' "$PROMPT" | "$CLAUDE_BIN" -p --no-session-persistence --model "$MODEL" --allowedTools "$TOOLS" 2>&1 |
    grep -v '^Permission allow rule' |
    while IFS= read -r line; do log "messenger: $line"; done

wait
