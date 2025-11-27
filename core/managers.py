"""Manager classes for engine, book, clock, and move processing."""

import logging
import time
import copy
import chess
import chess.polyglot
from typing import Optional, Set, Dict, Any
from uci.engine import UciEngine, UciShell
from timecontrol import TimeControl
from dgt.util import TimeMode, Mode, PlayMode


class EngineManager:
    """Manages the chess engine."""

    def __init__(self, engine: UciEngine, uci_shell: UciShell):
        """Initialize engine manager."""
        self.engine = engine
        self.uci_shell = uci_shell
        self.engine_name = None
        self._initialize_engine()
    
    def get_uci_shell(self) -> UciShell:
        """Get the UCI shell."""
        return self.uci_shell

    def _initialize_engine(self):
        """Initialize and get engine name."""
        try:
            self.engine_name = self.engine.get_name()
        except AttributeError:
            logging.error('engine not started')
            self.engine_name = None

    def get_engine(self) -> UciEngine:
        """Get the current engine."""
        return self.engine

    def get_name(self) -> Optional[str]:
        """Get engine name."""
        return self.engine_name

    def get_file(self) -> str:
        """Get engine file path."""
        return self.engine.get_file()

    def get_installed_engines(self) -> list:
        """Get list of installed engines."""
        return self.engine.get_installed_engines()

    def get_options(self) -> Dict[str, Any]:
        """Get engine options."""
        return self.engine.get_options()

    def has_chess960(self) -> bool:
        """Check if engine supports Chess960."""
        return self.engine.has_chess960()

    def has_ponder(self) -> bool:
        """Check if engine supports pondering."""
        return self.engine.has_ponder()

    def has_levels(self) -> bool:
        """Check if engine has levels."""
        return self.engine.has_levels()

    def is_waiting(self) -> bool:
        """Check if engine is waiting."""
        return self.engine.is_waiting()

    def is_thinking(self) -> bool:
        """Check if engine is thinking."""
        return self.engine.is_thinking()

    def is_pondering(self) -> bool:
        """Check if engine is pondering."""
        return self.engine.is_pondering()

    def startup(self, options: Dict[str, Any], reset: bool = True):
        """Start up engine with options."""
        self.engine.startup(options, reset)

    def newgame(self, game: chess.Board):
        """Start a new game."""
        self.engine.newgame(game)

    def position(self, game: chess.Board):
        """Set engine position."""
        self.engine.position(game)

    def go(self, uci_dict: Dict[str, Any]):
        """Start engine search."""
        self.engine.go(uci_dict)

    def stop(self, show_best: bool = False):
        """Stop engine search."""
        self.engine.stop(show_best)

    def ponder(self):
        """Start pondering."""
        self.engine.ponder()

    def brain(self, uci_dict: Dict[str, Any]):
        """Start permanent brain mode."""
        self.engine.brain(uci_dict)

    def hit(self):
        """Hit the pondering move."""
        self.engine.hit()

    def option(self, name: str, value: Any):
        """Set engine option."""
        self.engine.option(name, value)

    def send(self):
        """Send pending options to engine."""
        self.engine.send()

    def quit(self) -> bool:
        """Quit the engine."""
        return self.engine.quit()

    def mode(self, ponder: bool = False, analyse: bool = False):
        """Set engine mode."""
        self.engine.mode(ponder=ponder, analyse=analyse)

    def swap_engine(self, engine_file: str, options: Dict[str, Any]) -> bool:
        """Swap to a new engine."""
        old_file = self.get_file()
        old_options = {}
        raw_options = self.get_options()
        for name, value in raw_options.items():
            old_options[name] = str(value.default)

        # Stop the old engine
        self.stop()
        while not self.is_waiting():
            time.sleep(0.05)
            logging.warning('engine is still not waiting')

        # Closeout the engine process
        if self.quit():
            # Load the new one
            self.engine = UciEngine(file=engine_file, uci_shell=self.uci_shell)
            try:
                self.engine_name = self.engine.get_name()
                self.startup(options)
                return True
            except AttributeError:
                logging.error('new engine failed to start, reverting to %s', old_file)
                self.engine = UciEngine(file=old_file, uci_shell=self.uci_shell)
                try:
                    self.engine_name = self.engine.get_name()
                    self.startup(old_options)
                except AttributeError:
                    logging.error('no engines started')
                    return False
        return False


class BookManager:
    """Manages opening books."""

    def __init__(self, book_file: str):
        """Initialize book manager."""
        self.book_file = book_file
        self.bookreader = chess.polyglot.open_reader(book_file)

    def change_book(self, book_file: str):
        """Change to a different opening book."""
        self.book_file = book_file
        self.bookreader = chess.polyglot.open_reader(book_file)

    def get_book_file(self) -> str:
        """Get current book file."""
        return self.book_file

    def get_reader(self) -> chess.polyglot.PolyglotReader:
        """Get the book reader."""
        return self.bookreader


class ClockManager:
    """Manages the game clock."""

    def __init__(self, time_control: TimeControl):
        """Initialize clock manager."""
        self.time_control = time_control

    def get_time_control(self) -> TimeControl:
        """Get the time control object."""
        return self.time_control

    def start(self, turn: bool):
        """Start the clock for the given turn."""
        self.time_control.start_internal(turn)

    def stop(self):
        """Stop the clock."""
        self.time_control.stop_internal()

    def add_time(self, turn: bool):
        """Add increment time for the given turn."""
        self.time_control.add_time(turn)

    def reset(self):
        """Reset the clock."""
        self.time_control.reset()

    def reset_start_time(self):
        """Reset the start time."""
        self.time_control.reset_start_time()

    def is_running(self) -> bool:
        """Check if clock is running."""
        return self.time_control.internal_running()

    def get_uci_dict(self) -> Dict[str, str]:
        """Get UCI time dictionary."""
        return self.time_control.uci()

    def set_clock_times(self, white_time: int, black_time: int):
        """Set clock times from hardware."""
        self.time_control.set_clock_times(white_time, black_time)

    def change_time_control(self, time_control: TimeControl):
        """Change to a new time control."""
        self.time_control.stop_internal(log=False)
        self.time_control = time_control


class MoveProcessor:
    """Processes moves and maintains alternative move tracking."""

    def __init__(self):
        """Initialize move processor."""
        self.excludemoves = set()

    def reset(self):
        """Reset excluded moves."""
        self.excludemoves = set()

    def add_excluded(self, move: chess.Move):
        """Add a move to excluded list."""
        self.excludemoves.add(move)

    def get_search_moves(self, game: chess.Board) -> Set[chess.Move]:
        """Get all remaining legal moves excluding already tried moves."""
        searchmoves = set(game.legal_moves) - self.excludemoves
        if not searchmoves:
            self.reset()
            return set(game.legal_moves)
        return searchmoves

    def get_book_move(self, bookreader: chess.polyglot.PolyglotReader, 
                      game_copy: chess.Board) -> Optional[chess.uci.BestMove]:
        """Get a book move or None."""
        try:
            choice = bookreader.weighted_choice(game_copy, self.excludemoves)
        except IndexError:
            return None

        book_move = choice.move()
        self.add_excluded(book_move)
        game_copy.push(book_move)
        try:
            choice = bookreader.weighted_choice(game_copy)
            book_ponder = choice.move()
        except IndexError:
            book_ponder = None
        return chess.uci.BestMove(book_move, book_ponder)
