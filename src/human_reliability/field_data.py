"""Source-qualified physical measurements and incident cases, separate from HEP counts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
from typing import Literal
import zipfile

import numpy as np

from .actions import ProcessState, StateValue
from .contracts import Context, ContextValue, Contract, Evidence, Name, SignalSeries


class FieldSource(Contract):
    id: Name
    title: Name
    doi: Name
    url: Name
    license: Name
    license_evidence: Name
    attribution: Name
    origin: Literal[
        "measured_process",
        "observed_incident_codes",
        "observed_simulator_counts",
        "observed_field_opportunities",
    ]
    domain: Name
    human_opportunity_counts: bool
    conditions: tuple[Name, ...]
    limitations: tuple[Name, ...]

    def evidence(self):
        return Evidence(
            id="field:" + self.id,
            reference=self.attribution + " " + self.url,
            origin="observed",
            applicability="; ".join(self.conditions),
            version=self.doi,
            limitations=self.limitations
            + ("Data license: " + self.license + "; source terms: " + self.license_evidence,),
        )

    def require_human_opportunities(self):
        if not self.human_opportunity_counts or self.origin not in {
            "observed_simulator_counts",
            "observed_field_opportunities",
        }:
            raise ValueError("this source does not establish human task-opportunity counts")

    def context(self, identity: str, state: ProcessState, *, operating_mode: str):
        if self.origin != "measured_process":
            raise ValueError("only measured process sources can provide measured process context")
        return Context(
            id=identity,
            operating_mode=operating_mode,
            factors={
                key: ContextValue(value=value.value, unit=value.unit, evidence_id="field:" + self.id)
                for key, value in state.values.items()
            },
        )


def field_sources() -> dict[str, FieldSource]:
    data = json.loads(files("human_reliability.data").joinpath("field_sources.json").read_text("utf-8"))
    sources = [FieldSource.model_validate_json(json.dumps(row)) for row in data["sources"]]
    if len({s.id for s in sources}) != len(sources):
        raise ValueError("duplicate field source identity")
    return {source.id: source for source in sources}


@dataclass(frozen=True)
class ClockAudit:
    elapsed_s: tuple[float, ...] | None
    qualified: bool
    duplicate_intervals: int
    backwards_intervals: int
    large_gaps: int
    midnight_rollovers: int
    has_calendar_date: bool
    precision: str
    reason: str


def audit_clock(values, *, maximum_gap_s=90.0) -> ClockAudit:
    """Keep source precision; unwrap only a large backwards time-of-day rollover."""
    import pandas as pd

    if not np.isfinite(maximum_gap_s) or maximum_gap_s <= 0:
        raise ValueError("positive finite gap limit required")
    text = [str(value).strip() for value in values]
    if not text:
        raise ValueError("nonempty source clock required")
    dated = [bool(re.match(r"\d{1,2}/\d{1,2}/\d{2,4}\s", value)) for value in text]
    rollovers = 0
    precision = "seconds" if all(re.search(r"\d{1,2}:\d{2}:\d{2}$", t) for t in text) else "mixed_or_minutes"
    if any(dated) and not all(dated):
        return ClockAudit(None, False, 0, 0, 0, 0, True, precision, "mixed dated and undated clock")
    try:
        if all(dated):
            times = pd.to_datetime(pd.Series(text), format="mixed", dayfirst=True, errors="raise")
            seconds = (times - times.iloc[0]).dt.total_seconds().to_numpy()
        else:
            if not all(re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", t) for t in text):
                raise ValueError("unsupported time-of-day format")
            raw = np.asarray(
                [sum(int(v) * factor for v, factor in zip(t.split(":"), (3600, 60, 1))) for t in text], float
            )
            if any(int(t.split(":")[0]) > 23 or any(int(v) > 59 for v in t.split(":")[1:]) for t in text):
                raise ValueError("time-of-day outside range")
            jumps = np.diff(raw)
            midnight = jumps < -43200
            rollovers = int(midnight.sum())
            seconds = raw + np.r_[0, np.cumsum(midnight) * 86400]
            seconds -= seconds[0]
    except (ValueError, OverflowError, TypeError):
        return ClockAudit(
            None, False, 0, 0, 0, rollovers, all(dated), precision, "source clock not parseable"
        )
    diffs = np.diff(seconds)
    duplicates, backwards, gaps = (
        int(np.sum(diffs == 0)),
        int(np.sum(diffs < 0)),
        int(np.sum(diffs > maximum_gap_s)),
    )
    qualified = bool(
        len(seconds) > 1 and not (duplicates or backwards or gaps) and np.isfinite(seconds).all()
    )
    return ClockAudit(
        tuple(map(float, seconds)),
        qualified,
        duplicates,
        backwards,
        gaps,
        rollovers,
        all(dated),
        precision,
        "source clock qualified"
        if qualified
        else "duplicate, backwards, missing or large-gap timing; physical delays withheld",
    )


@dataclass
class DistillationRun:
    id: str
    scenario: str
    operating_point: str
    role: str
    frame: object
    clock: ClockAudit
    source_member: str
    source_sha256: str
    metadata_sha256: str
    annotation_audit: dict

    def numeric_matrix(self, channels):
        """Return numeric measurements plus an audit; preserve invalid raw cells in frame."""
        import pandas as pd

        if not channels or any(c.startswith("Label") or c not in self.frame for c in channels):
            raise ValueError("explicit measured numeric channels excluding labels required")
        arrays, audit = [], {}
        for channel in channels:
            raw = self.frame[channel]
            booleans = raw.map(lambda v: isinstance(v, (bool, np.bool_)))
            numeric = pd.to_numeric(raw, errors="coerce").to_numpy(dtype=float, na_value=np.nan, copy=True)
            malformed = ((~raw.isna()).to_numpy() & ~np.isfinite(numeric)) | booleans.to_numpy()
            numeric[malformed] = np.nan
            if malformed.any() or raw.isna().any():
                audit[channel] = {
                    "source_missing_cells": int(raw.isna().sum()),
                    "non_numeric_boolean_or_nonfinite_cells": int(malformed.sum()),
                    "usable_numeric_cells": int(np.isfinite(numeric).sum()),
                    "imputed": False,
                }
            arrays.append(numeric)
        return np.column_stack(arrays), audit

    def signal(self, channel, unit, *, declared_nominal_period_s=None):
        """Use physical source time by default; an assumed clock requires opt-in."""
        if channel.startswith("Label") or channel not in self.frame:
            raise ValueError("a measured channel, excluding evaluation labels, is required")
        origin = "measured_process"
        if declared_nominal_period_s is None:
            if not self.clock.qualified:
                raise ValueError("source clock is not qualified; no physical-time signal can be inferred")
            times = self.clock.elapsed_s
            clock_id = "source:" + self.id
        else:
            if not np.isfinite(declared_nominal_period_s) or declared_nominal_period_s <= 0:
                raise ValueError("positive explicitly assumed sample period required")
            times = tuple(float(i * declared_nominal_period_s) for i in range(len(self.frame)))
            clock_id, origin = "assumed_grid:" + self.id, "measured_values_on_assumed_clock"
        matrix, _ = self.numeric_matrix([channel])
        values = matrix[:, 0]
        return SignalSeries(
            time_s=times,
            values=tuple(float(v) if np.isfinite(v) else None for v in values),
            valid=tuple(bool(v) for v in np.isfinite(values)),
            clock_id=clock_id,
            unit=unit,
            origin=origin,
        )

    def process_state(self, row: int, channels: dict[str, str]):
        if type(row) is not int or not 0 <= row < len(self.frame) or not channels:
            raise ValueError("valid measured row and explicit channel units required")
        if any(c.startswith("Label") or c not in self.frame for c in channels):
            raise ValueError("evaluation labels must not enter a process observation")
        values = {}
        for channel, unit in channels.items():
            value = self.frame.iloc[row][channel]
            if isinstance(value, (bool, np.bool_)):
                scalar = bool(value)
            elif isinstance(value, (int, float, np.number)):
                scalar = float(value) if np.isfinite(value) else None
            else:
                raise ValueError("only numeric/boolean measured channels can become state values")
            values[channel] = StateValue(value=scalar, unit=unit)
        return ProcessState(revision=self.id + ":row:" + str(row), values=values)


def continuous_distillation(archive, *, strict_advanced_labels=False) -> tuple[DistillationRun, ...]:
    """Read pinned-compatible CSV schemas without resampling or copying source prose."""
    import pandas as pd

    runs = []
    with zipfile.ZipFile(archive) as source:
        for member in sorted(source.namelist()):
            if not re.search(r"/(?:train_normal|test_anormal)_experiment_\d+\.csv$", member):
                continue
            parts = member.split("/")
            if (
                len(parts) != 4
                or not parts[1].startswith("Scenario")
                or not parts[2].startswith("operating_point_")
            ):
                raise ValueError("unrecognized distillation experiment identity")
            if source.getinfo(member).file_size > 30_000_000:
                raise ValueError("distillation member exceeds inspection bound")
            content = source.read(member)
            import io

            frame = pd.read_csv(io.BytesIO(content))
            if "Time" not in frame or "Label (common/all)" not in frame or frame.empty:
                raise ValueError("required measured clock/label schema missing")
            annotation_audit = {}
            for column in frame:
                if column.startswith("Label (common/") and not frame[column].isin([0, 1]).all():
                    raise ValueError("common labels must remain binary source annotations")
                if column.startswith("Label (advanced/"):
                    invalid = ~frame[column].isin([0, 1, 2, 3])
                    if invalid.any():
                        annotation_audit[column] = {
                            "unrecognized_phase_samples": int(invalid.sum()),
                            "use_as_phase_truth": False,
                        }
                        if strict_advanced_labels:
                            raise ValueError("advanced source label phase outside range")
            meta = member[:-4] + ".yaml"
            if meta not in source.namelist():
                raise ValueError("experiment metadata member missing")
            runs.append(
                DistillationRun(
                    id="/".join(parts[1:])[:-4],
                    scenario=parts[1],
                    operating_point=parts[2],
                    role="reference" if parts[3].startswith("train_normal") else "evaluation",
                    frame=frame,
                    clock=audit_clock(frame.Time),
                    source_member=member,
                    source_sha256=hashlib.sha256(content).hexdigest(),
                    metadata_sha256=hashlib.sha256(source.read(meta)).hexdigest(),
                    annotation_audit=annotation_audit,
                )
            )
    if not runs or len({run.id for run in runs}) != len(runs):
        raise ValueError("nonempty unique experiment identities required")
    return tuple(runs)


def steel_energy(archive, *, midnight_policy="reject"):
    import pandas as pd

    with zipfile.ZipFile(archive) as source:
        names = [n for n in source.namelist() if Path(n).name == "Steel_industry_data.csv"]
        if len(names) != 1:
            raise ValueError("exactly one steel measurement member required")
        frame = pd.read_csv(source.open(names[0]))
    if not {"date", "Usage_kWh"} <= set(frame) or frame.empty:
        raise ValueError("steel energy/time fields missing")
    if midnight_policy not in {"reject", "end_of_recorded_day"}:
        raise ValueError("unknown explicit midnight interpretation")
    raw = pd.to_datetime(frame.date, format="%d/%m/%Y %H:%M", errors="raise")
    frame["source_time_raw"] = raw
    frame["source_time"] = raw.copy()
    corrected = 0
    if midnight_policy == "end_of_recorded_day":
        midnight = (raw.dt.hour == 0) & (raw.dt.minute == 0)
        for i in np.flatnonzero(midnight):
            if i == 0 or raw.iloc[i - 1] != raw.iloc[i] + pd.Timedelta(85500, unit="s"):
                raise ValueError("midnight row does not match the declared end-of-recorded-day convention")
            if i + 1 < len(raw) and raw.iloc[i + 1] != raw.iloc[i] + pd.Timedelta(87300, unit="s"):
                raise ValueError("next source row does not confirm the declared midnight convention")
            frame.loc[i, "source_time"] = raw.iloc[i] + pd.Timedelta(86400, unit="s")
            corrected += 1
    frame.attrs["clock_interpretation"] = {
        "policy": midnight_policy,
        "changed_rows": corrected,
        "raw_clock_preserved": True,
        "origin": "declared_interpretation" if corrected else "source_clock",
    }
    if frame.source_time.duplicated().any() or not frame.source_time.is_monotonic_increasing:
        raise ValueError("steel records must preserve strictly increasing source order")
    if not np.isfinite(frame.Usage_kWh).all() or (frame.Usage_kWh < 0).any():
        raise ValueError("finite nonnegative measured consumption required")
    return frame


def rail_incident_cases(path):
    import pandas as pd

    frame = pd.read_csv(path)
    frame.columns = frame.columns.str.strip()
    codes = ["C" + str(i) for i in range(1, 9)]
    if (
        not {"ID", *codes} <= set(frame)
        or frame.empty
        or frame.ID.isna().any()
        or frame.ID.duplicated().any()
    ):
        raise ValueError("unique investigation case IDs and all eight code fields required")
    if not frame[codes].isin([0, 1]).all().all():
        raise ValueError("investigation codes must remain binary and fully observed")
    return frame


def incident_code_summary(frame):
    codes = ["C" + str(i) for i in range(1, 9)]
    if not len(frame) or not set(codes) <= set(frame) or not frame[codes].isin([0, 1]).all().all():
        raise ValueError("nonempty binary investigation codes required")
    return {
        "source_id": "korea_rail_incidents",
        "origin": "observed_incident_codes",
        "recorded_cases": len(frame),
        "denominator_semantics": "recorded_investigated_accidents",
        "code_counts": {c: int(frame[c].sum()) for c in codes},
        "code_case_composition": {c: float(frame[c].mean()) for c in codes},
        "overlapping_code_cases": int((frame[codes].sum(axis=1) > 1).sum()),
        "human_failure_probability": None,
        "annual_human_error_frequency": None,
        "currency_specific_loss": None,
        "reason": "Successful tasks and exposure are absent; codes may overlap; CSV cost unit is not established.",
    }


def incident_lessons(frame, code_to_artifacts, *, analyst_review, recommendations=None):
    """Bind reviewed incident-code findings to existing assurance artifacts, without HEPs."""
    from .assurance import IncidentLesson

    summary = incident_code_summary(frame)
    if not isinstance(analyst_review, str) or not analyst_review.strip() or not code_to_artifacts:
        raise ValueError("explicit analyst transfer review and artifact bindings required")
    if set(code_to_artifacts) - set(summary["code_counts"]) or set(recommendations or {}) - set(
        code_to_artifacts
    ):
        raise ValueError("known incident codes and bound recommendations required")
    lessons = []
    for code, targets in code_to_artifacts.items():
        if not isinstance(targets, tuple) or not targets or len(set(targets)) != len(targets):
            raise ValueError("nonempty unique artifact identities required")
        count = summary["code_counts"][code]
        if count:
            lessons.append(
                IncidentLesson(
                    id="rail_code:" + code,
                    statement=f"Among {summary['recorded_cases']} investigated cases, {count} carry {code}. This is incident composition, not failure-on-demand probability. Transfer review: {analyst_review}",
                    affected_ids=targets,
                    evidence="field:korea_rail_incidents",
                    recommendation=(recommendations or {}).get(code),
                )
            )
    return tuple(lessons)
