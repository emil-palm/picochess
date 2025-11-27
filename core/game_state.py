"""Game state management class."""

import chess
import copy
from typing import Optional, List, Set
from dgt.util import PlayMode, GameResult


class GameState:
    """Manages the current game state and related information."""

    def __init__(self, initial_fen: Optional[str] = None, chess960_pos: Optional[int] = None):
        """Initialize game state."""
        if initial_fen:
            self.game = chess.Board(initial_fen)
        elif chess960_pos is not None:
            self.game = chess.Board()
            if chess960_pos != 518:  # Standard chess position
                self.game.set_chess960_pos(chess960_pos)
        else:
            self.game = chess.Board()

        self.play_mode = PlayMode.USER_WHITE
        self.game_declared = False  # User declared resignation or draw
        self.done_computer_fen = None
        self.done_move = chess.Move.null()
        self.pb_move = chess.Move.null()  # Permanent brain ponder move
        self.last_legal_fens = []
        self.legal_fens = []

    def copy(self) -> chess.Board:
        """Get a copy of the current game board."""
        return self.game.copy()

    def reset(self, fen: Optional[str] = None, chess960_pos: Optional[int] = None):
        """Reset the game to a new position."""
        if fen:
            self.game = chess.Board(fen)
        elif chess960_pos is not None:
            self.game = chess.Board()
            if chess960_pos != 518:
                self.game.set_chess960_pos(chess960_pos)
        else:
            self.game = chess.Board()

        self.done_computer_fen = None
        self.done_move = chess.Move.null()
        self.pb_move = chess.Move.null()
        self.last_legal_fens = []
        self.legal_fens = []
        self.game_declared = False

    def board_fen(self) -> str:
        """Get the board FEN string."""
        return self.game.board_fen()

    def fen(self) -> str:
        """Get the full FEN string."""
        return self.game.fen()

    def push(self, move: chess.Move):
        """Make a move on the board."""
        self.game.push(move)

    def pop(self):
        """Undo the last move."""
        self.game.pop()

    def is_game_over(self) -> bool:
        """Check if the game is over."""
        return self.game.is_game_over()

    def is_legal(self, move: chess.Move) -> bool:
        """Check if a move is legal."""
        return self.game.is_legal(move)

    def legal_moves(self) -> Set[chess.Move]:
        """Get all legal moves."""
        return self.game.legal_moves

    def turn(self) -> bool:
        """Get the current turn (True=White, False=Black)."""
        return self.game.turn

    def chess960_pos(self) -> int:
        """Get the chess960 position number."""
        return self.game.chess960_pos()
