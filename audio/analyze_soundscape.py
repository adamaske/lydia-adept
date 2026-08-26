"""Spectral analysis of the lab soundscape recording.

Usage: python audio/analyze_soundscape.py [path/to/file.wav]
Outputs PNGs + a text report next to the input file.
"""
import sys, pathlib
import numpy as np
import soundfile as sf
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "audio/lab_soundscape.wav")
x, fs = sf.read(path, dtype="float64")
if x.ndim > 1:
    x = x.mean(axis=1)
x -= x.mean()
dur = len(x) / fs
out = path.with_suffix("")

# --- Welch power spectral density (long window -> ~1 Hz resolution for tonal peaks)
nper = 2 ** int(np.ceil(np.log2(fs)))          # ~1 s window -> ~0.73 Hz bins
f, pxx = signal.welch(x, fs, window="hann", nperseg=nper, noverlap=nper // 2)
pxx_db = 10 * np.log10(pxx + 1e-20)

# --- Smooth baseline (median in log-freq) to find tonal peaks above broadband noise
def running_median_db(f, p_db, width_oct=0.33):
    base = np.empty_like(p_db)
    for i, fi in enumerate(f):
        if fi <= 0:
            base[i] = p_db[i]; continue
        lo, hi = fi * 2 ** (-width_oct / 2), fi * 2 ** (width_oct / 2)
        m = (f >= lo) & (f <= hi)
        base[i] = np.median(p_db[m])
    return base
base_db = running_median_db(f, pxx_db)
prom = pxx_db - base_db
valid = (f >= 20) & (f <= 8000)
peaks, props = signal.find_peaks(np.where(valid, prom, -np.inf), height=6, distance=3)
order = np.argsort(props["peak_heights"])[::-1]
peaks = peaks[order][:25]

# --- 1/3-octave band levels (relative dB, not calibrated)
centers = 1000 * 2 ** (np.arange(-17, 14) / 3)   # 19.7 Hz .. 20 kHz
band_db = []
for fc in centers:
    lo, hi = fc * 2 ** (-1 / 6), fc * 2 ** (1 / 6)
    m = (f >= lo) & (f < hi)
    band_db.append(10 * np.log10(np.trapezoid(pxx[m], f[m]) + 1e-20) if m.any() else np.nan)
band_db = np.array(band_db)
total_db = 10 * np.log10(np.trapezoid(pxx, f))

# --- Spectrogram
fS, tS, S = signal.spectrogram(x, fs, window="hann", nperseg=4096, noverlap=3072)
S_db = 10 * np.log10(S + 1e-20)

# --- Report
lines = [f"File: {path.name}  fs={fs} Hz  duration={dur:.1f} s",
         f"RMS (dBFS): {20*np.log10(np.sqrt(np.mean(x**2))):.1f}",
         f"Peak (dBFS): {20*np.log10(np.max(np.abs(x))):.1f}",
         "", "Strongest tonal peaks (level above local broadband baseline):",
         f"{'freq Hz':>9} {'PSD dB':>8} {'above base dB':>14}"]
for p in sorted(peaks, key=lambda i: f[i]):
    lines.append(f"{f[p]:9.1f} {pxx_db[p]:8.1f} {prom[p]:14.1f}")
lines += ["", "1/3-octave band levels (dB rel., total = %.1f):" % total_db]
for fc, b in zip(centers, band_db):
    if not np.isnan(b):
        lines.append(f"{fc:8.0f} Hz  {b:6.1f}  " + "#" * int(max(0, b - band_db[~np.isnan(band_db)].min())))
# energy share in coarse regions
def share(lo, hi):
    m = (f >= lo) & (f < hi); return 100 * np.trapezoid(pxx[m], f[m]) / np.trapezoid(pxx, f)
lines += ["", "Energy share: <100 Hz %.0f%% | 100-500 Hz %.0f%% | 500-2k %.0f%% | 2k-8k %.0f%% | >8k %.0f%%"
          % (share(0, 100), share(100, 500), share(500, 2000), share(2000, 8000), share(8000, fs / 2))]
report = "\n".join(lines)
print(report)
(out.parent / (out.name + "_report.txt")).write_text(report)

# --- Plots
fig, ax = plt.subplots(2, 1, figsize=(12, 9))
ax[0].semilogx(f, pxx_db, lw=0.7, label="Welch PSD")
ax[0].semilogx(f, base_db, lw=1, ls="--", label="local median baseline")
for p in peaks[:12]:
    ax[0].annotate(f"{f[p]:.0f}", (f[p], pxx_db[p]), textcoords="offset points", xytext=(0, 6),
                   ha="center", fontsize=7)
ax[0].set_xlim(20, fs / 2); ax[0].set_xlabel("Hz"); ax[0].set_ylabel("dB/Hz (uncalibrated)")
ax[0].set_title(f"{path.name} — power spectrum"); ax[0].grid(True, which="both", alpha=.3); ax[0].legend()
m = ~np.isnan(band_db)
ax[1].bar(np.arange(m.sum()), band_db[m], color="tab:blue")
ax[1].set_xticks(np.arange(m.sum())); ax[1].set_xticklabels([f"{c:.0f}" for c in centers[m]], rotation=90, fontsize=7)
ax[1].set_xlabel("1/3-octave centre (Hz)"); ax[1].set_ylabel("band level dB rel."); ax[1].set_title("1/3-octave band levels")
ax[1].grid(True, axis="y", alpha=.3)
fig.tight_layout(); fig.savefig(out.parent / (out.name + "_spectrum.png"), dpi=150)

fig, ax = plt.subplots(figsize=(12, 6))
pcm = ax.pcolormesh(tS, fS, S_db, shading="auto", cmap="magma", vmin=np.percentile(S_db, 5), vmax=S_db.max())
ax.set_yscale("log"); ax.set_ylim(20, fs / 2); ax.set_xlabel("s"); ax.set_ylabel("Hz"); ax.set_title("Spectrogram")
fig.colorbar(pcm, label="dB"); fig.tight_layout(); fig.savefig(out.parent / (out.name + "_spectrogram.png"), dpi=150)
print("\nwrote:", out.name + "_spectrum.png,", out.name + "_spectrogram.png,", out.name + "_report.txt")
