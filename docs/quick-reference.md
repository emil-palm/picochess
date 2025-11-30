# PicoChess Quick Reference Guide

## Overview
PicoChess is an event-driven chess computer system that connects physical DGT boards with UCI engines.

## Core Architecture

### Event-Driven Design
```
Input Sources → Event Queue → Main Loop → Engine/Display/etc.
     ↓              ↓              ↓            ↓
  Board          Queue         Process      Output
  Buttons        (FIFO)        Events       Actions
  Engine
```

### Three Main Queues
1. **evt_queue** - Input events (moves, buttons, engine results)
2. **dispatch_queue** - Display commands (clock, LEDs, text)
3. **msg_queue** - Broadcast messages (PGN, voice, logging)

---

## Feature Summary Table

| Feature | Purpose | Key Classes | Dependencies |
|---------|---------|-------------|--------------|
| Board Position | FEN parsing, move validation | `BoardPositionManager` | None (foundation) |
| UCI Engine | Chess engine communication | `UciEngine` | Board Position |
| Time Control | Clock management | `TimeControl` | Board events |
| Opening Books | Polyglot books | `OpeningBookManager` | Board Position |
| Interaction Modes | 7 play modes | `GameController` | Engine, Board |
| PGN Recording | Game history | `PGNRecorder` | Game state |
| Voice | Move announcements | `VoiceAnnouncer` | Move events |
| Web Interface | Remote access | `WebServer` | All features |
| Menu System | Configuration | `ChessMenu` | All features |
| Alternative Moves | Request different move | `AlternativeMoveManager` | Engine, Book |
| Analysis Info | PV/Score/Depth | `EngineInfoHandler` | Engine |
| i18n | Multi-language | `I18nManager` | Display |
| Display Manager | Clock output | `DisplayManager` | All features |

---

## Interaction Modes Quick Reference

| Mode | Computer Plays | Thinks on User Time | Shows Analysis | Clock Runs |
|------|---------------|---------------------|----------------|------------|
| NORMAL | ✓ | ✗ | ✗ | ✓ |
| BRAIN | ✓ | ✓ (Ponder) | ✗ | ✓ |
| ANALYSIS | ✗ | ✓ (Continuous) | ✓ | ✗ |
| KIBITZ | ✗ | ✓ (Continuous) | ✓ | ✗ |
| OBSERVE | ✗ | ✓ (Continuous) | ✓ | ✓ |
| REMOTE | ✗ (Remote player) | ✗ | ✗ | ✓ |
| PONDER | ✗ | ✓ (Continuous) | ✓ (Extended) | ✗ |

---

## Time Control Modes

### Fixed Time
- **Usage**: `TimeControl(TimeMode.FIXED, fixed=10)` 
- **Behavior**: 10 seconds per move
- **UCI**: `movetime=10000`

### Blitz
- **Usage**: `TimeControl(TimeMode.BLITZ, blitz=5)`
- **Behavior**: 5 minutes for entire game
- **UCI**: `wtime=300000 btime=300000`

### Fischer (Increment)
- **Usage**: `TimeControl(TimeMode.FISCHER, blitz=5, fischer=3)`
- **Behavior**: 5 minutes + 3 seconds per move
- **UCI**: `wtime=300000 btime=300000 winc=3000 binc=3000`

---

## Board FEN Processing States

```
Received FEN → Process
    ↓
    ├─ Same Position → Ignore
    ├─ Legal Move → Execute move
    ├─ Sliding → Handle piece movement
    ├─ Computer Move Done → Confirm
    ├─ In History → Takeback
    └─ Invalid → Error (wait 3 sec)
```

---

## Message/Event Flow Examples

### User Makes Move
```
1. Board → FEN Event
2. Main Loop → Validate Move
3. Game State → Update Position
4. Time Control → Add Increment (Fischer)
5. Display → Show Move
6. Voice → Announce Move
7. Engine → Start Search
```

### Engine Finds Move
```
1. Engine → BEST_MOVE Event
2. Main Loop → Validate
3. Display → Show Move
4. Game State → Store (not execute yet)
5. Wait for user to execute on board
```

### Computer Move Executed
```
1. Board → FEN matches predicted
2. Game State → Execute Move
3. Time Control → Start User Clock
4. Display → Clear Move Display
5. PGN → Record Move
6. Engine → Start Pondering (if BRAIN mode)
```

---

## Critical Implementation Patterns

### 1. FEN Validation with Legal Moves
```python
# Pre-compute legal FEN strings
legal_fens = [board.board_fen() for move in board.legal_moves 
              after pushing each move]

# When FEN received, check if in legal_fens
if received_fen in legal_fens:
    move = legal_moves[legal_fens.index(received_fen)]
    execute_move(move)
```

### 2. Sliding Detection
```python
# Save last legal FENs
last_legal_fens = legal_fens.copy()

# If new FEN in last_legal_fens but not current
if fen in last_legal_fens:
    # User is sliding piece
    handle_sliding(fen)
```

### 3. Engine Search with Time Control
```python
# Get UCI time parameters
uci_dict = time_control.to_uci_dict()

# Add search moves (for alternative moves)
uci_dict['searchmoves'] = searchmoves.all(board)

# Start asynchronous search
engine.go(uci_dict, callback=handle_result)
```

### 4. Display Throttling
```python
# Limit updates to 2 per second
if allow_update:
    allow_update = False
    Timer(0.5, lambda: setattr(self, 'allow_update', True)).start()
    fire_event(data)
```

---

## Configuration Examples

### Engine with Levels
```ini
# stockfish.uci
[Level-1]
Skill Level = 0

[Level-10]
Skill Level = 10
```

### Opening Books
```ini
# books.ini
[varied.bin]
large = Varied Opening
medium = Varied
small = varied
```

### Voice Configuration
```ini
# voices.ini
[en]
al = path/to/al/voice
christina = path/to/christina/voice
```

---

## Common Pitfalls & Solutions

### 1. Clock Synchronization
**Problem**: Internal time drifts from external clock
**Solution**: 
- Sync at move start/end
- Use external clock as source of truth
- Log time differences

### 2. Sliding Detection
**Problem**: Multiple move attempts during sliding
**Solution**:
- Field timer (0.25-0.5 sec delay)
- Configurable slow-slide factor
- Disable voice in low time

### 3. Ponder Hit/Miss
**Problem**: Determining if user made expected move
**Solution**:
- Store ponder move
- Compare with user move
- On hit: continue search
- On miss: stop and restart

### 4. Display Timing
**Problem**: Messages overlap or disappear too fast
**Solution**:
- Message queue per device
- maxtime parameter
- Priority system (wait flag)

---

## Minimum Viable Implementation Order

### Phase 1: Foundation (Days 1-3)
1. Event queue system
2. Board FEN parsing
3. Basic UCI engine
4. Simple display output

### Phase 2: Core Game (Days 4-7)
5. Time control (Blitz only)
6. Move validation
7. Game end detection
8. NORMAL interaction mode

### Phase 3: Enhancement (Days 8-14)
9. Opening books
10. PGN recording
11. Alternative moves
12. Basic menu

### Phase 4: Polish (Days 15+)
13. All interaction modes
14. Voice announcements
15. Web interface
16. Full i18n

---

## Testing Checklist

### Board Interface
- [ ] FEN parsing accuracy
- [ ] Legal move detection
- [ ] Sliding detection
- [ ] Takeback to any position
- [ ] Invalid position handling

### Engine Interface
- [ ] Engine startup
- [ ] Search with time limits
- [ ] Pondering
- [ ] Stop/restart
- [ ] Level configuration

### Time Control
- [ ] Fixed time per move
- [ ] Blitz countdown
- [ ] Fischer increment
- [ ] Out of time detection
- [ ] Clock synchronization

### Game Logic
- [ ] All 7 interaction modes
- [ ] Opening book usage
- [ ] Alternative moves
- [ ] Game end detection
- [ ] Move validation

### Display
- [ ] Text display
- [ ] Move display
- [ ] Time display
- [ ] Multi-device support
- [ ] Message timing

---

## Key Dependencies to Remember

### Before Implementation
- **Python chess library** for board logic
- **UCI protocol** for engine communication  
- **Polyglot format** for opening books
- **Threading** for async operations
- **Queue** for event handling

### Hardware (if applicable)
- DGT board driver
- Serial/I2C communication
- Audio output for voice
- Network for web interface

---

## Performance Targets

- **FEN Processing**: < 100ms
- **Display Update**: < 50ms
- **Engine Start**: < 1 second
- **Move Validation**: < 10ms
- **Clock Update**: < 100ms (every second)
- **Voice Announcement**: Non-blocking
- **Web Interface**: < 200ms latency

---

## Summary: What Makes PicoChess Work

1. **Event-Driven**: Everything communicates via queues
2. **Asynchronous**: Engine, I/O, and display all independent
3. **State Machine**: Interaction modes define behavior
4. **Modular**: Each feature is self-contained
5. **Multi-Device**: Same code drives multiple outputs
6. **Configurable**: INI files for all settings
7. **Robust**: Error handling and fallbacks everywhere

The key insight: **Don't block, don't poll, use events**. Every component fires events, every component listens for events, and the main loop orchestrates.

---

## For More Details

See the comprehensive analysis in `PICOCHESS_FEATURES_ANALYSIS.md` for:
- Detailed code examples
- Complete feature descriptions
- All dependencies
- Implementation patterns
- Configuration examples
