# Development Narrative

This is a readable account of how the solution was built with AI assistance. It is not a
separate report; it exists so the evaluator can see the reasoning chain behind the code:
what was measured, what failed, and why the final method looks the way it does.

## 1. Restating The Task

The assignment is not simply "detect field boundaries." The input boundary is an official
cadastral outline, usually close in shape but not always in the right place. The output is a
per-plot claim:

- corrected: move the boundary and provide a confidence;
- flagged: keep the official boundary because the evidence is weak or ambiguous.

The hard part is calibration and restraint. A method that moves every plot can look active
but will score poorly if it is confident on bad moves or shifts plots that were already
right.

## 2. First Measurements

I first compared the official geometries with the public example truths. Those examples are
too few to tune against, but they are enough to understand the failure mode.

The key observation was that the best rigid translation made the overlap much better while
the areas stayed broadly compatible. That suggested the common case is placement drift, not
a need to reshape every polygon. This shaped the whole solution: solve translation well,
then be honest about cases where translation is not enough.

Overlay inspection also showed that many truth boundaries line up with visible field edges
and with the optional `boundaries.tif` hints. The hints are not treated as truth, but they
are useful evidence when they agree with the imagery.

## 3. Method Choice

The core method is chamfer edge registration:

1. Read an imagery patch around a plot.
2. Build an edge target from image gradients and optional boundary hints.
3. Rasterise the official plot outline.
4. Search nearby translations and choose the one with the smallest mean distance from the
   outline to the edge target.

The implementation uses an FFT convolution to compute the full cost surface efficiently.
This makes the method practical for thousands of plots per village.

## 4. Why A Drift Field Was Needed

Raw edge matching worked well in clearer, larger fields. In denser villages, however, a
small plot can snap onto the wrong neighbouring edge pattern. That failure led to the
second pass.

The second pass estimates a local drift field from the village itself. Confident raw
matches vote for the shift expected nearby. Each plot is then re-solved with an adaptive
prior toward that local shift. The prior is weak when a plot has a sharp edge match and
stronger when the match is ambiguous.

This keeps the method general: no hidden truths or hand-coded plot IDs are used.

## 5. Confidence

Confidence is computed from signals that should transfer across villages:

- edge fit: does the shifted outline sit close to real edges?
- contrast: is this match clearly better than other nearby shifts?
- drift agreement: does the answer agree with nearby confident plots?
- edge density: was there enough image evidence to trust the match?

One important correction was to measure fit and contrast in metres, not pixels. The two
example villages have different pixel sizes, so pixel thresholds made confidence unstable.
Metre-based thresholds are more portable.

## 6. Restraint

The pipeline flags plots with weak evidence, keeps already-aligned plots inside a dead zone,
and gives poor fits low confidence rather than flattering them. This is intentional because
the rubric gives major weight to confidence calibration and to not moving control plots.

## 7. Current Results And Limits

On the public examples, the committed predictions improve median IoU on both villages:

- Vadnerbhairav: 0.612 official to 0.891 predicted.
- Malatavadi: 0.510 official to 0.715 predicted.

Those numbers are only a public sanity check. The method was kept deliberately thin to
avoid overfitting to nine example truths.

Known weak spots:

- thin or elongated plots, where translation is underdetermined along the long edge;
- plots where the recorded area and drawn shape disagree, where translation is the wrong
  correction;
- small rotations or sub-pixel refinements, which could improve the last few percent of
  IoU on clear plots.
