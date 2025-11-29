# DGT Clock Communication - Key Features

## Overview
Picochess communicates with DGT clocks through two main interfaces:
1. **Serial Interface (ser)** - For DGT XL, DGT 3000, and Revelation II clocks connected via USB/Bluetooth
2. **I2C Interface (i2c)** - For DGT Pi clocks connected via I2C bus

## Architecture

### Communication Layers
1. **DgtBoard** (`dgt/board.py`) - Low-level serial communication with the board/clock
2. **DgtHw** (`dgt/hw.py`) - Hardware abstraction for serial-connected clocks
3. **DgtPi** (`dgt/pi.py`) - Hardware abstraction for I2C-connected clocks
4. **DgtIface** (`dgt/iface.py`) - Base interface class defining common methods
5. **DgtDisplay** (`dgt/display.py`) - High-level message dispatcher

### Message Flow
```
picochess.py → Message → DgtDisplay → Dgt API → DgtHw/DgtPi → DgtBoard → Clock Hardware
```

## Key Clock Commands

### 1. Display Text
**Purpose**: Display text messages on the clock display

**DGT XL/3000/Rev2 (Serial)**:
- `set_text_xl()` - 6 characters max for XL
- `set_text_3k()` - 8 characters max for 3000
- `set_text_rp()` - 11 characters max for Rev2 Pi mode

**DGT Pi (I2C)**:
- `dgtpicom_set_text()` - 11 characters max

**Command Structure**:
```python
Dgt.DISPLAY_TEXT(l=long_text, m=medium_text, s=short_text, 
                 beep=bool, maxtime=seconds, devs={'ser','i2c','web'})
```

### 2. Display Move
**Purpose**: Display chess moves in algebraic notation

**Implementation**:
- Converts moves to SAN (Standard Algebraic Notation) or UCI format
- Supports different languages (en, de, nl, fr, es, it)
- Supports short notation mode
- Can display on left or right side of clock

**Command Structure**:
```python
Dgt.DISPLAY_MOVE(move=chess.Move, fen=fen_string, side=ClockSide.LEFT/RIGHT,
                 wait=bool, maxtime=seconds, beep=bool, devs={'ser','i2c','web'},
                 uci960=bool, lang='en', capital=bool, long=bool)
```

### 3. Clock Control - Set Time
**Purpose**: Set the time values on both sides of the clock

**Implementation**:
- Sets time in seconds (converted to hours:minutes:seconds)
- Stores time values internally before starting clock
- Uses `in_settime` flag to prevent reading clock time during set operation

**Command Structure**:
```python
Dgt.CLOCK_SET(time_left=seconds, time_right=seconds, devs={'ser','i2c','web'})
```

### 4. Clock Control - Start
**Purpose**: Start the clock counting down for one side

**Implementation**:
- Uses `SetAndRun` command for serial clocks
- Uses `dgtpicom_set_and_run()` for I2C clocks
- Specifies which side (LEFT/RIGHT) should count down
- Sends current time values to clock

**Command Structure**:
```python
Dgt.CLOCK_START(side=ClockSide.LEFT/RIGHT, wait=bool, devs={'ser','i2c','web'})
```

**Serial Implementation** (`set_and_run()`):
```python
# Parameters: l_run, l_hours, l_mins, l_secs, r_run, r_hours, r_mins, r_secs
# l_run=1, r_run=0 means left side running
# l_run=0, r_run=1 means right side running
```

### 5. Clock Control - Stop
**Purpose**: Stop the clock (both sides)

**Implementation**:
- Sends current time values with both sides set to not run
- Uses `SetAndRun` with l_run=0, r_run=0

**Command Structure**:
```python
Dgt.CLOCK_STOP(devs={'ser','i2c','web'}, wait=bool)
```

### 6. Display Time
**Purpose**: Return clock display to showing time (after showing text/move)

**Implementation**:
- Sends `DGT_CMD_CLOCK_END` command
- Only works if clock is running or `force=True`

**Command Structure**:
```python
Dgt.DISPLAY_TIME(wait=bool, force=bool, devs={'ser','i2c','web'})
```

### 7. Clock Version Query
**Purpose**: Request clock version information

**Implementation**:
- Sent during startup to detect clock presence
- Returns main and sub version numbers
- Used to determine clock type (XL vs 3000)

**Command Structure**:
```python
Dgt.CLOCK_VERSION(main=version, sub=subversion, devs={'ser','i2c'})
```

## Clock Message Reception

### Time Updates
**Message**: `DGT_MSG_BWTIME` (0x8d)

**Format**:
- 7 bytes containing time for both sides
- Byte 0: Right hours (low nibble) + status flags
- Byte 1: Right minutes (BCD format)
- Byte 2: Right seconds (BCD format)
- Byte 3: Left hours (low nibble) + status flags
- Byte 4: Left minutes (BCD format)
- Byte 5: Left seconds (BCD format)
- Byte 6: Status byte (connection, lever position)

**Processing**:
- Converts BCD to seconds
- Validates time values
- Checks for clock connection status
- Detects lever position changes
- Fires `Event.CLOCK_TIME` event

### Button Events
**Message**: `DGT_ACK_CLOCK_BUTTON` (0x88)

**Button Codes**:
- Button 0: 0x01
- Button 1: 0x02
- Button 2: 0x04
- Button 3: 0x08
- Button 4: 0x10
- Button 0+4: 0x11 (shutdown)
- Lever right down: 0x40
- Lever left down: -0x40

**Processing**:
- Fires `Message.DGT_BUTTON` event
- Handled by `DgtDisplay._process_button()`

### Acknowledgment Messages
**Message**: `DGT_MSG_BWTIME` with ACK flag set

**ACK Types**:
- `DGT_ACK_CLOCK_SETNRUN` (0x0a) - Clock time set and started
- `DGT_ACK_CLOCK_DISPLAY` (0x01) - Display command acknowledged
- `DGT_ACK_CLOCK_END` (0x03) - End text command acknowledged
- `DGT_ACK_CLOCK_VERSION` (0x09) - Version query answered

## Protocol Details

### Serial Clock Protocol

**Message Format**:
```
[DGT_CLOCK_MESSAGE (0x2b)] [Length] [START_MESSAGE (0x03)] 
[Command] [Data bytes...] [END_MESSAGE (0x00)]
```

**Key Commands**:
- `DGT_CMD_CLOCK_DISPLAY` (0x01) - Display 7-segment characters
- `DGT_CMD_CLOCK_SETNRUN` (0x0a) - Set time and start/stop
- `DGT_CMD_CLOCK_ASCII` (0x0c) - ASCII text (3000 only)
- `DGT_CMD_REV2_ASCII` (0x0d) - ASCII text (Rev2 only)
- `DGT_CMD_CLOCK_END` (0x03) - Return to time display
- `DGT_CMD_CLOCK_VERSION` (0x09) - Request version

**Locking Mechanism**:
- Uses `clock_lock` to prevent concurrent commands
- Waits for ACK before sending next command
- Implements watchdog timer for stuck commands

### I2C Clock Protocol (DGT Pi)

**Library**: `dgtpicom.so` (native library)

**Key Functions**:
- `dgtpicom_init()` - Initialize connection
- `dgtpicom_configure()` - Configure clock
- `dgtpicom_set_text()` - Display text
- `dgtpicom_set_and_run()` - Set time and start/stop
- `dgtpicom_run()` - Start/stop without setting time
- `dgtpicom_end_text()` - Return to time display
- `dgtpicom_get_time()` - Read current time
- `dgtpicom_get_button_message()` - Read button events

**Time Reading**:
- Polls clock every 0.1 seconds
- Reads 6 bytes: [l_hours, l_mins, l_secs, r_hours, r_mins, r_secs]
- Only updates time from the side that's counting down
- Waits 2 seconds after stop for accurate time reading

## Clock State Management

### Internal State Variables
- `l_time` / `r_time` - Current time in seconds for left/right
- `side_running` - Which side is currently counting (LEFT/RIGHT/NONE)
- `in_settime` - Flag indicating clock is in set mode
- `clock_lock` - Serial clock command lock
- `enable_ser_clock` - Clock detection status

### Time Control Integration
- `TimeControl` class manages game time
- Supports FIXED, BLITZ, and FISCHER time modes
- Integrates with clock for automatic time management
- Handles time increments and delays

## Error Handling

### Clock Connection Errors
- Detects missing clock via timeout
- Handles partial jack connection (DGT Pi)
- Implements retry logic for failed commands

### Time Validation
- Checks for illegal time values (>9 hours, >59 minutes/seconds)
- Validates time doesn't increase unexpectedly
- Handles clock disconnection gracefully

### Command Retry
- Resends failed commands once
- Uses watchdog timer to detect stuck commands
- Reconfigures clock on repeated failures

## Key Implementation Patterns

### 1. Device Abstraction
Different clock types (XL, 3000, Rev2, Pi) are handled through polymorphic interface:
- `DgtHw` for serial clocks
- `DgtPi` for I2C clocks
- Both inherit from `DgtIface`

### 2. Message Queue System
- Uses `dgt_queue` for commands to hardware
- Uses `msg_queue` for high-level messages
- Dispatcher handles timing and priority

### 3. Thread Safety
- Uses `Lock` objects for serial communication
- Separate threads for incoming messages
- Thread-safe queue operations

### 4. Time Synchronization
- Internal time tracking vs clock time
- Handles clock drift
- Validates clock time against expected values

## Usage Examples

### Starting a Clock
```python
# Set initial time
Dgt.CLOCK_SET(time_left=1800, time_right=1800, devs={'ser','i2c'})

# Start left side (white)
Dgt.CLOCK_START(side=ClockSide.LEFT, devs={'ser','i2c'})
```

### Displaying a Move
```python
Dgt.DISPLAY_MOVE(
    move=chess.Move.from_uci('e2e4'),
    fen=game.fen(),
    side=ClockSide.LEFT,
    wait=True,
    maxtime=2,
    beep=True,
    devs={'ser','i2c','web'},
    lang='en',
    capital=False,
    long=False
)
```

### Stopping Clock
```python
Dgt.CLOCK_STOP(devs={'ser','i2c'})
```

## Clock-Specific Features

### DGT XL
- 6-character display
- Icon support (dots, colons)
- 7-segment character encoding

### DGT 3000
- 8-character ASCII display
- No icon support
- Direct ASCII encoding

### Revelation II
- 11-character display (Pi mode)
- LED square lighting support
- Enhanced ASCII mode

### DGT Pi
- I2C communication
- Native library interface
- Button event polling
- Continuous time reading

## Best Practices

1. **Always wait for ACK** before sending next command
2. **Use `in_settime` flag** to prevent reading clock during set operations
3. **Validate time values** before sending to clock
4. **Handle clock disconnection** gracefully
5. **Use appropriate text length** for clock type
6. **Implement retry logic** for critical commands
7. **Monitor clock state** to prevent race conditions
