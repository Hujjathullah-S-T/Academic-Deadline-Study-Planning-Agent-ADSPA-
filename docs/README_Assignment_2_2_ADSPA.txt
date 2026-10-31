# Assignment 2.2 — ADSPA Distributed Agent Messaging

## Files
- `Assignment_2_2_ADSPA_Network.py` — client/server implementation
- `Assignment_2_2_ADSPA_Network.ipynb` — notebook with overview and verification demo
- `Assignment_2_2_Execution_Log.txt` — captured loopback demo output and rubric checklist

## Required dual-terminal scenario
Use Python 3.9+ and keep both terminals in the same directory.

**Terminal 1 — Agent-B server**
```bash
python Assignment_2_2_ADSPA_Network.py server
```

Expected message:
`ADSPA Agent-B server listening on 127.0.0.1:50525`

**Terminal 2 — Agent-A client**
```bash
python Assignment_2_2_ADSPA_Network.py client
```

Agent-A sends:
1. `STATE_TRANSFER` — its active ADSPA state and task parameters.
2. `INSTRUCTION` — asks Agent-B to evaluate the transferred tasks.
3. `PING` — checks network responsiveness.

Agent-B sends typed JSON responses: `STATE_ACK`, `INSTRUCTION_RESULT`, and `PONG`. Agent-B evaluates tasks using the same simple reflex rules from the previous assignments.

## One-process verification
```bash
python Assignment_2_2_ADSPA_Network.py demo
```
This uses a local loopback socket while running both endpoints in one process, which is convenient for automated verification. The dual-terminal commands above demonstrate the required two-endpoint architecture.

## Protocol
TCP, UTF-8 JSON, one JSON object per newline. Every message includes protocol version, UUID message ID, message type, sender, timestamp, reply correlation ID, and object payload.

## Safety and limitations
This is an educational localhost demo, not an authenticated production service. Do not expose it to an untrusted network without adding authentication, encryption (TLS), input limits, and stronger operational controls.
