# Weather Case Evidence for the Paper

## Purpose

This note captures the weather-side evidence relevant to the paper:

`Mendeleev's Method in the Age of AI: The Sequence Pattern Hypothesis Across Language and Weather`

It is intended as a paper-writing support document, not as a public-facing final draft.

## Repository and Primary Sources

Primary project path:

- `/home/vlad/Dev/weather_forecast`

Most useful source files:

- [README.md](/home/vlad/Dev/weather_forecast/README.md)
- [theory_and_runs.md](/home/vlad/Dev/weather_forecast/docs/theory_and_runs.md)
- [project_formulation.md](/home/vlad/Dev/weather_forecast/docs/project_formulation.md)
- [technical_report.html](/home/vlad/Dev/weather_forecast/docs/technical_report.html)
- [paper_artifacts/README.md](/home/vlad/Dev/weather_forecast/docs/paper_artifacts/README.md)
- [temperature_segmentation.json](/home/vlad/Dev/weather_forecast/docs/paper_artifacts/segmentation_reports/temperature_segmentation.json)
- [pressure_segmentation.json](/home/vlad/Dev/weather_forecast/docs/paper_artifacts/segmentation_reports/pressure_segmentation.json)
- [model_w12h.json](/home/vlad/Dev/weather_forecast/docs/paper_artifacts/training_reports/model_w12h.json)
- [model_w15d.json](/home/vlad/Dev/weather_forecast/docs/paper_artifacts/training_reports/model_w15d.json)
- [model_w45d.json](/home/vlad/Dev/weather_forecast/docs/paper_artifacts/training_reports/model_w45d.json)

## High-Level Framing

The weather repository already uses a framing closely aligned with the planned paper:

- weather is treated as a stream of recurring regimes rather than a raw stream of values
- each regime is represented by an analytical ODE segment
- the model learns the grammar of how such regimes follow one another

This is directly useful for the paper because it already matches the language-side structure:

- `observable content -> analytical units -> abstract patterns -> pattern sequences -> inference`

## What the Weather Project Claims

### Core claim

Raw hourly weather observations can be compressed into interpretable analytical segments, each described by:

- equation type
- fitted parameters
- duration

Those segment descriptors can then be used as the input language of a transformer sequence model.

### Strong formulation already present in the repo

From the weather README:

- the system learns weather pattern grammar from single-station observations
- forecasting is performed over sequences of analytical ODE segments
- the approach uses no atmospheric physics and no spatial information

### How to translate this into the main paper

In the main article, this should be phrased more cautiously:

- the weather project provides cross-domain support for the Sequence Pattern Hypothesis
- it shows that pattern-sequence inference is not limited to symbolic linguistic structures
- it does not show parity with operational NWP

## Analytical Units in the Weather Project

The analytical unit is the fitted ODE segment.

Each segment is not just a time window. It is a bounded interval where a local equation continues to fit the observed data.

This is important because the project explicitly rejects arbitrary clock-based slicing as the final representation. The intended logic is:

- fit a local equation
- extend the interval while the fit remains valid
- stop when the local mathematics no longer holds
- start a new segment with the best next equation

This is the weather-side equivalent of structural decomposition in ELA.

## Boundary Logic

The main paper should stress this point because it is one of the best cross-domain parallels.

### In language

Boundaries are induced by syntactic decomposition:

- sentence
- phrase
- word

### In weather

Boundaries are induced by mathematical fit failure:

- a segment continues while the current equation remains valid
- a boundary appears when the residual exceeds tolerance or the current local predictor stops holding

This is a major cross-domain insight:

- the boundary mechanism differs
- the abstraction logic is the same

## Pattern Families Used in the Weather Project

### Temperature

Candidate equation families described in the project:

- constant
- linear
- exponential
- harmonic
- linear-harmonic
- damped-harmonic

Observed segmentation report summary:

- total segments: `1707`
- total hours: `53,352`
- mean duration: `31.3 h`
- overall mean RMS: `0.566 C`

Breakdown:

- `linear_harmonic`: `1234` segments (`72.3%`)
- `damped_harmonic`: `450` segments (`26.4%`)
- `exponential`: `22` segments (`1.3%`)
- `linear`: `1` segment

### Pressure

Candidate equation families:

- constant
- linear
- exponential

Observed segmentation report summary:

- total segments: `1798`
- total hours: `53,352`
- mean duration: `29.7 h`
- overall mean RMS: `0.883 hPa`

Breakdown:

- `exponential`: `895` segments (`49.8%`)
- `linear`: `903` segments (`50.2%`)

### Wind speed

The project README states the wind channel also uses:

- constant
- linear
- exponential

Stored segment count in the paper artifacts:

- `1951` wind segments

## Joint Representation Used for Sequence Learning

After per-channel segmentation, boundaries are unified into a joint sequence.

Reported joint corpus size:

- `10,055` joint segments over 6 years
- mean duration: `5.3 h`

This number is one of the most important weather-side figures for the main paper.

## Sequence Model

The weather repository describes the forecasting model as a transformer encoder over segment sequences.

Important details already documented:

- input is a tail window of segment vectors
- output is a head window of future segment vectors
- the model predicts future analytical regimes rather than raw hourly values directly

Technical report details worth preserving:

- joint segment vectors are represented as 30-dimensional inputs
- a 3-layer transformer encoder is used
- model size: approximately 2.4M parameters
- selected ensemble models are trained with different context windows

## Ensemble Setup and Why It Matters

The weather project found that different horizons work better with different training window sizes.

Selected ensemble:

- `12 h` window model for `h 1-12`
- `45 d` window model for `h 13-24`
- `15 d` window model for `h 25-168`

Training report summaries:

- `model_w12h.json`: `n_segments=10055`, `final_loss=0.0695`
- `model_w45d.json`: `n_segments=10055`, `final_loss=0.1039`
- `model_w15d.json`: `n_segments=10055`, `final_loss=0.0931`

Important interpretation:

- lower training loss did not automatically correspond to better held-out forecast MAE
- this supports the claim that the representation and horizon alignment matter as much as optimization fit

## Main Reported Forecast Results

Evaluation period:

- 7-day evaluation period
- February 2026
- Knock Airport, Ireland

Main ensemble results from the README:

### Hours 1-12

- temperature MAE: `1.42 C`
- pressure MAE: `0.89 hPa`
- wind MAE: `2.48 kt`

### Hours 13-24

- temperature MAE: `2.31 C`
- pressure MAE: `3.74 hPa`
- wind MAE: `1.67 kt`

### Hours 25-168

- temperature MAE: `1.79 C`
- pressure MAE: `7.04 hPa`
- wind MAE: `6.22 kt`

### Key headline result

- pressure MAE at 12 h: `0.89 hPa`
- naive persistence baseline: `1.35 hPa`
- improvement over persistence: `34%`

This is the strongest single weather-side result for the paper.

## How Strong the Weather Evidence Actually Is

### Strong points

- the representation is explicit and interpretable
- the boundary logic is mathematically defined
- the project produces a real forecast from learned pattern sequences
- the system beats persistence on a defensible short-range pressure result
- the project works without spatial grids or embedded atmospheric equations

### Moderate points

- temperature appears roughly comparable to persistence on the reported week rather than clearly superior
- wind results are mixed and weaker
- the ensemble logic suggests different horizons require different context scales

### Weak points / limitations

- single-station setup
- one held-out week is too small for a full forecasting claim
- not competitive with ECMWF or GFS overall
- some internal theory documents are more exploratory than final

## What to Use in the Main Paper

### Safe claims

- The weather system decomposes raw observations into equation-based analytical units.
- Those units are organized into pattern sequences used for transformer-based forecasting.
- The joint segmentation corpus contains `10,055` segments over 6 years with mean duration `5.3 h`.
- On the February 2026 evaluation, pressure forecasting reached `0.89 hPa` MAE at `12 h`, outperforming naive persistence by `34%`.
- The project therefore provides cross-domain support for the Sequence Pattern Hypothesis.

### Claims to phrase carefully

- `the transformer learns the grammar of regimes`
- `the method transfers from language to weather`
- `the approach offers a third path`

These are good article claims, but they should be presented as supported interpretation, not as final proof.

### Claims to avoid or heavily soften

- that this is a general method for all science
- that weather has been solved without physics
- that the model rivals operational NWP

## Best Cross-Domain Parallels for the Main Paper

### Parallel 1: analytical units

- ELA: sentence / phrase / word nodes
- weather: ODE segments

### Parallel 2: boundary formation

- ELA: syntactic parse boundaries
- weather: fit-validity boundaries

### Parallel 3: abstraction

- ELA: node type, TAM, grammar class, CEFR, structural role
- weather: equation family, fitted parameters, duration, joint regime interval

### Parallel 4: sequence learning

- ELA: structural patterns support interpretation and controlled note generation
- weather: segment sequences support forecasting

### Parallel 5: hypothesis-level inference

- both systems claim that the transferable signal is not just raw surface values
- both systems move from content to abstract structured units before inference

## Recommended Weather Section Tone for the Main Paper

Use phrasing such as:

- `The weather case provides a non-linguistic test of the hypothesis.`
- `The same logic of abstraction reappears in a continuous physical signal domain.`
- `The strongest result is a 12-hour pressure forecast that improves on persistence.`
- `The evidence is promising but still preliminary relative to operational forecasting standards.`

## Draft One-Paragraph Weather Summary for Later Reuse

The weather project provides a cross-domain test of the Sequence Pattern Hypothesis in a continuous observational setting. Hourly single-station weather data are segmented into equation-based analytical units, with temperature modeled through six candidate local forms and pressure and wind through three simpler forms. After joint boundary unification, the six-year corpus yields 10,055 interpretable regime segments with mean duration 5.3 hours. A transformer encoder is then trained over sequences of these segment descriptors rather than over raw hourly values. On a held-out February 2026 evaluation, the strongest result is pressure forecasting at 12 hours, where the system achieves 0.89 hPa MAE and outperforms naive persistence by 34 percent. While the approach remains far from operational NWP quality, it provides concrete evidence that abstract pattern sequences can support inference beyond the linguistic domain in which the hypothesis first emerged.
