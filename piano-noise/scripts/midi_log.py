"""Optional MIDI keyboard logger, time-stamped on the LSL clock.

Records every note_on / note_off (and control changes) from a MIDI input port
to a CSV, with the same LSL local_clock() used for the trigger markers, so key
presses can be aligned with the fNIRS blocks for accuracy/timing scoring.
Optionally also pushes the events on a second LSL stream ("PianoMIDI") for
LabRecorder.

Requires: pip install mido python-rtmidi
"""
import csv
import threading
import time


def list_ports():
    import mido
    return mido.get_input_names()


class MidiLogger:
    FIELDS = ["t_lsl", "t_wall", "type", "channel", "note", "velocity", "control", "value"]

    def __init__(self, port_name, csv_path, lsl_clock=None, lsl_outlet=False, source_id="piano-noise-midi"):
        import mido
        self.port_name = port_name
        self.csv_path = csv_path
        self.clock = lsl_clock or time.perf_counter
        self.n = 0
        self._lock = threading.Lock()
        self._f = open(csv_path, "w", newline="")
        self._w = csv.DictWriter(self._f, fieldnames=self.FIELDS)
        self._w.writeheader()
        self.outlet = None
        if lsl_outlet:
            from pylsl import StreamInfo, StreamOutlet
            info = StreamInfo(name="PianoMIDI", type="MIDI", channel_count=3, nominal_srate=0,
                              channel_format="int32", source_id=source_id)
            self.outlet = StreamOutlet(info)
        self.port = mido.open_input(port_name, callback=self._on_msg)

    def _on_msg(self, msg):
        t_lsl = self.clock()
        t_wall = time.time()
        row = {"t_lsl": f"{t_lsl:.6f}", "t_wall": f"{t_wall:.6f}", "type": msg.type,
               "channel": getattr(msg, "channel", ""), "note": getattr(msg, "note", ""),
               "velocity": getattr(msg, "velocity", ""), "control": getattr(msg, "control", ""),
               "value": getattr(msg, "value", "")}
        with self._lock:
            self._w.writerow(row)
            self._f.flush()
            self.n += 1
        if self.outlet is not None and msg.type in ("note_on", "note_off"):
            code = 1 if (msg.type == "note_on" and msg.velocity > 0) else 0
            self.outlet.push_sample([code, msg.note, msg.velocity], t_lsl)

    def close(self):
        try:
            self.port.close()
        finally:
            with self._lock:
                self._f.close()


if __name__ == "__main__":
    print("MIDI input ports:")
    for p in list_ports():
        print("  ", p)
