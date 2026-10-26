"""Rubric text extraction and deterministic local parsing.

The local parser deliberately preserves the levels found in the source.  It does
not project every rubric onto a university grade-band template.
"""

from __future__ import annotations

import html
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from app.domain.levels import has_descriptors, with_ranges

_POINTS = r"(?:pts?|points?|marks?)"
_CRITERION = re.compile(
    rf"^(?:criterion\s*)?(?:\d+[.)]\s*)?(.+?)\s*(?:[—–\-:(]\s*)"
    rf"(?:max(?:imum)?\s*)?(\d+(?:\.\d+)?)\s*(?:%|{_POINTS})?\)?\s*$",
    re.IGNORECASE,
)
_CRITERION_HEADER = re.compile(r"^criterion\s*:\s*(.+?)\s*$", re.IGNORECASE)
_SUBCRITERION_HEADER = re.compile(r"^subcriterion\s*:\s*(.+?)\s*$", re.IGNORECASE)
_MAX_LINE = re.compile(rf"^max(?:imum)?\s*:\s*(\d+(?:\.\d+)?)\s*(?:{_POINTS})?\s*$", re.IGNORECASE)
_LEVEL_WITH_LABEL = re.compile(
    rf"^(.+?)\s*(?:\((\d+(?:\.\d+)?)\)|[—–\-:]\s*(\d+(?:\.\d+)?)\s*{_POINTS}?)"
    r"\s*[:—–\-]\s*(.*)$",
    re.IGNORECASE,
)
_POINT_LEVEL = re.compile(
    rf"^(\d+(?:\.\d+)?)\s*(?:{_POINTS})?\s*[:—–\-]\s*(.*)$", re.IGNORECASE
)
_NAMED_LEVEL = re.compile(
    r"^(HD|DI|D|CR|C|PS|P|FL|F|N|Excellent|Good|Satisfactory|Developing|Poor)"
    r"\s*[:—–\-.]\s*(.*)$",
    re.IGNORECASE,
)

# These names describe column *roles*, not any particular grading scheme.  A
# performance-level column can still be called HD, Excellent, Meets, A, 3, or
# anything else supplied by the rubric.
_CRITERION_COLUMNS = {
    "criterion",
    "criteria",
    "criterion name",
    "dimension",
    "category",
    "component",
    "element",
    "aspect",
    "trait",
    "assessment area",
    "assessment item",
    "competency",
    "capability",
    "learning objective",
    "section",
    "outcome",
    "learning outcome",
    "评分项",
    "评分标准",
    "标准",
}
_WEIGHT_COLUMNS = {
    "pts",
    "pt",
    "points",
    "point",
    "marks",
    "mark",
    "weight",
    "maximum",
    "maximum points",
    "maximum score",
    "max",
    "max points",
    "max score",
    "total points",
    "total marks",
    "score available",
    "available points",
    "分值",
    "满分",
    "权重",
}
_LEVEL_COLUMNS = {
    "level",
    "rating",
    "grade",
    "band",
    "performance level",
    "performance band",
    "achievement level",
    "quality band",
    "等级",
    "级别",
}
_SCORE_COLUMNS = {
    "score",
    "points",
    "point",
    "marks",
    "mark",
    "value",
    "分数",
    "得分",
}
_DESCRIPTION_COLUMNS = {
    "description",
    "descriptor",
    "standard",
    "performance descriptor",
    "definition",
    "indicator",
    "indicators",
    "performance standard",
    "描述",
    "表现描述",
}


def _clean_html(value: Any) -> str:
    """Canvas text fields: HTML line breaks, tags and (often repeatedly) escaped entities."""

    text = str(value or "")
    for _ in range(32):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(?:p|div|li)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r", "").replace("\u00a0", " ")
    text = re.sub(r"[ \t]*•[ \t]*", "• ", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _number(value: str) -> float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _level(
    label: str,
    points: float | None,
    description: str,
    position: int,
    *,
    source_label: str | None = None,
    source_description: str | None = None,
) -> dict[str, Any]:
    return {
        "id": _slug(label, f"level-{position + 1}"),
        "label": label.strip(),
        "points": points,
        "min_score": points,
        "max_score": points,
        "min_inclusive": True,
        "max_inclusive": True,
        "description": description.strip(),
        "prov": {
            "label": "extracted",
            "points": "extracted" if points is not None else "missing",
            "description": "extracted" if description.strip() else "missing",
        },
        "source_text": {
            "points": source_label if source_label is not None else label.strip(),
            "description": (
                source_description if source_description is not None else description.strip()
            ),
        },
    }


# How much each parser finding matters:
#   error   — the rubric cannot be used until it is fixed (no name, no maximum, a level without points)
#   warning — probably a mistake worth checking (a total that disagrees, some levels described, others not)
#   info    — valid but worth knowing (levels that have labels and points only)
_SEVERITY = {
    "criterion_missing_name": "error",
    "criterion_missing_weight": "error",
    "criterion_needs_levels": "error",
    "level_missing_points": "error",
    "level_missing_label": "error",
    "level_points_above_maximum": "error",
    "total_mismatch": "warning",
    "invalid_total": "warning",
    "level_missing_descriptor": "warning",
    "levels_without_descriptors": "info",
}


def _warning(code: str, message: str, **location: int) -> dict[str, Any]:
    return {"code": code, "severity": _SEVERITY.get(code, "warning"), **location, "message": message}


def _criterion(
    name: str,
    weight: float | None,
    levels: list[dict[str, Any]] | None = None,
    *,
    description: str = "",
    source_name: str | None = None,
    source_weight: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name.strip(),
        "weight": weight,
        "description": description.strip(),
        "stated_percent": None,
        "scoring_mode": "fixed_levels",
        "score_mapping": "explicit",
        "granularity": None,
        "levels": levels or [],
        "prov": {
            "name": "extracted" if name.strip() else "missing",
            "weight": "extracted" if weight is not None and weight > 0 else "missing",
            "description": "extracted" if description.strip() else "missing",
        },
        "source_text": {
            "name": source_name if source_name is not None else name.strip(),
            "weight": source_weight if source_weight is not None else "",
        },
    }


def _table_cells(line: str) -> list[str]:
    if "|" in line:
        return [part.strip() for part in line.strip().strip("|").split("|")]
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    return []


def _score_from_label(label: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", label)
    return _number(match.group()) if match else None


def _normalise_header(value: str) -> str:
    value = re.sub(r"[*_`#]", "", value).strip().lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", value).strip()


def _header_index(cells: list[str], roles: set[str]) -> int | None:
    for index, cell in enumerate(cells):
        if _normalise_header(cell) in roles:
            return index
    return None


def _is_table_separator(line: str) -> bool:
    return bool(re.fullmatch(r"[|:\-\s]+", line))


def _inferred_criterion_column(
    lines: list[str], header_index: int, header: list[str]
) -> int | None:
    explicit = _header_index(header, _CRITERION_COLUMNS)
    if explicit is not None:
        return explicit
    # A Markdown separator is reliable evidence that this is a header rather
    # than a data row.  For an unknown vocabulary, the first textual column is
    # the rubric dimension and the remaining columns are inferred by shape.
    if header_index + 1 < len(lines) and _is_table_separator(lines[header_index + 1]):
        return next((index for index, cell in enumerate(header) if cell.strip()), None)
    return None


def _pure_score(value: str) -> float | None:
    cleaned = re.sub(r"[*_`]", "", value).strip()
    matched = re.fullmatch(rf"(\d+(?:\.\d+)?)\s*(?:%|{_POINTS})?", cleaned, re.I)
    return _number(matched.group(1)) if matched else None


def _inferred_weight_column(
    lines: list[str], header_index: int, header: list[str], criterion_column: int
) -> int | None:
    explicit = _header_index(header, _WEIGHT_COLUMNS)
    if explicit is not None:
        return explicit
    samples: list[list[str]] = []
    for line in lines[header_index + 1 :]:
        if _is_table_separator(line):
            continue
        cells = _table_cells(line)
        if not cells:
            break
        cells += [""] * (len(header) - len(cells))
        samples.append(cells)
        if len(samples) == 4:
            break
    numeric_columns = [
        column
        for column in range(len(header))
        if column != criterion_column
        and samples
        and all(cells[column].strip() and _pure_score(cells[column]) is not None for cells in samples)
    ]
    # A single numeric-only column among descriptor columns is the maximum or
    # weight column.  Multiple numeric columns are performance levels instead.
    return numeric_columns[0] if len(numeric_columns) == 1 else None


def _logical_lines(text: str) -> list[str]:
    """Join wrapped pipe-table rows without changing ordinary rubric lines."""

    raw_lines = [raw.strip() for raw in text.splitlines()]
    joined: list[str] = []
    pending = ""
    for raw in raw_lines:
        if not raw:
            continue
        if pending:
            pending = f"{pending} {raw}"
            if raw.endswith("|"):
                joined.append(pending)
                pending = ""
            continue
        if raw.startswith("|") and not raw.endswith("|"):
            pending = raw
            continue
        joined.append(raw)
    if pending:
        joined.append(pending)
    logical: list[str] = []
    for raw in joined:
        if "\t" in raw:
            normalised = "\t".join(
                re.sub(r"\s+", " ", part).strip() for part in raw.split("\t")
            )
        else:
            normalised = re.sub(r"\s+", " ", raw).strip()
        logical.append(re.sub(r"^#{1,6}\s*", "", normalised))
    return logical


def _cell_score(value: str) -> tuple[float | None, str]:
    """Read a score prefix/suffix while preserving the supplied descriptor."""

    cleaned = value.strip()
    leading = re.match(
        rf"^(?:\*\*|__)?\s*[([]?(\d+(?:\.\d+)?)\s*(?:%|{_POINTS})?[)\]]?"
        r"\s*(?:\*\*|__)?\s*(?:[:—–\-]\s*)?(.*)$",
        cleaned,
        re.IGNORECASE,
    )
    if leading:
        return _number(leading.group(1)), leading.group(2).strip()
    trailing = re.match(
        rf"^(.*?)\s*\((\d+(?:\.\d+)?)\s*(?:%|{_POINTS})?\)\s*$",
        cleaned,
        re.IGNORECASE,
    )
    if trailing:
        return _number(trailing.group(2)), trailing.group(1).strip()
    return None, cleaned


def _parse_table(lines: list[str]) -> tuple[list[dict[str, Any]], set[int]]:
    criteria: list[dict[str, Any]] = []
    consumed: set[int] = set()
    for index, line in enumerate(lines):
        header = _table_cells(line)
        if len(header) < 3:
            continue
        if _header_index(header, _CRITERION_COLUMNS) is None:
            continue
        scores = [_score_from_label(cell) for cell in header[1:]]
        if sum(score is not None for score in scores) < 2:
            continue
        consumed.add(index)
        if index + 1 < len(lines) and re.fullmatch(r"[|:\-\s]+", lines[index + 1]):
            consumed.add(index + 1)
        row_index = index + 1
        while row_index < len(lines):
            cells = _table_cells(lines[row_index])
            if len(cells) < len(header):
                break
            if re.fullmatch(r"[|:\-\s]+", lines[row_index]):
                consumed.add(row_index)
                row_index += 1
                continue
            name = cells[0].strip()
            if not name:
                break
            explicit_max = re.search(rf"(\d+(?:\.\d+)?)\s*(?:%|{_POINTS})", name, re.I)
            max_points = _number(explicit_max.group(1)) if explicit_max else max(
                score for score in scores if score is not None
            )
            clean_name = re.sub(rf"\s*[([]?\d+(?:\.\d+)?\s*(?:%|{_POINTS})[)\]]?\s*$", "", name, flags=re.I)
            levels = []
            for pos, (label, score, description) in enumerate(zip(header[1:], scores, cells[1:])):
                if score is not None:
                    levels.append(_level(label, score, description, pos))
            if len(levels) >= 2:
                criteria.append(
                    _criterion(
                        clean_name or name,
                        max_points,
                        levels,
                        source_name=name,
                        source_weight=explicit_max.group(0) if explicit_max else str(max_points),
                    )
                )
                consumed.add(row_index)
            row_index += 1
        if criteria:
            break
    return criteria, consumed


def _parse_long_form_table(
    lines: list[str], header_index: int, header: list[str]
) -> tuple[list[dict[str, Any]], set[int]]:
    """Parse one-level-per-row tables using semantically inferred columns."""

    criterion_column = _inferred_criterion_column(lines, header_index, header)
    level_column = _header_index(header, _LEVEL_COLUMNS)
    score_column = _header_index(header, _SCORE_COLUMNS)
    description_column = _header_index(header, _DESCRIPTION_COLUMNS)
    weight_column = _inferred_weight_column(lines, header_index, header, criterion_column or 0)
    if criterion_column is None or level_column is None:
        return [], set()
    if score_column is None and description_column is None:
        return [], set()

    consumed = {header_index}
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    current_name = ""
    row_index = header_index + 1
    while row_index < len(lines):
        if _is_table_separator(lines[row_index]):
            consumed.add(row_index)
            row_index += 1
            continue
        cells = _table_cells(lines[row_index])
        if not cells:
            break
        cells += [""] * (len(header) - len(cells))
        supplied_name = cells[criterion_column].strip()
        if supplied_name:
            current_name = supplied_name
        if not current_name:
            row_index += 1
            continue
        label = cells[level_column].strip()
        if not label:
            break

        key = current_name.casefold()
        if key not in grouped:
            explicit_weight = None
            if weight_column is not None and weight_column != score_column:
                explicit_weight = _score_from_label(cells[weight_column])
            grouped[key] = _criterion(
                current_name,
                explicit_weight,
                source_name=current_name,
                source_weight=cells[weight_column] if weight_column is not None else "",
            )
            order.append(key)
        criterion = grouped[key]
        points = _score_from_label(cells[score_column]) if score_column is not None else None
        description = cells[description_column].strip() if description_column is not None else ""
        if description_column is None and score_column is not None:
            _, description = _cell_score(cells[score_column])
        criterion["levels"].append(
            _level(
                label,
                points,
                description,
                len(criterion["levels"]),
                source_label=cells[score_column] if score_column is not None else label,
                source_description=description,
            )
        )
        if points is not None and (
            criterion["weight"] is None or criterion["prov"]["weight"] == "inferred"
        ):
            criterion["weight"] = max(float(criterion["weight"] or 0), float(points))
            criterion["prov"]["weight"] = "inferred"
            criterion["source_text"]["weight"] = "highest level score"
        consumed.add(row_index)
        row_index += 1
    return [grouped[key] for key in order], consumed


def _parse_scoring_table(lines: list[str]) -> tuple[list[dict[str, Any]], set[int]]:
    """Infer wide or long rubric-table roles without assuming level names."""

    for header_index, line in enumerate(lines):
        header = _table_cells(line)
        if len(header) < 3:
            continue
        criterion_column = _inferred_criterion_column(lines, header_index, header)
        if criterion_column is None:
            continue

        long_criteria, long_consumed = _parse_long_form_table(lines, header_index, header)
        if long_criteria:
            return long_criteria, long_consumed

        weight_column = _inferred_weight_column(
            lines, header_index, header, criterion_column
        )
        level_columns = [
            index
            for index in range(len(header))
            if index not in {criterion_column, weight_column}
        ]
        if len(level_columns) < 2:
            continue

        consumed = {header_index}
        criteria: list[dict[str, Any]] = []
        row_index = header_index + 1
        while row_index < len(lines):
            if _is_table_separator(lines[row_index]):
                consumed.add(row_index)
                row_index += 1
                continue
            cells = _table_cells(lines[row_index])
            if not cells:
                break
            cells += [""] * (len(header) - len(cells))
            name = cells[criterion_column].strip()
            if not name:
                break

            explicit_weight = (
                _score_from_label(cells[weight_column]) if weight_column is not None else None
            )
            levels: list[dict[str, Any]] = []
            for position, column in enumerate(level_columns):
                label = header[column].strip()
                cell_points, description = _cell_score(cells[column])
                points = cell_points
                if points is None:
                    points = _score_from_label(label)
                if label or description:
                    levels.append(
                        _level(
                            label or f"Level {position + 1}",
                            points,
                            description,
                            position,
                            source_label=header[column],
                            source_description=cells[column],
                        )
                    )
            if len(levels) < 2:
                break
            inferred_weight = max(
                (float(level["points"]) for level in levels if level["points"] is not None),
                default=0,
            )
            criterion = _criterion(
                name,
                explicit_weight if explicit_weight is not None else (inferred_weight or None),
                levels,
                source_name=name,
                source_weight=cells[weight_column] if weight_column is not None else "",
            )
            if explicit_weight is None and inferred_weight:
                criterion["prov"]["weight"] = "inferred"
                criterion["source_text"]["weight"] = "highest level score"
            criteria.append(criterion)
            consumed.add(row_index)
            row_index += 1
        if criteria:
            return criteria, consumed
    return [], set()


def _parse_hierarchical(lines: list[str]) -> list[dict[str, Any]]:
    """Flatten explicitly scored subcriteria while retaining their parent label."""

    if not any(_SUBCRITERION_HEADER.match(line) for line in lines):
        return []
    criteria: list[dict[str, Any]] = []
    parent = ""
    current: dict[str, Any] | None = None
    for line in lines:
        header = _CRITERION_HEADER.match(line)
        if header:
            parent = header.group(1).strip(" —–-:")
            current = None
            continue
        subcriterion = _SUBCRITERION_HEADER.match(line)
        if subcriterion:
            child = subcriterion.group(1).strip(" —–-:")
            current = _criterion(
                f"{parent} — {child}" if parent else child,
                None,
                source_name=child,
            )
            criteria.append(current)
            continue
        maximum = _MAX_LINE.match(line)
        if maximum and current is not None:
            current["weight"] = _number(maximum.group(1))
            current["prov"]["weight"] = "extracted"
            current["source_text"]["weight"] = line
            continue
        if current is None or re.match(r"^(?:id|granularity|source)\s*:", line, re.I):
            continue
        matched = _POINT_LEVEL.match(line)
        if matched:
            points = _number(matched.group(1))
            current["levels"].append(
                _level(f"{points:g} points", points, matched.group(2), len(current["levels"]))
            )
    return criteria


def _parse_json_rubric(text: str, source_name: str | None) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Rubric JSON is invalid at line {exc.lineno}, column {exc.colno}") from exc
    canvas_meta: dict[str, Any] = {}
    if isinstance(raw, list):
        raw = {"criteria": raw}
    elif isinstance(raw, dict) and isinstance(raw.get("rubric"), dict):
        raw = raw["rubric"]
    elif isinstance(raw, dict) and isinstance(raw.get("rubric"), list):
        # Canvas course export: {"course", "assignment": {"rubric_settings"}, "rubric": [...]}
        assignment = raw.get("assignment") if isinstance(raw.get("assignment"), dict) else {}
        settings = assignment.get("rubric_settings") if isinstance(assignment.get("rubric_settings"), dict) else {}
        course = raw.get("course") if isinstance(raw.get("course"), dict) else {}
        canvas_meta = {
            "title": settings.get("title") or assignment.get("name"),
            "total": settings.get("points_possible", assignment.get("points_possible")),
            "source": " · ".join(
                part
                for part in (
                    "Canvas",
                    _clean_html(course.get("name") or course.get("course_code")),
                    _clean_html(assignment.get("name")),
                )
                if part
            ),
        }
        raw = {"criteria": raw["rubric"]}
    if not isinstance(raw, dict):
        raise ValueError("Rubric JSON must be an object")
    source_criteria = raw.get("criteria")
    if not isinstance(source_criteria, list) or not source_criteria:
        raise ValueError("Rubric JSON has no criteria array")
    canvas = any(isinstance(item, dict) and "ratings" in item for item in source_criteria)
    criteria: list[dict[str, Any]] = []
    for item in source_criteria:
        if not isinstance(item, dict):
            continue
        if canvas:
            name = _clean_html(item.get("description") or item.get("name"))
            description = _clean_html(item.get("long_description"))
            weight_value = item.get("points")
            levels_source = item.get("ratings") or []
        else:
            name = str(item.get("name") or item.get("description") or "").strip()
            description = str(item.get("description") or "").strip()
            weight_value = item.get("weight", item.get("points"))
            levels_source = item.get("levels", item.get("ratings", [])) or []
        try:
            weight = _number(str(weight_value)) if weight_value not in (None, "") else None
        except (TypeError, ValueError):
            weight = None
        levels: list[dict[str, Any]] = []
        for level_position, level in enumerate(levels_source):
            if not isinstance(level, dict):
                continue
            if canvas:
                label = _clean_html(level.get("description") or level.get("label"))
                level_description = _clean_html(level.get("long_description"))
            else:
                label = str(level.get("label") or level.get("description") or "").strip()
                level_description = str(level.get("description") or "").strip()
            points_value = level.get("points", level.get("max_score"))
            try:
                points = (
                    _number(str(points_value)) if points_value not in (None, "") else None
                )
            except (TypeError, ValueError):
                points = None
            parsed_level = _level(
                label,
                points,
                level_description,
                level_position,
                source_label=json.dumps(
                    {"label": label, "points": points_value}, ensure_ascii=False
                ),
                source_description=level_description,
            )
            if not canvas:
                parsed_level["min_score"] = level.get("min_score", points)
                parsed_level["max_score"] = level.get("max_score", points)
                parsed_level["min_inclusive"] = bool(level.get("min_inclusive", True))
                parsed_level["max_inclusive"] = bool(level.get("max_inclusive", True))
            levels.append(parsed_level)
        criterion = _criterion(
            name,
            weight,
            levels,
            description=description,
            source_name=name,
            source_weight=str(weight_value or ""),
        )
        if canvas:
            # Canvas ratings are bands: 5 / 3.99 / 3 / 1.99 … — each covers the scores up to
            # its points and above the next rating.
            criterion["levels"] = with_ranges(levels)
        criterion["stated_percent"] = item.get("stated_percent")
        criterion["scoring_mode"] = str(item.get("scoring_mode") or "fixed_levels")
        criterion["score_mapping"] = str(item.get("score_mapping") or ("range" if canvas else "explicit"))
        criterion["granularity"] = item.get("granularity")
        criteria.append(criterion)
    if not criteria:
        raise ValueError("Rubric JSON contains no usable criteria")
    title = _clean_html(
        canvas_meta.get("title")
        or raw.get("title")
        or raw.get("name")
        or (Path(source_name).stem if source_name else "Imported rubric")
    )
    stated_total = canvas_meta.get("total", raw.get("total_score", raw.get("points_possible")))
    return {
        "title": title or "Imported rubric",
        "source": canvas_meta.get("source") or raw.get("source"),
        "total_score": stated_total,
        "total_score_source": "stated" if stated_total is not None else "computed",
        "criteria": criteria,
        "warnings": [],
        "_parser": "canvas_json" if canvas else "native_json",
    }


def _finalise_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    warnings = list(parsed.get("warnings") or [])
    criteria = list(parsed.get("criteria") or [])
    computed_total = sum(float(item.get("weight") or 0) for item in criteria)
    stated_total = parsed.get("total_score")
    if stated_total is None:
        parsed["total_score"] = computed_total
        parsed["total_score_source"] = "computed"
    else:
        try:
            stated_number = float(stated_total)
        except (TypeError, ValueError):
            stated_number = computed_total
            parsed["total_score"] = computed_total
            parsed["total_score_source"] = "computed"
            warnings.append(_warning("invalid_total", "The stated total is not numeric."))
        if abs(stated_number - computed_total) > 0.01:
            warnings.append(
                _warning(
                    "total_mismatch",
                    f"Rubric says {stated_number:g} marks; criteria add up to {computed_total:g}.",
                )
            )
    for criterion_index, criterion in enumerate(criteria):
        if not str(criterion.get("name") or "").strip():
            warnings.append(
                _warning(
                    "criterion_missing_name",
                    "A criterion has no name.",
                    criterion_index=criterion_index,
                )
            )
        if not float(criterion.get("weight") or 0) > 0:
            warnings.append(
                _warning(
                    "criterion_missing_weight",
                    f"Criterion '{criterion.get('name') or criterion_index + 1}' has no maximum marks.",
                    criterion_index=criterion_index,
                )
            )
        levels = list(criterion.get("levels") or [])
        if len(levels) < 2:
            warnings.append(
                _warning(
                    "criterion_needs_levels",
                    f"Criterion '{criterion.get('name') or criterion_index + 1}' needs at least two scoring levels.",
                    criterion_index=criterion_index,
                )
            )
        described = has_descriptors(levels)
        name = criterion.get("name") or criterion_index + 1
        if levels and not described:
            warnings.append(
                _warning(
                    "levels_without_descriptors",
                    f"'{name}' has level labels and points only; the AI judges against the criterion"
                    + (" description." if str(criterion.get("description") or "").strip() else " name."),
                    criterion_index=criterion_index,
                )
            )
        maximum = float(criterion.get("weight") or 0)
        for level_index, level in enumerate(levels):
            if not str(level.get("label") or "").strip():
                warnings.append(
                    _warning(
                        "level_missing_label",
                        f"Level {level_index + 1} of '{name}' has no label.",
                        criterion_index=criterion_index,
                        level_index=level_index,
                    )
                )
            if maximum > 0 and level.get("points") is not None and float(level["points"]) > maximum + 1e-9:
                warnings.append(
                    _warning(
                        "level_points_above_maximum",
                        f"Level '{level.get('label')}' of '{name}' is worth more than the criterion maximum ({maximum:g}).",
                        criterion_index=criterion_index,
                        level_index=level_index,
                    )
                )
            if level.get("points") is None:
                warnings.append(
                    _warning(
                        "level_missing_points",
                        f"Level '{level.get('label') or level_index + 1}' has no score.",
                        criterion_index=criterion_index,
                        level_index=level_index,
                    )
                )
            if described and not str(level.get("description") or "").strip():
                warnings.append(
                    _warning(
                        "level_missing_descriptor",
                        f"Level '{level.get('label') or level_index + 1}' has no description.",
                        criterion_index=criterion_index,
                        level_index=level_index,
                    )
                )
    parsed["criteria"] = criteria
    parsed["warnings"] = warnings
    return parsed


def parse_rubric_text(text: str, source_name: str | None = None) -> dict[str, Any]:
    """Parse table or block-form rubrics while retaining arbitrary level scales."""

    if (source_name or "").lower().endswith(".json") or text.lstrip().startswith(("{", "[")):
        parsed = _parse_json_rubric(text, source_name)
        # Run JSON through the same warning/assessment normaliser as text by
        # serialising its already parsed structure below.
        return _finalise_parsed(parsed)

    lines = _logical_lines(text)
    if not lines:
        raise ValueError("Rubric text is empty")

    criteria = _parse_hierarchical(lines)
    parser_name = "hierarchical" if criteria else ""
    consumed: set[int] = set()
    if not criteria:
        criteria, consumed = _parse_scoring_table(lines)
        if criteria:
            parser_name = "scoring_table"
    if not criteria:
        criteria, consumed = _parse_table(lines)
        if criteria:
            parser_name = "numeric_header_table"
    warnings: list[dict[str, Any]] = []
    if not criteria:
        current: dict[str, Any] | None = None
        for line in lines:
            header = _CRITERION_HEADER.match(line)
            if header:
                current = _criterion(
                    header.group(1).strip(" —–-:"), None, source_name=line
                )
                criteria.append(current)
                continue
            maximum = _MAX_LINE.match(line)
            if maximum and current is not None:
                current["weight"] = _number(maximum.group(1))
                current["prov"]["weight"] = "extracted"
                current["source_text"]["weight"] = line
                continue
            if re.match(r"^(?:id|granularity|source)\s*:", line, re.IGNORECASE):
                continue
            criterion = _CRITERION.match(line)
            if criterion and not re.search(r"\brubric\b", criterion.group(1), re.I):
                current = _criterion(
                    criterion.group(1).strip(" —–-:"),
                    _number(criterion.group(2)),
                    source_name=line,
                    source_weight=criterion.group(2),
                )
                criteria.append(current)
                continue
            if current is None:
                continue
            matched = _LEVEL_WITH_LABEL.match(line)
            if matched:
                points = _number(matched.group(2) or matched.group(3))
                current["levels"].append(
                    _level(matched.group(1), points, matched.group(4), len(current["levels"]))
                )
                continue
            matched_points = _POINT_LEVEL.match(line)
            if matched_points:
                points = _number(matched_points.group(1))
                current["levels"].append(
                    _level(f"{points:g} points", points, matched_points.group(2), len(current["levels"]))
                )
                continue
            named = _NAMED_LEVEL.match(line)
            if named:
                current["levels"].append(
                    _level(
                        named.group(1).upper(),
                        None,
                        named.group(2),
                        len(current["levels"]),
                        source_label=line,
                        source_description=named.group(2),
                    )
                )
        parser_name = "level_text"

    if not criteria:
        raise ValueError(
            "No rubric criteria were found. Include criterion headings, scoring levels, or ask AI to draft a rubric."
        )
    metadata_names = {"id", "max", "maximum", "granularity", "source"}
    names = [str(criterion.get("name") or "").strip().lower() for criterion in criteria]
    if any(name in metadata_names for name in names) or len(set(names)) != len(names):
        raise ValueError("Rubric metadata was misidentified as scoring criteria")
    if any(len(criterion.get("levels", [])) > 20 for criterion in criteria):
        raise ValueError("An implausible number of scoring levels was detected")

    title = next((line for line in lines if re.search(r"\brubric\b", line, re.I)), "")
    if not title:
        first_table_row = min(consumed) if consumed else len(lines)
        title = next(
            (
                line
                for index, line in enumerate(lines)
                if index < first_table_row
                and index not in consumed
                and not _table_cells(line)
                and not _POINT_LEVEL.match(line)
                and not _NAMED_LEVEL.match(line)
            ),
            Path(source_name).stem if source_name else "Imported rubric",
        )
    title = re.sub(r"\s*[—–-]\s*(?:marking\s+)?rubric.*$", "", title, flags=re.I).strip()
    declared_total = re.search(r"\((\d+(?:\.\d+)?)\s*(?:marks?|points?|pts?)\)", title, re.I)
    parsed_total = sum(float(criterion.get("weight") or 0) for criterion in criteria)
    if declared_total and abs(float(declared_total.group(1)) - parsed_total) > 0.01:
        warnings.append(
            _warning(
                "total_mismatch",
                f"Rubric says {float(declared_total.group(1)):g} marks; criteria add up to "
                f"{parsed_total:g}.",
            )
        )
    for criterion_index, criterion in enumerate(criteria):
        if not str(criterion.get("name") or "").strip():
            warnings.append(
                _warning(
                    "criterion_missing_name",
                    "A criterion has no name.",
                    criterion_index=criterion_index,
                )
            )
        if not float(criterion.get("weight") or 0) > 0:
            warnings.append(
                _warning(
                    "criterion_missing_weight",
                    f"Criterion '{criterion.get('name') or criterion_index + 1}' has no maximum marks.",
                    criterion_index=criterion_index,
                )
            )
        levels = criterion.get("levels") or []
        if len(levels) < 2:
            warnings.append(
                _warning(
                    "criterion_needs_levels",
                    f"Criterion '{criterion.get('name') or criterion_index + 1}' needs at least two scoring levels.",
                    criterion_index=criterion_index,
                )
            )
        for level_index, level in enumerate(levels):
            if level.get("points") is None:
                warnings.append(
                    _warning(
                        "level_missing_points",
                        f"Level '{level.get('label') or level_index + 1}' has no score.",
                        criterion_index=criterion_index,
                        level_index=level_index,
                    )
                )
            if not str(level.get("description") or "").strip():
                warnings.append(
                    _warning(
                        "level_missing_descriptor",
                        f"Level '{level.get('label') or level_index + 1}' has no description.",
                        criterion_index=criterion_index,
                        level_index=level_index,
                    )
                )
    stated_total = float(declared_total.group(1)) if declared_total else None
    result = {
        "title": title or "Imported rubric",
        "total_score": stated_total if stated_total is not None else parsed_total,
        "total_score_source": "stated" if stated_total is not None else "computed",
        "criteria": criteria,
        "warnings": warnings,
        "_parser": parser_name or "table",
    }
    return result


def _spreadsheet_as_table(text: str, delimiter: str) -> str:
    """Turn CSV/TSV rows (e.g. exported from Excel) into the pipe table the parser reads."""

    import csv
    from io import StringIO

    rows = [
        [cell.strip().replace("|", "/") for cell in row]
        for row in csv.reader(StringIO(text), delimiter=delimiter)
        if any(cell.strip() for cell in row)
    ]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(lines)


def extract_rubric_file(filename: str, content: bytes) -> str:
    """Extract text from the lightweight local-MVP rubric formats."""

    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".tsv", ".json"}:
        text = None
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = content.decode("utf-8", errors="replace")
        if suffix in {".csv", ".tsv"}:
            return _spreadsheet_as_table(text, "\t" if suffix == ".tsv" else ",")
        return text
    if suffix == ".docx":
        from docx import Document

        document = Document(BytesIO(content))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            paragraphs.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        return "\n".join(paragraphs)
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    raise ValueError("Rubric file must be PDF, DOCX, TXT, MD, CSV, TSV, or JSON")
