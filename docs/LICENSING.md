# Source and data reuse policy

The project distributes independently written Python code, original explanatory
text, original analysis prompts, method references, dataset metadata and aggregate
research outputs. Original contributions use MIT. This license does not relicense
external datasets, third-party implementations, publications or organization-owned
material.

## Implementation practice

Implement mathematical functions and interfaces from an explicit specification.
Write comments, examples and explanations for the new code. Do not reproduce an
external publication's prose, diagrams, distinctive worksheets, example narratives
or descriptive coefficient tables. Changing individual words alone is not a
clearance method. Required authorship, method references and dependency notices
remain visible.

Generic concepts, methods and mathematical relationships are distinct from their
particular written or visual expression. The
[U.S. Copyright Office explanation](https://www.copyright.gov/help/faq/faq-protect.html)
describes that distinction; it is not a jurisdiction-independent legal opinion or
a patent/trademark search. Attribution alone is not a substitute for permission to
redistribute protected material.

## Data and dependencies

Prefer clear public-domain or permissive assets. Preserve source-specific terms,
authors, versions, integrity evidence and transformation records. A repository's
software license does not necessarily identify its data license. Data that requires
registration, has unresolved reuse terms or adds unnecessary redistribution
obligations is deferred until the intended use is reviewed.

The public source contains acquisition instructions instead of raw source assets or
participant-level data. Version 0.2.0 also includes the separately attributed numeric
catalog described in `DATA_LICENSES.md`: approved aggregate SACADA counts and method
references with independently authored labels. That catalog is not universally
relicensed MIT. COG subset integrity records identify verified members and the
unverified full archive separately. HITL metadata and its archive's embedded license
are recorded without treating them as interchangeable.

Numerical and data libraries are installed as dependencies and keep their own
notices. The package does not bundle external native solvers or external project
source. See `THIRD_PARTY_NOTICES.md` and `research/environment.json` for the recorded
boundary. Adding a new optional backend requires its own review.

## Publication check

Run the build and source-boundary audit. Inspect the resulting wheel and source
archive, the selected dataset terms, added dependency metadata and any newly added
artifacts. Keep credentials, raw data, external source modules and local research
caches outside the source set. Only this project folder is the proposed repository.

Passing the automated check confirms the inspected file boundary. It does not
guarantee the absence of all intellectual-property, employment ownership, privacy,
contractual or jurisdiction-specific issues. No such universal guarantee is made.
