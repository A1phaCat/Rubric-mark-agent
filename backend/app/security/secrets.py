from __future__ import annotations

import base64
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes

_KEYCHAIN_SERVICE = "ai-assisted-marker"
_KEYCHAIN_ACCOUNT = "local-ai-api-key"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value)
    blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _crypt32():
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    library.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    library.CryptProtectData.restype = wintypes.BOOL
    library.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    library.CryptUnprotectData.restype = wintypes.BOOL
    return library


def _release(pointer: ctypes.POINTER(ctypes.c_byte)) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree(pointer)


def protect_secret(value: str) -> str:
    """Protect a secret with the current user's native OS credential store."""

    if not value:
        return ""
    if sys.platform == "darwin":
        try:
            subprocess.run(
                [
                    "security",
                    "add-generic-password",
                    "-U",
                    "-s",
                    _KEYCHAIN_SERVICE,
                    "-a",
                    _KEYCHAIN_ACCOUNT,
                    "-w",
                    value,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Could not save the API key in macOS Keychain") from exc
        return f"keychain:{_KEYCHAIN_SERVICE}:{_KEYCHAIN_ACCOUNT}"
    if os.name != "nt":
        raise RuntimeError("Persistent API-key storage requires Windows DPAPI or macOS Keychain")
    source, _source_buffer = _blob(value.encode("utf-8"))
    output = _DataBlob()
    if not _crypt32().CryptProtectData(
        ctypes.byref(source), "AI-assisted marker", None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        protected = ctypes.string_at(output.pbData, output.cbData)
        return "dpapi:" + base64.b64encode(protected).decode("ascii")
    finally:
        _release(output.pbData)


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("keychain:"):
        if sys.platform != "darwin":
            raise RuntimeError("This API key is stored in macOS Keychain")
        _, service, account = value.split(":", 2)
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Could not read the API key from macOS Keychain") from exc
        return result.stdout.rstrip("\r\n")
    if not value.startswith("dpapi:"):
        return value
    if os.name != "nt":
        raise RuntimeError("This API key is protected with Windows DPAPI")
    source, _source_buffer = _blob(base64.b64decode(value.removeprefix("dpapi:")))
    output = _DataBlob()
    if not _crypt32().CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        _release(output.pbData)
