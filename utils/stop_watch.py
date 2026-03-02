# stop_watch.py

import time  
  
class StopWatch:  
    def __init__(self, label="Duration"):
        self.label = label
        self._start_ns = None  
        self._end_ns = None
  
    # ---------- Timer ----------  
    def start(self):  
        self._start_ns = time.perf_counter_ns()   # ns  
        self._end_ns = None  
  
    def stop(self):  
        if self._start_ns is None:  
            raise RuntimeError("Timer wurde nicht gestartet.")  
        self._end_ns = time.perf_counter_ns()  
  
    def get_duration(self):  
        if self._start_ns is None:  
            raise RuntimeError("Timer wurde nicht gestartet.")  
        end_ns = self._end_ns if self._end_ns is not None else time.perf_counter_ns()  
        return (end_ns - self._start_ns) / 1_000_000_000  # zurück in Sekunden  
  
    # ---------- Format ----------  
    def get_formatted_duration(self):  
        """HH:mm:ss,ms - aber jetzt mit Millisekunden-Genauigkeit."""  
        total_ms = int(round(self.get_duration() * 1_000))    # Millisekunden runden  
        ms = total_ms % 1000  
        total_s = total_ms // 1000  
        s = total_s % 60  
        m = (total_s // 60) % 60  
        h = total_s // 3600  
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"  
  
    # ---------- Context Manager ----------  
    def __enter__(self):  
        self.start()  
        return self  
  
    def __exit__(self, exc_type, exc_value, traceback):  
        self.stop()  
        print(f"{self.label}: {self.get_formatted_duration()}")  
        return False


_stopwatch = StopWatch()
_stopwatch.start()

def get_stop_watch():
    global _stopwatch
    return _stopwatch
