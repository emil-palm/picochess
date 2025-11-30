# Event System Architecture

## Overview
The event system is the foundation of PicoChess, implementing an event-driven architecture where all components communicate through message queues. This decouples features from each other and from specific hardware implementations.

---

## Core Concept

### The Three Queues

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│ Input       │ ──────> │ Main Event   │ ──────> │ Output      │
│ Sources     │ Events  │ Loop         │ Actions │ Devices     │
│             │         │              │         │             │
│ - Board     │         │ Process      │         │ - Clock     │
│ - Buttons   │         │ Validate     │         │ - Display   │
│ - Engine    │         │ Update State │         │ - Voice     │
│ - Timer     │         │ Fire Actions │         │ - Web       │
└─────────────┘         └──────────────┘         └─────────────┘
       │                        │                        │
       └───> evt_queue ─────────┴───> dispatch_queue <───┘
                                 │
                                 └───> msg_queue (broadcast)
```

---

## Queue Types

### 1. Event Queue (evt_queue)
**Purpose**: Carries input events from all sources to the main processing loop

**Producers**:
- Board hardware (FEN changes)
- Button presses (menu navigation)
- Engine callbacks (best move found)
- Timer events (time expired)
- Web interface (remote moves)

**Consumers**:
- Main game loop (single consumer)

**Example Events**:
```python
Event.FEN(fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR")
Event.KEYBOARD_BUTTON(button=2, dev='ser')
Event.BEST_MOVE(move=Move.from_uci('e2e4'), ponder=Move.from_uci('e7e5'))
Event.OUT_OF_TIME(color=chess.BLACK)
Event.NEW_GAME(pos960=518)
```

### 2. Dispatch Queue (dispatch_queue)
**Purpose**: Carries display commands to output devices

**Producers**:
- Game logic (show moves, time)
- Menu system (show menu items)
- Display manager (timed messages)

**Consumers**:
- Display dispatcher (routes to devices)
- DGT hardware handlers
- Web interface
- Voice system

**Example Commands**:
```python
Dgt.DISPLAY_TEXT(l='Hello', m='Hello', s='Hello', beep=True, maxtime=2.0)
Dgt.DISPLAY_MOVE(move=Move.from_uci('e2e4'), fen='...', side=ClockSide.LEFT)
Dgt.CLOCK_START(side=ClockSide.LEFT, devs={'ser', 'i2c'})
Dgt.CLOCK_SET(time_left=300, time_right=300, devs={'ser'})
```

### 3. Message Queue (msg_queue)
**Purpose**: Broadcast messages to all interested subsystems

**Producers**:
- Game state changes
- Configuration changes
- System events

**Consumers**:
- PGN recorder (game moves)
- Voice announcer (move pronunciation)
- Web interface (state updates)
- Logging system

**Example Messages**:
```python
Message.USER_MOVE_DONE(move=..., fen=..., turn=chess.WHITE, game=...)
Message.COMPUTER_MOVE(move=..., ponder=..., game=..., wait=True)
Message.GAME_ENDS(result=GameResult.MATE, play_mode=..., game=...)
Message.ENGINE_READY(eng=..., engine_name='Stockfish', ...)
```

---

## Implementation

### Basic Queue Setup

```python
import queue
import threading
import copy

# Create the three main queues
evt_queue = queue.Queue()      # Input events
dispatch_queue = queue.Queue()  # Display commands
msg_queue = queue.Queue()       # Broadcast messages

# Observable pattern for events
class Observable:
    """Input sources fire events here"""
    
    @staticmethod
    def fire(event):
        """Put event on queue with deep copy to prevent mutations"""
        evt_queue.put(copy.deepcopy(event))

# Dispatcher pattern for display
class DispatchDgt:
    """Display logic fires commands here"""
    
    @staticmethod
    def fire(dgt_command):
        """Put display command on queue"""
        dispatch_queue.put(copy.deepcopy(dgt_command))

# Broadcaster pattern for messages
class DisplayMsg:
    """Message broadcaster to all registered displays"""
    
    registered_displays = []
    
    def __init__(self):
        self.msg_queue = queue.Queue()
        DisplayMsg.registered_displays.append(self)
    
    @staticmethod
    def show(message):
        """Send message to all registered displays"""
        for display in DisplayMsg.registered_displays:
            display.msg_queue.put(copy.deepcopy(message))
```

### Main Event Loop

```python
def main_event_loop():
    """
    Main game loop - processes events sequentially.
    This is the heart of the system.
    """
    
    logging.info('Event loop ready')
    
    while True:
        try:
            # Wait for next event (blocking)
            event = evt_queue.get()
            
            logging.debug('Processing event: %s', event)
            
            # Process event based on type
            if isinstance(event, Event.FEN):
                handle_fen_event(event)
            
            elif isinstance(event, Event.BEST_MOVE):
                handle_best_move_event(event)
            
            elif isinstance(event, Event.KEYBOARD_BUTTON):
                handle_button_event(event)
            
            elif isinstance(event, Event.NEW_GAME):
                handle_new_game_event(event)
            
            # ... more event types ...
            
            else:
                logging.warning('Unknown event type: %s', event)
            
            # Mark task as done
            evt_queue.task_done()
            
        except queue.Empty:
            # Should never happen with blocking get()
            pass
        except Exception as e:
            logging.error('Error processing event: %s', e)
```

---

## Event Definition Pattern

### Using Class Factory

```python
class BaseEvent:
    """Base class for all events"""
    
    def __init__(self, event_type):
        self._type = event_type
    
    def __repr__(self):
        return self._type
    
    def __hash__(self):
        return hash(str(self.__class__) + ": " + str(self.__dict__))

def EventFactory(name, argnames):
    """
    Factory for creating event classes.
    
    Usage:
        FEN = EventFactory('EVT_FEN', ['fen'])
        event = FEN(fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
    """
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            if key not in argnames:
                raise TypeError(f"Invalid argument {key} for {name}")
            setattr(self, key, value)
        BaseEvent.__init__(self, name)
    
    new_class = type(name, (BaseEvent,), {"__init__": __init__})
    return new_class

# Define all event types
class Event:
    """Event API - all possible events"""
    
    # Board events
    FEN = EventFactory('EVT_FEN', ['fen'])
    
    # Engine events
    BEST_MOVE = EventFactory('EVT_BEST_MOVE', ['move', 'ponder', 'inbook'])
    NEW_PV = EventFactory('EVT_NEW_PV', ['pv'])
    NEW_SCORE = EventFactory('EVT_NEW_SCORE', ['score', 'mate'])
    NEW_DEPTH = EventFactory('EVT_NEW_DEPTH', ['depth'])
    
    # User events
    KEYBOARD_BUTTON = EventFactory('EVT_KEYBOARD_BUTTON', ['button', 'dev'])
    NEW_GAME = EventFactory('EVT_NEW_GAME', ['pos960'])
    LEVEL = EventFactory('EVT_LEVEL', ['options', 'level_text', 'level_name'])
    
    # Time events
    OUT_OF_TIME = EventFactory('EVT_OUT_OF_TIME', ['color'])
    CLOCK_TIME = EventFactory('EVT_CLOCK_TIME', ['time_white', 'time_black', 'dev', 'connect'])
    
    # System events
    SHUTDOWN = EventFactory('EVT_SHUTDOWN', ['dev'])
    REBOOT = EventFactory('EVT_REBOOT', ['dev'])
```

---

## Threading Model

### Input Sources (Producers)
Each input source runs in its own thread:

```python
class DgtBoard(threading.Thread):
    """Board FEN reading thread"""
    
    def run(self):
        while True:
            fen = self.read_board_position()  # Blocking read
            Observable.fire(Event.FEN(fen=fen))

class EngineHandler:
    """Engine callbacks run in engine thread"""
    
    def on_best_move(self, result):
        # Called by engine thread when search completes
        Observable.fire(Event.BEST_MOVE(
            move=result.bestmove,
            ponder=result.ponder,
            inbook=False
        ))

class TimeControl:
    """Timer thread for time control"""
    
    def _out_of_time_callback(self):
        # Called by timer thread when time expires
        Observable.fire(Event.OUT_OF_TIME(color=self.active_color))
```

### Main Loop (Consumer)
Single thread processes all events:

```python
# Main thread runs event loop
main_thread = threading.Thread(target=main_event_loop)
main_thread.start()
```

### Output Handlers (Consumers)
Each output device runs in its own thread:

```python
class DgtHw(threading.Thread):
    """Serial clock output thread"""
    
    def run(self):
        while True:
            command = dispatch_queue.get()
            self.process_command(command)

class PgnDisplay(threading.Thread):
    """PGN recorder thread"""
    
    def run(self):
        while True:
            message = self.msg_queue.get()
            self.process_message(message)
```

---

## Thread Safety

### Queue Operations
Python's `queue.Queue` is thread-safe, so no additional locking needed:

```python
# Thread-safe - no lock needed
evt_queue.put(event)
event = evt_queue.get()
```

### Shared State
Any shared state requires locking:

```python
import threading

class GameState:
    def __init__(self):
        self.board = chess.Board()
        self.lock = threading.Lock()
    
    def make_move(self, move):
        with self.lock:
            self.board.push(move)
    
    def get_fen(self):
        with self.lock:
            return self.board.fen()
```

### Deep Copying
Always deep copy objects when putting on queues:

```python
# WRONG - mutations in one thread affect others
evt_queue.put(game_state)

# CORRECT - each thread gets independent copy
evt_queue.put(copy.deepcopy(game_state))
```

---

## Event Processing Patterns

### Pattern 1: Simple Handler
```python
def handle_new_game_event(event):
    """Reset game state"""
    game = chess.Board()
    if event.pos960 != 518:
        game.set_chess960_pos(event.pos960)
    
    engine.newgame(game)
    time_control.reset()
    
    DisplayMsg.show(Message.START_NEW_GAME(game=game, newgame=True))
```

### Pattern 2: State Machine
```python
def handle_fen_event(event):
    """Process FEN with state machine"""
    
    if event.fen == game.board_fen():
        # State: SAME_POSITION
        return
    
    elif event.fen in legal_fens:
        # State: LEGAL_MOVE
        move = get_move_from_fen(event.fen)
        execute_move(move)
    
    elif event.fen in last_legal_fens:
        # State: SLIDING
        handle_sliding(event.fen)
    
    elif event.fen == done_computer_fen:
        # State: COMPUTER_MOVE_DONE
        confirm_computer_move()
    
    else:
        # State: INVALID or TAKEBACK
        handle_invalid_or_takeback(event.fen)
```

### Pattern 3: Async Trigger
```python
def handle_best_move_event(event):
    """Handle engine's best move"""
    
    # Stop clock
    time_control.stop_internal()
    
    # Display move (don't execute yet - wait for user)
    DisplayMsg.show(Message.COMPUTER_MOVE(
        move=event.move,
        ponder=event.ponder,
        game=game.copy(),
        wait=True
    ))
    
    # Store for later execution
    done_computer_fen = get_fen_after_move(game, event.move)
    done_move = event.move
    ponder_move = event.ponder
```

---

## Error Handling

### Event Loop Protection
```python
def main_event_loop():
    while True:
        try:
            event = evt_queue.get()
            process_event(event)
            evt_queue.task_done()
        
        except KeyboardInterrupt:
            logging.info('Shutting down gracefully')
            break
        
        except Exception as e:
            logging.error('Event processing error: %s', e, exc_info=True)
            # Continue processing - don't let one error kill the system
            evt_queue.task_done()
```

### Producer Protection
```python
class DgtBoard(threading.Thread):
    def run(self):
        while True:
            try:
                fen = self.read_board()
                Observable.fire(Event.FEN(fen=fen))
            
            except SerialException as e:
                logging.error('Board communication error: %s', e)
                time.sleep(1)  # Wait before retrying
            
            except Exception as e:
                logging.error('Unexpected error: %s', e, exc_info=True)
```

---

## Performance Considerations

### Queue Size
```python
# Unlimited queue (default) - may consume memory
evt_queue = queue.Queue()

# Limited queue - blocks producers when full
evt_queue = queue.Queue(maxsize=100)
```

### Event Priority
```python
# Use PriorityQueue for critical events
from queue import PriorityQueue

priority_queue = PriorityQueue()

# Lower number = higher priority
priority_queue.put((0, critical_event))  # Process first
priority_queue.put((10, normal_event))   # Process later
```

### Timeout Handling
```python
try:
    # Don't block forever
    event = evt_queue.get(timeout=1.0)
except queue.Empty:
    # No events in 1 second - check system health
    check_hardware_connection()
```

---

## Benefits of Event-Driven Architecture

### 1. Decoupling
- Features don't know about each other
- Easy to add/remove features
- Hardware-independent logic

### 2. Testability
- Mock events for testing
- No need for actual hardware
- Reproducible test scenarios

### 3. Flexibility
- Easy to add new input devices
- Easy to add new output devices
- Features work with any I/O combination

### 4. Robustness
- One component failure doesn't crash system
- Easy to implement retries
- Clear error boundaries

### 5. Maintainability
- Each component has clear responsibility
- Easy to trace message flow
- Simple debugging with event logging

---

## Common Patterns

### Fire and Forget
```python
# Producer doesn't wait for result
Observable.fire(Event.NEW_GAME(pos960=518))
```

### Request-Response
```python
# Producer waits for result
engine.go(...)
result = engine.stop()  # Blocking call returns result
```

### Publish-Subscribe
```python
# Multiple consumers receive same message
DisplayMsg.show(Message.USER_MOVE_DONE(...))
# -> PGN recorder gets it
# -> Voice announcer gets it
# -> Web interface gets it
```

---

## Summary

The event system is the foundation that makes PicoChess flexible and maintainable:

1. **Three queues** separate concerns (input, output, broadcast)
2. **Thread-safe** communication between components
3. **Decoupled** features for maximum flexibility
4. **Observable pattern** for firing events
5. **Single consumer** main loop for state consistency

When recreating this system, maintain these principles for the same benefits.
