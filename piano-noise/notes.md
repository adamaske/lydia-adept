# Monday 21-09-2026
We are going to deliver the Piano-Noise dataset to the company today.
NIRWizard has gotten some upgrades since last time and we're redoing the
analysis of the data.

In this report we will include HbO AND HbR this time.

## Quality Control

## Regions of Interest
Define ROIs in NIRWizard

## Preprocessing
We are opening the 4 recordings (noise_1, noise_2, quiet_1, quiet_2) as a single
session by concatenting the recordings in NIRWizard 0.2.1
1. Optical Density (OD)
2. Motion correction; Recursive PCA, Temporal Derivatie Distrbutive Repair
   (TDDR), Wavelet Correction
3. Bandpass filter; 0.01 - 0.2 Hz
4. Beer-Lambert: MBLL
 
## Analysis
5. Block Averaging; -10 - 50 ?
6. General Linear Model (GLM); remember 40s blocks: Contrast QUIET>NOISE
IMPORTANT REGARDING GLM: Here we had to concatnate the runs for a proper glm
run, whereas blocka veraging was done one a per-run basis. The group glm cannot
run without >2 subjects.
8. Laterality - GLM:B, t-stat -> BA: Mean, peak
9. Connectivity; Per-epoch FC?

## Visualization
1. On-cortex ROIs 
2. BA movies
3. GLM on-cortex; no threshold + q>0.05/t>8
4. 
