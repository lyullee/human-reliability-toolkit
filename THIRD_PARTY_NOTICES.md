# Third party notices

Original project code and documentation use MIT. The packaged numeric evidence has
source-specific attribution/use notices in `DATA_LICENSES.md` and its source registry.
External libraries and datasets
retain their own licenses. No external implementation is represented as original
project code. Installing an optional library does not change the dataset license.

Core dependencies are NumPy (BSD), SciPy (BSD) and Pydantic (MIT). Optional libraries
include pandas (BSD), scikit-learn (BSD), CoolProp (MIT), lifelines (MIT), SALib (MIT),
dd (BSD), openpyxl (MIT), xlrd (BSD) and rdata (MIT). Optional curation uses
pdfplumber/pdfminer.six (MIT) and keeps their dependencies' own notices. The selected RData reader is a pure-Python
implementation with permissive licensing and no bundled R runtime.
Exact installed metadata and dependency licenses are recorded by
`scripts/inventory_environment.py`. Native optional backends can have additional
terms and are not bundled.

Dataset titles, creators, license evidence, immutable record identifiers and
acquisition checks are in `research/datasets.json` and `research/acquisition.json`.
Raw source assets and participant-level records are excluded from releases.
The approved numeric catalog includes attributed aggregate simulator counts and
method references; it does not relicense external evidence MIT. Dataset
users must retain applicable attribution and transformation notices.

Method references identify mathematical approaches and scope. They do not imply
endorsement by the original authors or that this package is their official tool.
Organizational or employment-related ownership is not resolved by a repository
maintainer name. The release checks establish the inspected source boundary,
not universal freedom from every intellectual-property or jurisdictional issue.
