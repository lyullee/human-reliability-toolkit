# External method, software and data sources

Reviewed 2026-10-26. Source references identify the public specification or library
used for a capability decision. They do not imply official implementation status.
Descriptive source prose and table layouts are excluded. Independently labeled
numeric records and permitted training aggregates have separate reuse notices
in `DATA_LICENSES.md`.

| Topic | Primary source | Use in this project |
|---|---|---|
| Cognition-based HRA | [NRC NUREG-2256, IDHEAS-ECA](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-staff/sr2256) | Appendix B numeric references and limited function kernel; official full quantification not implemented |
| General IDHEAS | [NRC 2021 publication register](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-available-in-adams/2021) | Review of NUREG-2198 general methodology |
| SPAR-H | [NRC NUREG/CR-6883](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-contractors/cr6883) | Arithmetic, dependency and independently labeled at-power numeric profiles |
| Dynamic human/plant analysis | [INL Risk-Informed Systems Analysis reports](https://lwrs.inl.gov/risa-reports/) and [2025 Rancor-HUNTER record](https://inl.elsevierpure.com/en/publications/rancor-hunter-using-a-simulator-engine-for-realistic-human-perfor/) | Motivation for explicit simulator timelines; no HUNTER reproduction claim |
| Survival models | [lifelines regression documentation](https://lifelines.readthedocs.io/en/latest/Survival%20Regression.html) | Optional Weibull AFT/Cox and reference comparison |
| Thermodynamic properties | [CoolProp high-level API](https://coolprop.org/coolprop/HighLevelAPI.html) | SI PropsSI wrapper; backend explicitly selected |
| Boolean decision diagrams | [dd project](https://github.com/tulip-control/dd) | Exact shared-event evaluation backend |
| Sensitivity analysis | [SALib API documentation](https://salib.readthedocs.io/en/latest/api.html) | Sobol indices under declared independent uniform inputs |
| RData parser | [rdata usage documentation](https://rdata.readthedocs.io/en/stable/usage.html) | Optional permissive Python parser for TEP |
| Copyright expression distinction | [U.S. Copyright Office FAQ](https://www.copyright.gov/help/faq/faq-protect.html) | Reuse policy background, not legal clearance |

## Dataset registry

`research/datasets.json` contains dataset titles, creators, license evidence,
selected/deferred decisions and asset locations. `research/acquisition.json`
contains acquired byte counts, hashes and bounded subset integrity records.
`docs/DATA.md` explains what the data can and cannot establish.

## Human-error evidence extension

`research/human_evidence_review.json` records 18 candidate decisions. The selected
seven sources, versions, creators and rights are recorded in the packaged
`human_evidence_sources.json`; `docs/HUMAN_ERROR_DATA.md` explains each record kind.
Pinned source bytes and curation exceptions are in
`research/human_evidence_assets.json` and `research/human_evidence_audit.json`.

| Source | Selected use |
|---|---|
| [NRC SACADA public data](https://www.nrc.gov/documents-reports/nrc-data), April 2019 release | Simulator training UNSAT/opportunity aggregates for five functions |
| [IDHEAS-ECA, NUREG-2256](https://www.nrc.gov/docs/ML2230/ML22300A117.pdf) | Numeric bases, modifiers, floors and explicitly marked placeholders |
| [SPAR-H, NUREG/CR-6883](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-contractors/cr6883) | Numeric at-power diagnosis/action references; contractor-work distinction preserved |
| [Aghaei et al., 2021](https://doi.org/10.1371/journal.pone.0253827) | HEART numeric task/EPC references and power-line expert case estimates |
| [Guo and Sun, 2020](https://doi.org/10.1371/journal.pone.0231391) | Aviation HEART and IAHP-HEART model case estimates |
| [Guo and Suo, 2024](https://doi.org/10.1371/journal.pone.0302511) | CREAM nominal values and aviation case estimates |
| [Fan, Enshaei and Jayasinghe, 2022](https://doi.org/10.3390/jmse10030333) | CREAM control-mode ranges and the published LNG bunkering model prior |

Public accessibility alone does not determine redistribution permission. Each
included subset retains its source-specific notice; deferred/restricted sources
remain metadata-only. None of these method case estimates is an observed annual
human-error frequency series.

- [UCI hydraulic](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems)
- [UCI MetroPT-3](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset)
- [UCI gas turbine](https://archive.ics.uci.edu/dataset/551/gas+turbine+co+and+nox+emission+data+set)
- [UCI water treatment](https://archive.ics.uci.edu/dataset/106/water+treatment+plant)
- [UCI AI4I](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset)
- [UCI SECOM](https://archive.ics.uci.edu/dataset/179/secom)
- [HITL release 13984198](https://zenodo.org/records/13984198)
- [COG-BCI release 7413650](https://zenodo.org/records/7413650)
- [Harvard TEP release](https://doi.org/10.7910/DVN/6C3JR1)

## Existing project interfaces

The reviewed account is [lyullee on GitHub](https://github.com/lyullee).
`docs/INTEGRATION.md` and `research/integration_checks.json` record the exact
repository/package pins, module hashes and executed boundaries. Pins are
reproducibility evidence; they are not a claim that a later upstream version
retains the same API.
