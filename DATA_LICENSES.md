# Numeric evidence and source notices

The MIT license covers original software and original project explanations. It
does not replace the terms of external evidence. Keep this notice and the packaged
`human_evidence_sources.json` with `human_error_records.json` when redistributing
the catalog. Resolve every record's `source_id` before reusing it.

## Public government evidence

The `sacada_2019` records are numeric context-group counts derived from the NRC's
[public human reliability dataset](https://www.nrc.gov/documents-reports/nrc-data),
released in April 2019 with observations through March 2019. Credit the U.S.
Nuclear Regulatory Commission. The `idheas_eca_2022` references derive from
J. Xing, Y.J. Chang and J. DeJesus Segarra, *Integrated Human Event Analysis System
for Event and Condition Assessment*, NUREG-2256, October 2022,
[official source](https://www.nrc.gov/docs/ML2230/ML22300A117.pdf).

The [NRC site policy](https://www.nrc.gov/about-nrc/site-disclaimer) describes public
use of U.S. Government site material and excludes separately copyrighted material.
This project preserves attribution and does not imply NRC endorsement.

For `spar_h_2005`, credit D.I. Gertman, H.S. Blackman, J.L. Marble, J.C. Byers and
C.L. Smith, *The SPAR-H Human Reliability Analysis Method*, NUREG/CR-6883, August
2005, [official source](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-contractors/cr6883).
The catalog contains factual numerical parameters with independently written
labels. It does not redistribute the contractor report, its worksheets or its
descriptive text, and does not assert that every part of that report is a U.S.
Government work. Its rights record therefore identifies a numeric-facts boundary
instead of inventing a standard public-domain license for the complete report.

## Creative Commons attribution sources

The following published sources use attribution licenses. Numeric selections in
the catalog retain their source identity and locator. They are not relicensed MIT.
Retain credit, source links, the license link and the transformation statement.

- `plos_powerline_2021`: Hamed Aghaei, Mostafa Mirzaei Aliabadi, Farzaneh
  Mollabahrami and Kamran Najafi (2021), *Human reliability analysis in
  de-energization of power line using HEART in the context of Z-numbers*.
  [Article and license notice](https://doi.org/10.1371/journal.pone.0253827).
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `plos_flight_2020`: Yundong Guo and Youchao Sun (2020),
  *Flight safety assessment based on an integrated human
  reliability quantification approach*.
  [Article and license notice](https://doi.org/10.1371/journal.pone.0231391).
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `mdpi_lng_2022`: Hongjun Fan, Hossein Enshaei and Shantha Gamini Jayasinghe
  (2022), *Human Error Probability Assessment for LNG Bunkering Based on Fuzzy
  Bayesian Network-CREAM Model*.
  [Article and license notice](https://doi.org/10.3390/jmse10030333).
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- `plos_cream_2024`: Yundong Guo and Xinshi Suo (2024), *Flight safety assessment
  based on a modified human error risk quantification approach*.
  [Article and license notice](https://doi.org/10.1371/journal.pone.0302511).
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Transformations: numerical fields were selected and reorganized into typed records;
source codes and locators were retained; descriptive labels were independently
written; merged table cells were resolved into explicit records; unsafe or ambiguous
interpretations were recorded as limitations. A reversed published HEART interval
was withheld without substituting a guessed correction. IDHEAS placeholder weights
remain marked as placeholders. Case-study outputs remain method estimates.

The published references themselves may cite earlier methods or external material.
No claim is made to relicense those earlier works. No third-party diagrams,
worksheets, prose, articles or raw participant records are included in the release.

## Sources retained only as research metadata

`research/human_evidence_review.json` records candidates excluded because of missing
denominators, engineered errors, unavailable raw data, restrictive licenses or
unresolved reuse conditions. A link in that file grants no license to the linked
work. Restricted source numbers are not silently added to the usable catalog.
Local research downloads and source-page caches remain excluded from Git and
distribution archives.


## Original operational examples

Version 0.3 adds original typed templates, synthetic count fixtures and process
state demonstrations. These are authored software examples, not additional
external observations or field-calibrated parameters. The seven-source numeric
catalog is unchanged. New user-owned operational records need their own rights,
provenance and privacy review before redistribution.
