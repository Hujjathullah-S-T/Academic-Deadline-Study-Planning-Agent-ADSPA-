#!/usr/bin/env python3
"""
Assignment 2.2: Distributed Agent Messaging using Sockets
Academic Deadline & Study Planning Agent (ADSPA)

Run Agent B (server) in Terminal 1:
    python Assignment_2_2_ADSPA_Network.py server

Run Agent A (client) in Terminal 2:
    python Assignment_2_2_ADSPA_Network.py client

Optional automated local demonstration:
    python Assignment_2_2_ADSPA_Network.py demo
"""
import argparse
import json
import socket
import threading
import time
import uuid
from datetime import datetime, timezone

HOST = "127.0.0.1"
PORT = 50525
PROTOCOL = "ADSPA/1.0"


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def send_json_line(sock, payload):
    """Send one UTF-8 JSON message terminated by newline."""
    data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    sock.sendall(data)


def receive_json_line(file_obj):
    """Read one newline-delimited JSON message and validate its top-level type."""
    line = file_obj.readline()
    if not line:
        return None
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON message: {exc}") from exc
    if not isinstance(message, dict):
        raise ValueError("Message must be a JSON object")
    required = {"protocol", "message_id", "message_type", "sender", "timestamp", "payload"}
    missing = required.difference(message)
    if missing:
        raise ValueError(f"Missing required message fields: {sorted(missing)}")
    if message["protocol"] != PROTOCOL:
        raise ValueError(f"Unsupported protocol: {message['protocol']}")
    if not isinstance(message["payload"], dict):
        raise ValueError("payload must be a JSON object")
    return message


def make_message(message_type, sender, payload, reply_to=None):
    return {
        "protocol": PROTOCOL,
        "message_id": str(uuid.uuid4()),
        "message_type": message_type,
        "sender": sender,
        "timestamp": now_iso(),
        "reply_to": reply_to,
        "payload": payload,
    }


def sample_agent_state():
    """Mock active state carried forward from the earlier ADSPA assignments."""
    return {
        "agent_name": "Academic Deadline & Study Planning Agent (ADSPA)",
        "agent_id": "ADSPA-Agent-A",
        "status": "active",
        "tasks": [
            {"task_id": "T101", "title": "Submit ML assignment", "deadline_hours": 5, "completed": False, "study_minutes_available": 120},
            {"task_id": "T102", "title": "Review NLP notes", "deadline_hours": 30, "completed": False, "study_minutes_available": 90},
            {"task_id": "T103", "title": "Upload lab record", "deadline_hours": -2, "completed": False, "study_minutes_available": 30},
            {"task_id": "T104", "title": "Read agent technology", "deadline_hours": 18, "completed": True, "study_minutes_available": 60},
        ],
        "parameters": {"urgent_threshold_hours": 24, "poll_interval_seconds": 0.5},
    }


def apply_adspa_rules(task, urgent_threshold=24):
    """Simple reflex rules shared with Assignments 1.2 and 2.1."""
    if task.get("completed", False):
        return {"task_id": task.get("task_id"), "action": "NO_ACTION", "reason": "Task already completed"}
    deadline = task.get("deadline_hours")
    available = task.get("study_minutes_available", 0)
    if deadline is None:
        return {"task_id": task.get("task_id"), "action": "REQUEST_DEADLINE", "reason": "Deadline missing"}
    if deadline < 0:
        return {"task_id": task.get("task_id"), "action": "FLAG_OVERDUE", "reason": "Deadline has passed"}
    if deadline <= urgent_threshold and available < 30:
        return {"task_id": task.get("task_id"), "action": "RESCHEDULE", "reason": "Urgent task has insufficient study time"}
    if deadline <= urgent_threshold:
        return {"task_id": task.get("task_id"), "action": "URGENT_ALERT", "reason": "Deadline is within urgent threshold"}
    return {"task_id": task.get("task_id"), "action": "PLAN_AHEAD", "reason": "Deadline is beyond urgent threshold"}


def handle_remote_message(message, agent_state):
    """Autonomously parse typed messages and choose a response."""
    kind = message["message_type"]
    payload = message["payload"]

    if kind == "STATE_TRANSFER":
        incoming_state = payload.get("state")
        if not isinstance(incoming_state, dict):
            return "ERROR", {"status": "error", "detail": "STATE_TRANSFER requires object field 'state'"}
        task_count = len(incoming_state.get("tasks", [])) if isinstance(incoming_state.get("tasks", []), list) else 0
        return "STATE_ACK", {
            "status": "accepted",
            "received_agent_id": incoming_state.get("agent_id", "unknown"),
            "task_count": task_count,
            "received_parameters": incoming_state.get("parameters", {}),
        }

    if kind == "INSTRUCTION":
        command = payload.get("command")
        if command == "evaluate_tasks":
            tasks = payload.get("tasks")
            if tasks is None:
                tasks = agent_state.get("tasks", [])
            if not isinstance(tasks, list):
                return "ERROR", {"status": "error", "detail": "'tasks' must be a list"}
            threshold = agent_state.get("parameters", {}).get("urgent_threshold_hours", 24)
            results = [apply_adspa_rules(task, threshold) for task in tasks]
            return "INSTRUCTION_RESULT", {
                "status": "completed",
                "command": command,
                "evaluated_count": len(results),
                "results": results,
            }
        if command == "ping":
            return "INSTRUCTION_RESULT", {"status": "ok", "command": command, "agent_status": "ready"}
        if command == "set_urgent_threshold":
            value = payload.get("hours")
            if not isinstance(value, (int, float)) or value < 0:
                return "ERROR", {"status": "error", "detail": "'hours' must be a non-negative number"}
            agent_state.setdefault("parameters", {})["urgent_threshold_hours"] = value
            return "INSTRUCTION_RESULT", {
                "status": "updated",
                "command": command,
                "urgent_threshold_hours": value,
            }
        return "ERROR", {"status": "error", "detail": f"Unknown instruction: {command}"}

    if kind == "PING":
        return "PONG", {"status": "ok", "agent_id": agent_state.get("agent_id")}

    return "ERROR", {"status": "error", "detail": f"Unsupported message_type: {kind}"}


def handle_connection(conn, address, server_state, log_lock):
    with conn:
        conn.settimeout(10)
        reader = conn.makefile("rb")
        try:
            while True:
                message = receive_json_line(reader)
                if message is None:
                    break
                started = time.perf_counter()
                response_type, response_payload = handle_remote_message(message, server_state)
                response = make_message(response_type, "ADSPA-Agent-B", response_payload, message["message_id"])
                send_json_line(conn, response)
                elapsed_ms = (time.perf_counter() - started) * 1000
                with log_lock:
                    print(f"[{now_iso()}] {address} | received={message['message_type']} "
                          f"| reply={response_type} | processing_ms={elapsed_ms:.3f}")
        except (ValueError, OSError, TimeoutError) as exc:
            with log_lock:
                print(f"[SERVER] Connection {address} ended: {exc}")
        finally:
            try:
                reader.close()
            except OSError:
                pass


def run_server(host=HOST, port=PORT):
    state = {
        "agent_name": "Academic Deadline & Study Planning Agent (ADSPA)",
        "agent_id": "ADSPA-Agent-B",
        "status": "ready",
        "tasks": [],
        "parameters": {"urgent_threshold_hours": 24, "poll_interval_seconds": 0.5},
    }
    lock = threading.Lock()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(5)
        print(f"ADSPA Agent-B server listening on {host}:{port}")
        print("Waiting for Agent-A. Press Ctrl+C to stop.")
        try:
            while True:
                conn, address = server.accept()
                thread = threading.Thread(
                    target=handle_connection,
                    args=(conn, address, state, lock),
                    daemon=True,
                    name=f"client-handler-{address[1]}",
                )
                thread.start()
        except KeyboardInterrupt:
            print("\nServer shutdown requested.")


def run_client(host=HOST, port=PORT):
    state = sample_agent_state()
    print(f"ADSPA Agent-A connecting to {host}:{port} ...")
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.settimeout(10)
        reader = sock.makefile("rb")

        state_msg = make_message("STATE_TRANSFER", "ADSPA-Agent-A", {"state": state})
        send_json_line(sock, state_msg)
        ack = receive_json_line(reader)
        print("\n[Agent-A] STATE_TRANSFER acknowledgement:")
        print(json.dumps(ack, indent=2))

        instruction = make_message("INSTRUCTION", "ADSPA-Agent-A", {
            "command": "evaluate_tasks",
            "tasks": state["tasks"],
        })
        send_json_line(sock, instruction)
        result = receive_json_line(reader)
        print("\n[Agent-A] Autonomous response to remote instruction:")
        print(json.dumps(result, indent=2))

        ping = make_message("PING", "ADSPA-Agent-A", {"text": "health check"})
        send_json_line(sock, ping)
        pong = receive_json_line(reader)
        print("\n[Agent-A] Network health check:")
        print(json.dumps(pong, indent=2))
        reader.close()


def run_demo():
    """Run both endpoints in one process for quick testing; dual-terminal mode is the primary deliverable."""
    server_ready = threading.Event()
    server_state = {
        "agent_name": "Academic Deadline & Study Planning Agent (ADSPA)",
        "agent_id": "ADSPA-Agent-B",
        "status": "ready",
        "tasks": [],
        "parameters": {"urgent_threshold_hours": 24, "poll_interval_seconds": 0.5},
    }
    lock = threading.Lock()

    def server_worker():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen(1)
            server_ready.set()
            conn, address = server.accept()
            handle_connection(conn, address, server_state, lock)

    thread = threading.Thread(target=server_worker, daemon=True, name="demo-server")
    thread.start()
    if not server_ready.wait(2):
        raise RuntimeError("Demo server failed to start")
    time.sleep(0.05)
    run_client(HOST, PORT)
    thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description="ADSPA distributed socket messaging demo")
    parser.add_argument("mode", choices=["server", "client", "demo"], help="server, client, or one-process demo")
    parser.add_argument("--host", default=HOST, help="server bind/connect host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=PORT, help=f"TCP port (default: {PORT})")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be in the range 1..65535")
    if args.mode == "server":
        run_server(args.host, args.port)
    elif args.mode == "client":
        run_client(args.host, args.port)
    else:
        run_demo()


if __name__ == "__main__":
    main()
