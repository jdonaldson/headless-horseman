# Headless Horseman: weekday closing-time reminder for Claude Code threads (macOS, launchd, tmux).
#
#   make install            install script + sound, render the plist, load it into launchd
#   make install HOUR=17    same, at 5pm instead of 4pm (MINUTE=30 also works)
#   make dry-run            list the tmux panes that would receive the message, send nothing
#   make fire               run the reminder once, right now
#   make status             launchd state and the last log lines
#   make uninstall          unload from launchd and remove the installed files
#   make play               play the neigh
#   make synth              regenerate the optional synthetic alternate, sounds/neigh-synth.wav
#   make install SOUND=sounds/neigh-synth.wav   install with a different sound file

LABEL   := io.jjd.headless-horseman
HOUR    ?= 16
MINUTE  ?= 0

BIN_DIR   ?= $(HOME)/bin
SHARE_DIR ?= $(HOME)/.local/share/headless-horseman
AGENTS    ?= $(HOME)/Library/LaunchAgents

SCRIPT := headless-horseman.sh
SOUND  ?= sounds/horseman.wav
SYNTH  := sounds/neigh-synth.wav
PLIST  := build/$(LABEL).plist
DOMAIN  = gui/$$(id -u)

.PHONY: all install uninstall dry-run fire status synth play clean

all: $(PLIST)

$(SYNTH): tools/make_neigh.py
	python3 $< $@

$(PLIST): $(LABEL).plist.in
	mkdir -p build
	sed -e 's|@HOME@|$(HOME)|g' -e 's|@HOUR@|$(HOUR)|g' -e 's|@MINUTE@|$(MINUTE)|g' $< > $@
	plutil -lint $@

synth:
	python3 tools/make_neigh.py $(SYNTH)

play:
	afplay $(SOUND)

install: $(PLIST)
	mkdir -p $(BIN_DIR) $(SHARE_DIR) $(AGENTS)
	install -m 755 $(SCRIPT) $(BIN_DIR)/$(SCRIPT)
	install -m 644 $(SOUND) $(SHARE_DIR)/horseman.wav
	-launchctl bootout $(DOMAIN)/$(LABEL) 2>/dev/null
	install -m 644 $(PLIST) $(AGENTS)/$(LABEL).plist
	launchctl bootstrap $(DOMAIN) $(AGENTS)/$(LABEL).plist
	@echo "installed: fires weekdays at $(HOUR):$$(printf '%02d' $(MINUTE)) local"

uninstall:
	-launchctl bootout $(DOMAIN)/$(LABEL) 2>/dev/null
	rm -f $(AGENTS)/$(LABEL).plist $(BIN_DIR)/$(SCRIPT) $(SHARE_DIR)/horseman.wav
	-rmdir $(SHARE_DIR) 2>/dev/null

dry-run:
	bash $(SCRIPT) --dry-run

fire:
	launchctl kickstart -p $(DOMAIN)/$(LABEL)

status:
	-launchctl print $(DOMAIN)/$(LABEL) | grep -E 'state|last exit|run interval' | head
	-tail -n 10 $(HOME)/Library/Logs/headless-horseman.log

clean:
	rm -rf build
