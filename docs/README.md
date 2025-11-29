# PicoChess Feature Documentation

## Overview
This documentation provides a comprehensive analysis of PicoChess features for recreating the functionality in another codebase. Each feature is documented separately with implementation examples, dependencies, and integration guidelines.

**Target Audience**: Developers looking to implement chess computer functionality using Cursor or similar development environments.

---

## Documentation Structure

### 📐 Architecture
Core architectural patterns and systems:
- [Event System](architecture/event-system.md) - Message queue architecture
- [Message Flow](architecture/message-flow.md) - How data flows through the system

### ⚙️ Core Features
Game logic and chess engine features:
- [01. Board Position Management](features/01-board-position.md) - FEN parsing, legal moves, sliding detection
- [02. UCI Engine Management](features/02-engine-uci.md) - Chess engine communication and control
- [03. Time Control System](features/03-time-control.md) - Clock management (Fixed, Blitz, Fischer)
- [04. Opening Books](features/04-opening-books.md) - Polyglot book integration
- [05. Interaction Modes](features/05-interaction-modes.md) - 7 game modes (Normal, Brain, Analysis, etc.)
- [06. PGN Recording](features/06-pgn-recording.md) - Game history and email delivery
- [07. Voice Announcements](features/07-voice-announcements.md) - Text-to-speech move announcements
- [08. Menu System](features/08-menu-system.md) - Hierarchical configuration interface
- [09. Alternative Moves](features/09-alternative-moves.md) - Request different engine/book moves
- [10. Analysis Information](features/10-analysis-info.md) - PV, Score, Depth display
- [11. Internationalization](features/11-internationalization.md) - Multi-language support

### 📥 Input Devices
How the system receives input:
- [DGT Electronic Board](input/dgt-board.md) - Position sensing via FEN
- [DGT Clock Buttons](input/dgt-buttons.md) - 5 button navigation
- [Web Interface Input](input/web-interface-input.md) - Browser-based control
- [Console Input](input/console-input.md) - Command-line interface

### 📤 Output Devices
How the system displays information:
- [DGT XL Clock](output/dgt-xl-clock.md) - 6 character serial display
- [DGT 3000 Clock](output/dgt-3000-clock.md) - 8 character serial display
- [DGT Pi Clock](output/dgt-pi-clock.md) - 11 character i2c display
- [DGT Revelation II](output/revelation-ii.md) - 11 character display + LED board
- [Web Interface Output](output/web-interface-output.md) - Browser display
- [Voice Output](output/voice-output.md) - Audio announcements

### 🔗 Integration Guides
Putting it all together:
- [Dependencies](integration/dependencies.md) - Feature dependency graph
- [Implementation Order](integration/implementation-order.md) - Recommended build sequence
- [Quick Reference](quick-reference.md) - Fast lookup for common patterns

---

## Quick Start Guide

### For Minimum Viable Product (MVP)
1. Start with [Event System](architecture/event-system.md)
2. Implement [Board Position](features/01-board-position.md)
3. Add [UCI Engine](features/02-engine-uci.md)
4. Include [Time Control](features/03-time-control.md) (Blitz mode only)
5. Add one input device (e.g., [Web Interface](input/web-interface-input.md))
6. Add one output device (e.g., [Web Interface](output/web-interface-output.md))

### For Full Implementation
Follow the recommended sequence in [Implementation Order](integration/implementation-order.md).

---

## Key Concepts

### Event-Driven Architecture
PicoChess uses three main message queues:
- **evt_queue**: Input events (board FEN, buttons, engine results)
- **dispatch_queue**: Display commands (clock, LEDs, text)
- **msg_queue**: Broadcast messages (PGN, voice, logging)

### Device Independence
The same game logic works with multiple I/O devices through abstraction layers. Features don't know about specific hardware - they just fire events and consume events.

### Asynchronous Operations
All blocking operations (engine searches, file I/O, network) run in separate threads to keep the main event loop responsive.

---

## Interaction Modes Summary

| Mode | Computer Plays | Ponders on User Time | Shows Analysis | Clock Runs |
|------|---------------|---------------------|----------------|------------|
| NORMAL | ✓ | ✗ | ✗ | ✓ |
| BRAIN | ✓ | ✓ | ✗ | ✓ |
| ANALYSIS | ✗ | ✓ | ✓ | ✗ |
| KIBITZ | ✗ | ✓ | ✓ | ✗ |
| OBSERVE | ✗ | ✓ | ✓ | ✓ |
| REMOTE | ✗ | ✗ | ✗ | ✓ |
| PONDER | ✗ | ✓ | ✓ | ✗ |

---

## Hardware Compatibility

### Input Devices Supported
- DGT e-Board (USB/Bluetooth)
- DGT Pi (i2c)
- DGT 3000/XL (serial)
- Web browser
- Console/keyboard

### Output Devices Supported
- DGT XL Clock (6 chars, serial)
- DGT 3000 Clock (8 chars, serial)
- DGT Pi Clock (11 chars, i2c)
- DGT Revelation II (11 chars + LEDs, serial)
- Web browser
- Audio (voice)

---

## Example Integration

```python
# 1. Setup event system
evt_queue = Queue()
dispatch_queue = Queue()

# 2. Initialize core features
board_mgr = BoardPositionManager()
engine = UCIEngine('stockfish')
time_control = TimeControl(TimeMode.BLITZ, blitz=5)

# 3. Connect input device
dgt_board = DGTBoard(port='/dev/ttyACM0')
dgt_board.start()

# 4. Connect output device
dgt_clock = DGTXLClock()
dgt_clock.start()

# 5. Main event loop
while True:
    event = evt_queue.get()
    process_event(event)
```

---

## Dependencies Between Features

```
Board Position (foundation)
    ↓
Engine + Time Control + Opening Books (core)
    ↓
Interaction Modes (behavior)
    ↓
Display + Voice + Web (I/O)
    ↓
PGN + Menu (utilities)
```

See [Dependencies](integration/dependencies.md) for detailed dependency graph.

---

## Common Pitfalls

1. **Clock Synchronization**: External clock is source of truth, sync internal time regularly
2. **Sliding Detection**: Use field timer (0.25-0.5s) to debounce piece movements
3. **Engine Pondering**: Track expected move for ponder hit/miss optimization
4. **Display Timing**: Queue messages with maxtime to avoid overlaps
5. **Thread Safety**: All queue operations must be thread-safe

---

## Testing Approach

### Unit Tests
- Board FEN parsing and legal move generation
- Time control arithmetic
- UCI command generation
- Message queue behavior

### Integration Tests
- Engine + Time control
- Board + Move validation
- Menu + Configuration
- Multi-device coordination

### Hardware Tests
- DGT board accuracy
- Clock synchronization
- Button response
- LED feedback

---

## Version History

- **v1.0** - Initial documentation based on PicoChess v0.9n
- Analyzed: ~30 Python files, ~10,000 lines of code
- Features documented: 11 core + 4 input + 6 output devices

---

## Contributing

This documentation is designed to be:
- **Generic**: Not PicoChess-specific terminology
- **Practical**: Includes working code examples
- **Complete**: All features and dependencies documented
- **Maintainable**: Separated by feature for easy updates

When recreating features, maintain the event-driven architecture and device independence for maximum flexibility.

---

## Getting Help

1. Start with [Architecture](architecture/event-system.md) to understand the foundation
2. Read feature docs in numerical order (01-11)
3. Check [Dependencies](integration/dependencies.md) before implementing
4. Use [Quick Reference](quick-reference.md) for fast lookups
5. See [Implementation Order](integration/implementation-order.md) for phased approach

---

## License

This documentation is based on analysis of PicoChess, which is licensed under GPL v3.

Original PicoChess: https://github.com/jromang/picochess
