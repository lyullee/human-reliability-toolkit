# Dataset acquisition and eligibility

This page describes the original process/context collection. Version 0.2.0 adds a
separate packaged human-performance catalog; see [Human-error evidence](HUMAN_ERROR_DATA.md)
and its acquisition/audit manifests. The new SACADA acquisition supersedes this
project's earlier deferred-availability assessment.

Fifteen candidate data families were reviewed. Nine were selected and acquired,
occupying approximately 1.705 GB of retained assets. This count includes four
complete Tennessee Eastman files and behavior-only subsets from 29 COG-BCI subject
archives. It excludes the large EEG archive contents that were never downloaded.

## Selected data

| Dataset | Source | Released observations used here | Role |
|---|---|---|---|
| Hydraulic condition monitoring | [UCI 447](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems) | 2,205 independent 60-second cycles | Component-condition and process-context input |
| MetroPT-3 | [UCI 791](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset) | 1,516,948 source records, deterministic stride for the example | Real compressor alarm context |
| Gas turbine emissions | [UCI 551](https://archive.ics.uci.edu/dataset/551/gas+turbine+co+and+nox+emission+data+set) | 36,733 records | Process operating variables; no human failure labels |
| Water treatment plant | [UCI 106](https://archive.ics.uci.edu/dataset/106/water+treatment+plant) | 527 records with missing fields | Missing-data and observation-grain handling |
| AI4I | [UCI 601](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset) | 10,000 synthetic records | Explicitly synthetic failure/context examples |
| SECOM | [UCI 179](https://archive.ics.uci.edu/dataset/179/secom) | 1,567 manufactured items | High-dimensional missingness and item labels |
| Tennessee Eastman additional data | [Harvard Dataverse](https://doi.org/10.7910/DVN/6C3JR1) | Four source files acquired; 250,000 normal-training rows loaded in the audit | Simulated process boundaries and fault scenarios |
| HITL control-room experiment | [Zenodo 13984198](https://zenodo.org/records/13984198) | 47 participants and 139 released simulator-summary rows | Experimental outcome prediction and context analysis |
| COG-BCI version 4 | [Zenodo 7413650](https://zenodo.org/records/7413650) | 3,107 numeric monitoring responses and 7,830 PVT rows | Conditional response distributions and data-quality diagnostics |

Creators, DOI, license evidence, source versions and intended use are recorded in
`research/datasets.json`. Six UCI assets and the Zenodo records have CC BY 4.0
metadata. The HITL archive also contains an MIT file; the catalog preserves both
facts and does not use the embedded software license to erase dataset attribution.
Harvard's TEP record uses a custom public-domain dedication and disclaimer. Preserve
the actual terms rather than replacing them with an invented standard license.

## Acquisition and integrity

```console
python scripts/acquire_data.py
python scripts/acquire_data.py --only hitl cog_bci
python scripts/audit_data.py
python scripts/audit_data.py --only cog_bci
```

Full assets have retained SHA-256 digests and available supplier checksums.
Previously acquired UCI assets can be reused through `--cache-root` after integrity
checks. Archive readers inspect members without uncontrolled extraction.

COG-BCI behavioral members are obtained using validated HTTP byte ranges. The ZIP
member CRC is checked and the extracted member SHA-256 is recorded. The full remote
archive MD5 is only supplier metadata: it is explicitly **not verified**, because
the EEG contents are not downloaded. Local subset archive hashes are retained.
Rate-limited sources are retried with bounded concurrency and server backoff.

The acquisition report lists acquired and failed families. Failed downloads remain
visible, and cached successful subject subsets can be reused on retry. Raw sources,
transformed participant rows, source-page caches and external source modules are
excluded from version control and package distributions.

## Important findings

The HITL overview describes a broader 92-participant study. The current consolidated
file contains 57 participant-info identities and simulator logs for 47 identities,
not 92 complete operator histories. It has scenario-level summaries rather than
one row per alarm opportunity. Its `Accuracy` column is not bounded to [0,1], and
time units/censoring semantics are unresolved. None of those columns is automatically
converted into a human error probability or a physical response deadline.

The COG archives have inconsistent wrapper depth. Readers identify explicit subject
and session components instead of assuming fixed path positions. Numeric MATB and
PVT records can be read; 435 opaque/unsupported MATLAB objects are retained as an
explicit unsupported inventory rather than silently interpreted. A future MATLAB
table reader must reproduce a verified source interpretation before use.

Every PVT session has one positive `error_trial` flag at zero-based ordinal 8. The
same pattern occurs in all 87 sessions. Without an authoritative explanation, it
could represent an instrument convention or another structural marker. HEP
calibration from those flags is withheld. The initial flag-rate diagnostic is kept
as rejected evidence so a later researcher does not repeat the interpretation.

SYSMON's first numeric column is retained as a source alarm code because observed
values resemble codes rather than a time axis. Positive recorded reactions do not
establish the count of alarms that received no response. Distribution results are
conditional on observed responses and retain native units. Physical time mapping
and a missed-alarm denominator require further evidence.

MetroPT's observed spacing differs from a simple interpretation of the nominal
sampling statement. The stride-60 example has a median observed spacing of about
600 seconds. Use actual timestamps and gap policies rather than reconstructing
a one-second clock. Hydraulic cycles are separate experiments; only 21 cycles are
nominal in all four component labels. These limits affect tail calibration.

## Deferred candidates

The larger six-mode TEP reference is CC0 but about 143 GB; initial scenarios already
have a smaller complete TEP source. SKAB's repository carries GPL terms, and a
separately reviewed data asset was not selected for the permissive release.
HAI data-version terms were not resolved. SWaT requires an access/terms workflow.
The earlier SACADA availability conclusion is superseded: the April-2019 public
function/context counts were located and acquired in version 0.2.0. These are
aggregate simulator records, with the limitations explained in the evidence guide.
The earlier EEG
competition has share-alike conditions and is unnecessary for the selected direct
behavior analysis. Deferred does not mean those datasets are unusable; it describes
this release's evidence and acquisition decision.

## New data adapters

An added dataset needs source identity, version, authors, rights evidence, units,
clock, observation unit, labels, missingness, transformation history and intended
use. Human failure calibration additionally needs a defined failure and denominator,
recovered-error treatment, censoring, operator/task grouping and reporting coverage.
Keep a future independent evaluation set outside method selection and fitting.
