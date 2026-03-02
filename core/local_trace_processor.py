# local_trace_processor.py

import json
import os
from typing import Any
#from agents.tracing.processor_interface import TracingProcessor
#from agents.tracing.traces import Trace
from agents.tracing import Trace, Span, TracingProcessor
from agents import RunResult

class LocalTraceProcessor(TracingProcessor):
    def __init__(self):
        self.trace: Trace | None = None
        self.spans: list[Span] = []
        self._listeners = []

    def on_trace_start(self, trace: Trace) -> None:
        self.trace = trace
        self.spans.clear()  # neue Trace, neue Spans
    
    def on_trace_end(self, trace):
        # z. B. automatisch span-Ausgabe loggen
        #print(f"✅ Trace beendet: {trace.trace_id}")
        for listener in self._listeners:
            try:
                listener(self)  # Übergibt sich selbst (inkl. trace & spans)
            except Exception as e:
                print(f"⚠️ Error in Trace-Listener: {e}")


    def on_span_start(self, span: Span[Any]) -> None:
        self.spans.append(span)

    def on_span_end(self, span: Span[Any]) -> None:
        # Ended spans evt. ergänzen oder loggen
        pass

    def force_flush(self) -> None:
        # nichts nötig
        pass

    def shutdown(self, timeout: float | None = None) -> None:
        # nichts nötig
        pass

    def add_trace_end_listener(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_trace_end_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)



_input_tokens = 0
_output_tokens = 0
_total_tokens = 0

def get_input_tokens():
    global _input_tokens
    return _input_tokens

def get_output_tokens():
    global _output_tokens
    return _output_tokens

def get_total_tokens():
    global _total_tokens
    return _total_tokens

def reset_token_count():
    global _input_tokens
    global _output_tokens
    global _total_tokens

    _input_tokens = 0
    _output_tokens = 0
    _total_tokens = 0

def add_tokens_from_run_result(result: RunResult):
    global _input_tokens
    global _output_tokens
    global _total_tokens
    if not result:
        return
    for r in result.raw_responses:
        _input_tokens += r.usage.input_tokens
        _output_tokens += r.usage.output_tokens 
        _total_tokens += r.usage.total_tokens