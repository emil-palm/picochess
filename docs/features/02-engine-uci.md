# UCI Engine Management

## Overview
Manages UCI chess engines - initialization, search control, pondering, and level configuration.

## Key Components
- Engine process management (local/remote)
- UCI protocol communication
- Asynchronous search with callbacks
- Permanent brain (pondering)

## Implementation
See comprehensive example in original PICOCHESS_FEATURES_ANALYSIS.md starting at "Feature 2".

## Dependencies
- **Requires**: Board position, Time control
- **Required by**: All game modes
