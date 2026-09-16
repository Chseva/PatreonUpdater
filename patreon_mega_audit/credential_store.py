"""Minimal Windows Credential Manager storage for the Patreon API token."""

from __future__ import annotations

import ctypes
from ctypes import POINTER, Structure, byref, c_void_p, cast
from ctypes.wintypes import DWORD, LPWSTR

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_TARGET_NAME = "PatreonUpdater:patreon_api_token"
_ADVAPI32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)


class _Credential(Structure):
    _fields_ = [
        ("Flags", DWORD), ("Type", DWORD), ("TargetName", LPWSTR), ("Comment", LPWSTR),
        ("LastWritten", ctypes.c_byte * 8), ("CredentialBlobSize", DWORD), ("CredentialBlob", c_void_p),
        ("Persist", DWORD), ("AttributeCount", DWORD), ("Attributes", c_void_p),
        ("TargetAlias", LPWSTR), ("UserName", LPWSTR),
    ]


def _require_windows() -> None:
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("Windows Credential Manager is only available on Windows.")


def load_token() -> str | None:
    """Return the stored token for the current Windows user, if one exists."""
    _require_windows()
    credential = POINTER(_Credential)()
    if not _ADVAPI32.CredReadW(_TARGET_NAME, _CRED_TYPE_GENERIC, 0, byref(credential)):
        if ctypes.get_last_error() == _ERROR_NOT_FOUND:
            return None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        raw = ctypes.string_at(credential.contents.CredentialBlob, credential.contents.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        _ADVAPI32.CredFree(credential)


def save_token(token: str) -> None:
    """Store a token in Windows Credential Manager for the current user."""
    _require_windows()
    encoded = token.encode("utf-16-le")
    blob = ctypes.create_string_buffer(encoded)
    credential = _Credential()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = _TARGET_NAME
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = cast(blob, c_void_p)
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "PatreonUpdater"
    if not _ADVAPI32.CredWriteW(byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def delete_token() -> bool:
    """Delete the saved token. Return False when no token exists."""
    _require_windows()
    if _ADVAPI32.CredDeleteW(_TARGET_NAME, _CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == _ERROR_NOT_FOUND:
        return False
    raise ctypes.WinError(ctypes.get_last_error())
