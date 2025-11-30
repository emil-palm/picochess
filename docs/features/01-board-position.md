# Board Position Management

## Overview
Handles FEN (Forsyth-Edwards Notation) strings from the electronic board and manages game state transitions including move validation, sliding detection, and takeback.

---

## Purpose
Translate physical board state into game state, validating moves and handling edge cases like:
- Piece sliding (user moving piece around before settling)
- Takebacks (returning to previous position)
- Invalid positions (illegal placements)

---

## Key Components

### 1. FEN Processing
```python
import chess

class BoardPositionManager:
    """Manages board positions and legal moves"""
    
    def __init__(self):
        self.game = chess.Board()
        self.legal_fens = []          # FENs reachable from current position
        self.last_legal_fens = []     # FENs from previous position (for sliding)
        self.done_computer_fen = None # Expected FEN after computer move
```

### 2. Legal FEN Pre-computation
Pre-compute all legal FEN strings to quickly recognize moves:

```python
def compute_legal_fens(self, board: chess.Board) -> list:
    """
    Generate FEN strings for all legal moves.
    This is key to fast move recognition!
    """
    fens = []
    for move in board.legal_moves:
        board.push(move)
        fens.append(board.board_fen())  # Only board, no move counters
        board.pop()
    return fens
```

### 3. FEN State Machine
```python
def process_fen(self, received_fen: str):
    """
    State machine for FEN processing.
    Returns: (state, data)
    """
    
    # State 1: Same position (no change)
    if received_fen == self.game.board_fen():
        return ("SAME", None)
    
    # State 2: Sliding - piece being moved
    # (FEN from last legal position)
    elif received_fen in self.last_legal_fens:
        move_index = self.last_legal_fens.index(received_fen)
        move = list(self.game.legal_moves)[move_index]
        return ("SLIDING", move)
    
    # State 3: Legal move
    elif received_fen in self.legal_fens:
        move_index = self.legal_fens.index(received_fen)
        move = list(self.game.legal_moves)[move_index]
        
        # Update state
        self.last_legal_fens = self.legal_fens.copy()
        self.game.push(move)
        self.legal_fens = self.compute_legal_fens(self.game)
        
        return ("LEGAL_MOVE", move)
    
    # State 4: Computer move executed by user
    elif received_fen == self.done_computer_fen:
        return ("COMPUTER_MOVE_DONE", self.done_move)
    
    # State 5: Takeback to previous position
    else:
        game_copy = self.game.copy()
        while game_copy.move_stack:
            game_copy.pop()
            if game_copy.board_fen() == received_fen:
                # Revert game to this position
                moves_to_undo = len(self.game.move_stack) - len(game_copy.move_stack)
                for _ in range(moves_to_undo):
                    self.game.pop()
                return ("TAKEBACK", moves_to_undo)
        
        # State 6: Invalid position
        return ("INVALID", None)
```

---

## Sliding Detection

### Why It Matters
When user picks up a piece and slides it across the board, the hardware may detect intermediate positions. We need to:
1. Detect this is happening
2. Not start multiple move attempts
3. Wait for stable position

### Implementation
```python
class BoardPositionManager:
    def __init__(self):
        # ... other init ...
        self.field_timer = None
        self.field_timer_running = False
        self.low_time = False  # Set by time control when < 60s
    
    def start_field_timer(self):
        """Wait for board position to stabilize"""
        # Shorter wait in time pressure
        if self.low_time:
            wait = 0.10  # 100ms in bullet time
        else:
            wait = 0.25  # 250ms normally
        
        if self.field_timer_running:
            # Position changed again - cancel old timer
            self.field_timer.cancel()
        
        self.field_timer = Timer(wait, self.field_timer_expired)
        self.field_timer.start()
        self.field_timer_running = True
    
    def field_timer_expired(self):
        """Position stable - process it"""
        self.field_timer_running = False
        # Now request board FEN from hardware
        self.request_board_fen()
```

### Configurable Sliding Factor
```python
# picochess.ini setting
slow_slide = 0  # 0-9, adds delay

# In field timer calculation
wait = 0.25 + (0.03 * self.slow_slide_factor)
```

---

## Takeback Handling

```python
def handle_takeback(self, target_fen: str):
    """
    Allow user to take back moves to any previous position.
    Just place pieces in old position on board.
    """
    # Stop any ongoing search/clock
    engine.stop()
    time_control.stop_internal()
    
    # Revert to that position
    # (already done in process_fen)
    
    # Reset move caches
    self.done_computer_fen = None
    self.done_move = None
    self.legal_fens = self.compute_legal_fens(self.game)
    self.last_legal_fens = []
    
    # Fire takeback event
    fire_event(Event.TAKE_BACK(game=self.game.copy()))
```

---

## Integration with Other Features

### With Engine
```python
def handle_sliding_during_search(self, move):
    """User sliding while engine thinking"""
    
    # In NORMAL/BRAIN mode, if computer's turn
    if is_computer_turn() and engine.is_thinking():
        engine.stop()  # Stop search
        self.game.pop()  # Undo last move
        # User can make different move
```

### With Time Control
```python
def handle_move(self, move):
    """Execute validated move"""
    
    # Stop clock if running
    if time_control.is_running():
        time_control.stop_internal()
    
    # Execute move
    self.game.push(move)
    
    # Add increment (Fischer mode)
    time_control.add_increment(not self.game.turn)
    
    # Start opponent's clock
    time_control.start_internal(self.game.turn)
```

---

## Error Handling

### Invalid FEN Timer
```python
def handle_invalid_fen(self, fen):
    """
    Invalid position detected.
    Wait 3 seconds before showing error (might be in transition).
    """
    
    # Start error timer
    self.error_fen = fen
    self.fen_error_timer = Timer(3.0, self.show_fen_error)
    self.fen_error_timer.start()

def show_fen_error(self):
    """Show error after delay if FEN still invalid"""
    if self.error_fen:
        display.show_text("Wrong FEN")
        self.error_fen = None
```

---

## Performance Optimization

### Pre-computation Strategy
```python
# Instead of: checking if move legal on each FEN
#   O(n) where n = number of legal moves
for fen in legal_fens:
    if fen == received_fen:
        # Found it
        
# We use: pre-computed FEN list with index lookup
#   O(1) average case with Python list.index()
fens = compute_legal_fens(board)  # Done once per position
if received_fen in fens:
    move_index = fens.index(received_fen)
    move = list(board.legal_moves)[move_index]
```

### Typical Performance
- FEN computation: ~10ms for average position
- FEN validation: <1ms (list lookup)
- Move execution: <1ms

---

## Dependencies

### Required By
- **Time Control**: Needs to know when moves happen
- **Engine**: Needs position updates
- **Display**: Shows current position
- **PGN**: Records moves

### Requires
- **Chess library**: For board representation and validation
- **Event system**: To fire move events

### Optional
- **Board hardware**: Physical board (could use virtual/web)

---

## Testing

### Unit Tests
```python
def test_legal_move_detection():
    mgr = BoardPositionManager()
    mgr.legal_fens = mgr.compute_legal_fens(mgr.game)
    
    # Make e2-e4
    mgr.game.push(chess.Move.from_uci('e2e4'))
    fen = mgr.game.board_fen()
    mgr.game.pop()
    
    state, move = mgr.process_fen(fen)
    assert state == "LEGAL_MOVE"
    assert move == chess.Move.from_uci('e2e4')

def test_sliding_detection():
    mgr = BoardPositionManager()
    mgr.legal_fens = mgr.compute_legal_fens(mgr.game)
    
    # Execute move
    mgr.process_fen(fen_after_e4)
    
    # Now try old position again (sliding)
    state, move = mgr.process_fen(fen_after_e4)
    assert state == "SLIDING"

def test_takeback():
    mgr = BoardPositionManager()
    # Make several moves
    mgr.game.push_san('e4')
    mgr.game.push_san('e5')
    mgr.game.push_san('Nf3')
    
    # Takeback to start
    state, _ = mgr.process_fen(chess.STARTING_FEN)
    assert state == "TAKEBACK"
    assert len(mgr.game.move_stack) == 0
```

---

## Common Issues & Solutions

### Issue: Multiple move attempts during sliding
**Solution**: Use field timer with delay

### Issue: Valid position not recognized
**Solution**: Ensure FEN comparison uses board_fen() not full FEN (which includes move counters)

### Issue: Takeback not working
**Solution**: Ensure move history is maintained in game object

### Issue: Slow FEN validation
**Solution**: Pre-compute legal FENs, don't validate each time

---

## Summary

Board Position Management is the foundation feature:
- Translates board state to game state
- Validates moves before execution
- Handles edge cases (sliding, takeback)
- Must be fast (<100ms) for good UX
- Pre-computation is key to performance

**Next Steps**: Once board position works, add [UCI Engine](02-engine-uci.md) to get computer moves.
