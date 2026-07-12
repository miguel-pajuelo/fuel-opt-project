from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from typing import Any, Mapping, Protocol


ORS_CREDENTIAL_TARGET = "FuelOpt/ORS_API_KEY"
ORS_CREDENTIAL_USERNAME = "FuelOpt"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
REDACTED = "[REDACTED]"


class CredentialStoreError(RuntimeError):
    pass


class CredentialStoreUnavailable(CredentialStoreError):
    pass


class CredentialStore(Protocol):
    def read(self, target: str) -> str | None: ...

    def write(self, target: str, secret: str, *, username: str = ORS_CREDENTIAL_USERNAME) -> None: ...

    def delete(self, target: str) -> bool: ...


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    pass


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTEW)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """Current-user generic credentials backed by Advapi32 Credential APIs."""

    def __init__(self, advapi32: Any | None = None) -> None:
        if sys.platform != "win32" and advapi32 is None:
            raise CredentialStoreUnavailable("Windows Credential Manager is unavailable")
        self._api = advapi32 or ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        pointer_type = ctypes.POINTER(_CREDENTIALW)
        try:
            self._api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
            self._api.CredWriteW.restype = wintypes.BOOL
            self._api.CredReadW.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(pointer_type),
            ]
            self._api.CredReadW.restype = wintypes.BOOL
            self._api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self._api.CredDeleteW.restype = wintypes.BOOL
            self._api.CredFree.argtypes = [wintypes.LPVOID]
            self._api.CredFree.restype = None
        except AttributeError as exc:
            raise CredentialStoreUnavailable("Credential Manager API is incomplete") from exc

    @staticmethod
    def _last_error(action: str) -> CredentialStoreError:
        code = ctypes.get_last_error()
        return CredentialStoreError(f"Credential Manager {action} failed with Windows error {code}")

    def read(self, target: str) -> str | None:
        credential_pointer = ctypes.POINTER(_CREDENTIALW)()
        ok = self._api.CredReadW(
            target,
            CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_pointer),
        )
        if not ok:
            if ctypes.get_last_error() == ERROR_NOT_FOUND:
                return None
            raise self._last_error("read")
        try:
            credential = credential_pointer.contents
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return blob.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise CredentialStoreError("Credential Manager returned an invalid UTF-8 secret") from exc
        finally:
            self._api.CredFree(credential_pointer)

    def write(self, target: str, secret: str, *, username: str = ORS_CREDENTIAL_USERNAME) -> None:
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        blob = secret.encode("utf-8")
        blob_buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = _CREDENTIALW()
        credential.Flags = 0
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = username
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            raise self._last_error("write")

    def delete(self, target: str) -> bool:
        if self._api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
            return True
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return False
        raise self._last_error("delete")


class UnavailableCredentialStore:
    def read(self, target: str) -> str | None:
        raise CredentialStoreUnavailable("Windows Credential Manager is unavailable")

    def write(self, target: str, secret: str, *, username: str = ORS_CREDENTIAL_USERNAME) -> None:
        raise CredentialStoreUnavailable("Windows Credential Manager is unavailable")

    def delete(self, target: str) -> bool:
        raise CredentialStoreUnavailable("Windows Credential Manager is unavailable")


def default_credential_store() -> CredentialStore:
    if sys.platform != "win32":
        return UnavailableCredentialStore()
    return WindowsCredentialStore()


def _usable_secret(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    secret = value.strip()
    if not secret or secret.lower() in {"replace-me", "changeme"} or secret.startswith("<"):
        return None
    return secret


def resolve_ors_api_key(
    *,
    environ: Mapping[str, str] | None = None,
    store: CredentialStore | None = None,
) -> str | None:
    active_store = store or default_credential_store()
    try:
        stored = _usable_secret(active_store.read(ORS_CREDENTIAL_TARGET))
    except CredentialStoreError:
        stored = None
    if stored:
        return stored
    env = os.environ if environ is None else environ
    return _usable_secret(env.get("ORS_API_KEY"))


def _redact_value(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return value.replace(secret, REDACTED)
    if isinstance(value, tuple):
        return tuple(_redact_value(item, secret) for item in value)
    if isinstance(value, list):
        return [_redact_value(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, secret) for key, item in value.items()}
    return value


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secret: str | None) -> None:
        super().__init__()
        self._secret = _usable_secret(secret)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secret:
            return True
        record.msg = _redact_value(record.msg, self._secret)
        record.args = _redact_value(record.args, self._secret)
        if record.exc_info:
            exception_text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = exception_text.replace(self._secret, REDACTED)
            record.exc_info = None
        if isinstance(record.stack_info, str):
            record.stack_info = record.stack_info.replace(self._secret, REDACTED)
        return True


def install_secret_redaction(logger: logging.Logger, secret: str | None) -> SecretRedactionFilter | None:
    if not _usable_secret(secret):
        return None
    redaction_filter = SecretRedactionFilter(secret)
    logger.addFilter(redaction_filter)
    for handler in logger.handlers:
        handler.addFilter(redaction_filter)
    return redaction_filter
