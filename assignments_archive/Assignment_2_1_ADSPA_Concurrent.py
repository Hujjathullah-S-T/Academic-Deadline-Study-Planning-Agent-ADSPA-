"""
Assignment 2.1: Concurrent Task Daemonization using Threads and Workers
Agent: Academic Deadline & Study Planning Agent (ADSPA)

Demonstrates a daemon monitor thread, mock telemetry polling, a thread-safe
queue, lock-protected shared state, and execution latency measurements.
Run with Python 3.
"""
import queue
import threading
import time
from datetime import datetime

telemetry_queue = queue.Queue()
shared_lock = threading.Lock()
shared_state = {}
performance_log = []
stop_event = threading.Event()


def timestamp():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def mock_task_source():
    """Mock academic task telemetry, consistent with Assignments 1.1 and 1.2."""
    return [
        {"task_name": "AI Assignment", "hours_until_deadline": 18, "completed": False,
         "available_study_hours": 3, "estimated_study_hours": 5},
        {"task_name": "Database Lab Report", "hours_until_deadline": 6, "completed": False,
         "available_study_hours": 4, "estimated_study_hours": 2},
        {"task_name": "NLP Quiz Preparation", "hours_until_deadline": 48, "completed": False,
         "available_study_hours": 5, "estimated_study_hours": 3},
        {"task_name": "Python Practical", "hours_until_deadline": -3, "completed": False,
         "available_study_hours": 2, "estimated_study_hours": 2},
        {"task_name": "Data Mining Notes", "hours_until_deadline": 12, "completed": True,
         "available_study_hours": 0, "estimated_study_hours": 2},
    ]


def background_monitor_worker(poll_interval=0.5):
    """Daemon worker polls the mock source and queues each new observation."""
    cycle = 0
    while not stop_event.is_set():
        cycle += 1
        poll_started = time.perf_counter()
        tasks = mock_task_source()
        time.sleep(0.01)  # Simulate sensor polling delay.
        poll_latency_ms = (time.perf_counter() - poll_started) * 1000
        for task in tasks:
            telemetry_queue.put({
                "cycle": cycle,
                "task": task,
                "produced_at": time.perf_counter(),
                "poll_latency_ms": poll_latency_ms,
            })
        # Wait can be interrupted immediately when shutdown is requested.
        stop_event.wait(poll_interval)


def apply_reflex_rule(task):
    """Apply the same ADSPA condition-action rules from Assignment 1.2."""
    if task["completed"]:
        return "MARK COMPLETED"
    if task["hours_until_deadline"] < 0:
        return "FLAG OVERDUE"
    if task["hours_until_deadline"] <= 24:
        if task["available_study_hours"] < task["estimated_study_hours"]:
            return "URGENT ALERT + RESCHEDULE"
        return "URGENT ALERT + START NOW"
    return "PLAN AHEAD"


def main():
    print("=" * 76)
    print("ASSIGNMENT 2.1: CONCURRENT TASK DAEMONIZATION USING THREADS AND WORKERS")
    print("Agent: Academic Deadline & Study Planning Agent (ADSPA)")
    print("=" * 76)

    monitor = threading.Thread(
        target=background_monitor_worker,
        name="ADSPA-Monitor",
        kwargs={"poll_interval": 0.5},
        daemon=True,
    )
    start = time.perf_counter()
    monitor.start()
    print(f"[{timestamp()}] MAIN: application is responsive; daemon monitor started.")

    # Process two batches of five telemetry observations.
    target_events = 10
    processed = 0
    while processed < target_events:
        try:
            event = telemetry_queue.get(timeout=3.0)
        except queue.Empty:
            print(f"[{timestamp()}] MAIN: queue timeout; waiting for telemetry.")
            continue

        received_at = time.perf_counter()
        task = event["task"]
        action = apply_reflex_rule(task)
        queue_latency_ms = (received_at - event["produced_at"]) * 1000
        processing_latency_ms = (time.perf_counter() - received_at) * 1000

        # A lock prevents concurrent reads/writes from corrupting shared data.
        with shared_lock:
            shared_state[task["task_name"]] = {
                "last_action": action,
                "last_cycle": event["cycle"],
            }
            performance_log.append({
                "task": task["task_name"],
                "cycle": event["cycle"],
                "queue_latency_ms": queue_latency_ms,
                "processing_latency_ms": processing_latency_ms,
                "poll_latency_ms": event["poll_latency_ms"],
            })

        processed += 1
        print(
            f"[{timestamp()}] MAIN: cycle={event['cycle']} task='{task['task_name']}' "
            f"-> {action} | queue={queue_latency_ms:.3f} ms, "
            f"process={processing_latency_ms:.3f} ms"
        )
        telemetry_queue.task_done()

    stop_event.set()
    monitor.join(timeout=2.0)

    with shared_lock:
        records = list(performance_log)
        state = dict(shared_state)

    total_ms = (time.perf_counter() - start) * 1000
    avg_queue = sum(r["queue_latency_ms"] for r in records) / len(records)
    avg_process = sum(r["processing_latency_ms"] for r in records) / len(records)
    avg_poll = sum(r["poll_latency_ms"] for r in records) / len(records)

    print("\n" + "-" * 76)
    print("PERFORMANCE SUMMARY")
    print(f"Telemetry events processed: {processed}")
    print(f"Distinct tasks tracked: {len(state)}")
    print(f"Average queue latency: {avg_queue:.3f} ms")
    print(f"Average rule-processing latency: {avg_process:.3f} ms")
    print(f"Average polling latency: {avg_poll:.3f} ms")
    print(f"Total elapsed time: {total_ms:.3f} ms")
    print(f"Monitor thread stopped cleanly: {not monitor.is_alive()}")
    print("Thread safety: queue.Queue transfers events; Lock protects shared state/log.")
    print("=" * 76)


if __name__ == "__main__":
    main()
