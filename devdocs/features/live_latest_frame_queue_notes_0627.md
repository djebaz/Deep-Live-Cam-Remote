# Live Latest-Frame Queue Patch

This package contains:

- `windows_app/live_webcam.py`: updated client file.
- `colab_api_live_latest_frame_queue_0627.patch`: backend patch for root `colab_api.py`.

## What It Adds

- Client sends a `live_frame_meta` JSON message before each frame bytes payload.
- Metadata includes sequence id, capture wall time, send wall time, codec, size, quality, and payload size.
- Backend can keep only the latest unprocessed frame, dropping stale payloads before decode/process.
- Backend perf can report queue/drop/latency metrics:
  - `frame_seq`
  - `server_queue_ms`
  - `client_to_server_ms`
  - `capture_to_server_ms`
  - `receive_to_send_ms`
  - `latest_drop_count`
  - `frames_dropped_before_process`
- Backend `swap_ms` is split further:
  - `source_refresh_ms`
  - `face_swap_ms`

## Expected Behavior

Throughput may not rise much because `face_swap_ms` is still the main compute cost.
The win should be lower live latency: old frames should be dropped before expensive backend work.
