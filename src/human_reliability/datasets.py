"""Readers preserve source grain, origin and missingness instead of inventing human labels."""

from __future__ import annotations

import io
from pathlib import Path
import zipfile

import numpy as np


def hitl_tables(archive: str | Path):
    import pandas as pd

    with zipfile.ZipFile(archive) as source:
        names = [name for name in source.namelist() if name.endswith(".xlsx")]
        if len(names) != 1:
            raise ValueError("expected one consolidated HITL workbook")
        book = pd.ExcelFile(io.BytesIO(source.read(names[0])))
        return {sheet: pd.read_excel(book, sheet_name=sheet) for sheet in book.sheet_names}


def cog_behavior(archives):
    """Read numeric MATB/PVT records; opaque MATLAB tables remain explicitly unsupported.

    Durations retain native units. The parser does not interpret SYSMON's first
    column as an onset clock: observed values resemble alarm codes. No missing
    monitoring trials or censoring deadlines are reconstructed.
    """
    import pandas as pd
    from scipy.io import loadmat

    monitoring, vigilance, unsupported = [], [], []

    def unpack(mapping):
        while isinstance(mapping, dict) and not {"SYSMON", "reaction_times"} & set(mapping):
            values = [value for key, value in mapping.items() if not key.startswith("__")]
            if len(values) != 1:
                return mapping
            mapping = values[0]
        return mapping

    for path in sorted(map(Path, archives)):
        with zipfile.ZipFile(path) as source:
            for name in source.namelist():
                if not name.endswith(".mat"):
                    continue
                parts = name.split("/")
                participants = {part for part in parts if part.startswith("sub-")}
                sessions = {part for part in parts if part.startswith("ses-")}
                if len(participants) != 1 or len(sessions) != 1:
                    raise ValueError("ambiguous participant/session path")
                participant, session, task = next(iter(participants)), next(iter(sessions)), Path(name).stem
                if not path.name.startswith(participant + "_"):
                    raise ValueError("archive and member participant identities disagree")
                value = unpack(loadmat(io.BytesIO(source.read(name)), simplify_cells=True))
                if not isinstance(value, dict):
                    unsupported.append({"source": name, "reason": "opaque MATLAB object"})
                    continue
                if "SYSMON" in value:
                    array = np.asarray(value["SYSMON"], float)
                    if array.ndim != 2 or array.shape[1] != 2:
                        raise ValueError("unexpected SYSMON matrix")
                    for trial, (code, duration) in enumerate(array):
                        monitoring.append(
                            {
                                "participant": participant,
                                "session": session,
                                "task": task,
                                "trial": trial,
                                "source_alarm_code": code,
                                "duration_native": duration,
                                "duration_valid": bool(np.isfinite(duration) and duration > 0),
                            }
                        )
                    if "COMM" in value:
                        unsupported.append({"source": name, "reason": "COMM opaque MATLAB table not decoded"})
                elif "reaction_times" in value:
                    times = np.atleast_1d(value["reaction_times"]).astype(float)
                    failures = np.atleast_1d(value["error_trial"])
                    if times.shape != failures.shape or not np.all(np.isin(failures, [0, 1])):
                        raise ValueError("invalid PVT error flags or trial shape")
                    for trial, (duration, failed) in enumerate(zip(times, failures)):
                        vigilance.append(
                            {
                                "participant": participant,
                                "session": session,
                                "task": task,
                                "trial": trial,
                                "duration_native": duration,
                                "duration_valid": bool(np.isfinite(duration) and duration > 0),
                                "source_error_flag": bool(failed),
                            }
                        )
                else:
                    unsupported.append({"source": name, "reason": "unsupported behavioral object"})
    return {
        "monitoring": pd.DataFrame(monitoring),
        "vigilance": pd.DataFrame(vigilance),
        "unsupported": unsupported,
    }


def uci_ai4i(archive):
    import pandas as pd

    with zipfile.ZipFile(archive) as source:
        name = next(name for name in source.namelist() if name.endswith(".csv"))
        return pd.read_csv(source.open(name))


def uci_hydraulic(archive, sensors=("PS1", "TS1", "FS1")):
    """Cycle-wise sensor means; rows remain cycles rather than pseudo time samples."""
    import pandas as pd

    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        profile_name = next(name for name in names if name.endswith("profile.txt"))
        profile = np.loadtxt(source.open(profile_name))
        columns = {
            "cooler_condition": profile[:, 0],
            "valve_condition": profile[:, 1],
            "pump_leakage": profile[:, 2],
            "accumulator_bar": profile[:, 3],
            "unstable": profile[:, 4],
        }
        for sensor in sensors:
            name = next(name for name in names if name.endswith(sensor + ".txt"))
            array = np.loadtxt(source.open(name))
            if array.shape[0] != len(profile):
                raise ValueError("sensor and profile cycle counts disagree")
            columns[sensor + "_mean"] = array.mean(axis=1)
    return pd.DataFrame(columns)


def uci_metropt(archive, *, stride=60):
    """Deterministic global row stride, preserving source timestamps and original units."""
    import pandas as pd

    if type(stride) is not int or stride < 1:
        raise ValueError("positive integer row stride required")
    frames, offset = [], 0
    with zipfile.ZipFile(archive) as source:
        name = next(name for name in source.namelist() if name.endswith(".csv"))
        with source.open(name) as stream:
            for chunk in pd.read_csv(stream, chunksize=100_000):
                select = (np.arange(len(chunk)) + offset) % stride == 0
                frames.append(chunk.loc[select])
                offset += len(chunk)
    result = pd.concat(frames, ignore_index=True)
    result.attrs["source_rows"] = offset
    result.attrs["stride"] = stride
    return result


def uci_gas_turbine(archive):
    import pandas as pd

    frames = []
    with zipfile.ZipFile(archive) as source:
        for name in sorted(source.namelist()):
            if name.endswith(".csv"):
                frame = pd.read_csv(source.open(name))
                frame["source_file"] = Path(name).name
                frames.append(frame)
    if not frames:
        raise ValueError("no gas-turbine CSV members")
    return pd.concat(frames, ignore_index=True)


def uci_water(archive):
    import pandas as pd

    with zipfile.ZipFile(archive) as source:
        name = next(name for name in source.namelist() if name.endswith("water-treatment.data"))
        return pd.read_csv(source.open(name), header=None, na_values="?")


def uci_secom(archive):
    import pandas as pd

    with zipfile.ZipFile(archive) as source:
        name = next(name for name in source.namelist() if name.endswith("secom.data"))
        labels = next(name for name in source.namelist() if name.endswith("secom_labels.data"))
        frame = pd.read_csv(source.open(name), sep=r"\s+", header=None, na_values="NaN")
        target = pd.read_csv(source.open(labels), sep=r"\s+", header=None)
    if len(frame) != len(target):
        raise ValueError("SECOM item and label counts disagree")
    return frame, target.iloc[:, 0].to_numpy()


def tep_rdata(path):
    """Optional RData reader; use selected files within available memory.

    rdata is an optional MIT reader, installed separately from the core. The
    returned data remains a simulated process dataset without human outcomes.
    """
    import rdata

    objects = rdata.read_rda(str(path))
    if len(objects) != 1:
        raise ValueError("expected one TEP data frame per source file")
    return next(iter(objects.values()))
