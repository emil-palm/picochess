# Implementation Order

## Phase 1: Foundation (Week 1)

### Days 1-2: Event System
- [ ] Create three queues (evt, dispatch, msg)
- [ ] Implement Observable pattern
- [ ] Create event types
- [ ] Test with mock events

### Days 3-4: Board Position
- [ ] FEN parsing and validation
- [ ] Legal move computation
- [ ] FEN state machine
- [ ] Sliding detection

### Days 5-7: UCI Engine
- [ ] Engine process management
- [ ] UCI communication
- [ ] Asynchronous search
- [ ] Test with Stockfish

## Phase 2: Core Game (Week 2)

### Days 8-10: Time Control
- [ ] Blitz mode
- [ ] Fischer mode
- [ ] Fixed mode
- [ ] Clock synchronization

### Days 11-12: Basic I/O
- [ ] Console input (for testing)
- [ ] Console output (for testing)
- [ ] Test full game flow

### Days 13-14: NORMAL Mode
- [ ] Implement NORMAL interaction mode
- [ ] Integrate engine + time + board
- [ ] Test complete games

## Phase 3: Enhancement (Week 3)

### Days 15-16: Opening Books
- [ ] Polyglot reader
- [ ] Book move selection
- [ ] Book/engine transition

### Days 17-18: Web Interface
- [ ] Basic web server
- [ ] WebSocket communication
- [ ] Virtual board display
- [ ] Clock display

### Days 19-21: Additional Modes
- [ ] BRAIN mode (pondering)
- [ ] ANALYSIS mode
- [ ] REMOTE mode

## Phase 4: Polish (Week 4)

### Days 22-23: Display System
- [ ] Hardware abstraction layer
- [ ] DGT XL output
- [ ] DGT Pi output
- [ ] Display queue management

### Days 24-25: Voice
- [ ] Voice file structure
- [ ] Move announcer
- [ ] Event announcer
- [ ] Multi-language support

### Days 26-28: Final Features
- [ ] PGN recording
- [ ] Menu system
- [ ] Alternative moves
- [ ] Testing and debugging

## Testing Milestones

### Milestone 1: Basic Functionality
- [ ] Can play a complete game vs engine (console)
- [ ] Time control works correctly
- [ ] Engine responds to position changes

### Milestone 2: Web Interface
- [ ] Can play via web browser
- [ ] Real-time updates work
- [ ] Multiple clients supported

### Milestone 3: Hardware Integration
- [ ] DGT board input works
- [ ] Clock display works
- [ ] Button navigation works

### Milestone 4: Full Feature Set
- [ ] All 7 modes work
- [ ] Voice announcements work
- [ ] PGN recording works
- [ ] Menu configuration works

## Critical Path Items

**Must have for MVP**:
1. Event system
2. Board position
3. UCI engine
4. Time control (Blitz)
5. NORMAL mode
6. Basic web interface

**Nice to have**:
- Opening books
- Additional modes
- Voice
- PGN
- Menu system

**Hardware dependent**:
- DGT board input
- DGT clock output
- Physical buttons

## Risk Mitigation

### Risk: Hardware delays
**Mitigation**: Build web interface first for testing

### Risk: Engine integration issues
**Mitigation**: Test with multiple engines early

### Risk: Threading complexity
**Mitigation**: Use proven queue patterns, thorough testing

### Risk: Display timing
**Mitigation**: Implement queue with maxtime early
