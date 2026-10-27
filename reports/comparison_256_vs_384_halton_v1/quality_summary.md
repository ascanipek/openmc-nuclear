# 384 Halton branch: fixed-mask signal review

PROVISIONAL / EXPLORATORY. Geometric fuel mask: fuel_volume_fraction > 0.
Measured zeros are not interpreted as physical zero or zero uncertainty.

| Group | Scenarios | Fuel voxels | Measured zero | Low signal | Upper 4 zero / fuel |
| --- | ---: | ---: | ---: | ---: | ---: |
| old_256 | 256 | 1351680 | 180434 (13.3%) | 380837 (28.2%) | 130944 / 270336 |
| new_halton_128 | 128 | 675840 | 91747 (13.6%) | 190176 (28.1%) | 65485 / 135168 |

Low signal uses the existing V2 fission tally diagnostic; this is a review flag, not a pass/fail threshold.
Halton-03 case 0011 has two failed attempts and one completed attempt; only the completed one entered the dataset.
Original 256 has 11 alternate nuclear-index hash cases. Byte equivalence remains unassessed.
Source convergence and physical validation remain unassessed. The lightweight student ZIPs omit statepoints.
