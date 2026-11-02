"""De-identification of student submissions before they enter the marker.

Imported datasets (and, optionally, uploads) can contain student numbers, names, e-mail
addresses and phone numbers. ``Anonymiser`` replaces every match with a stable keyed
pseudonym (HMAC-SHA256 with a local secret salt), so the same student number maps to the
same token across a batch but cannot be reversed without the salt. Over-redaction is
preferred to leaking an identifier: any standalone 8–10 digit number is treated as a
possible student number.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(
    r"(?<![\w])(?:(?:\+?61[\s-]?|0)4\d{2}[\s-]?\d{3}[\s-]?\d{3}"  # mobiles
    r"|(?:\+?61[\s-]?|\(?0)[2378]\)?[\s-]?\d{4}[\s-]?\d{4})(?!\d)"  # landlines, "61-7-54362000"
)
# "open('76543210/data.csv')": a student number used as a folder name
_PATH_NUMBER = re.compile(r"(?<=['\"])\d{8,10}(?=/)")
# "Student ID: 12345678", "SID 123", "student no. 1234567", "ID:12345678"
_LABELLED_ID = re.compile(
    r"(?i)\b(student\s*(?:id|number|no\.?|#)|sid|id\s*(?:number|no\.?)?)(\s*[:#=\-]?\s*)(\d{4,12}(?:[ \t]\d{3,6})*)\b"
)
_LONG_NUMBER = re.compile(r"(?<!\d)(?<!\d[.,/-])\d{8,10}(?![\d/]|-\d|[.,]\d|\s*%)")
# residual check: any 8-10 digit run except inside DOIs/URLs ("/") and decimals
_ANY_LONG_NUMBER = re.compile(r"(?<!\d)(?<![\w.]/)(?<!\d\.)\d{8,10}(?!\d|\.\d|e-)")
# "12345678-Smith-A2.csv": the surname after a student number in a file name
_FILE_ROSTER = re.compile(r"(?<!\d)\d{8,10}[-_]([A-Z][a-z]{2,})\b")
_FILENAME_SID = re.compile(r"(?i)SID[-_ ]?\d+")
# "Name: Jane Doe", "Author: Virtual Student", "Submitted by Alex Chen", "Prepared by: ..."
_LABELLED_NAME = re.compile(
    r"(?m)\b((?i:student\s*name|full\s+name|student(?=\s*:)|by(?=[ \t]+[A-Z][a-z]+[ \t]+[A-Z][a-z]+(?:[ \t]*[,(|\n]|[ \t]+-|$))|(?:team|group)[ \t]+[\w-]+(?=:)|given\s+name|first\s+name|last\s+name|surname|name|authors?|submitted\s+by|prepared\s+by|written\s+by|(?:laboratory\s+|lab\s+|unit\s+)?tutor|lecturer|supervisor|(?:team|group)\s+members?|members?|candidate|contact))"
    r"([ \t]*[:\-][ \t]*(?:\n[ \t]*)?|[ \t]+)"
    r"[\"']?((?:[A-Z][A-Za-z'\-]+|[A-Z]\.)(?:(?:[ \t]+|,[ \t]*|[ \t]+and[ \t]+)(?:[A-Z][A-Za-z'\-]+|[A-Z]\.)){0,11})\b[\"']?(?![ \t]*[:\-][ \t]*\S)"
)
# Words that follow "name:" in code or notebooks rather than a person's name.
# "Unit name: Data Analysis", "Project name: TagTag" name things, not people.
_THING_NAMES = {"unit", "course", "project", "file", "table", "column", "dataset", "company", "product",
                "app", "application", "business", "brand", "team", "group", "model", "variable", "user"}
# A roster line: "Mia Chen (530112874)", "Noah Williams 530502117". Names found next to a
# student number are then redacted everywhere they appear in the document.
_NAME_WORD = r"[A-Z][a-z]+(?:['\-][A-Z]?[a-z]+)?|[A-Z]'[A-Z][a-z]+|[A-Z]\."
_ROSTER = re.compile(rf"((?:{_NAME_WORD})(?:[ \t]+(?:{_NAME_WORD})){{1,3}})\s*[(\[]?[ \t]*\d{{8,10}}\b")
_HONORIFIC = re.compile(rf"\b(?:Dr|Prof|Professor|A/Prof|Mr|Mrs|Ms|Miss)\.?[ \t]+(?:{_NAME_WORD})(?:[ \t]+(?:{_NAME_WORD})){{0,2}}")
_GROUP = re.compile(r"(?i)\b(group|team)(\s*(?:no\.?|number|#)?\s*)(\d{1,3})\b")
# Capitalised words that appear in name slots of templates ("Your Name Here", "Alex Smith Student")
_GENERIC_WORDS = {"Prof", "Professor", "Miss", "Student", "Students", "Name", "Your", "Here", "Role", "Number",
                  "Virtual", "University", "Group", "Team", "Member", "Members", "Leader", "The", "And", "Example",
                  "Unit", "Course", "Tutor", "Lecturer", "Lab", "Date", "ID", "Assignment", "Report", "Project",
                  "Submission", "Word", "Count", "Page", "Monash", "Sydney", "Australia", "Data", "Table", "Figure"}
# zID / s-number style university IDs: z1234567, s1234567
_UNI_ID = re.compile(r"(?<![\w])[zZsS]\d{7}(?!\w)")
_PERSON = rf"((?:{_NAME_WORD})(?:[ \t]+(?:{_NAME_WORD})){{1,2}})"
_BEFORE_ID = re.compile(_PERSON + r"[ \t]*(?:[-–—,(|:][ \t]*)?(?:(?i:student\s*id|sid|id)\b[ \t:#]*)?\(?\[ID-[0-9a-f]{6}\]")
_AFTER_ID = re.compile(r"\[ID-[0-9a-f]{6}\]\)?[ \t]*[-–—,|:]?[ \t]*" + _PERSON + r"(?![ \t]*[a-z])")
_NOT_A_NAME = {"python", "python3", "ir", "r", "julia", "none", "null", "true", "false", "string"}


@dataclass
class AnonymisationReport:
    emails: int = 0
    phones: int = 0
    student_ids: int = 0
    long_numbers: int = 0
    names: int = 0
    groups: int = 0
    tokens: dict[str, str] = field(default_factory=dict, repr=False)

    def total(self) -> int:
        return self.emails + self.phones + self.student_ids + self.long_numbers + self.names + self.groups


def _line_before(match: re.Match[str]) -> list[str]:
    """Words before the match on the same line ("Unit name:" vs "Product Team\nName:")."""

    start = match.string.rfind("\n", 0, match.start()) + 1
    return match.string[start:match.start()].split()


class Anonymiser:
    def __init__(self, salt: bytes) -> None:
        if len(salt) < 16:
            raise ValueError("Use a random salt of at least 16 bytes")
        self._salt = salt

    def digest(self, kind: str, value: str) -> str:
        key = f"{kind}:{value.strip().lower()}".encode("utf-8")
        return hmac.new(self._salt, key, hashlib.sha256).hexdigest()

    def pseudonym(self, kind: str, value: str, length: int = 8) -> str:
        return self.digest(kind, value)[:length]

    def student_number(self, value: str) -> str:
        """An 8-digit pseudonymous student number (digits only, so SID parsing still works)."""

        return "9" + str(int(self.digest("sid", value), 16) % 10_000_000).zfill(7)

    def text(self, text: str, report: AnonymisationReport | None = None) -> str:
        report = report if report is not None else AnonymisationReport()

        def email(match: re.Match[str]) -> str:
            report.emails += 1
            return f"[email-{self.pseudonym('email', match.group(0), 6)}]"

        def phone(match: re.Match[str]) -> str:
            report.phones += 1
            return "[phone]"

        def labelled_id(match: re.Match[str]) -> str:
            report.student_ids += 1
            return f"{match.group(1)}{match.group(2)}[ID-{self.pseudonym('sid', match.group(3), 6)}]"

        def long_number(match: re.Match[str]) -> str:
            report.long_numbers += 1
            return f"[ID-{self.pseudonym('sid', match.group(0), 6)}]"

        def name(match: re.Match[str]) -> str:
            candidate = match.group(3)
            before = _line_before(match)
            if candidate.strip().lower() in _NOT_A_NAME or candidate.split()[0] in _GENERIC_WORDS or (
                match.group(1).lower() == "name" and before and before[-1].lower() in _THING_NAMES
            ):
                return match.group(0)
            report.names += 1
            return f"{match.group(1)}{match.group(2)}[STUDENT-{self.pseudonym('name', candidate, 6)}]"

        def redact_people(text: str, roster: set[str]) -> str:
            for person in sorted(roster, key=len, reverse=True):
                token = f"[STUDENT-{self.pseudonym('name', person, 6)}]"
                text, count = re.subn(rf"(?<![\w\[]){re.escape(person)}(?!\w)", token, text)
                report.names += count
                # the same person written differently ("Chen, M.", "Mia") keeps the full-name token
                for part in person.replace(".", " ").split():
                    if len(part) >= 3 and part not in _GENERIC_WORDS:
                        text, count = re.subn(rf"(?<![\w\[-]){re.escape(part)}(?![\w])", token, text)
                        report.names += count
            return text

        # 1. people named next to a student number, an honorific or a name label
        roster = {m.group(1).strip() for m in _ROSTER.finditer(text)}
        roster |= {m.group(0).strip() for m in _HONORIFIC.finditer(text)}
        roster |= {m.group(1) for m in _FILE_ROSTER.finditer(text)}
        for m in _LABELLED_NAME.finditer(text):
            if m.group(1).lower() == "name" and (
                (_line_before(m) or [""])[-1].lower() in _THING_NAMES
            ):
                continue
            for chunk in re.split(r",|[ \t]+and[ \t]+", m.group(3)):
                words = chunk.split()
                while words and words[-1] in _GENERIC_WORDS:
                    words.pop()
                person = " ".join(words)
                if (person and person.lower() not in _NOT_A_NAME and len(words) <= 4
                        and not any(w in _GENERIC_WORDS for w in words)):
                    roster.add(person)
        text = redact_people(text, roster)

        def group(match: re.Match[str]) -> str:
            report.groups += 1
            return f"{match.group(1)}{match.group(2)}G{self.pseudonym('group', match.group(3), 4)}"

        def uni_id(match: re.Match[str]) -> str:
            report.student_ids += 1
            return f"[ID-{self.pseudonym('sid', match.group(0), 6)}]"

        # 2. numbers, contact details and group numbers
        text = _GROUP.sub(group, text)
        text = _EMAIL.sub(email, text)
        text = _PHONE.sub(phone, text)
        text = _LABELLED_ID.sub(labelled_id, text)
        text = _LONG_NUMBER.sub(long_number, text)
        text = _PATH_NUMBER.sub(long_number, text)
        text = _UNI_ID.sub(uni_id, text)
        # 3. people written right before or after a (now redacted) ID: "Alex Chen - ID [ID-…]"
        roster = {m.group(1) for m in _BEFORE_ID.finditer(text)} | {m.group(1) for m in _AFTER_ID.finditer(text)}
        text = redact_people(text, {p for p in roster if not set(p.split()) & _GENERIC_WORDS})
        text = _LABELLED_NAME.sub(name, text)
        return text


_PLACEHOLDER = re.compile(r"\[(?:ID|STUDENT|email)-[0-9a-f]{6}\]|\[phone\]")


def residual_identifiers(text: str) -> list[str]:
    """Identifier-shaped strings still present after anonymisation (should be empty)."""

    text = _PLACEHOLDER.sub(" ", text)
    found = [m.group(0) for m in _EMAIL.finditer(text)]
    found += [m.group(0) for m in _PHONE.finditer(text)]
    found += [m.group(0) for m in _LABELLED_ID.finditer(text)]
    found += [m.group(0) for m in _ANY_LONG_NUMBER.finditer(text)]
    return found


def strip_filename_sid(name: str) -> str:
    return _FILENAME_SID.sub("SID", name)
