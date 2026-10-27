WizardHat export

Montage:  PianoNoise_62
Optodes:  16 sources, 16 detectors, 49 channels
Cap:      head circumference 58 cm, pin-snap joints
Hold:     seam grommets held by a ring joint on each side, 8 to snap
Made:     2026-10-06T10:32:16.002334913+00:00
Exported: 2026-10-06T10:32:48.964214154+00:00
Engine:   wh-cap 0.0.4
App:      WizardHat 0.0.4

What is in this folder

  panels/
    sideLeft.stl    230 x 230 x 6.2 mm
    sideRight.stl    234 x 232 x 6.2 mm
    top1.stl    85 x 180 x 3.3 mm
    top2.stl    90 x 180 x 3.3 mm
  nirsite/    the montage as the NIRSite folder that Aurora loads
  PianoNoise_62.snirf    the montage as a probe-only SNIRF
  PianoNoise_62.nirwmontage    the montage the cap was generated from, with its cap facts
  pattern.svg    the pieces at 1:1 with a title block: a record of the cap, not a print file
  cap.yaml    the resolved cap file: every parameter the cap was generated with

Printing

The panels lie as the engine made them. A panel that is wider than the bed may fit
turned: the Preview stage of WizardHat says by how much. Turn it in the slicer.

What agrees with what

The cap and the probe files agree by position, on one head.

Every file of this folder names the same optodes, the same numbers and the
same channels. The positions in the probe files (nirsite/, the .snirf and the
.nirwmontage) are on the design head, WizardHat's Colin27. The cap was made
on the same head, scaled to the cap's size, with the probe registered on it
at that size. Mapped back to the design head, a grommet lies where its
optode lies in the probe files, up to what the registration at the cap's
size moves it. Until the design head is remeshed, a grommet on a pleat of a
flat piece may lie up to a few millimetres from its site
(docs/known-issues/design-head-pleats.md).
