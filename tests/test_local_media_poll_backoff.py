from worker.local_media_supervisor import queue_poll_delay

def test_idle_scans_are_at_most_once_per_minute_and_active_handoffs_stay_fast():
    assert queue_poll_delay(10, idle=True) == 60
    assert queue_poll_delay(10) == 10
    assert queue_poll_delay(120, idle=True) == 120

def test_connection_errors_back_off_and_cap_without_zero_delay():
    assert [queue_poll_delay(10, failures=i) for i in range(1, 8)] == [30, 60, 120, 240, 300, 300, 300]
    assert queue_poll_delay(10, failures=0, idle=True) == 60
