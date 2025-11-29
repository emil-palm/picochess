# PicoChess Feature Analysis and Recreation Guide

## Executive Summary

PicoChess is a comprehensive chess computer system that interfaces physical DGT electronic chess boards with UCI chess engines. It provides a complete chess playing experience with time controls, opening books, voice announcements, web interface, and PGN game recording.

## Architecture Overview

### Core Design Pattern: Event-Driven Architecture

PicoChess uses a message-passing architecture with three main queues:
1. **evt_queue**: Events from input devices (board, buttons, engine)
2. **dispatch_queue**: Commands to output devices (clock, display, LEDs)
3. **msg_queue**: Messages for display/notification systems

```python
# Example: Event-driven architecture
from queue import Queue
import threading

# Central event queues
event_queue = Queue()
dispatch_queue = Queue()
message_queue = Queue()

class EventDispatcher:
    """Observable pattern for event distribution"""
    @staticmethod
    def fire(event):
        event_queue.put(event)

class MessageBroadcaster:
    """Broadcast messages to all registered displays"""
    registered_displays = []
    
    @staticmethod
    def show(message):
        for display in registered_displays:
            display.queue.put(message)
```

---

## Feature 1: Board Position Management

### Description
Handles FEN (Forsyth-Edwards Notation) strings from the electronic board and manages game state transitions including move validation, sliding detection, and takeback.

### Key Components
- FEN validation and comparison
- Legal move computation
- Sliding move detection
- Position takeback/undo

### Implementation Guide

```python
import chess

class BoardPositionManager:
    """Manages board positions and legal moves"""
    
    def __init__(self):
        self.game = chess.Board()
        self.legal_fens = []
        self.last_legal_fens = []
        self.done_computer_fen = None
        
    def compute_legal_fens(self, board: chess.Board) -> list:
        """
        Generate FEN strings for all legal moves from current position.
        Used to recognize when user makes a move.
        """
        fens = []
        for move in board.legal_moves:
            board.push(move)
            fens.append(board.board_fen())  # Only board part, no metadata
            board.pop()
        return fens
    
    def process_fen(self, received_fen: str):
        """
        Process a FEN string from the board.
        Determines if it's: same position, legal move, sliding, or takeback
        """
        # Case 1: Same position (no change)
        if received_fen == self.game.board_fen():
            return "SAME_POSITION"
            
        # Case 2: Sliding - user is moving piece (in last legal positions)
        elif received_fen in self.last_legal_fens:
            # User started moving but changed their mind
            move_index = self.last_legal_fens.index(received_fen)
            move = list(self.game.legal_moves)[move_index]
            return "SLIDING", move
            
        # Case 3: Legal move from current position
        elif received_fen in self.legal_fens:
            move_index = self.legal_fens.index(received_fen)
            move = list(self.game.legal_moves)[move_index]
            self.last_legal_fens = self.legal_fens.copy()
            self.game.push(move)
            self.legal_fens = self.compute_legal_fens(self.game)
            return "LEGAL_MOVE", move
            
        # Case 4: Computer move was executed on board
        elif received_fen == self.done_computer_fen:
            return "COMPUTER_MOVE_DONE"
            
        # Case 5: Takeback - position exists in game history
        else:
            game_copy = self.game.copy()
            while game_copy.move_stack:
                game_copy.pop()
                if game_copy.board_fen() == received_fen:
                    # Found in history, revert to this position
                    while len(game_copy.move_stack) < len(self.game.move_stack):
                        self.game.pop()
                    return "TAKEBACK", len(self.game.move_stack)
            
            return "INVALID_POSITION"
    
    def handle_sliding(self, move: chess.Move):
        """
        Handle case where user picks up piece and moves it around.
        Important for preventing multiple move attempts during sliding.
        """
        # If computer is thinking, stop the search
        # If computer move is displayed, revert game state
        pass
```

### Dependencies
- **Input**: FEN strings from board hardware
- **Output**: Move validation, game state updates
- **Related**: Time control (must pause during invalid positions), Engine search (must stop on sliding)

---

## Feature 2: UCI Engine Management

### Description
Manages UCI (Universal Chess Interface) chess engines including initialization, level configuration, search control, and pondering.

### Key Components
- Engine process management (local or remote SSH)
- UCI option configuration
- Asynchronous search with callbacks
- Permanent brain (pondering on opponent's time)

### Implementation Guide

```python
import chess.uci
from subprocess import DEVNULL

class ChessEngine:
    """Manages UCI chess engine communication"""
    
    def __init__(self, engine_path: str, remote_shell=None):
        """
        Initialize engine (local or remote).
        remote_shell: SSH shell connection for remote engines
        """
        if remote_shell:
            self.engine = chess.uci.spur_spawn_engine(remote_shell, [engine_path])
        else:
            self.engine = chess.uci.popen_engine(engine_path, stderr=DEVNULL)
        
        self.engine.uci()  # Initialize UCI protocol
        self.options = {}
        self.current_search = None
        
    def configure_level(self, level_options: dict):
        """
        Configure engine strength/level.
        level_options example:
        {
            'Skill Level': '10',
            'UCI_LimitStrength': 'true',
            'UCI_Elo': '1500'
        }
        """
        self.engine.setoption(level_options)
        
    def search(self, board: chess.Board, time_control: dict, callback):
        """
        Start asynchronous search.
        time_control example:
        {
            'wtime': '300000',  # milliseconds
            'btime': '300000',
            'winc': '2000',     # Fischer increment
            'binc': '2000'
        }
        """
        self.engine.position(board)
        self.current_search = self.engine.go(
            async_callback=callback,
            **time_control
        )
        return self.current_search
    
    def permanent_brain(self, board: chess.Board, ponder_move: chess.Move, time_control: dict):
        """
        Permanent brain: Think on opponent's time.
        Makes ponder_move and starts thinking.
        """
        board_copy = board.copy()
        board_copy.push(ponder_move)
        self.engine.position(board_copy)
        
        self.current_search = self.engine.go(
            ponder=True,
            async_callback=self._brain_callback,
            **time_control
        )
        
    def ponder_hit(self):
        """
        Called when opponent makes the expected ponder move.
        Converts pondering into actual search.
        """
        self.engine.ponderhit()
    
    def stop(self):
        """Stop current search and wait for result"""
        if not self.engine.idle:
            self.engine.stop()
        return self.current_search.result() if self.current_search else None
    
    def new_game(self, board: chess.Board):
        """Signal engine that new game started"""
        self.engine.ucinewgame()
        self.engine.position(board)
        
    def set_mode(self, ponder: bool, analyse: bool):
        """
        Set engine mode.
        - Normal: ponder=False, analyse=False
        - Brain: ponder=True, analyse=False
        - Analysis: ponder=False, analyse=True
        """
        self.engine.setoption({
            'Ponder': ponder,
            'UCI_AnalyseMode': analyse
        })
```

### Engine Level Configuration

Engines support different level systems:
```python
# Example: Reading engine configuration from .uci file
# a-stockfish.uci content:
# [Level-1]
# Skill Level=0
# [Level-2]
# Skill Level=5
# ...

import configparser

def read_engine_levels(engine_file: str):
    """Read available levels from engine .uci config file"""
    parser = configparser.ConfigParser()
    parser.optionxform = str  # Case sensitive
    parser.read(engine_file + '.uci')
    
    levels = {}
    for section in parser.sections():
        levels[section] = dict(parser[section])
    return levels
```

### Dependencies
- **Input**: Board position, time control, level settings
- **Output**: Best moves, analysis scores, PV (Principal Variation)
- **Related**: Time control (provides time parameters), Opening books (alternative to engine in opening)

---

## Feature 3: Time Control System

### Description
Comprehensive time management supporting Fixed time, Blitz, and Fischer (increment) modes with internal clock tracking and synchronization with external DGT clock.

### Key Components
- Three time modes: Fixed, Blitz, Fischer
- Internal time tracking with threads
- Clock synchronization
- Out-of-time detection

### Implementation Guide

```python
import time
import threading
import chess

class TimeMode:
    FIXED = 'fixed'      # Seconds per move
    BLITZ = 'blitz'      # Minutes per game
    FISCHER = 'fischer'  # Minutes + increment

class TimeControl:
    """Manages chess clock times"""
    
    def __init__(self, mode, fixed=0, blitz=0, fischer=0):
        """
        Initialize time control.
        - Fixed: fixed seconds per move
        - Blitz: blitz minutes for entire game
        - Fischer: blitz minutes + fischer seconds increment per move
        """
        self.mode = mode
        self.move_time = fixed      # seconds per move (Fixed mode)
        self.game_time = blitz       # minutes per game (Blitz/Fischer)
        self.increment = fischer     # seconds increment (Fischer mode)
        
        # Internal tracking
        self.clock_time = {
            chess.WHITE: 0,
            chess.BLACK: 0
        }
        self.internal_time = {
            chess.WHITE: 0.0,
            chess.BLACK: 0.0
        }
        
        self.timer = None
        self.active_color = None
        self.start_time = None
        
        self.reset()
    
    def reset(self):
        """Initialize clock times based on mode"""
        if self.mode == TimeMode.BLITZ:
            self.clock_time[chess.WHITE] = self.game_time * 60
            self.clock_time[chess.BLACK] = self.game_time * 60
            
        elif self.mode == TimeMode.FISCHER:
            # Add increment to initial time
            self.clock_time[chess.WHITE] = self.game_time * 60 + self.increment
            self.clock_time[chess.BLACK] = self.game_time * 60 + self.increment
            
        elif self.mode == TimeMode.FIXED:
            self.clock_time[chess.WHITE] = self.move_time
            self.clock_time[chess.BLACK] = self.move_time
        
        self.internal_time = {
            chess.WHITE: float(self.clock_time[chess.WHITE]),
            chess.BLACK: float(self.clock_time[chess.BLACK])
        }
        self.active_color = None
    
    def start_internal(self, color):
        """
        Start internal clock for given color.
        Spawns thread to trigger OUT_OF_TIME event.
        """
        if self.mode in (TimeMode.BLITZ, TimeMode.FISCHER):
            self.active_color = color
            self.start_time = time.time()
            
            # Start timeout thread
            if self.internal_time[color] > 0:
                self.timer = threading.Timer(
                    self.internal_time[color],
                    self._out_of_time,
                    [self.internal_time[color]]
                )
                self.timer.start()
    
    def stop_internal(self):
        """Stop internal clock and update remaining time"""
        if self.timer and self.mode in (TimeMode.BLITZ, TimeMode.FISCHER):
            self.timer.cancel()
            
            # Calculate used time
            used_time = time.time() - self.start_time
            self.internal_time[self.active_color] -= used_time
            
            if self.internal_time[self.active_color] < 0:
                self.internal_time[self.active_color] = 0
            
            self.active_color = None
    
    def add_increment(self, color):
        """Add increment after move (Fischer mode)"""
        if self.mode == TimeMode.FISCHER:
            self.internal_time[color] += self.increment
            self.clock_time[color] += self.increment
            
        elif self.mode == TimeMode.FIXED:
            # Reset to full time for next move
            self.reset()
    
    def _out_of_time(self, initial_time):
        """Called by timer thread when time expires"""
        if self.mode == TimeMode.FIXED:
            # In Fixed mode, no out-of-time event (just take longer)
            return
            
        if self.active_color is not None:
            # Fire OUT_OF_TIME event
            self.fire_event_out_of_time(self.active_color)
    
    def to_uci_dict(self):
        """
        Convert to UCI time parameters for engine.
        Returns dict with wtime, btime, winc, binc, or movetime.
        """
        if self.mode in (TimeMode.BLITZ, TimeMode.FISCHER):
            result = {
                'wtime': str(int(self.internal_time[chess.WHITE] * 1000)),
                'btime': str(int(self.internal_time[chess.BLACK] * 1000))
            }
            
            if self.mode == TimeMode.FISCHER:
                result['winc'] = str(self.increment * 1000)
                result['binc'] = str(self.increment * 1000)
                
            return result
            
        elif self.mode == TimeMode.FIXED:
            return {'movetime': str(self.move_time * 1000)}
    
    def get_display_time(self):
        """Get times for clock display"""
        return (
            int(self.internal_time[chess.WHITE]),
            int(self.internal_time[chess.BLACK])
        )
```

### Usage Example

```python
# Blitz: 5 minutes per game
tc = TimeControl(TimeMode.BLITZ, blitz=5)

# Fischer: 3 minutes + 2 seconds increment
tc = TimeControl(TimeMode.FISCHER, blitz=3, fischer=2)

# Fixed: 10 seconds per move
tc = TimeControl(TimeMode.FIXED, fixed=10)

# When player moves:
tc.stop_internal()          # Stop their clock
tc.add_increment(chess.WHITE)  # Add increment if Fischer
tc.start_internal(chess.BLACK) # Start opponent's clock

# For UCI engine:
engine_time_params = tc.to_uci_dict()
```

### Dependencies
- **Input**: Move events from board, clock synchronization messages
- **Output**: Clock display updates, OUT_OF_TIME events
- **Related**: Engine (provides time for search), Display (shows remaining time)

---

## Feature 4: Opening Book Support

### Description
Uses polyglot opening book format to provide book moves in opening phase, with alternative move selection and book exit detection.

### Key Components
- Polyglot format reading
- Weighted move selection
- Alternative move exclusion
- Book/Engine transition

### Implementation Guide

```python
import chess.polyglot

class OpeningBookManager:
    """Manages opening book and alternative moves"""
    
    def __init__(self, book_path: str):
        """
        Initialize with polyglot book file.
        Example files: varied.bin, performance.bin, etc.
        """
        self.book_reader = chess.polyglot.open_reader(book_path)
        self.excluded_moves = set()
    
    def get_book_move(self, board: chess.Board):
        """
        Get a move from opening book.
        Returns: (move, ponder_move) or None if out of book
        """
        try:
            # Get weighted random choice from book
            # Excludes previously tried alternatives
            entry = self.book_reader.weighted_choice(
                board,
                exclude_moves=self.excluded_moves
            )
            
            if entry is None:
                return None
            
            book_move = entry.move()
            
            # Add to excluded moves for alternative move feature
            self.excluded_moves.add(book_move)
            
            # Try to get ponder move (expected response)
            board_copy = board.copy()
            board_copy.push(book_move)
            
            try:
                ponder_entry = self.book_reader.weighted_choice(board_copy)
                ponder_move = ponder_entry.move() if ponder_entry else None
            except IndexError:
                ponder_move = None
            
            return book_move, ponder_move
            
        except IndexError:
            # No book moves available
            return None
    
    def reset_alternatives(self):
        """Clear excluded moves (after position change)"""
        self.excluded_moves = set()
    
    def get_all_book_moves(self, board: chess.Board):
        """Get all available book moves with weights"""
        moves = []
        for entry in self.book_reader.find_all(board):
            moves.append({
                'move': entry.move(),
                'weight': entry.weight,
                'learn': entry.learn
            })
        return moves

# Configuration file example (books.ini):
"""
[a-nobook.bin]
small = no book
medium = No Book
large = No Book

[h-varied.bin]
small = varied
medium = Varied
large = Varied

[k-stfish.bin]
small = stockfish
medium = Stockfish
large = Stockfish Book
"""

def load_opening_books():
    """Load all available opening books from config"""
    import configparser
    
    config = configparser.ConfigParser()
    config.read('books/books.ini')
    
    books = []
    for section in config.sections():
        books.append({
            'file': f'books/{section}',
            'name': config[section]['large'],
            'small': config[section]['small'],
            'medium': config[section]['medium']
        })
    return books
```

### Usage Example

```python
# Initialize book
book_mgr = OpeningBookManager('books/varied.bin')

# In game loop, try book first before engine
def get_move(board, time_control):
    # Try opening book
    book_result = book_mgr.get_book_move(board)
    
    if book_result:
        move, ponder = book_result
        print(f"Book move: {move}")
        return move, ponder, True  # inbook=True
    else:
        # Out of book, use engine
        print("Out of book, using engine")
        return engine.search(board, time_control)

# Alternative move feature
def request_alternative_move(board):
    """User wants different book move"""
    # Current move already excluded
    book_result = book_mgr.get_book_move(board)
    
    if book_result:
        return book_result  # Alternative book move
    else:
        # No more book alternatives, ask engine
        book_mgr.reset_alternatives()
        return None
```

### Dependencies
- **Input**: Current board position
- **Output**: Book moves or None (triggers engine)
- **Related**: Engine (fallback when out of book), Alternative moves (excludes moves)

---

## Feature 5: Interaction Modes

### Description
Seven different modes controlling how the system responds to moves and manages player/computer interaction.

### Modes Description

```python
class InteractionMode:
    NORMAL = 'normal'         # Play against computer
    BRAIN = 'brain'           # Computer ponders on your time
    ANALYSIS = 'analysis'     # Computer continuously analyzes
    KIBITZ = 'kibitz'         # Like analysis but different display
    OBSERVE = 'observe'       # Watch two players, computer analyzes
    REMOTE = 'remote'         # Play against remote opponent
    PONDER = 'ponder'         # Computer shows its thinking
```

### Mode Behaviors

| Mode | Computer Plays | Computer Thinks on Your Time | Shows Analysis | Clock Runs |
|------|---------------|------------------------------|----------------|------------|
| NORMAL | Yes | No | No | Yes |
| BRAIN | Yes | Yes (Permanent brain) | No | Yes |
| ANALYSIS | No | Yes (Continuous) | Yes (PV/Score) | No |
| KIBITZ | No | Yes (Continuous) | Yes (Different format) | No |
| OBSERVE | No | Yes (Continuous) | Yes | Yes |
| REMOTE | No (Remote does) | No | No | Yes |
| PONDER | No | Yes (Continuous) | Yes (Extended) | No |

### Implementation Guide

```python
class GameController:
    """Manages game flow based on interaction mode"""
    
    def __init__(self):
        self.mode = InteractionMode.NORMAL
        self.play_mode = PlayMode.USER_WHITE
    
    def handle_user_move(self, move, board, engine, time_control):
        """Handle user move based on current mode"""
        
        if self.mode == InteractionMode.NORMAL:
            # Normal: Stop clock, make move, start engine thinking
            time_control.stop_internal()
            board.push(move)
            
            if self._is_computer_turn(board.turn):
                time_control.start_internal(board.turn)
                engine.search(board, time_control.to_uci_dict())
            else:
                time_control.start_internal(board.turn)
        
        elif self.mode == InteractionMode.BRAIN:
            # Brain mode with permanent brain (pondering)
            time_control.stop_internal()
            
            # Check if move matches ponder move (ponder hit)
            if move == engine.ponder_move:
                print("Ponder hit!")
                engine.ponder_hit()  # Continue with same search
            else:
                print("Ponder miss")
                engine.stop()  # Stop pondering
                board.push(move)
                time_control.start_internal(board.turn)
                engine.search(board, time_control.to_uci_dict())
            
        elif self.mode == InteractionMode.ANALYSIS:
            # Analysis: Just analyze position continuously
            engine.stop()
            board.push(move)
            engine.analyze(board)  # Infinite analysis
            
        elif self.mode == InteractionMode.OBSERVE:
            # Observe: Like analysis but clock runs
            engine.stop()
            board.push(move)
            time_control.start_internal(board.turn)
            engine.analyze(board)
            
        elif self.mode == InteractionMode.REMOTE:
            # Remote: Wait for remote move, clock runs
            time_control.stop_internal()
            board.push(move)
            
            if self._is_remote_turn(board.turn):
                time_control.start_internal(board.turn)
                # Wait for remote move from network
            else:
                time_control.start_internal(board.turn)
    
    def set_engine_mode(self, engine):
        """Configure engine based on interaction mode"""
        ponder = (self.mode == InteractionMode.BRAIN)
        analyse = (self.mode in [
            InteractionMode.ANALYSIS,
            InteractionMode.KIBITZ,
            InteractionMode.OBSERVE,
            InteractionMode.PONDER
        ])
        
        engine.set_mode(ponder=ponder, analyse=analyse)
    
    def _is_computer_turn(self, turn):
        """Check if it's computer's turn (NORMAL/BRAIN mode)"""
        if self.play_mode == PlayMode.USER_WHITE:
            return turn == chess.BLACK
        else:
            return turn == chess.WHITE
```

### Mode Switching

```python
def switch_mode(new_mode, current_game_state):
    """Switch interaction mode safely"""
    
    # Can't switch to analysis modes with computer move displayed
    if new_mode not in (InteractionMode.NORMAL, InteractionMode.REMOTE):
        if current_game_state.computer_move_displayed:
            return False, "Cannot switch to analysis mode with move displayed"
    
    # Stop any ongoing activity
    engine.stop()
    time_control.stop_internal()
    
    # Configure new mode
    controller.mode = new_mode
    controller.set_engine_mode(engine)
    
    # Restart appropriate analysis/pondering
    if new_mode in (InteractionMode.ANALYSIS, InteractionMode.KIBITZ, 
                    InteractionMode.PONDER, InteractionMode.OBSERVE):
        engine.analyze(board)
    elif new_mode == InteractionMode.BRAIN:
        # Start permanent brain if computer already moved
        if not current_game_state.computer_move_displayed:
            engine.permanent_brain(board, ponder_move, time_control)
    
    return True, "Mode switched successfully"
```

### Dependencies
- **Input**: User moves, mode selection
- **Output**: Engine search behavior, clock behavior
- **Related**: Engine (mode affects search type), Time control (some modes don't use clock), Display (different info shown)

---

## Feature 6: PGN Game Recording and Email

### Description
Records games in PGN (Portable Game Notation) format with headers, sends via email (SMTP or Mailgun), and maintains game history.

### Implementation Guide

```python
import chess.pgn
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

class PGNRecorder:
    """Records games in PGN format"""
    
    def __init__(self, pgn_file: str, player_name: str, player_elo: str):
        self.pgn_file = pgn_file
        self.player_name = player_name
        self.player_elo = player_elo
        
        self.engine_name = "Unknown"
        self.engine_elo = "-"
        self.level_name = ""
        self.game_start_time = None
    
    def start_new_game(self):
        """Called when new game starts"""
        self.game_start_time = datetime.datetime.now()
    
    def save_game(self, game: chess.Board, result, play_mode):
        """
        Save game to PGN file at game end.
        
        result: GameResult enum (WIN_WHITE, WIN_BLACK, DRAW, etc.)
        play_mode: Who was playing white (USER_WHITE or USER_BLACK)
        """
        if not game.move_stack:
            # No moves, don't save
            return
        
        # Create PGN game from board
        pgn_game = chess.pgn.Game().from_board(game)
        
        # Set standard headers
        pgn_game.headers['Event'] = 'PicoChess Game'
        pgn_game.headers['Site'] = 'Location'  # Could be IP or physical location
        pgn_game.headers['Date'] = datetime.date.today().strftime('%Y.%m.%d')
        pgn_game.headers['Time'] = self.game_start_time.strftime('%H:%M:%S')
        
        # Set result
        if result == GameResult.DRAW:
            pgn_game.headers['Result'] = '1/2-1/2'
        elif result == GameResult.WIN_WHITE:
            pgn_game.headers['Result'] = '1-0'
        elif result == GameResult.WIN_BLACK:
            pgn_game.headers['Result'] = '0-1'
        elif result == GameResult.OUT_OF_TIME:
            # Whoever's turn it is lost on time
            pgn_game.headers['Result'] = '0-1' if game.turn == chess.WHITE else '1-0'
        else:
            pgn_game.headers['Result'] = '*'
        
        # Set players based on play mode
        engine_label = f"{self.engine_name} ({self.level_name})" if self.level_name else self.engine_name
        
        if play_mode == PlayMode.USER_WHITE:
            pgn_game.headers['White'] = self.player_name
            pgn_game.headers['Black'] = engine_label
            pgn_game.headers['WhiteElo'] = self.player_elo
            pgn_game.headers['BlackElo'] = self.engine_elo
        else:
            pgn_game.headers['White'] = engine_label
            pgn_game.headers['Black'] = self.player_name
            pgn_game.headers['WhiteElo'] = self.engine_elo
            pgn_game.headers['BlackElo'] = self.player_elo
        
        # Append to file
        with open(self.pgn_file, 'a') as f:
            exporter = chess.pgn.FileExporter(f)
            pgn_game.accept(exporter)
            f.write('\n\n')
        
        return str(pgn_game)


class EmailSender:
    """Send PGN games via email"""
    
    def __init__(self, email_address: str):
        self.email = email_address
        self.smtp_config = {}
        
    def configure_smtp(self, server: str, user: str, password: str, 
                      use_ssl: bool = False, from_addr: str = None):
        """Configure SMTP settings"""
        self.smtp_config = {
            'server': server,
            'user': user,
            'password': password,
            'use_ssl': use_ssl,
            'from': from_addr or 'noreply@chesscomputer.com'
        }
    
    def send_pgn(self, pgn_text: str, pgn_file_path: str):
        """Send PGN game via email"""
        if not self.email or not self.smtp_config:
            return False
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"Your Chess Computer <{self.smtp_config['from']}>"
            msg['To'] = self.email
            msg['Subject'] = 'Chess Game PGN'
            
            body = f"Game completed!\n\n{pgn_text}"
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach PGN file
            with open(pgn_file_path, 'rb') as f:
                attachment = MIMEText(f.read().decode('utf-8'), 'plain')
                attachment.add_header('Content-Disposition', 'attachment', 
                                    filename='games.pgn')
                msg.attach(attachment)
            
            # Send via SMTP
            if self.smtp_config['use_ssl']:
                from smtplib import SMTP_SSL as SMTP
            else:
                from smtplib import SMTP
            
            with SMTP(self.smtp_config['server']) as conn:
                if self.smtp_config['user'] and self.smtp_config['password']:
                    conn.login(self.smtp_config['user'], self.smtp_config['password'])
                conn.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"Email send failed: {e}")
            return False
```

### Usage Example

```python
# Initialize
pgn_recorder = PGNRecorder('games/games.pgn', 'John Doe', '1800')
pgn_recorder.engine_name = 'Stockfish 15'
pgn_recorder.engine_elo = '3000'
pgn_recorder.level_name = 'Level 10'

email_sender = EmailSender('john@example.com')
email_sender.configure_smtp(
    server='smtp.gmail.com',
    user='chess@gmail.com',
    password='app_password',
    use_ssl=True
)

# At game start
pgn_recorder.start_new_game()

# At game end
pgn_text = pgn_recorder.save_game(game_board, GameResult.WIN_WHITE, PlayMode.USER_WHITE)
if pgn_text:
    email_sender.send_pgn(pgn_text, 'games/games.pgn')
```

### PGN Output Example

```
[Event "PicoChess Game"]
[Site "192.168.1.100"]
[Date "2024.01.15"]
[Time "14:30:22"]
[White "John Doe"]
[Black "Stockfish 15 (Level 10)"]
[WhiteElo "1800"]
[BlackElo "3000"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6
8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 ... 1-0
```

### Dependencies
- **Input**: Game board, result, player info
- **Output**: PGN files, email notifications
- **Related**: Game state (needs final position and moves)

---

## Feature 7: Voice Announcements

### Description
Text-to-speech announcements for moves, game events, and system messages using pre-recorded voice files in multiple languages.

### Implementation Guide

```python
import subprocess
from pathlib import Path

class VoiceAnnouncer:
    """Handles voice announcements"""
    
    def __init__(self, voice_path: str, speed_factor: float = 1.0):
        """
        Initialize voice announcer.
        voice_path: e.g., 'voices/en/christina'
        speed_factor: 0.9 to 1.35 (90% to 135% speed)
        """
        self.voice_path = Path(voice_path)
        self.speed_factor = speed_factor
        
        if not self.voice_path.exists():
            print(f"Warning: Voice path {voice_path} not found")
            self.voice_path = None
    
    def announce(self, sound_files: list):
        """
        Play sequence of sound files.
        sound_files: List of .ogg files like ['e2.ogg', 'e4.ogg']
        """
        if not self.voice_path:
            return False
        
        for sound_file in sound_files:
            file_path = self.voice_path / sound_file
            
            if not file_path.exists():
                print(f"Warning: Sound file {sound_file} not found")
                continue
            
            if self.speed_factor == 1.0:
                # Use ogg123 (vorbis-tools package)
                cmd = ['ogg123', str(file_path)]
            else:
                # Use play with tempo (sox package)
                cmd = ['play', str(file_path), 'tempo', str(self.speed_factor)]
            
            try:
                subprocess.call(cmd, stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL)
            except OSError:
                print("Voice playback failed")
                return False
        
        return True


class ChessVoiceAnnouncer:
    """Chess-specific voice announcements"""
    
    def __init__(self, user_voice: str, computer_voice: str, speed: float):
        """
        user_voice: 'en:anna' (language:speaker)
        computer_voice: 'en:john'
        """
        self.user_announcer = VoiceAnnouncer(user_voice, speed) if user_voice else None
        self.computer_announcer = VoiceAnnouncer(computer_voice, speed) if computer_voice else None
        self.low_time = False  # Disable voice in time pressure
    
    def announce_move(self, move: chess.Move, board: chess.Board, is_user: bool):
        """
        Announce a chess move.
        Creates sound sequence for the move.
        """
        if self.low_time:
            return  # Don't announce in time pressure
        
        sounds = self._move_to_sounds(move, board)
        
        announcer = self.user_announcer if is_user else self.computer_announcer
        if announcer:
            announcer.announce(sounds)
    
    def _move_to_sounds(self, move: chess.Move, board: chess.Board) -> list:
        """
        Convert move to sequence of sound files.
        Example: e2e4 -> ['e2.ogg', 'e4.ogg']
                 Nf3 -> ['knight.ogg', 'f3.ogg']
                 O-O -> ['castling.ogg']
        """
        sounds = []
        
        # Check special moves
        if board.is_castling(move):
            sounds.append('castling.ogg')
            return sounds
        
        if board.is_en_passant(move):
            sounds.append('enpassant.ogg')
        
        # Get piece name
        piece = board.piece_at(move.from_square)
        piece_sounds = {
            chess.PAWN: None,  # Pawns not announced by piece type
            chess.KNIGHT: 'knight.ogg',
            chess.BISHOP: 'bishop.ogg',
            chess.ROOK: 'rook.ogg',
            chess.QUEEN: 'queen.ogg',
            chess.KING: 'king.ogg'
        }
        
        if piece and piece_sounds[piece.piece_type]:
            sounds.append(piece_sounds[piece.piece_type])
        
        # From square
        from_square_name = chess.square_name(move.from_square)
        sounds.append(f'{from_square_name}.ogg')
        
        # Capture
        if board.is_capture(move):
            sounds.append('takes.ogg')
        
        # To square
        to_square_name = chess.square_name(move.to_square)
        sounds.append(f'{to_square_name}.ogg')
        
        # Promotion
        if move.promotion:
            promo_sounds = {
                chess.KNIGHT: 'knight.ogg',
                chess.BISHOP: 'bishop.ogg',
                chess.ROOK: 'rook.ogg',
                chess.QUEEN: 'queen.ogg'
            }
            sounds.append(promo_sounds[move.promotion])
        
        # Check/Checkmate
        board_copy = board.copy()
        board_copy.push(move)
        
        if board_copy.is_checkmate():
            sounds.append('checkmate.ogg')
        elif board_copy.is_check():
            sounds.append('check.ogg')
        
        return sounds
    
    def announce_game_event(self, event: str):
        """Announce game events"""
        event_sounds = {
            'newgame': ['newgame.ogg'],
            'draw': ['draw.ogg'],
            'resign': ['resign.ogg'],
            'whitewins': ['whitewins.ogg'],
            'blackwins': ['blackwins.ogg'],
            'error': ['error.ogg'],
            'timeout': ['timeout.ogg']
        }
        
        if event in event_sounds:
            # Use computer voice for system announcements
            if self.computer_announcer:
                self.computer_announcer.announce(event_sounds[event])
```

### Voice File Structure

```
voices/
├── en/
│   ├── anna/
│   │   ├── a1.ogg
│   │   ├── a2.ogg
│   │   ├── ...
│   │   ├── h8.ogg
│   │   ├── knight.ogg
│   │   ├── bishop.ogg
│   │   ├── takes.ogg
│   │   ├── check.ogg
│   │   ├── checkmate.ogg
│   │   └── newgame.ogg
│   └── john/
│       └── ...
├── de/
│   └── ...
└── voices.ini  # Configuration
```

### Dependencies
- **Input**: Moves, game events
- **Output**: Audio playback
- **Related**: Low time detection (disables voice), Move processing
- **External**: Requires `vorbis-tools` (ogg123) and `sox` (play) packages

---

## Feature 8: Web Interface

### Description
WebSocket-based web interface for remote play and board visualization with real-time game state synchronization.

### Implementation Guide

```python
import tornado.web
import tornado.websocket
from tornado.ioloop import IOLoop
import json

class WebSocketGameHandler(tornado.websocket.WebSocketHandler):
    """WebSocket handler for real-time game updates"""
    
    clients = set()  # All connected clients
    
    def open(self):
        """Client connected"""
        self.clients.add(self)
        # Send current game state
        self.write_message(json.dumps({
            'type': 'game_state',
            'fen': current_game.fen(),
            'pgn': current_game.pgn()
        }))
    
    def on_close(self):
        """Client disconnected"""
        self.clients.remove(self)
    
    def on_message(self, message):
        """Receive message from client"""
        data = json.loads(message)
        
        if data['action'] == 'move':
            # Client sent a move
            move = chess.Move.from_uci(data['move'])
            self.handle_remote_move(move)
        
        elif data['action'] == 'button':
            # Clock button pressed on web interface
            self.handle_button_press(data['button'])
    
    @classmethod
    def broadcast(cls, message_dict):
        """Broadcast message to all connected clients"""
        msg = json.dumps(message_dict)
        for client in cls.clients:
            try:
                client.write_message(msg)
            except:
                pass


class ChessWebServer:
    """Web server for chess interface"""
    
    def __init__(self, port: int):
        self.shared_state = {
            'game': None,
            'clock_time': {'white': 0, 'black': 0},
            'last_move': None
        }
        
        self.app = tornado.web.Application([
            (r'/', MainHandler, dict(shared=self.shared_state)),
            (r'/ws', WebSocketGameHandler, dict(shared=self.shared_state)),
            (r'/api/move', MoveHandler, dict(shared=self.shared_state)),
            (r'/api/clock', ClockHandler, dict(shared=self.shared_state)),
        ])
        
        self.app.listen(port)
    
    def start(self):
        """Start web server in thread"""
        IOLoop.instance().start()
    
    def update_game_state(self, game: chess.Board):
        """Called when game state changes"""
        self.shared_state['game'] = game
        
        # Broadcast to all clients
        WebSocketGameHandler.broadcast({
            'type': 'position',
            'fen': game.fen(),
            'last_move': str(game.peek()) if game.move_stack else None
        })
    
    def update_clock(self, white_time: int, black_time: int):
        """Called when clock updates"""
        self.shared_state['clock_time'] = {
            'white': white_time,
            'black': black_time
        }
        
        WebSocketGameHandler.broadcast({
            'type': 'clock',
            'white': white_time,
            'black': black_time
        })
    
    def show_computer_move(self, move: chess.Move):
        """Display computer's move"""
        WebSocketGameHandler.broadcast({
            'type': 'computer_move',
            'move': move.uci(),
            'from': chess.square_name(move.from_square),
            'to': chess.square_name(move.to_square)
        })


# JavaScript client example
"""
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === 'position') {
        // Update board display
        board.position(data.fen);
    }
    else if (data.type === 'clock') {
        // Update clock display
        updateClock(data.white, data.black);
    }
    else if (data.type === 'computer_move') {
        // Highlight computer move
        highlightMove(data.from, data.to);
    }
};

// Send move to server
function sendMove(from, to) {
    ws.send(JSON.stringify({
        action: 'move',
        move: from + to
    }));
}
"""
```

### Remote Play Feature

```python
class RemotePlayManager:
    """Manages remote play sessions"""
    
    def __init__(self):
        self.remote_mode = False
        self.remote_players = {}  # IP -> player info
    
    def enter_remote_room(self, player_ip: str):
        """Player enters remote play room"""
        self.remote_players[player_ip] = {
            'joined': datetime.datetime.now(),
            'color': None
        }
        
        # If this is the second player, start remote game
        if len(self.remote_players) == 2:
            self.start_remote_game()
    
    def leave_remote_room(self, player_ip: str):
        """Player leaves remote play room"""
        if player_ip in self.remote_players:
            del self.remote_players[player_ip]
        
        # If room empty, exit remote mode
        if len(self.remote_players) == 0:
            self.exit_remote_mode()
    
    def handle_remote_move(self, move: chess.Move, from_ip: str):
        """Process move from remote player"""
        if not self.remote_mode:
            return False
        
        # Validate it's the correct player's turn
        player_color = self.remote_players[from_ip]['color']
        if player_color != self.current_turn:
            return False
        
        # Process move
        if move in self.game.legal_moves:
            self.game.push(move)
            # Broadcast to other players
            self.broadcast_move(move)
            return True
        
        return False
```

### Dependencies
- **Input**: Web client moves, button presses
- **Output**: Game state updates, clock display
- **Related**: Game state, Time control, Board position
- **External**: Requires `tornado` web framework

---

## Feature 9: Menu System

### Description
Hierarchical menu system for configuration using DGT clock buttons, supporting engine selection, time controls, opening books, and system settings.

### Menu Structure

```
TOP MENU
├── MODE (Interaction modes)
│   ├── Normal
│   ├── Brain
│   ├── Analysis
│   ├── Kibitz
│   ├── Observe
│   ├── Remote
│   └── Ponder
├── POSITION (Setup position)
│   ├── Color to move
│   ├── Reverse board
│   └── Chess960
├── TIME (Time controls)
│   ├── Fixed time
│   │   └── 1s, 3s, 5s, 10s, 15s, 30s, 60s, 90s
│   ├── Blitz
│   │   └── 1m, 3m, 5m, 10m, 15m, 30m, 60m, 90m
│   └── Fischer
│       └── 1+1, 3+2, 5+3, 10+5, 15+10, 30+15, 60+20, 90+30
├── BOOK (Opening books)
│   └── List of available books
├── ENGINE (Engine selection)
│   ├── Engine list
│   └── Level for each engine
└── SYSTEM (System settings)
    ├── Info (Version, IP, Battery)
    ├── Sound (Beep settings)
    ├── Language
    ├── Voice settings
    └── Display settings
```

### Implementation Guide

```python
class MenuState:
    """Menu state tracking"""
    TOP = 1000
    MODE = 2000
    TIME = 3000
    TIME_BLITZ = 3100
    TIME_FISCHER = 3200
    TIME_FIXED = 3300
    BOOK = 4000
    ENGINE = 5000
    ENGINE_LEVEL = 5100
    SYSTEM = 6000

class ChessMenu:
    """Hierarchical menu system"""
    
    def __init__(self):
        self.state = MenuState.TOP
        self.current_selection = {}
        
        # Available options
        self.modes = ['NORMAL', 'BRAIN', 'ANALYSIS', 'KIBITZ', 
                     'OBSERVE', 'REMOTE', 'PONDER']
        self.time_modes = ['FIXED', 'BLITZ', 'FISCHER']
        self.time_values = {
            'FIXED': [1, 3, 5, 10, 15, 30, 60, 90],
            'BLITZ': [1, 3, 5, 10, 15, 30, 60, 90],
            'FISCHER': [(1,1), (3,2), (5,3), (10,5), (15,10), (30,15), (60,20), (90,30)]
        }
        self.books = []  # Loaded from config
        self.engines = []  # Loaded from config
        
        self.current_index = 0
    
    def handle_button_press(self, button: int):
        """
        Handle DGT clock button press.
        Buttons 0-4 on DGT clock:
        0: Up/Previous
        1: Down/Next  
        2: Ok/Select
        3: Back
        4: Help/Info
        """
        if button == 0:  # UP
            return self._move_up()
        elif button == 1:  # DOWN
            return self._move_down()
        elif button == 2:  # OK
            return self._select()
        elif button == 3:  # BACK
            return self._go_back()
        elif button == 4:  # HELP
            return self._show_help()
    
    def _move_up(self):
        """Navigate to previous menu item"""
        if self.state == MenuState.TOP:
            # Cycle through top menu
            menus = ['MODE', 'POSITION', 'TIME', 'BOOK', 'ENGINE', 'SYSTEM']
            self.current_index = (self.current_index - 1) % len(menus)
            return self._display_menu_item(menus[self.current_index])
        
        elif self.state == MenuState.MODE:
            self.current_index = (self.current_index - 1) % len(self.modes)
            return self._display_menu_item(self.modes[self.current_index])
        
        # Similar for other states...
    
    def _move_down(self):
        """Navigate to next menu item"""
        if self.state == MenuState.TOP:
            menus = ['MODE', 'POSITION', 'TIME', 'BOOK', 'ENGINE', 'SYSTEM']
            self.current_index = (self.current_index + 1) % len(menus)
            return self._display_menu_item(menus[self.current_index])
        
        elif self.state == MenuState.MODE:
            self.current_index = (self.current_index + 1) % len(self.modes)
            return self._display_menu_item(self.modes[self.current_index])
        
        # Similar for other states...
    
    def _select(self):
        """Select current menu item"""
        if self.state == MenuState.TOP:
            # Enter submenu
            if self.current_index == 0:  # MODE
                self.state = MenuState.MODE
                self.current_index = 0
                return self._display_menu_item(self.modes[0])
            
            elif self.current_index == 2:  # TIME
                self.state = MenuState.TIME
                self.current_index = 0
                return self._display_menu_item(self.time_modes[0])
            
            # etc...
        
        elif self.state == MenuState.MODE:
            # Apply selection
            selected_mode = self.modes[self.current_index]
            self.current_selection['mode'] = selected_mode
            self.state = MenuState.TOP
            return {'action': 'set_mode', 'mode': selected_mode}
        
        elif self.state == MenuState.TIME:
            # Enter time value selection
            selected_time_mode = self.time_modes[self.current_index]
            if selected_time_mode == 'BLITZ':
                self.state = MenuState.TIME_BLITZ
            # etc...
    
    def _go_back(self):
        """Go back to parent menu"""
        if self.state == MenuState.MODE:
            self.state = MenuState.TOP
        elif self.state == MenuState.TIME_BLITZ:
            self.state = MenuState.TIME
        elif self.state == MenuState.TIME:
            self.state = MenuState.TOP
        # etc...
        
        self.current_index = 0
        return {'action': 'menu_back'}
    
    def _display_menu_item(self, item):
        """Return display text for menu item"""
        return {'text': item, 'state': self.state}


# Usage in main event loop
def handle_clock_button(button):
    """Handle button press from DGT clock"""
    result = menu.handle_button_press(button)
    
    if result.get('action') == 'set_mode':
        # User selected a mode
        set_interaction_mode(result['mode'])
    elif result.get('action') == 'set_time':
        # User selected time control
        set_time_control(result['time_mode'], result['time_value'])
    
    # Display menu text on clock
    if 'text' in result:
        display_on_clock(result['text'])
```

### Special Menu Features

```python
class MenuPositionSetup:
    """Special menu for setting up positions"""
    
    def setup_position_by_board(self, timeout=30):
        """
        Let user setup position by placing pieces on board.
        Reads board after timeout seconds of no changes.
        """
        print("Setup position: Place pieces on board")
        
        # Wait for board to stabilize
        last_fen = None
        stable_count = 0
        
        while stable_count < timeout:
            current_fen = read_board_fen()
            
            if current_fen == last_fen:
                stable_count += 1
            else:
                stable_count = 0
                last_fen = current_fen
            
            time.sleep(1)
        
        # Validate position
        try:
            board = chess.Board(last_fen)
            if board.is_valid():
                return board
        except:
            pass
        
        return None

class MenuTimeControl:
    """Time control menu with special board-based selection"""
    
    def select_time_by_queen_position(self, fen: str):
        """
        Alternative time selection: Place queen on specific square
        to select time control.
        
        Example mappings:
        - Queen on a6: Fixed 1s
        - Queen on b6: Fixed 3s
        - Queen on a4: Blitz 1m
        - Queen on a3: Fischer 1+1
        """
        board = chess.Board(fen)
        
        # Find queen positions
        white_queens = board.pieces(chess.QUEEN, chess.WHITE)
        
        if not white_queens:
            return None
        
        queen_square = white_queens.pop()
        
        # Map square to time control
        time_control_map = {
            # Row 6 (7th rank): Fixed time
            chess.A6: TimeControl(TimeMode.FIXED, fixed=1),
            chess.B6: TimeControl(TimeMode.FIXED, fixed=3),
            chess.C6: TimeControl(TimeMode.FIXED, fixed=5),
            # Row 4 (5th rank): Blitz
            chess.A4: TimeControl(TimeMode.BLITZ, blitz=1),
            chess.B4: TimeControl(TimeMode.BLITZ, blitz=3),
            # Row 3 (4th rank): Fischer
            chess.A3: TimeControl(TimeMode.FISCHER, blitz=1, fischer=1),
            chess.B3: TimeControl(TimeMode.FISCHER, blitz=3, fischer=2),
        }
        
        return time_control_map.get(queen_square)
```

### Dependencies
- **Input**: Button presses from DGT clock or web interface
- **Output**: Configuration changes, menu display
- **Related**: All features (menu configures everything)

---

## Feature 10: Alternative Move Request

### Description
Allows user to request different move from engine or opening book by excluding previously suggested moves.

### Implementation Guide

```python
class AlternativeMoveManager:
    """Manages alternative move requests"""
    
    def __init__(self):
        self.excluded_moves = set()
    
    def get_remaining_moves(self, board: chess.Board) -> set:
        """
        Get all legal moves minus excluded ones.
        Returns all moves if all have been excluded.
        """
        all_moves = set(board.legal_moves)
        remaining = all_moves - self.excluded_moves
        
        if not remaining:
            # All moves tried, reset
            self.reset()
            return all_moves
        
        return remaining
    
    def get_alternative_book_move(self, book_reader, board: chess.Board):
        """
        Get alternative move from opening book.
        Returns None if no more book moves available.
        """
        try:
            # Ask book for move, excluding previous suggestions
            entry = book_reader.weighted_choice(
                board,
                exclude_moves=self.excluded_moves
            )
            
            if entry:
                move = entry.move()
                self.excluded_moves.add(move)
                
                # Get ponder move
                board_copy = board.copy()
                board_copy.push(move)
                try:
                    ponder_entry = book_reader.weighted_choice(board_copy)
                    ponder = ponder_entry.move() if ponder_entry else None
                except IndexError:
                    ponder = None
                
                return move, ponder
        except IndexError:
            pass
        
        return None
    
    def get_alternative_engine_move(self, engine, board: chess.Board, time_control):
        """
        Get alternative move from engine.
        Uses searchmoves to exclude previous suggestions.
        """
        remaining_moves = self.get_remaining_moves(board)
        
        # Tell engine to only search these moves
        uci_dict = time_control.to_uci_dict()
        uci_dict['searchmoves'] = remaining_moves
        
        result = engine.search(board, uci_dict)
        
        if result:
            self.excluded_moves.add(result.bestmove)
            return result.bestmove, result.ponder
        
        return None
    
    def add_move(self, move: chess.Move):
        """Add a move to excluded list"""
        self.excluded_moves.add(move)
    
    def reset(self):
        """Clear excluded moves (on position change)"""
        self.excluded_moves = set()


# Integration example
class GameManager:
    def __init__(self):
        self.alternative_mgr = AlternativeMoveManager()
    
    def request_alternative_move(self):
        """User pressed button to request alternative move"""
        
        # Must have computer move displayed
        if not self.computer_move_displayed:
            return False
        
        # Undo computer move
        self.game.pop()
        self.computer_move_displayed = False
        
        # Try book first
        book_result = self.alternative_mgr.get_alternative_book_move(
            self.book_reader,
            self.game
        )
        
        if book_result:
            move, ponder = book_result
            print(f"Alternative book move: {move}")
            return self.display_computer_move(move, ponder, inbook=True)
        
        # No book move, use engine
        engine_result = self.alternative_mgr.get_alternative_engine_move(
            self.engine,
            self.game,
            self.time_control
        )
        
        if engine_result:
            move, ponder = engine_result
            print(f"Alternative engine move: {move}")
            return self.display_computer_move(move, ponder, inbook=False)
        
        return False
    
    def on_position_change(self):
        """Position changed (user moved, takeback, etc)"""
        self.alternative_mgr.reset()
```

### User Interface

```python
# Trigger alternative move request:
# 1. Via clock button press (button 4 or special combination)
# 2. Via web interface button
# 3. Via special board action (e.g., lift both kings)

def detect_alternative_move_request():
    """Detect user wants alternative move"""
    
    # Method 1: Clock button
    if button_pressed == 4 and computer_move_displayed:
        return True
    
    # Method 2: Both kings lifted
    if kings_lifted_count == 2 and computer_move_displayed:
        return True
    
    return False
```

### Dependencies
- **Input**: Alternative move request (button/board action)
- **Output**: Different computer move
- **Related**: Opening book, Engine, Game state (requires displayed computer move)

---

## Feature 11: Engine Analysis Information (PV, Score, Depth)

### Description
Real-time display of engine analysis information including Principal Variation (PV), evaluation score, and search depth, with throttling to prevent display overload.

### Key Components
- PV (Principal Variation) - best line found
- Score - position evaluation
- Depth - search depth in plies
- Throttling - limit update frequency

### Implementation Guide

```python
import chess
from threading import Timer

class EngineInfoHandler:
    """Handles engine analysis information with throttling"""
    
    def __init__(self):
        self.allow_score = True
        self.allow_pv = True
        self.allow_depth = True
        
        self.current_pv = []
        self.current_score = None
        self.current_mate = None
        self.current_depth = 0
    
    def on_engine_info(self, info: dict):
        """
        Process UCI info from engine.
        info contains: score, pv, depth, nodes, time, etc.
        """
        # Update score
        if 'score' in info:
            score_info = info['score']
            
            if score_info.is_mate():
                # Mate score
                mate_in = score_info.mate()
                if self._allow_fire_score():
                    self.current_mate = mate_in
                    self.current_score = None
                    self.fire_score_event(None, mate_in)
            else:
                # Centipawn score
                cp = score_info.cp
                if self._allow_fire_score():
                    self.current_score = cp
                    self.current_mate = None
                    self.fire_score_event(cp, None)
        
        # Update PV (Principal Variation)
        if 'pv' in info and info['pv']:
            if self._allow_fire_pv():
                self.current_pv = info['pv']
                self.fire_pv_event(info['pv'])
        
        # Update depth
        if 'depth' in info:
            depth = info['depth']
            if self._allow_fire_depth():
                self.current_depth = depth
                self.fire_depth_event(depth)
    
    def _allow_fire_score(self):
        """Throttle score updates to max 2 per second"""
        if self.allow_score:
            self.allow_score = False
            Timer(0.5, self._reset_allow_score).start()
            return True
        return False
    
    def _reset_allow_score(self):
        self.allow_score = True
    
    def _allow_fire_pv(self):
        """Throttle PV updates to max 2 per second"""
        if self.allow_pv:
            self.allow_pv = False
            Timer(0.5, self._reset_allow_pv).start()
            return True
        return False
    
    def _reset_allow_pv(self):
        self.allow_pv = True
    
    def _allow_fire_depth(self):
        """Throttle depth updates to max 2 per second"""
        if self.allow_depth:
            self.allow_depth = False
            Timer(0.5, self._reset_allow_depth).start()
            return True
        return False
    
    def _reset_allow_depth(self):
        self.allow_depth = True
    
    def fire_score_event(self, centipawns, mate):
        """Fire score update event"""
        # Broadcast to display
        pass
    
    def fire_pv_event(self, pv_moves):
        """Fire PV update event"""
        # Broadcast to display
        pass
    
    def fire_depth_event(self, depth):
        """Fire depth update event"""
        # Broadcast to display
        pass


class AnalysisDisplay:
    """Display engine analysis on screen/clock"""
    
    def __init__(self):
        self.ponder_interval = 3  # Seconds to show each part
        self.show_mode = 0  # 0=score, 1=depth, 2=pv
    
    def format_score(self, centipawns=None, mate=None) -> str:
        """
        Format score for display.
        Centipawns: +150 = "+1.50", -230 = "-2.30"
        Mate: mate in 5 = "M 5", mate in -3 = "M-3"
        """
        if mate is not None:
            sign = '+' if mate > 0 else ''
            return f"M{sign}{mate}"
        elif centipawns is not None:
            # Convert centipawns to pawns
            pawns = centipawns / 100.0
            return f"{pawns:+.2f}"
        else:
            return "----"
    
    def format_pv(self, pv_moves: list, max_moves: int = 3) -> list:
        """
        Format PV moves for display.
        Returns list of move strings.
        """
        formatted = []
        for i, move in enumerate(pv_moves[:max_moves]):
            # Convert to SAN (Standard Algebraic Notation)
            move_san = self._to_san(move)
            formatted.append(move_san)
        return formatted
    
    def combine_depth_and_score(self, depth: int, score_str: str) -> str:
        """
        Combine depth and score for display.
        Example: "12 +1.50" (depth 12, score +1.50)
        """
        return f"{depth:2d} {score_str}"
    
    def cycle_display_mode(self):
        """Cycle through display modes in ponder interval"""
        # Show score for ponder_interval seconds
        # Then show PV for ponder_interval seconds
        # Then repeat
        pass


# Integration with UCI engine
import chess.uci

class UCIEngineWithInfo:
    """UCI engine with info handler"""
    
    def __init__(self, engine_path):
        self.engine = chess.uci.popen_engine(engine_path)
        self.engine.uci()
        
        # Attach info handler
        self.info_handler = EngineInfoHandler()
        self.engine.info_handlers.append(self.info_handler)
    
    def analyze(self, board: chess.Board, time_limit: float = None):
        """Start infinite analysis"""
        self.engine.position(board)
        
        if time_limit:
            self.engine.go(movetime=int(time_limit * 1000), 
                         async_callback=self._analysis_done)
        else:
            self.engine.go(infinite=True, 
                         async_callback=self._analysis_done)
    
    def _analysis_done(self, command):
        """Called when analysis completes"""
        result = command.result()
        # Process final result
        pass
```

### Display Formats

```python
# Score display examples
score_formats = {
    'short': '{:5s}',   # " +1.5" or "  M 5"
    'medium': '{:7s}',  # " +1.50 " or "  M  5"
    'long': '{:9s}'     # " +1.50   " or "  M   5 "
}

# Combined depth+score
# "12 +1.50" - depth 12, evaluation +1.50 pawns
# "15 M 5" - depth 15, mate in 5

# PV display
# "1.e4 e5 2.Nf3" - First 3 half-moves of PV
```

### Dependencies
- **Input**: UCI info from engine
- **Output**: Display updates
- **Related**: Engine search, Analysis modes, Display throttling

---

## Feature 12: Internationalization (i18n)

### Description
Multi-language support for display texts, move announcements, and system messages across English, German, Dutch, French, Spanish, and Italian.

### Implementation Guide

```python
class InternationalizationManager:
    """Manages translations and localized text"""
    
    SUPPORTED_LANGUAGES = ['en', 'de', 'nl', 'fr', 'es', 'it']
    
    def __init__(self, language: str = 'en'):
        self.language = language
        self.translations = self._load_translations()
        self.capital_letters = False
        self.short_notation = True  # True = short (e4), False = long (e2-e4)
    
    def _load_translations(self):
        """
        Load translations for all text codes.
        Text codes format: XNN_textid where:
        - X = beep type (B=button, N=no, Y=yes, K=okay, C=config, M=map)
        - NN = display time in deciseconds
        - textid = text identifier
        """
        translations = {
            # System messages
            'Y15_goodbye': {
                'en': {'l': 'Good bye   ', 'm': 'Good bye', 's': 'bye   '},
                'de': {'l': 'Tschuess   ', 'm': 'Tschuess', 's': 'tschau'},
                'nl': {'l': 'tot ziens  ', 'm': 'totziens', 's': 'dag   '},
                'fr': {'l': 'au revoir  ', 'm': 'a plus  ', 's': 'bye   '},
                'es': {'l': 'adios      ', 'm': 'adios   ', 's': 'adios '},
                'it': {'l': 'arrivederci', 'm': 'a presto', 's': 'ciao  '}
            },
            'Y15_pleasewait': {
                'en': {'l': 'please wait', 'm': 'pls wait', 's': 'wait  '},
                'de': {'l': 'bitteWarten', 'm': 'warten  ', 's': 'warten'},
                'nl': {'l': 'wacht even ', 'm': 'wachten ', 's': 'wacht '},
                'fr': {'l': 'patientez  ', 'm': 'patience', 's': 'patien'},
                'es': {'l': 'espere     ', 'm': 'espere  ', 's': 'espere'},
                'it': {'l': 'un momento ', 'm': 'attendi ', 's': 'attesa'}
            },
            # Game messages
            'B10_nomove': {
                'en': {'l': 'no move    ', 'm': 'no move ', 's': 'nomove'},
                'de': {'l': 'Kein Zug   ', 'm': 'Kein Zug', 's': 'kn zug'},
                'nl': {'l': 'Geen zet   ', 'm': 'Geen zet', 's': 'gn zet'},
                'fr': {'l': 'pas de mouv', 'm': 'pas mvt ', 's': 'pasmvt'},
                'es': {'l': 'sin mov    ', 'm': 'sin mov ', 's': 'no mov'},
                'it': {'l': 'no mossa   ', 'm': 'no mossa', 's': 'nmossa'}
            },
            # Time control messages
            'B00_tc_fixed': {
                'en': {'l': '{:2d}s move  ', 'm': '{:2d}s move', 's': '{:2d}s mv'},
                'de': {'l': '{:2d}s Zug   ', 'm': '{:2d}s Zug', 's': '{:2d}s z'},
                # ... other languages
            },
            # Mode messages  
            'B00_mode_normal_menu': {
                'en': {'l': 'normal     ', 'm': 'normal  ', 's': 'normal'},
                'de': {'l': 'normal     ', 'm': 'normal  ', 's': 'normal'},
                # ... other languages
            }
            # ... hundreds more text codes
        }
        return translations
    
    def get_text(self, text_code: str, params=None):
        """
        Get localized text for given code.
        
        text_code: e.g., 'B10_nomove'
        params: Format parameters for text with placeholders
        
        Returns: DisplayText object with l/m/s variants + metadata
        """
        # Parse code
        beep_char = text_code[0]
        display_time = int(text_code[1:3])
        text_id = text_code[4:]
        
        # Get beep setting
        beep = self._should_beep(beep_char)
        
        # Get translations
        if text_code in self.translations:
            trans = self.translations[text_code][self.language]
        else:
            # Fallback to English
            trans = self.translations.get(text_code, {}).get('en', {
                'l': text_id[:11],
                'm': text_id[:8], 
                's': text_id[:6]
            })
        
        # Apply parameters if needed
        if params:
            trans = {
                'l': trans['l'].format(*params) if '{}' in trans['l'] else trans['l'],
                'm': trans['m'].format(*params) if '{}' in trans['m'] else trans['m'],
                's': trans['s'].format(*params) if '{}' in trans['s'] else trans['s']
            }
        
        # Apply capital letters if enabled
        if self.capital_letters:
            trans = {k: v.upper() for k, v in trans.items()}
        
        # Create display text object
        return DisplayText(
            large=trans['l'],
            medium=trans['m'],
            small=trans['s'],
            beep=beep,
            maxtime=display_time / 10.0  # Convert to seconds
        )
    
    def _should_beep(self, beep_char: str) -> bool:
        """Determine if this message should beep"""
        beep_types = {
            'B': 'BUTTON',   # Button press
            'N': 'NO',       # No/negative action
            'Y': 'YES',      # Yes/positive action
            'K': 'OKAY',     # Confirmation
            'C': 'CONFIG',   # Configuration change
            'M': 'MAP'       # Menu/mapping
        }
        # Check beep configuration
        return True  # Simplified
    
    def format_move(self, move: chess.Move, board: chess.Board) -> str:
        """
        Format move for display in current notation.
        
        Short notation: e4, Nf3, O-O
        Long notation: e2-e4, Ng1-f3, O-O
        """
        if self.short_notation:
            # Standard Algebraic Notation (SAN)
            return board.san(move)
        else:
            # Long notation
            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)
            
            piece = board.piece_at(move.from_square)
            piece_symbol = piece.symbol().upper() if piece.piece_type != chess.PAWN else ''
            
            capture = 'x' if board.is_capture(move) else '-'
            
            return f"{piece_symbol}{from_sq}{capture}{to_sq}"

class DisplayText:
    """Display text with multiple size variants"""
    
    def __init__(self, large: str, medium: str, small: str, beep: bool, maxtime: float):
        self.l = large      # 11 chars for DGT XL clock
        self.m = medium     # 8 chars for DGT 3000
        self.s = small      # 6 chars for small displays
        self.beep = beep
        self.maxtime = maxtime  # How long to display
```

### Text Display Sizes

```python
# DGT clock display sizes
clock_sizes = {
    'large': 11,   # DGT XL clock (11 characters)
    'medium': 8,   # DGT 3000 clock (8 characters)
    'small': 6     # Small displays (6 characters)
}

# Example translations
examples = {
    'en': {
        'l': 'please wait',  # 11 chars max
        'm': 'pls wait',     # 8 chars max
        's': 'wait  '        # 6 chars max
    }
}
```

### Move Notation Examples

```python
# Short notation (SAN)
short_examples = {
    'pawn': 'e4',
    'piece': 'Nf3',
    'capture': 'exd5',
    'piece_capture': 'Nxe5',
    'castle_kingside': 'O-O',
    'castle_queenside': 'O-O-O',
    'promotion': 'e8=Q',
    'check': 'Qh5+',
    'checkmate': 'Qh7#'
}

# Long notation
long_examples = {
    'pawn': 'e2-e4',
    'piece': 'Ng1-f3',
    'capture': 'e4xd5',
    'piece_capture': 'Ne4xe5',
    'castle_kingside': 'O-O',
    'castle_queenside': 'O-O-O',
    'promotion': 'e7-e8=Q'
}
```

### Dependencies
- **Input**: Language selection from menu
- **Output**: All text displays
- **Related**: Display system, Menu, Voice (language affects both)

---

## Feature 13: Display/Clock Management

### Description
Manages display updates to DGT clocks and other display devices with message timing, beep control, and multi-device support.

### Key Components
- Multiple display devices (serial clock, i2c clock, web)
- Display timing and queue management
- Beep level configuration
- Message priority

### Implementation Guide

```python
from collections import deque
import time

class DisplayManager:
    """Manages display output to multiple devices"""
    
    def __init__(self):
        self.devices = set()  # 'ser', 'i2c', 'web'
        self.current_display = {}  # Current text on each device
        self.display_timer = {}  # Timer for max display time
        self.delayed_messages = {}  # Queued messages per device
        self.beep_level = BeepLevel.SOME
    
    def register_device(self, device: str):
        """Register a display device"""
        self.devices.add(device)
        self.current_display[device] = None
        self.delayed_messages[device] = deque()
    
    def display_text(self, text: DisplayText, devices: set):
        """
        Display text on specified devices.
        
        text: DisplayText object with l/m/s variants
        devices: Set of device names {'ser', 'i2c', 'web'}
        """
        for device in devices & self.devices:
            # Check if device is busy
            if self._is_displaying(device):
                if text.wait:
                    # Queue message for later
                    self.delayed_messages[device].append(text)
                    continue
                else:
                    # Force display, cancel current
                    self._cancel_display_timer(device)
            
            # Display on device
            self._show_on_device(device, text)
            
            # Set timer if maxtime specified
            if text.maxtime > 0:
                self._set_display_timer(device, text.maxtime)
    
    def display_move(self, move: chess.Move, fen: str, side: str, 
                     beep: bool, devices: set, notation: str):
        """
        Display a chess move on clock.
        
        move: The chess move
        fen: Board position
        side: Which side moved (for clock icon)
        beep: Whether to beep
        devices: Target devices
        notation: 'short' or 'long'
        """
        # Format move for display
        move_text = self._format_move_for_display(move, fen, notation)
        
        for device in devices & self.devices:
            if device == 'ser':
                # DGT serial clock specific format
                self._display_move_serial(move_text, side, beep)
            elif device == 'i2c':
                # DGT Pi clock specific format
                self._display_move_i2c(move_text, side, beep)
            elif device == 'web':
                # Web interface
                self._display_move_web(move, fen)
    
    def display_time(self, white_time: int, black_time: int, 
                     running_side: str, devices: set):
        """
        Display clock times.
        
        white_time: Seconds remaining for white
        black_time: Seconds remaining for black
        running_side: 'white', 'black', or None
        """
        for device in devices & self.devices:
            # Format time as MM:SS
            white_display = self._format_time(white_time)
            black_display = self._format_time(black_time)
            
            # Send to device with running indicator
            if device == 'ser':
                self._set_clock_serial(white_display, black_display, running_side)
            elif device == 'i2c':
                self._set_clock_i2c(white_display, black_display, running_side)
    
    def _format_time(self, seconds: int) -> str:
        """Format seconds as display string"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:1d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:2d}:{secs:02d}"
    
    def _is_displaying(self, device: str) -> bool:
        """Check if device is currently showing timed message"""
        return device in self.display_timer and self.display_timer[device] is not None
    
    def _set_display_timer(self, device: str, maxtime: float):
        """Set timer to return to time display after maxtime"""
        timer = Timer(maxtime, self._display_timer_expired, [device])
        timer.start()
        self.display_timer[device] = timer
    
    def _cancel_display_timer(self, device: str):
        """Cancel current display timer"""
        if device in self.display_timer and self.display_timer[device]:
            self.display_timer[device].cancel()
            self.display_timer[device] = None
    
    def _display_timer_expired(self, device: str):
        """Display timer expired, process queued messages or show time"""
        self.display_timer[device] = None
        
        # Check for queued messages
        if self.delayed_messages[device]:
            message = self.delayed_messages[device].popleft()
            self.display_text(message, {device})
        else:
            # Return to time display
            self.display_time_on_device(device)
    
    def _show_on_device(self, device: str, text: DisplayText):
        """Actually send text to hardware device"""
        # Implementation depends on device type
        if device == 'ser':
            self._send_to_serial_clock(text)
        elif device == 'i2c':
            self._send_to_i2c_display(text)
        elif device == 'web':
            self._send_to_web_interface(text)


class BeepLevel:
    """Beep level flags (bitwise)"""
    NO = 0x00       # No beeps
    CONFIG = 0x01   # Configuration changes
    BUTTON = 0x02   # Button presses
    MAP = 0x04      # Menu navigation
    OKAY = 0x08     # Confirmations
    YES = 0x0F      # All beeps

class BeepConfig:
    """Beep configuration"""
    OFF = 'none'    # Never beep
    ON = 'always'   # Always beep
    SOME = 'some'   # Selective beeps (use beep_level)
```

### Display Hash Prevention

```python
class DisplayHashManager:
    """Prevents redundant display updates"""
    
    def __init__(self):
        self.last_hash = {}
    
    def should_display(self, device: str, message) -> bool:
        """
        Check if message should be displayed.
        Returns False if identical message already showing.
        """
        current_hash = hash(str(message))
        
        if device in self.last_hash:
            if self.last_hash[device] == current_hash:
                return False  # Same message, skip
        
        self.last_hash[device] = current_hash
        return True
```

### Dependencies
- **Input**: Display messages from all features
- **Output**: Hardware clock/display updates
- **Related**: Internationalization (text formatting), Time control (clock display)

---

## Cross-Feature Dependencies

### Dependency Graph

```
Board Position ← → Time Control
     ↓               ↓
   Engine   ← → Opening Book
     ↓               ↓
Interaction Mode     ↓
     ↓               ↓
   PGN     ← → Voice
     ↓               ↓
   Email        Web Interface
     ↑               ↑
     └─── Menu ──────┘
```

### Critical Dependencies

1. **Game State Dependencies**
   - Board Position → Engine (provides position)
   - Board Position → Opening Book (provides position)
   - Board Position → PGN (provides moves)
   - Board Position → Voice (provides moves to announce)
   - Board Position → Display (shows position)

2. **Time Management Dependencies**
   - Time Control → Engine (provides time for search)
   - Time Control → Display (shows remaining time)
   - Board Position → Time Control (triggers start/stop)
   - Interaction Mode → Time Control (some modes don't use clock)

3. **Engine Dependencies**
   - Engine → Time Control (needs time limits)
   - Engine → Board Position (needs position)
   - Engine → Opening Book (alternative to book)
   - Interaction Mode → Engine (affects search type)

4. **Display Dependencies**
   - All features → Display (show information)
   - Display → Time Control (clock synchronization)
   - Display → Menu (show menu items)

5. **Configuration Dependencies**
   - Menu → All features (configures everything)
   - Menu → Display (shows on clock)

---

## Implementation Order for Recreation

### Phase 1: Core Foundation
1. **Event System** - Message queue architecture
2. **Board Position** - FEN handling, legal moves
3. **UCI Engine** - Basic engine communication
4. **Time Control** - All three time modes

### Phase 2: Game Logic
5. **Interaction Modes** - At least NORMAL mode
6. **Opening Book** - Book integration
7. **Alternative Moves** - Move exclusion
8. **Game End Detection** - Checkmate, stalemate, etc.

### Phase 3: I/O Features
9. **Display System** - Clock/screen output
10. **Board Input** - FEN from hardware
11. **Button Input** - Navigation
12. **PGN Recording** - Game saving

### Phase 4: Enhancement Features
13. **Web Interface** - Remote access
14. **Voice Announcements** - Audio output
15. **Email** - PGN sending
16. **Menu System** - Configuration UI

### Phase 5: Advanced Features
17. **Permanent Brain** - Pondering
18. **Remote Play** - Network play
19. **Analysis Modes** - Continuous analysis
20. **System Integration** - Updates, logging, etc.

---

## Key Design Patterns Used

### 1. Observer Pattern (Event System)
```python
class Observable:
    @staticmethod
    def fire(event):
        event_queue.put(event)

# Consumers
while True:
    event = event_queue.get()
    process_event(event)
```

### 2. State Pattern (Interaction Modes)
```python
if mode == Mode.NORMAL:
    handle_normal_mode()
elif mode == Mode.BRAIN:
    handle_brain_mode()
# ...
```

### 3. Strategy Pattern (Time Control)
```python
class TimeControl:
    def __init__(self, mode):
        self.mode = mode  # FIXED, BLITZ, FISCHER
    
    def reset(self):
        if self.mode == FIXED:
            # Fixed time strategy
        elif self.mode == BLITZ:
            # Blitz strategy
```

### 4. Command Pattern (Display Commands)
```python
DisplayMsg.show(Message.COMPUTER_MOVE(move=move, ponder=ponder))
```

### 5. Factory Pattern (Message Creation)
```python
Message = ClassFactory('MessageType', ['param1', 'param2'])
```

---

## Configuration File Format

### picochess.ini
```ini
[dgt]
dgt-port = /dev/ttyACM0
dgtpi = False
disable-revelation-leds = False
slow-slide = 0

[engine]
engine = engines/aarch64/stockfish
engine-level = Level@10

[time]
time = 5 0  # 5 min blitz

[book]
book = books/varied.bin

[voice]
user-voice = en:anna
computer-voice = en:john
speed-voice = 2

[system]
log-level = info
language = en
web-server = 8080

[email]
email = user@example.com
smtp-server = smtp.gmail.com
```

---

## Testing Considerations

### Unit Tests Needed
1. FEN parsing and legal move generation
2. Time control arithmetic
3. UCI command generation
4. PGN generation
5. Menu navigation logic

### Integration Tests Needed
1. Engine + Time Control
2. Board + Engine search
3. Book + Engine fallback
4. Menu + Configuration changes
5. Web interface + Game state

### Hardware Testing
1. DGT board FEN accuracy
2. Clock synchronization
3. Button response time
4. LED feedback (Revelation boards)

---

## Performance Considerations

### Critical Paths
1. **FEN Processing** - Must be < 100ms
2. **Engine Communication** - Asynchronous
3. **Clock Updates** - Every second, must be accurate
4. **Web Socket** - Low latency for remote play

### Optimization Tips
1. Cache legal FEN calculations
2. Use threading for engine searches
3. Batch display updates
4. Limit voice announcements during time pressure

---

## Security Considerations

### Input Validation
1. Validate all FEN strings
2. Validate UCI engine responses
3. Sanitize web interface input
4. Validate remote moves

### Network Security
1. Use authentication for remote play
2. Rate limit web interface
3. Sanitize email addresses
4. Use HTTPS for web interface

---

## Conclusion

PicoChess is a comprehensive chess computer system with modular architecture. The key to recreation is:

1. **Start with event-driven architecture** - All components communicate via message queues
2. **Implement core game logic first** - Board, engine, time control
3. **Add I/O incrementally** - Display, input, web interface
4. **Test each component independently** - Unit tests for each feature
5. **Integration test carefully** - Especially timing-sensitive features

The modular design allows recreation piece by piece, with each feature relatively independent but communicating through well-defined message interfaces.
