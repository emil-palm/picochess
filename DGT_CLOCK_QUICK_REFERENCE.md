# DGT Clock Communication - Quick Reference

## Core Communication Functions

### Display Functions

| Function | Purpose | Max Length | Clock Types |
|----------|---------|------------|-------------|
| `set_text_xl()` | Display text on XL | 6 chars | DGT XL |
| `set_text_3k()` | Display text on 3000 | 8 chars | DGT 3000 |
| `set_text_rp()` | Display text on Rev2 | 11 chars | Revelation II |
| `dgtpicom_set_text()` | Display text on Pi | 11 chars | DGT Pi |

### Clock Control Functions

| Function | Purpose | Parameters |
|----------|---------|------------|
| `set_clock()` | Set time values | `time_left`, `time_right`, `devs` |
| `start_clock()` | Start clock counting | `side` (LEFT/RIGHT), `devs` |
| `stop_clock()` | Stop clock | `devs` |
| `end_text()` | Return to time display | - |
| `set_and_run()` | Set time and start/stop | `l_run`, `l_hms`, `r_run`, `r_hms` |

## DGT API Commands

### High-Level Commands (via Dgt API)

```python
# Display text
Dgt.DISPLAY_TEXT(l=long, m=medium, s=short, beep=bool, maxtime=sec, devs={'ser','i2c','web'})

# Display move
Dgt.DISPLAY_MOVE(move=Move, fen=str, side=ClockSide, wait=bool, maxtime=sec, 
                 beep=bool, devs=set, uci960=bool, lang=str, capital=bool, long=bool)

# Clock control
Dgt.CLOCK_SET(time_left=int, time_right=int, devs=set)
Dgt.CLOCK_START(side=ClockSide, wait=bool, devs=set)
Dgt.CLOCK_STOP(devs=set, wait=bool)
Dgt.DISPLAY_TIME(wait=bool, force=bool, devs=set)
Dgt.CLOCK_VERSION(main=int, sub=int, devs=set)
```

## Low-Level Protocol Commands

### Serial Clock Commands (DgtClk enum)

| Command | Value | Purpose |
|---------|-------|---------|
| `DGT_CMD_CLOCK_DISPLAY` | 0x01 | Control 7-segment display |
| `DGT_CMD_CLOCK_SETNRUN` | 0x0a | Set time and run |
| `DGT_CMD_CLOCK_END` | 0x03 | Return to time display |
| `DGT_CMD_CLOCK_ASCII` | 0x0c | ASCII text (3000) |
| `DGT_CMD_REV2_ASCII` | 0x0d | ASCII text (Rev2) |
| `DGT_CMD_CLOCK_VERSION` | 0x09 | Request version |
| `DGT_CMD_CLOCK_START_MESSAGE` | 0x03 | Message start marker |
| `DGT_CMD_CLOCK_END_MESSAGE` | 0x00 | Message end marker |

### Message Format

```
[DGT_CLOCK_MESSAGE (0x2b)] [Length] [START (0x03)] [Command] [Data...] [END (0x00)]
```

## Clock Messages Received

### DGT_MSG_BWTIME (0x8d)

**Format**: 7 bytes
- Byte 0: Right hours (low 4 bits) + flags
- Byte 1: Right minutes (BCD)
- Byte 2: Right seconds (BCD)
- Byte 3: Left hours (low 4 bits) + flags
- Byte 4: Left minutes (BCD)
- Byte 5: Left seconds (BCD)
- Byte 6: Status (connection, lever)

**ACK Detection**: If byte 0 or 3 has 0x0a in low nibble, it's an ACK message

### Button Events

| Button | Code | Special |
|--------|------|---------|
| 0 | 0x01 | - |
| 1 | 0x02 | - |
| 2 | 0x04 | - |
| 3 | 0x08 | - |
| 4 | 0x10 | - |
| 0+4 | 0x11 | Shutdown |
| Lever Right | 0x40 | - |
| Lever Left | -0x40 | - |

## Clock Side Enumeration

```python
ClockSide.LEFT = 0x01   # White side
ClockSide.RIGHT = 0x02  # Black side
ClockSide.NONE = 0x04   # Neither side
```

## I2C Clock Functions (DGT Pi)

### Native Library Functions

```c
int dgtpicom_init()                    // Initialize connection
int dgtpicom_configure()                // Configure clock
int dgtpicom_set_text(char*, int, int, int)  // Display text
int dgtpicom_set_and_run(int, int, int, int, int, int, int, int)  // Set time & run
int dgtpicom_run(int, int)              // Start/stop clock
int dgtpicom_end_text()                 // Return to time display
void dgtpicom_get_time(char*)           // Read time (6 bytes)
int dgtpicom_get_button_message(char*, char*)  // Read buttons
```

## State Management

### Key Variables

```python
l_time          # Left side time (seconds)
r_time          # Right side time (seconds)
side_running    # ClockSide.LEFT/RIGHT/NONE
in_settime      # bool - clock in set mode
clock_lock      # timestamp - serial command lock
enable_ser_clock # bool - clock detected
```

## Common Patterns

### Starting a Game
```python
# 1. Set initial time
Dgt.CLOCK_SET(time_left=1800, time_right=1800, devs={'ser','i2c'})

# 2. Start white's clock
Dgt.CLOCK_START(side=ClockSide.LEFT, devs={'ser','i2c'})
```

### After a Move
```python
# 1. Stop clock
Dgt.CLOCK_STOP(devs={'ser','i2c'})

# 2. Display move (optional)
Dgt.DISPLAY_MOVE(move=move, ...)

# 3. Start opponent's clock
Dgt.CLOCK_START(side=ClockSide.RIGHT, devs={'ser','i2c'})
```

### Displaying Information
```python
# Show text temporarily
Dgt.DISPLAY_TEXT(m="Engine", maxtime=2, devs={'ser','i2c'})

# Return to time display
Dgt.DISPLAY_TIME(devs={'ser','i2c'})
```

## Error Handling

### Common Issues

1. **Clock not responding**
   - Check connection
   - Verify clock is in correct mode
   - Retry command

2. **Time values invalid**
   - Validate: hours < 10, minutes/seconds < 60
   - Check for clock disconnection

3. **Command timeout**
   - Check `clock_lock` duration
   - Resend command if > 2 seconds

4. **Time reading errors**
   - Wait 2 seconds after stop for accurate reading
   - Only read from counting side
   - Check `in_settime` flag

## File Locations

| Component | File |
|-----------|------|
| Low-level serial | `dgt/board.py` |
| Serial clock interface | `dgt/hw.py` |
| I2C clock interface | `dgt/pi.py` |
| Base interface | `dgt/iface.py` |
| Message dispatcher | `dgt/display.py` |
| API definitions | `dgt/api.py` |
| Utilities/enums | `dgt/util.py` |
| Main application | `picochess.py` |

## Threading Model

- **DgtBoard**: Separate thread for incoming messages
- **DgtHw/DgtPi**: Separate thread for command queue
- **DgtDisplay**: Separate thread for message processing
- **Locks**: Used for serial communication and library calls
