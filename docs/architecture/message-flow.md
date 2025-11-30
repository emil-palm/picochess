# Message Flow Architecture

## Overview
This document describes how messages flow through the PicoChess system, from input to output, showing the complete path of common operations.

---

## User Makes Move

```
┌──────────────┐
│ User moves   │
│ piece on     │
│ board        │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ DGT Board Hardware                       │
│ - Detects piece position changes        │
│ - Generates FEN string                   │
└──────┬───────────────────────────────────┘
       │ Event.FEN(fen='...')
       ▼
┌──────────────────────────────────────────┐
│ evt_queue                                │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Main Event Loop                          │
│ - Validates FEN against legal moves      │
│ - Identifies which move was made         │
│ - Updates game state                     │
│ - Checks game end conditions             │
└──────┬───────────────────────────────────┘
       │
       ├─────────────────────────────────┐
       │                                 │
       ▼                                 ▼
┌─────────────────┐          ┌──────────────────┐
│ Time Control    │          │ Display Manager  │
│ - Stop user     │          │                  │
│   clock         │          └─────┬────────────┘
│ - Add increment │                │ Message.USER_MOVE_DONE
│ - Start engine  │                ▼
│   clock         │          ┌──────────────────┐
└─────────────────┘          │ msg_queue        │
                             └─────┬────────────┘
                                   │
       ┌───────────────────────────┼─────────────┐
       │                           │             │
       ▼                           ▼             ▼
┌──────────────┐          ┌─────────────┐  ┌─────────┐
│ Voice        │          │ PGN         │  │ Web     │
│ "e2 to e4"   │          │ Recorder    │  │ Display │
└──────────────┘          └─────────────┘  └─────────┘
       
       │ (if Normal/Brain mode)
       ▼
┌──────────────────────────────────────────┐
│ UCI Engine                               │
│ - Receives position                      │
│ - Starts search with time limits         │
│ - Runs in separate thread                │
└──────────────────────────────────────────┘
```

---

## Engine Finds Best Move

```
┌──────────────────────────────────────────┐
│ UCI Engine                               │
│ - Search completes                       │
│ - Callback triggered                     │
└──────┬───────────────────────────────────┘
       │ Event.BEST_MOVE(move=..., ponder=...)
       ▼
┌──────────────────────────────────────────┐
│ evt_queue                                │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Main Event Loop                          │
│ - Validates move is legal                │
│ - Stores move (doesn't execute yet!)     │
│ - Calculates expected board FEN          │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Time Control                             │
│ - Stops engine clock                     │
└──────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│ Display Manager                          │
│ - Shows move on clock                    │
│ - Optionally lights LEDs                 │
└──────┬───────────────────────────────────┘
       │ Dgt.DISPLAY_MOVE(move=...)
       ▼
┌──────────────────────────────────────────┐
│ dispatch_queue                           │
└──────┬───────────────────────────────────┘
       │
       ├──────────────────┬──────────────┐
       │                  │              │
       ▼                  ▼              ▼
┌─────────────┐    ┌──────────┐   ┌──────────┐
│ DGT Clock   │    │ DGT Pi   │   │ Web      │
│ (serial)    │    │ (i2c)    │   │ Display  │
│ Shows "e2e4"│    │ Shows    │   │ Animates │
│             │    │ "1.e4"   │   │ Move     │
└─────────────┘    └──────────┘   └──────────┘

       │ User executes move on board
       ▼
┌──────────────────────────────────────────┐
│ Board FEN matches expected                │
│ -> Event.FEN triggers computer move done │
└──────────────────────────────────────────┘
```

---

## Complete Game Flow

```
           START
              │
              ▼
      ┌───────────────┐
      │  Initialize   │
      │  - Board      │
      │  - Engine     │
      │  - Time Ctrl  │
      └───────┬───────┘
              │
              ▼
      ┌───────────────┐
      │ Wait for      │◄─────────┐
      │ User Move     │          │
      └───────┬───────┘          │
              │                  │
              ▼                  │
      ┌───────────────┐          │
      │ Validate &    │          │
      │ Execute Move  │          │
      └───────┬───────┘          │
              │                  │
              ▼                  │
      ┌───────────────┐          │
      │ Game Over?    │──YES──> EXIT
      └───────┬───────┘          │
              │ NO               │
              ▼                  │
      ┌───────────────┐          │
      │ Computer's    │          │
      │ Turn?         │──NO──────┘
      └───────┬───────┘
              │ YES
              ▼
      ┌───────────────┐
      │ Engine        │
      │ Searches      │
      └───────┬───────┘
              │
              ▼
      ┌───────────────┐
      │ Display       │
      │ Move          │
      └───────┬───────┘
              │
              ▼
      ┌───────────────┐
      │ Wait for      │
      │ User to       │
      │ Execute       │
      └───────┬───────┘
              │
              ▼
      ┌───────────────┐
      │ Execute       │
      │ Computer Move │
      └───────┬───────┘
              │
              └──────────────────┘
```

---

## Button Press Flow

```
User presses button
        │
        ▼
┌─────────────────┐
│ Hardware        │
│ Detects Press   │
└────────┬────────┘
         │ Event.KEYBOARD_BUTTON(button=X)
         ▼
┌─────────────────┐
│ evt_queue       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ Main Loop               │
│ Checks menu state       │
└────────┬────────────────┘
         │
    ┌────┴────┐
    │ In Menu?│
    └────┬────┘
         │
    ┌────┴────┐
    │         │
   YES       NO
    │         │
    ▼         ▼
┌────────┐  ┌─────────────┐
│ Menu   │  │ In-Game     │
│ Action │  │ Action      │
│        │  │             │
│ B0: Up │  │ B0: Last    │
│ B1: Dn │  │     Move    │
│ B2: Sel│  │ B1: Score   │
│ B3: Nxt│  │ B2: Pause/  │
│ B4: Bak│  │     Alt.Move│
└────┬───┘  │ B3: Hint    │
     │      │ B4: Menu    │
     │      └─────┬───────┘
     │            │
     └────────┬───┘
              ▼
      ┌──────────────┐
      │ Display Text │
      │ or Action    │
      └──────────────┘
```

---

## Clock Time Update Flow

```
┌────────────────────────┐
│ External Clock (DGT)   │
│ Sends time every 1 sec │
└──────────┬─────────────┘
           │ Event.CLOCK_TIME
           ▼
┌────────────────────────┐
│ evt_queue              │
└──────────┬─────────────┘
           │
           ▼
┌────────────────────────────────┐
│ Main Loop                      │
│ Checks device priority         │
│ (i2c > ser > web)             │
└──────────┬─────────────────────┘
           │
           ▼
┌────────────────────────────────┐
│ Time Control                   │
│ - Syncs internal time          │
│ - Checks for time < 60s        │
│ - Sets low_time flag           │
└──────────┬─────────────────────┘
           │
           ▼
┌────────────────────────────────┐
│ Display Manager                │
│ Broadcasts time update         │
└──────────┬─────────────────────┘
           │ Message.CLOCK_TIME
           ▼
┌────────────────────────────────┐
│ msg_queue                      │
└──────────┬─────────────────────┘
           │
           ├────────────┬─────────────┐
           │            │             │
           ▼            ▼             ▼
      ┌────────┐  ┌─────────┐  ┌─────────┐
      │ Voice  │  │ Web     │  │ Other   │
      │ (if    │  │ Display │  │ Systems │
      │ low    │  │ Updates │  │         │
      │ time,  │  │ Time    │  │         │
      │ stop)  │  │         │  │         │
      └────────┘  └─────────┘  └─────────┘
```

---

## New Game Flow

```
User action (button/menu/board reset)
           │
           ▼
   ┌───────────────┐
   │ Event.        │
   │ NEW_GAME      │
   └───────┬───────┘
           │
           ▼
   ┌───────────────────────┐
   │ Main Loop             │
   │ Checks if game active │
   └───────┬───────────────┘
           │
      ┌────┴────┐
      │ Active? │
      └────┬────┘
           │
       ┌───┴───┐
      YES     NO
       │       │
       ▼       │
   ┌───────┐  │
   │ Send  │  │
   │ ABORT │  │
   └───┬───┘  │
       │      │
       └──┬───┘
          │
          ▼
   ┌──────────────────┐
   │ Reset Game State │
   │ - Clear board    │
   │ - Reset clocks   │
   │ - New position   │
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │ Engine.newgame() │
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │ Time.reset()     │
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │ Display          │
   │ START_NEW_GAME   │
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │ Voice            │
   │ "New Game"       │
   └──────────────────┘
```

---

## Analysis Mode Flow

```python
# User switches to Analysis mode

┌─────────────────┐
│ Event.          │
│ SET_INTERACTION │
│ _MODE(ANALYSIS) │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ Main Loop               │
│ Validates mode change   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Stop any current        │
│ search/clock            │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Engine.mode(            │
│   ponder=False,         │
│   analyse=True          │
│ )                       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Engine.go(              │
│   infinite=True         │
│ )                       │
└────────┬────────────────┘
         │
         │ Continuous stream of analysis
         ▼
┌────────────────────────────────────┐
│ Event.NEW_PV / NEW_SCORE / NEW_DEP│
│ (every 0.5 seconds, throttled)    │
└────────┬───────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Display PV/Score/Depth  │
│ on clock and web        │
└─────────────────────────┘

# User makes move in analysis mode

┌─────────────────┐
│ Event.FEN       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ Main Loop               │
│ Validates move          │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Engine.stop()           │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Game.push(move)         │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Engine.go(              │
│   infinite=True         │
│ )                       │
└────────┬────────────────┘
         │
         │ Analysis continues for new position
         ▼
    (repeat cycle)
```

---

## Permanent Brain (Brain Mode)

```
┌─────────────────────────────────┐
│ User makes move                 │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Check if move == ponder_move    │
└────────┬────────────────────────┘
         │
    ┌────┴────┐
    │ Match?  │
    └────┬────┘
         │
    ┌────┴─────┐
   YES        NO
    │          │
    │          ▼
    │     ┌────────────┐
    │     │ Stop       │
    │     │ Engine     │
    │     └──────┬─────┘
    │            │
    │            ▼
    │     ┌────────────┐
    │     │ Start new  │
    │     │ search     │
    │     └────────────┘
    │
    ▼
┌────────────────┐
│ PONDER HIT!    │
│ Engine.hit()   │
└────────┬───────┘
         │
         │ Engine continues same search
         │ but now it's a real search
         ▼
┌────────────────────┐
│ Engine finds move  │
│ faster (advantage!)│
└────────────────────┘

# After computer move executed

┌────────────────────┐
│ Computer move done │
└────────┬───────────┘
         │
         ▼
┌───────────────────────┐
│ Engine.brain(         │
│   position + ponder,  │
│   time_control        │
│ )                     │
└───────┬───────────────┘
         │
         │ Engine thinks on user's time
         ▼
┌───────────────────────┐
│ Waiting for user move │
│ (engine pondering)    │
└───────────────────────┘
```

---

## Data Flow Summary

### Hot Path (Every Move)
1. Board → FEN → Event Queue
2. Main Loop → Validate → Update State
3. Time Control → Update Clocks
4. Display → Show Move
5. Voice → Announce (if enabled)

### Analysis Path (Continuous)
1. Engine → Info Updates (PV/Score/Depth)
2. Throttle → 2 per second max
3. Display → Show Analysis
4. Web → Update in real-time

### Configuration Path (Menu)
1. Button → Event Queue
2. Menu → Process Navigation
3. Menu → Update Setting
4. Config → Fire Change Event
5. Feature → Reconfigure

---

## Performance Bottlenecks

### 1. FEN Processing
- **Critical path**: < 100ms
- **Solution**: Pre-compute legal FENs
- **Monitoring**: Log slow FEN validations

### 2. Display Updates
- **Issue**: Can overwhelm slow serial ports
- **Solution**: Queue with max time
- **Monitoring**: Track queue depth

### 3. Engine Communication
- **Issue**: Blocking I/O
- **Solution**: Async callbacks
- **Monitoring**: Track response times

### 4. Voice Announcements
- **Issue**: Blocking audio playback
- **Solution**: Play in separate thread
- **Monitoring**: Skip in low time

---

## Summary

Message flow in PicoChess follows these principles:

1. **Unidirectional**: Input → Processing → Output
2. **Async**: All I/O in separate threads
3. **Decoupled**: Features communicate via queues
4. **Reliable**: Queue-based ensures no dropped messages
5. **Traceable**: Every action creates events/messages

When recreating, maintain clear boundaries between:
- Input collection (threading)
- Event processing (single threaded)
- Output distribution (threading)
