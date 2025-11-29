# Web Interface Output

## Overview
Browser-based display with virtual board, clock, and analysis.

## Display Components
1. **Chess Board**: Drag-and-drop interface
2. **Clock**: Digital time display
3. **Move History**: PGN notation
4. **Analysis**: Score/PV/Depth
5. **Control Buttons**: Virtual clock buttons

## Communication
- **Protocol**: WebSocket (bidirectional)
- **Format**: JSON messages
- **Updates**: Real-time board state

## Message Types
- Position updates (FEN)
- Clock time updates
- Move display with animation
- Analysis info (score/PV/depth)

## Implementation Details
File: `server.py` - WebSocket handler
Frontend: `web/` directory with JavaScript

See web server examples in PICOCHESS_FEATURES_ANALYSIS.md Feature 8.
