"""Rebuild the licensed numeric catalog from acquired, checksum-pinned primary assets.

Original descriptions are replaced by concise project-authored labels. Source identifiers,
numeric facts and locators remain available for independent review. This is not an
implementation of every source method's complete analysis procedure.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pandas as pd

from human_reliability.evidence_catalog import load_evidence_catalog

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/hra_evidence"
OUT = ROOT / "src/human_reliability/data"

# Short descriptions are independently authored. A source code is a locator, not a new method.
ECA_LABELS = {
    "SF0": "Practiced routine context",
    "SF1": "Changing dynamics in a known setting",
    "SF2": "Unfamiliar scenario elements",
    "SF3": "Scenario practice and encounter frequency",
    "SF4": "A misleading preferred strategy",
    "Inf0": "Complete dependable information",
    "Inf1": "Incomplete access to necessary information",
    "Inf2": "Uncertainty in information reliability",
    "C0": "Unchallenged detection",
    "C1": "Competing signals to track",
    "C2": "Indirect detection criteria",
    "C3": "Attention-intensive detection",
    "C4": "Difficult logic for detecting a condition",
    "C5": "Weak prompts for noticing a condition",
    "C6": "Detection without an established prompt",
    "C10": "Unchallenged interpretation",
    "C11": "Message load in interpretation",
    "C12": "Relations integrated during interpretation",
    "C13": "Deep comprehension required",
    "C14": "Several possible interpretations",
    "C15": "Obscured interpretation cues",
    "C16": "Contradictory diagnostic inputs",
    "C20": "Unchallenged choice",
    "C21": "Choosing a procedure branch",
    "C22": "Selecting another procedure",
    "C23": "Hard-to-apply choice criteria",
    "C24": "Prioritizing several objectives",
    "C25": "Incompatible objectives",
    "C26": "Developing a response strategy",
    "C27": "Combining expertise across parties",
    "C28": "Complex integration of varied cues",
    "C30": "Unchallenged execution",
    "C31": "Many straightforward procedure steps",
    "C32": "Difficult navigation across procedures",
    "C33": "Continuous parameter observation",
    "C34": "Dynamic manual regulation",
    "C35": "Intermittent control over a long period",
    "C36": "Delay between deciding and acting",
    "C37": "Difficult execution criteria or order",
    "C38": "Coordinated work at separated locations",
    "C39": "Suppressing a learned action habit",
    "C40": "Unchallenged team exchange",
    "C41": "Information content exchanged between teams",
    "C42": "Unclear command structure",
    "C43": "Unclear authorization path",
    "C44": "Coordinating diverse organizations",
    "ENV0": "Reference environmental conditions",
    "ENV1": "Cold exposure during physical execution",
    "ENV2": "Cold exposure during cognitive work",
    "ENV3": "Hot or humid surroundings",
    "ENV4": "Insufficient illumination",
    "ENV5": "Glare around the visual target",
    "ENV6": "Severely obscured visibility",
    "ENV7": "Distracting ambient or sudden noise",
    "ENV8": "Bulky protective equipment",
    "ENV9": "Poor footing",
    "ENV10": "Weather or obstacles during strenuous work",
    "ENV11": "Weather or obstacles during travel",
    "ENV12": "Traffic obstructing travel",
    "ENV13": "An unstable work platform",
    "SIC0": "Reference system transparency",
    "SIC1": "Unexpected system behavior",
    "SIC2": "Unexpected reset behavior",
    "SIC3": "Hard-to-predict system behavior",
    "SIC4": "Unclear system failure behavior",
    "HSI0": "Reference interface support",
    "HSI1": "Look-alike indications",
    "HSI2": "Insufficient distinction between instruments",
    "HSI3": "Scattered task information",
    "HSI4": "Unfamiliar display conventions",
    "HSI5": "A target lost in display clutter",
    "HSI6": "Inconsistent display conventions",
    "HSI7": "Inconsistent display interpretation",
    "HSI8": "Look-alike control selection",
    "HSI9": "Controls scattered over panels",
    "HSI10": "Difficult control handling",
    "HSI11": "Confusing control nomenclature",
    "HSI12": "Unidentified controls",
    "HSI13": "Unclear action confirmation",
    "HSI14": "Unclear control state transitions",
    "HSI15": "Unclear human/automation responsibility",
    "TP0": "Reference tool readiness",
    "TP1": "Difficult tool handling",
    "TP2": "Unclear tool limitations",
    "TP3": "Unreliable tool operation",
    "TP4": "Equipment/document naming conflict",
    "TP5": "Unfamiliar tools",
    "TP6": "Uncertain availability of controlled tools",
    "STA0": "Reference staffing",
    "STA1": "Missing needed personnel",
    "STA2": "Missing independent backup",
    "STA3": "Unclear assigned responsibilities",
    "STA4": "Task/personnel mismatch",
    "STA5": "Insufficient decision expertise",
    "STA6": "Weak fitness oversight",
    "PG0": "Reference procedure support",
    "PG1": "Difficult procedure usability",
    "PG2": "Interpretive procedure wording",
    "PG3": "Missing procedural detail",
    "PG4": "Confusing procedural meaning",
    "PG5": "Procedure/scenario mismatch",
    "PG6": "Missing checks of key indications",
    "PG7": "Missing confirmation of suspect information",
    "TE0": "Reference qualification and practice",
    "TE1": "Training recency category",
    "TE2": "Insufficient practical rehearsal",
    "TE3": "Insufficient adaptive procedure training",
    "TE4": "Insufficient qualification training",
    "TE5": "Limited operator experience",
    "TE6": "Weak training administration",
    "TE7": "Insufficient instrument knowledge",
    "TE8": "Insufficient alarm criticality training",
    "TE9": "Insufficient confirmatory-data training",
    "TE10": "Early termination of diagnosis data collection",
    "TE11": "Insufficient action-margin training",
    "TE12": "Insufficient contextual procedure training",
    "TE13": "Insufficient execution checking training",
    "TF0": "Reference team organization",
    "TF1": "Insufficient team capability",
    "TF2": "Weak command allocation",
    "TF3": "Weak shared information management",
    "TF4": "Weak interteam communication",
    "TF5": "Teams competing for resources",
    "WP0": "Reference work practices",
    "WP1": "Weak self/cross verification",
    "WP2": "Weak peer oversight",
    "WP3": "Poor ordering and scheduling of work",
    "WP4": "Weak pre-task hazard awareness",
    "WP5": "Weak safety issue detection practices",
    "WP6": "Weak safety reporting practices",
    "WP7": "An adversarial workplace",
    "MT0": "Reference attention allocation",
    "MT1": "Competing activity distracts attention",
    "MT2": "Main activity interrupted",
    "MT3": "Visual monitoring plus another activity",
    "MT4": "Auditory monitoring plus another activity",
    "MT5": "Diagnosis plus another activity",
    "MT6": "Concurrent binary choices",
    "MT7": "Interwoven complex decisions",
    "MT8": "Action sequence plus another memory task",
    "MT9": "Interwoven execution plans",
    "MT10": "Multiple concurrent team exchanges",
    "MF0": "Reference cognitive endurance",
    "MF1": "Sustained attention beyond half an hour",
    "MF2": "Perceived urgency",
    "MF3": "Rushing removes verification",
    "MF4": "Hesitation over adverse consequences",
    "MF5": "Demanding work beyond four hours",
    "MF6": "Abrupt workload increase",
    "MF7": "Abrupt workload decrease",
    "MF8": "Emotional strain",
    "MF9": "Physical strain affecting cognition",
    "MF10": "Insufficient sleep",
    "PD0": "Reference physical demands",
    "PD1": "Work near physical capacity",
    "PD2": "Fine spatial or temporal accuracy",
    "PD3": "Coordinated fine movement by several people",
    "PD4": "Awkward or unbalanced loading",
    "PD5": "Moving loads with lifting equipment",
}
HEART_TASK_LABELS = dict(
    zip(
        "ABCDEFGHM",
        (
            "Urgent work in an unfamiliar situation",
            "Unassisted system reconfiguration",
            "Demanding skilled comprehension",
            "Simple work with limited attention",
            "Practiced rapid routine work",
            "Checked reconfiguration using procedures",
            "Highly rehearsed work under favorable support",
            "Responding to interpreted supervisory prompts",
            "Unclassified task reference",
        ),
        strict=True,
    )
)
EPC_LABELS = (
    "Rare unfamiliar circumstances",
    "Little time for noticing and correction",
    "Weak signal separation",
    "Easy suppression of important indications",
    "Poor representation of system relationships",
    "Designer/operator mental-model disagreement",
    "Difficult reversal of an unintended operation",
    "Too much information at once",
    "Replacing a contrary learned technique",
    "Knowledge transfer between tasks",
    "Unclear required performance",
    "Misjudged risk",
    "Unhelpful system feedback",
    "Delayed action confirmation",
    "Limited task experience",
    "Weak procedural or interpersonal information",
    "Insufficient independent checking",
    "Conflict between short and long term aims",
    "Lack of diverse corroborating inputs",
    "Task/education mismatch",
    "Incentive for a less safe alternative",
    "Restricted activity beyond the immediate job",
    "Noticeably unreliable instrumentation",
    "Judgment outside demonstrated capability",
    "Unclear responsibility allocation",
    "Poor indication of task progress",
    "Work near physical limits",
    "Low intrinsic task meaning",
    "Emotional pressure",
    "Illness affecting performance",
    "Low team morale",
    "Inconsistent meaning across displays and procedures",
    "Adverse surroundings",
    "Low-demand repetitive work",
    "Disrupted sleep/work rhythm",
    "Externally imposed task pace",
    "Additional personnel beyond the task need",
    "Age-related perceptual task reference",
)
POWER_TASK_LABELS = (
    "Prepare the work order",
    "Obtain work authorization",
    "Locate the isolation point",
    "Select protective equipment before isolation",
    "Disconnect the feeder",
    "Apply isolation identification",
    "Report isolation status",
    "Select protective equipment before testing",
    "Verify the test instrument",
    "Test for absence of voltage",
    "Recheck the test instrument",
    "Report test findings",
    "Position the grounding point",
    "Lay out the discharge connection",
    "Secure discharge connections",
    "Prepare the discharge device",
    "Check personnel clearance around the connection",
    "Perform discharge and assess its indication",
    "Report discharge status",
    "Choose the temporary grounding site",
    "Inspect the temporary grounding connection",
    "Clear unnecessary personnel",
    "Attach the grounding end",
    "Connect phase grounding points",
    "Ground the opposite end",
    "Report temporary grounding status",
)


def numeric(value):
    text = str(value).strip().replace("\u2212", "-").replace(" ", "")
    if text.startswith("E"):
        text = "1" + text
    return float(text)


def table(xml_root, identity):
    element = xml_root.find(f'.//table-wrap[@id="{identity}"]')
    if element is None:
        raise ValueError("source table not found: " + identity)
    return [
        [" ".join(cell.itertext()).strip() for cell in row if cell.tag in {"td", "th"}]
        for row in element.findall(".//tr")
    ]


def source_record(identity, title, authors, url, version, setting, license_id, license_url, limitations):
    return dict(
        id=identity,
        title=title,
        authors=authors,
        url=url,
        version=version,
        reviewed_on="2026-10-26",
        setting=setting,
        rights=dict(
            license_id=license_id,
            reference=license_url,
            numeric_reuse=(
                "government_public_use"
                if license_id == "US-government-public-use"
                else "numeric_facts_only"
                if license_id == "NRC-publication-numeric-facts"
                else "permitted_with_attribution"
            ),
            notice="Retain source credit and this license; project labels are independently authored. "
            "External works and third-party exclusions retain their own terms.",
        ),
        limitations=limitations,
    )


def asset_check():
    manifest = json.loads((ROOT / "research/human_evidence_assets.json").read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        path = ROOT / asset["path"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError("missing or changed evidence asset: " + asset["path"])
    return manifest


def category_labels(column, legend, function):
    binary = {"0": "Condition absent", "1": "Condition present"}
    if "Not Exist" in legend or "Not exist" in legend:
        return binary
    choices = {
        "ActionType": ["Unspecified", "Discrete action", "Ordered actions", "Maintaining a condition"],
        "ActionLocation": ["Unspecified", "Main/auxiliary board", "Rear control panel"],
        "ActionGuidance": [
            "Unspecified",
            "Procedural guidance",
            "Craft skill with intact equipment",
            "STAR with faulted equipment",
        ],
        "ActionRecoverability": [
            "Unspecified",
            "Readily recoverable",
            "Recovery needs substantial effort",
            "No recovery available",
        ],
        "Workload": [
            "Unspecified",
            "Reference workload",
            "A concurrent demand",
            "Several concurrent demands",
        ],
        "TimeCriticality": ["Unspecified", "Large time margin", "Reference time margin", "Small time margin"],
        "ExtendOfCommunication": [
            "Unspecified",
            "Reference exchange",
            "Extensive exchange on site",
            "Extensive exchange in control room",
        ],
        "DetectionMode": (
            [
                "Unspecified",
                "Self-revealing cue",
                "Procedure prompts a check",
                "Procedure prompts monitoring",
                "Awareness or inspection",
            ]
            if function == "detect_alarm"
            else [
                "Unmapped zero category",
                "Procedure prompts a check",
                "Source combined knowledge-monitoring/self-revealing category",
                "Procedure prompts monitoring",
                "Awareness or inspection",
            ]
        ),
        "AlarmBoardStatus": ["Unspecified", "Dark alarm board", "Busy alarm board", "Overloaded alarm board"],
        "Expectation": ["Unspecified", "Expected cue", "Unexpected cue", "Not applicable"],
        "DecisionBasis": ["Unspecified", "Standard context", "Adaptation needed", "Anomalous context"],
        "DecisionFamiliarity": [
            "Unspecified",
            "Clear choice",
            "Uncertain choice",
            "Competing priorities",
            "Conflicting guidance",
        ],
        "DecisionUncertainty": [
            "Unspecified",
            "Procedure-guided behavior",
            "Skill-guided behavior",
            "Knowledge-guided behavior",
        ],
        "DecisionOutcome": ["Unspecified", "Discrete outcome", "Ordered outcome", "Maintaining a condition"],
        "ChangeDegree": ["Unspecified", "Small change", "Clear change"],
        "DiagnosisBasis": [
            "Unspecified",
            "Procedure-guided interpretation",
            "Skill-guided interpretation",
            "Knowledge-guided interpretation",
        ],
        "DiagnosisFamiliarity": ["Unspecified", "Standard context", "Novel context", "Anomalous context"],
        "DiagnosisOutcome": [
            "Unspecified",
            "Procedure-guided behavior",
            "Skill-guided behavior",
            "Knowledge-guided behavior",
        ],
        "Information Specificity": [
            "Unspecified",
            "Specific information",
            "Nonspecific information",
            "Not applicable",
        ],
    }
    if column == "Alarm-StatusTile":
        return {"1": "Alarm indication", "2": "Status indication"}
    if column == "Meter Type":
        return {
            "3": "Meter",
            "4": "Indicator lamp",
            "5": "Flag",
            "6": "Computer display",
            "7": "Other source",
        }
    if column not in choices:
        raise ValueError("unreviewed categorical source field: " + column)
    result = {str(i): label for i, label in enumerate(choices[column])}
    if column == "DetectionMode" and function == "read_indicator":
        result.pop("0")
    return result


def sacada_records():
    records, codebook, audit = [], {}, {}
    source_aliases = {
        "AditionalMentalEffortRequired": "additional_mental_effort_required",
        "PoorInfomrationTiming": "poor_information_timing",
        "ExtendOfCommunication": "extent_of_communication",
        "MultipleDemands": "multiple_demand",
    }
    for stem, function in (
        ("alarms", "detect_alarm"),
        ("indicator", "read_indicator"),
        ("understanding", "understanding"),
        ("deciding", "decision"),
        ("action", "action"),
    ):
        path = RAW / "sacada" / f"sacada-{stem}psfs-201904.xls"
        sheet = pd.ExcelFile(path).sheet_names[0]
        frame = pd.read_excel(path)
        legends = frame.iloc[0]
        frame = frame.iloc[1:].apply(pd.to_numeric, errors="raise")
        if frame.isna().any().any() or (frame.to_numpy() % 1 != 0).any():
            raise ValueError("SACADA needs complete integer codes and counts")
        frame = frame.astype(int)
        names = []
        book = {}
        for name in frame.columns[:-2]:
            alias = source_aliases.get(name) or re.sub(r"(?<=[a-z])(?=[A-Z])", "_", name).lower().replace(
                "-", "_"
            ).replace(" ", "_")
            names.append(alias)
            legend = str(legends[name])
            codes = sorted(set(int(v) for v in frame[name]))
            null_codes = [0] if re.search(r"0\s*:\s*NULL", legend, re.I) else []
            book[alias] = dict(
                source_column=name,
                observed_codes=codes,
                missing_codes=null_codes,
                codes=category_labels(name, legend, function),
                interpretation="Categorical source code; 0 is missing only when listed in missing_codes.",
            )
        codebook[function] = book
        if frame.iloc[:, :-2].duplicated().any():
            raise ValueError("source repeats a full context vector; do not assume disjoint groups")
        for ordinal, (_, row) in enumerate(frame.iterrows(), start=3):
            records.append(
                dict(
                    id=f"sacada.{function}.r{ordinal:04}",
                    source_id="sacada_2019",
                    kind="observed_count",
                    method="observed_counts",
                    function=function,
                    label=f"Observed {function.replace('_', ' ')} training-objective context {ordinal - 2}",
                    domain="nuclear_simulator",
                    locator=f"{path.name}; {sheet}; Excel row {ordinal}",
                    quantity="probability",
                    opportunity_definition="One evaluated simulator training objective element in the released function/context group",
                    failure_definition="UNSAT assessment of the evaluated simulator training objective element",
                    conditions=dict(zip(names, (int(row[name]) for name in frame.columns[:-2]), strict=True)),
                    failures=int(row["UNSAT#"]),
                    opportunities=int(row["Opportunity#"]),
                    basis="simulator_observation",
                    limitations=[
                        "UNSAT is the training assessment outcome; recovery and timing cannot be separated from the released counts.",
                        "Crew/episode identities and exposure years are absent; repeated trials are not verified independent.",
                    ],
                )
            )
        audit[function] = dict(
            contexts=len(frame),
            unsatisfactory=int(frame["UNSAT#"].sum()),
            opportunities=int(frame["Opportunity#"].sum()),
            minimum_context_opportunities=int(frame["Opportunity#"].min()),
        )
    return records, codebook, audit


def method_row(
    identity,
    source,
    method,
    function,
    label,
    value,
    locator,
    *,
    kind="method_probability",
    conditions=None,
    lower=None,
    upper=None,
    basis="method_reference",
    limitations=(),
):
    quantity = {
        "method_probability": "probability",
        "method_interval": "probability",
        "method_component": "base_component",
        "method_multiplier": "multiplier",
        "method_rule": "terminal_rule",
    }[kind]
    result = dict(
        id=identity,
        source_id=source,
        kind=kind,
        method=method,
        function=function,
        label=label,
        domain="method_reference",
        locator=locator,
        quantity=quantity,
        opportunity_definition="One task or cognitive function under the source method's stated definition",
        failure_definition="Source-defined error for the referenced task or cognitive function",
        conditions=conditions or {},
        basis=basis,
        limitations=list(limitations),
    )
    if value is not None:
        result["value"] = float(value)
    if lower is not None:
        result.update(lower=float(lower), upper=float(upper))
    return result


def eca_records():
    import pdfplumber

    records, excluded = [], []
    functions = ("detection", "understanding", "decision", "action", "coordination")
    page_table = {
        96: 1,
        97: 2,
        98: 2,
        **{page: 3 for page in range(99, 104)},
        104: 4,
        105: 5,
        106: 6,
        107: 7,
        108: 9,
        109: 10,
        110: 10,
        111: 11,
        112: 12,
        113: 13,
        114: 14,
        115: 15,
    }
    seen = Counter()
    variants = {
        ("SF3", 1): "trained_infrequent",
        ("SF3", 2): "unfamiliar_rare",
        ("SF3", 3): "extremely_rare",
        ("Inf1", 1): "temporarily_incomplete",
        ("Inf1", 2): "moderately_incomplete",
        ("Inf1", 3): "largely_incomplete",
        ("Inf2", 1): "low_uncertainty",
        ("Inf2", 2): "moderate_uncertainty",
        ("Inf2", 3): "high_uncertainty",
        ("Inf2", 4): "extreme_uncertainty",
        ("ENV2", 1): "moderate_cold",
        ("ENV2", 2): "extreme_cold",
    }
    special = {
        "C1": [
            ("fewer_than_7_signals", 0.003),
            ("7_to_11_signals", 0.01),
            ("11_to_20_signals", 0.1),
            ("more_than_20_signals", 0.3),
        ],
        "C11": [
            ("fewer_than_11_messages", 0.01),
            ("11_to_15_messages", 0.05),
            ("15_to_20_messages", 0.1),
            ("more_than_20_messages", 0.3),
        ],
        "C12": [
            ("2_relations", 0.02),
            ("3_relations", 0.045),
            ("4_relations", 0.1),
            ("more_than_4_relations", 0.3),
        ],
        "C41": [
            ("simple_exchange", 0.0015),
            ("moderate_exchange", 0.01),
            ("high_complexity_exchange", 0.05),
            ("extreme_complexity_exchange", 0.1),
        ],
    }
    with pdfplumber.open(RAW / "methods/ML22300A117.pdf") as document:
        for page_number, table_number in page_table.items():
            last_code = None
            for source_table in document.pages[page_number - 1].extract_tables():
                if len(source_table[0]) not in {3, 7}:
                    continue
                for row in source_table[1:]:
                    raw_code = (row[0] or "").strip()
                    if raw_code.startswith("Notes"):
                        continue
                    code = re.sub(r"(?<=\d)a$", "", raw_code) if raw_code else last_code
                    if code not in ECA_LABELS:
                        raise ValueError("unreviewed ECA source identifier: " + str(code))
                    last_code = code
                    seen[code] += 1
                    variant = variants.get((code, seen[code]), "source_level")
                    number = 8 if code.startswith("STA") else table_number
                    locator = f"NUREG-2256; Table B-{number}; printed B-{page_number - 94}; source {code}; variant {seen[code]}"
                    if len(row) == 3:
                        function = functions[(page_number - 99)]
                        levels = special.get(code) or [(variant, numeric(row[2]))]
                        for level, value in levels:
                            records.append(
                                method_row(
                                    f"eca.{code}.{level}.{function}",
                                    "idheas_eca_2022",
                                    "idheas_eca",
                                    function,
                                    ECA_LABELS[code] + " / " + level.replace("_", " "),
                                    value,
                                    locator,
                                    kind="method_component",
                                    conditions={
                                        "pif_code": code,
                                        "pif_family": "task_complexity",
                                        "level": level,
                                    },
                                )
                            )
                        continue
                    for function, cell in zip(functions, row[2:], strict=True):
                        text = (cell or "").strip()
                        if text in {"NA", ""}:
                            excluded.append(
                                dict(locator=locator, function=function, reason="not_applicable_or_blank")
                            )
                            continue
                        if code == "ENV1":
                            levels = list(
                                zip(
                                    (
                                        "moderate_cold",
                                        "extreme_cold_instrument",
                                        "extreme_cold_strenuous",
                                        "extreme_cold_precise",
                                    ),
                                    map(numeric, text.splitlines()),
                                    strict=True,
                                )
                            )
                        elif code == "TE1":
                            levels = [
                                ("less_than_6_months_or_SAT_backbone", 1),
                                ("6_to_12_months_or_SAT_infrequent", 1.2),
                                (
                                    "more_than_4_years_or_outside_SAT",
                                    5 if function in {"detection", "coordination"} else 10,
                                ),
                            ]
                        elif code in {"MT1", "MT2", "MT3", "MT4", "MT5"} and not re.fullmatch(
                            r"[\d.]+", text
                        ):
                            mapping = {
                                "MT1": [("weak", 1.2), ("moderate", 2), ("high", 2.8)],
                                "MT2": list(
                                    zip(
                                        ("weak", "moderate", "frequent_or_long"),
                                        {
                                            "detection": (1.15, 2.8, 4),
                                            "understanding": (1.15, 1.5, 1.7),
                                            "decision": (1.15, 1.5, 1.7),
                                            "action": (1.15, 2.8, 4),
                                            "coordination": (1.1, 2.8, 4),
                                        }[function],
                                        strict=True,
                                    )
                                ),
                                "MT3": [("low", 2), ("moderate", 5), ("high", 10)],
                                "MT4": [("auditory_plus_visual", 10), ("auditory_plus_auditory", 20)],
                                "MT5": [("low", 3), ("high", 30)],
                            }
                            levels = mapping[code]
                        else:
                            levels = [(variant, numeric(text))]
                        for level, value in levels:
                            base = number <= 3
                            placeholder = not base and value in {1.1, 1.2}
                            limitations = []
                            if placeholder:
                                limitations.append(
                                    "Source Appendix B identifies 1.1/1.2 as placeholders with insufficient quantitative conversion evidence; not a measured multiplier."
                                )
                            if code == "WP3":
                                limitations.append(
                                    "Source footnote identifies a 2021 three-expert elicitation; uncertainty documentation is required."
                                )
                            records.append(
                                method_row(
                                    f"eca.{code}.v{seen[code]}.{level}.{function}",
                                    "idheas_eca_2022",
                                    "idheas_eca",
                                    function,
                                    ECA_LABELS[code] + " / " + level.replace("_", " "),
                                    value,
                                    locator,
                                    kind="method_component" if base else "method_multiplier",
                                    conditions={
                                        "pif_code": code,
                                        "level": level,
                                        "pif_family": "scenario_familiarity"
                                        if number == 1
                                        else "information"
                                        if number == 2
                                        else "modifier",
                                    },
                                    basis="placeholder" if placeholder else "method_reference",
                                    limitations=limitations,
                                )
                            )
    for function in functions:
        records.append(
            method_row(
                f"eca.minimum.{function}",
                "idheas_eca_2022",
                "idheas_eca",
                function,
                "Minimum reference when all three base influences are inactive",
                0.0001 if function in {"detection", "action"} else 0.001,
                "NUREG-2256; Appendix B introductory note; printed B-1",
                limitations=(
                    "This floor belongs to the source's crew/task model; it is not a measured field error rate.",
                ),
            )
        )
    return records, excluded


def plos_records():
    records, source_info, anomalies = [], [], []
    for stem, source_id, title, setting in (
        (
            "powerline_xml",
            "plos_powerline_2021",
            "Human reliability analysis in de-energization of power line using HEART in the context of Z-numbers",
            "Expert-assessed electrical isolation case study",
        ),
        (
            "flight_heart_xml",
            "plos_flight_2020",
            "Flight safety assessment based on an integrated human reliability quantification approach",
            "Expert-assessed flight phase case study",
        ),
        (
            "cream_xml",
            "plos_cream_2024",
            "Flight safety assessment based on a modified human error risk quantification approach",
            "Method reference and low-visibility approach case study",
        ),
    ):
        xml = ET.parse(RAW / "methods" / (stem + ".xml")).getroot()
        doi = xml.find('.//article-id[@pub-id-type="doi"]').text
        authors = [
            " ".join(
                "".join(node.itertext())
                for tag in ("given-names", "surname")
                if (node := author.find(tag)) is not None
            )
            for author in xml.findall('.//contrib[@contrib-type="author"]/name')
        ]
        license_node = xml.find(".//license")
        if license_node is None or "creativecommons.org/licenses/by/" not in ET.tostring(
            license_node, encoding="unicode"
        ):
            raise ValueError("expected attribution-only source license not found")
        source_info.append(
            source_record(
                source_id,
                title,
                authors,
                "https://doi.org/" + doi,
                "Published article XML",
                setting,
                "CC-BY-4.0",
                "https://creativecommons.org/licenses/by/4.0/",
                [
                    "Published method numbers are not observed error/opportunity counts.",
                    "Use the source task, elicitation and domain conditions; no universal transfer or superiority claim.",
                ],
            )
        )
        if stem == "powerline_xml":
            for row in table(xml, "pone.0253827.t001")[1:]:
                code, _, value, interval = row
                bounds = [float(v.replace(",", ".")) for v in re.findall(r"\d+[.,]\d+", interval)]
                extra = {}
                if bounds[0] <= numeric(value) <= bounds[1]:
                    extra = dict(lower=bounds[0], upper=bounds[1])
                else:
                    anomalies.append(
                        dict(
                            source_id=source_id,
                            locator="Table 1 / " + code,
                            issue="Published interval is reversed or does not contain its nominal; bounds withheld, not silently corrected.",
                            source_bounds=bounds,
                            nominal=numeric(value),
                        )
                    )
                records.append(
                    method_row(
                        "heart.gtt." + code,
                        source_id,
                        "heart",
                        "generic_task",
                        HEART_TASK_LABELS[code],
                        numeric(value),
                        "Table 1 / GTT " + code,
                        conditions={"generic_task_code": code},
                        **extra,
                        limitations=(
                            "Source percentile bounds describe a method reference, not a confidence interval from released counts.",
                        ),
                    )
                )
            seen = Counter()
            for code, _, value in table(xml, "pone.0253827.t002")[1:]:
                index = int(code)
                seen[index] += 1
                records.append(
                    method_row(
                        f"heart.epc.{index}.v{seen[index]}",
                        source_id,
                        "heart",
                        "generic_task",
                        EPC_LABELS[index - 1] + (" / later period" if seen[index] > 1 else ""),
                        numeric(value.replace("\u00d7", "")),
                        f"Table 2 / EPC {index} / variant {seen[index]}",
                        kind="method_multiplier",
                        conditions={"epc_code": index, "variant": seen[index]},
                    )
                )
            for row in table(xml, "pone.0253827.t006"):
                if not re.fullmatch(r"T\d+", row[0]):
                    continue
                task, generic, _, epc, z_value, fuzzy_value = row
                for method, value in (("z_heart", z_value), ("fuzzy_heart", fuzzy_value)):
                    record = method_row(
                        f"powerline.{task}.{method}",
                        source_id,
                        method,
                        "procedural_task",
                        POWER_TASK_LABELS[int(task[1:]) - 1],
                        numeric(value),
                        "Table 6 / " + task,
                        conditions={"task_code": task, "generic_task_code": generic, "epc_codes": epc},
                        basis="expert_case_study",
                    )
                    record["domain"] = "electrical_isolation_case_study"
                    records.append(record)
        elif stem == "flight_heart_xml":
            for row in table(xml, "pone.0231391.t003")[2:]:
                task, generic, epcs, improved, original = row[-5:]
                for method, value in (("iahp_heart", improved), ("heart", original)):
                    record = method_row(
                        f"flight.{task}.{method}",
                        source_id,
                        method,
                        "flight_task",
                        "Flight task " + task + " in the published elicitation",
                        numeric(value),
                        "Table 3 / " + task,
                        conditions={
                            "task_code": task,
                            "flight_phase_code": task.split(".")[0],
                            "generic_task_code": generic,
                            "epc_codes": epcs,
                        },
                        basis="expert_case_study",
                    )
                    record["domain"] = "aviation_expert_case_study"
                    records.append(record)
        else:
            labels = {
                "O1": "Selecting the wrong observation target",
                "O2": "Misclassifying an observation",
                "O3": "Skipping an observation",
                "I1": "Reaching the wrong diagnosis",
                "I2": "Choosing an unsuitable response",
                "I3": "Interpreting too late",
                "P1": "Ordering priorities incorrectly",
                "P2": "Constructing an inadequate plan",
                "E1": "Choosing an incorrect action form",
                "E2": "Acting at an unsuitable time",
                "E3": "Operating the wrong target",
                "E4": "Executing steps in an unsuitable order",
                "E5": "Omitting a required action",
            }
            for row in table(xml, "pone.0302511.t003")[1:]:
                code = re.search(r"[OIPE]\d", row[-2])[0]
                records.append(
                    method_row(
                        "cream.nominal." + code,
                        source_id,
                        "cream_extended_nominal",
                        {"O": "detection", "I": "understanding", "P": "planning", "E": "action"}[code[0]],
                        labels[code],
                        numeric(row[-1]),
                        "Table 3 / " + code,
                        conditions={"failure_mode_code": code},
                        limitations=(
                            "A secondary published nominal reference, not an official CREAM software output or local calibration.",
                        ),
                    )
                )
            for row in table(xml, "pone.0302511.t005")[1:]:
                task, _, error, nominal, hep = row[-9:-4]
                value = re.match(r"[\d.]+E[-+]?\d+", hep)[0]
                record = method_row(
                    "flight_cream." + task,
                    source_id,
                    "cream_case_study",
                    "flight_task",
                    "Low-visibility approach operation " + task,
                    numeric(value),
                    "Table 5 / " + task,
                    conditions={
                        "task_code": task,
                        "failure_mode_code": error,
                        "nominal_reference": numeric(nominal),
                    },
                    basis="expert_case_study",
                )
                record["domain"] = "aviation_expert_case_study"
                records.append(record)
    return records, source_info, anomalies


def lng_records():
    import pdfplumber

    with pdfplumber.open(RAW / "methods/jmse-10-00333.pdf") as source:
        text = "".join(page.extract_text() or "" for page in source.pages)
    if "0.009841" not in text:
        raise ValueError("published LNG estimate is absent from the pinned source")
    rows = []
    for mode, lower, upper in (
        ("strategic", 0.000005, 0.01),
        ("tactical", 0.001, 0.1),
        ("opportunistic", 0.01, 0.5),
        ("scrambled", 0.1, 1.0),
    ):
        rows.append(
            method_row(
                "cream.control_mode." + mode,
                "mdpi_lng_2022",
                "cream_control_mode",
                "generic_task",
                "Control-mode reference / " + mode,
                None,
                "Table 2 / " + mode,
                kind="method_interval",
                lower=lower,
                upper=upper,
                conditions={"control_mode": mode},
                limitations=(
                    "Source intervals are method categories, not sampled confidence intervals or probability distributions.",
                ),
            )
        )
    result = method_row(
        "lng.fuzzy_bn_cream.published_prior",
        "mdpi_lng_2022",
        "fuzzy_bn_cream_case_study",
        "bunkering_task",
        "Published LNG bunkering context prior",
        0.009841,
        "Abstract / published prior HEP",
        basis="expert_case_study",
        conditions={"same_probability_assumed_for_all_tasks": True, "time_invariant_assumption": True},
        limitations=(
            "Questionnaire-derived model output, not counted operational failures.",
            "Source assumes equal HEPs across tasks and no duration dependence; do not transfer to a specific station without review.",
        ),
    )
    result["domain"] = "lng_bunkering_expert_case_study"
    rows.append(result)
    return rows


def main():
    manifest = asset_check()
    observations, codebook, audit = sacada_records()
    components, excluded = eca_records()
    estimates, plos_sources, anomalies = plos_records()
    profiles = json.loads((ROOT / "research/human_method_profiles.json").read_text(encoding="utf-8"))
    sources = [
        source_record(
            "sacada_2019",
            "NRC SACADA public human-performance context counts",
            ["U.S. Nuclear Regulatory Commission"],
            "https://www.nrc.gov/documents-reports/nrc-data",
            "April 2019 release; observations through March 2019",
            "Licensed operators in nuclear training simulators",
            "US-government-public-use",
            "https://www.nrc.gov/about-nrc/site-disclaimer",
            [
                "Training-objective UNSAT counts are not chemical-plant field HEPs.",
                "Functions may share crews and episodes; do not pool across function files.",
                "No calendar exposure or participant-level clustering information is released.",
            ],
        ),
        source_record(
            "idheas_eca_2022",
            "NRC NUREG-2256 IDHEAS-ECA numeric references",
            ["J. Xing", "Y.J. Chang", "J. DeJesus Segarra"],
            "https://www.nrc.gov/docs/ML2230/ML22300A117.pdf",
            "NUREG-2256, October 2022",
            "Generalized method evidence for cognitive functions",
            "US-government-public-use",
            "https://www.nrc.gov/about-nrc/site-disclaimer",
            [
                "Components and modifiers are not complete HEPs.",
                "The values 1.1 and 1.2 are source placeholders, not quantitatively measured multipliers.",
                "Source boundaries at 11 signals and 15 messages overlap as printed; analyst selection must resolve the ambiguity.",
                "No complete official IDHEAS-ECA workflow implementation is claimed.",
            ],
        ),
        source_record(
            "spar_h_2005",
            "NRC NUREG/CR-6883 SPAR-H numerical profile",
            ["D.I. Gertman", "H.S. Blackman", "J.L. Marble", "J.C. Byers", "C.L. Smith"],
            "https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-contractors/cr6883",
            "NUREG/CR-6883, August 2005",
            "Nuclear HRA method reference",
            "NRC-publication-numeric-facts",
            "https://www.nrc.gov/about-nrc/site-disclaimer",
            [
                "Numeric parameters with independently authored labels only; no report prose or worksheet is redistributed.",
                "NRC site policy excludes separately copyrighted third-party material; no blanket relicensing of external works.",
                "PSF selection, context transfer, uncertainty and dependency require analyst review.",
            ],
        ),
        *plos_sources,
        source_record(
            "mdpi_lng_2022",
            "Human Error Probability Assessment for LNG Bunkering Based on Fuzzy Bayesian Network-CREAM Model",
            ["Hongjun Fan", "Hossein Enshaei", "Shantha Gamini Jayasinghe"],
            "https://doi.org/10.3390/jmse10030333",
            "Published 27 February 2022",
            "Questionnaire-informed LNG bunkering model",
            "CC-BY-4.0",
            "https://creativecommons.org/licenses/by/4.0/",
            [
                "The published HEP is a model result; the questionnaire is not an observed error/opportunity series.",
                "The complete fuzzy Bayesian network and 19,683-row CPT are not reproduced by this catalog.",
            ],
        ),
    ]
    records = observations + components + estimates + profiles["records"] + lng_records()
    source_doc, record_doc = (
        dict(schema_version="1", sources=sources),
        dict(schema_version="1", records=records),
    )
    catalog = load_evidence_catalog(source_doc, record_doc)
    OUT.mkdir(exist_ok=True)
    for name, document in (
        ("human_evidence_sources.json", source_doc),
        ("human_error_records.json", record_doc),
        ("sacada_codebook.json", dict(schema_version="1", functions=codebook)),
    ):
        (OUT / name).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    report = dict(
        schema_version="1",
        version="0.2.0",
        source_count=len(sources),
        record_count=len(records),
        by_kind=dict(Counter(row.kind for row in catalog.records.values())),
        by_method=dict(Counter(row.method for row in catalog.records.values())),
        sacada_functions=audit,
        source_anomalies=anomalies,
        excluded_cells=excluded,
        raw_asset_count=len(manifest["assets"]),
        independent_field_trials_claim=False,
        observed_annual_frequency_records=0,
        catalog_sha256=hashlib.sha256((OUT / "human_error_records.json").read_bytes()).hexdigest(),
    )
    (ROOT / "research/human_evidence_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "source_count",
                    "record_count",
                    "by_kind",
                    "by_method",
                    "sacada_functions",
                    "source_anomalies",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
