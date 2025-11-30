# Web Interface Input

## Overview
Receives moves and commands from web browser via WebSocket.

## Input Types
1. **Move input**: Drag-and-drop on virtual board
2. **Button presses**: Virtual clock buttons
3. **Console commands**: Text commands (fen:, go, move)
4. **Room control**: Enter/leave remote play

## Protocol
- WebSocket connection
- JSON message format
- Bidirectional communication

## Implementation Details
File: `server.py` in PicoChess source

See web interface examples in PICOCHESS_FEATURES_ANALYSIS.md Feature 8.
