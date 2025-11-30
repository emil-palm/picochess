# DGT Clock Time Input

## Overview
DGT clocks act as **both input and output devices**. While they display information (output), they also send time updates back to the system (input) for clock synchronization and time tracking.

---

## Purpose
The external clock is the **source of truth** for time keeping. The system's internal time must synchronize with the external clock to:
- Maintain accurate time tracking
- Detect out-of-time conditions
- Handle clock lever movements
- Detect button presses (separate from time)

---

## Clock Types & Protocols

### DGT XL / DGT 3000 (Serial)
**Protocol**: Serial (DGT protocol)  
**Update Frequency**: Every 1 second  
**Message Type**: `DGT_MSG_BWTIME`

```python
# Message format (7 bytes)
# [0] = right hours (0x0f mask)
# [1] = right minutes (BCD)
# [2] = right seconds (BCD)
# [3] = left hours (0x0f mask)
# [4] = left minutes (BCD)
# [5] = left seconds (BCD)
# [6] = status byte
```

**Status Byte (byte 6)**:
```python
status = message[6] & 0x3f
connect = not (status & 0x20)  # Clock connected?
right_side_down = bool(status & 0x02)  # Lever position
```

### DGT Pi (I2C)
**Protocol**: I2C via dgtpicom library  
**Update Frequency**: Every 100ms (sampled every 1 second)  
**Library Call**: `dgtpicom_get_time()`

```python
# Returns 6 bytes:
# bytes[0:3] = left time (hours, minutes, seconds)
# bytes[3:6] = right time (hours, minutes, seconds)
```

---

## Time Message Processing

### 1. Receiving Time Updates

```python
class ClockTimeInput:
    """Handles incoming clock time messages"""
    
    def __init__(self):
        self.last_left_time = 3600 * 10   # 10 hours (max)
        self.last_right_time = 3600 * 10
        self.in_settime = False  # True during clock set operation
    
    def process_clock_time(self, message):
        """
        Process incoming time from clock.
        
        message format:
        - left_hours, left_mins, left_secs
        - right_hours, right_mins, right_secs
        - status/connection byte
        """
        # Parse time
        left_hours = message[0] & 0x0f
        left_mins = (message[1] >> 4) * 10 + (message[1] & 0x0f)  # BCD
        left_secs = (message[2] >> 4) * 10 + (message[2] & 0x0f)  # BCD
        
        right_hours = message[3] & 0x0f
        right_mins = (message[4] >> 4) * 10 + (message[4] & 0x0f)
        right_secs = (message[5] >> 4) * 10 + (message[5] & 0x0f)
        
        # Convert to seconds
        left_time = left_hours * 3600 + left_mins * 60 + left_secs
        right_time = right_hours * 3600 + right_mins * 60 + right_secs
        
        # Validate time
        if self._is_valid_time(left_time, right_time):
            # Check if time going backwards (error condition)
            if left_time > self.last_left_time or right_time > self.last_right_time:
                # Time increased - probably error or just set
                if not self.in_settime:
                    logging.warning('Clock time went backwards - ignoring')
                    return None
            
            # Update last known time
            self.last_left_time = left_time
            self.last_right_time = right_time
            
            # Fire time event
            return Event.CLOCK_TIME(
                time_left=left_time,
                time_right=right_time,
                connect=True,
                dev='ser'  # or 'i2c'
            )
        
        return None
    
    def _is_valid_time(self, left_time, right_time):
        """Validate time values"""
        # Check for valid ranges
        if left_time >= 3600 * 10 or right_time >= 3600 * 10:
            return False  # > 10 hours is invalid
        if left_time < 0 or right_time < 0:
            return False
        return True
```

### 2. Clock Synchronization Strategy

```python
class TimeControl:
    """Synchronizes internal time with external clock"""
    
    def __init__(self):
        self.internal_time = {
            chess.WHITE: 0.0,
            chess.BLACK: 0.0
        }
        self.clock_time = {
            chess.WHITE: 0,
            chess.BLACK: 0
        }
        self.active_color = None
    
    def handle_clock_time_event(self, event):
        """
        Handle incoming time from clock.
        External clock is source of truth!
        """
        # Update clock time (received from hardware)
        self.clock_time[chess.WHITE] = event.time_left
        self.clock_time[chess.BLACK] = event.time_right
        
        # If clock is running, sync internal time
        if self.active_color is not None:
            # Only sync the running clock
            # (stopped clock might not update correctly)
            if self.active_color == chess.WHITE:
                self.internal_time[chess.WHITE] = float(event.time_left)
            else:
                self.internal_time[chess.BLACK] = float(event.time_right)
        else:
            # Clock stopped, sync both
            self.internal_time[chess.WHITE] = float(event.time_left)
            self.internal_time[chess.BLACK] = float(event.time_right)
        
        # Check for low time (< 60 seconds)
        min_time = min(event.time_left, event.time_right)
        low_time = (min_time <= 60)
        
        # Broadcast time update
        fire_event(Message.CLOCK_TIME(
            time_white=event.time_left,
            time_black=event.time_right,
            low_time=low_time
        ))
```

---

## Device Priority

When multiple clocks are connected, prioritize:

```python
def is_priority_device(self, device: str, connected: bool) -> bool:
    """
    Determine which clock is source of truth.
    Priority: i2c > ser > web
    """
    if not connected:
        return False
    
    if 'i2c' in registered_devices:
        return device == 'i2c'
    elif 'ser' in registered_devices:
        return device == 'ser'
    else:
        return device == 'web'
```

**Priority Order**:
1. **DGT Pi (i2c)** - Highest priority (most reliable)
2. **DGT Serial (ser)** - Medium priority
3. **Web Interface (web)** - Lowest priority (can be laggy)

---

## Special Cases

### 1. Clock in Set Mode

```python
if self.in_settime:
    # Clock is being set, ignore incoming time updates
    # (they might be transitional values)
    logging.debug('Clock in set mode, ignoring time update')
    return
```

### 2. Time Going Backwards

```python
if new_time > last_time:
    # Time increased - this is an error unless we just set the clock
    if new_time - last_time > 3600:
        # More than 1 hour difference - definitely wrong
        logging.error('Clock time jumped by > 1 hour, ignoring')
        return
    
    if not self.in_settime:
        logging.warning('Clock time increased unexpectedly')
```

### 3. Clock Disconnected

```python
status = message[6] & 0x3f
connected = not (status & 0x20)

if not connected:
    # Clock unplugged or communication lost
    # Keep using last known time
    logging.info('Clock not connected, using last known time')
    return Event.CLOCK_TIME(
        time_left=self.last_left_time,
        time_right=self.last_right_time,
        connect=False,
        dev='ser'
    )
```

---

## Lever Position Detection

The clock status byte also indicates lever position:

```python
class LeverDetector:
    """Detect clock lever movement from status byte"""
    
    def __init__(self):
        self.last_lever_pos = None
    
    def detect_lever(self, status_byte):
        """
        Detect lever movement from clock status.
        Returns: 0x40 (right down), -0x40 (left down), or None
        """
        right_side_down = bool(status_byte & 0x02)
        
        if right_side_down:
            lever_pos = 0x40
        else:
            lever_pos = -0x40
        
        # Only fire event on change
        if lever_pos != self.last_lever_pos:
            if self.last_lever_pos is not None:
                # Lever moved
                fire_event(Event.KEYBOARD_BUTTON(
                    button=lever_pos,
                    dev='ser'
                ))
            self.last_lever_pos = lever_pos
```

---

## Integration with Time Control

### Flow Diagram

```
┌─────────────────┐
│ External Clock  │
│ (DGT Hardware)  │
└────────┬────────┘
         │ Every 1 second
         │ Event.CLOCK_TIME
         ▼
┌─────────────────┐
│ evt_queue       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ Main Loop               │
│ Check device priority   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Time Control            │
│ Sync internal time      │
│ with external clock     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Check low time          │
│ (< 60 seconds)          │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Broadcast to displays   │
│ (web, voice, etc.)      │
└─────────────────────────┘
```

---

## Critical Timing Issues

### Issue 1: Set Time vs. Get Time
```python
# Problem: Clock takes ~2 seconds to finish SET_TIME
# During this time, GET_TIME returns transitional values

# Solution: Use in_settime flag
def set_clock(self, time_left, time_right):
    self.in_settime = True
    send_set_and_run_command(time_left, time_right)
    # in_settime cleared when ACK received

def process_time(self, message):
    if self.in_settime:
        return  # Ignore transitional values
```

### Issue 2: Clock Update Lag
```python
# Problem: External clock updates every 1 second
# Internal clock updates continuously

# Solution: Use internal clock for engine, sync with external
def get_time_for_engine(self):
    # Use internal time (more accurate)
    return self.internal_time[color]

def get_time_for_display(self):
    # Use external clock (source of truth)
    return self.clock_time[color]
```

### Issue 3: Clock Running Detection
```python
# Problem: Need to know which side is running

# Solution: Track from our own START_CLOCK commands
# Don't rely on clock to tell us (it doesn't in all modes)

self.side_running = ClockSide.LEFT  # We track this
```

---

## Error Detection

### Sanity Checks

```python
def validate_clock_message(self, message):
    """Validate incoming clock time message"""
    
    # Check 1: Valid time ranges
    if any(message[:6]) > 99:  # BCD values should be < 100
        return False
    
    # Check 2: No time > 10 hours
    for hours in [message[0] & 0x0f, message[3] & 0x0f]:
        if hours > 9:
            return False
    
    # Check 3: Valid minutes/seconds (0-59)
    for bcd_val in [message[1], message[2], message[4], message[5]]:
        tens = (bcd_val >> 4)
        ones = (bcd_val & 0x0f)
        if tens > 5 or ones > 9:
            return False
    
    return True
```

---

## Implementation Details

### Serial Clock (DGT XL/3000)

**File**: `dgt/board.py` in PicoChess source

**Key Functions**:
- `_process_board_message()` - Handles `DGT_MSG_BWTIME`
- Parses BCD (Binary Coded Decimal) format
- Detects ACK messages (when clock confirms commands)
- Detects button presses embedded in time messages

### I2C Clock (DGT Pi)

**File**: `dgt/pi.py` in PicoChess source

**Key Functions**:
- `_process_incoming_clock_forever()` - Continuous loop
- Calls `dgtpicom_get_time()` every 100ms
- Samples time every 1 second for stability
- Separate from button detection

---

## Testing Clock Input

### Unit Test Example

```python
def test_clock_time_processing():
    clock = ClockTimeInput()
    
    # Simulate clock message: 5:30 left, 4:45 right
    message = [
        0x05,  # left hours
        0x30,  # left minutes (BCD: 3*10 + 0)
        0x00,  # left seconds
        0x04,  # right hours
        0x45,  # right minutes (BCD: 4*10 + 5)
        0x00,  # right seconds
        0x00   # status
    ]
    
    event = clock.process_clock_time(message)
    
    assert event.time_left == 5 * 3600 + 30 * 60
    assert event.time_right == 4 * 3600 + 45 * 60
    assert event.connect == True

def test_clock_time_backwards():
    clock = ClockTimeInput()
    
    # First update: 5:00
    clock.last_left_time = 300
    
    # Second update: 5:30 (time went UP - error!)
    message = [0x00, 0x05, 0x30, 0x00, 0x00, 0x00, 0x00]
    
    event = clock.process_clock_time(message)
    assert event is None  # Rejected
```

---

## Common Issues & Solutions

### Issue: Time updates stop
**Cause**: Clock disconnected or communication error  
**Solution**: Check connection status byte, implement reconnection logic

### Issue: Time jumps around
**Cause**: Transitional values during SET_TIME  
**Solution**: Use `in_settime` flag to ignore updates during set

### Issue: Wrong time displayed
**Cause**: Using internal time instead of external  
**Solution**: Always use external clock as source of truth for display

### Issue: Low time not detected
**Cause**: Not checking clock time updates  
**Solution**: Check for < 60 seconds on each update

---

## Dependencies

### Required By
- **Time Control**: Needs clock time for synchronization
- **Display**: Shows current time
- **Game Logic**: Detects out-of-time

### Requires
- **Serial/I2C Communication**: Hardware interface
- **Event System**: To fire CLOCK_TIME events
- **Device Priority**: To handle multiple clocks

### Related Features
- **DGT Buttons** (`dgt-buttons.md`) - Buttons are separate from time
- **Time Control** (`../features/03-time-control.md`) - Uses this input
- **Clock Output** (`../output/dgt-*-clock.md`) - Same device, output side

---

## Summary

The DGT clock as an input device is **critical for time accuracy**:

1. **Source of Truth**: External clock time overrides internal time
2. **Update Frequency**: Every 1 second from hardware
3. **Priority System**: i2c > serial > web
4. **Validation**: Check for time going backwards, invalid ranges
5. **Synchronization**: Continuous sync between internal and external time
6. **Low Time Detection**: Track when < 60 seconds remain

**Remember**: The clock is both input (time updates) AND output (time display). Both directions must work correctly for proper time management.
