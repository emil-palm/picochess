# Feature Dependencies

## Dependency Graph

```
Foundation Layer (no dependencies):
  - Event System
  - Board Position Management

Core Layer (requires foundation):
  - UCI Engine (requires: Board)
  - Time Control (requires: Events)
  - Opening Books (requires: Board)

Game Logic Layer (requires core):
  - Interaction Modes (requires: Engine, Time, Board)
  - Alternative Moves (requires: Engine, Books)

I/O Layer (requires game logic):
  - Display Management (requires: All features)
  - Menu System (requires: All features)
  - Voice (requires: Moves)
  - Web Interface (requires: All features)

Utility Layer (requires game logic):
  - PGN Recording (requires: Game state)
  - Internationalization (requires: Display)
  - Analysis Info (requires: Engine)
```

## Critical Dependencies

### Board Position
- **Required by**: Everything
- **Requires**: Nothing

### Engine
- **Required by**: All game modes
- **Requires**: Board, Time Control

### Time Control
- **Required by**: Engine, Display
- **Requires**: Events

### Interaction Modes
- **Required by**: Game behavior
- **Requires**: Engine, Time Control, Board

## Build Order
See [Implementation Order](implementation-order.md) for recommended sequence.
