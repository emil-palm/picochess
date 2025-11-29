# Console Input

## Overview
Command-line interface for testing without hardware.

## Commands
- `fen:<fen_string>`: Set board position
- `<uci_move>`: Make move (e.g., e2e4)
- `go`: Execute last displayed move
- Standard UCI commands

## Use Cases
- Testing without hardware
- Automated testing
- Remote operation
- Development/debugging

## Implementation Details
Simulates board FEN events via keyboard input.
