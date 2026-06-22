"""
Interactive login flows: phone+code, two-factor (2FA) and QR code.

Each function is synchronous (it wraps Telethon's async API with ``run_async``)
and returns plain data structures so the Django views stay simple. The partial
``StringSession`` is returned to the caller, which persists it (encrypted) in
``AccountLoginSession`` between steps.
"""
from __future__ import annotations

from dataclasses import dataclass

from telethon import functions, types
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from .client import build_client, run_async


@dataclass
class LoginResult:
    status: str  # "code_sent" | "password_needed" | "ok" | "qr_pending" | "error"
    session_string: str = ""
    phone_code_hash: str = ""
    qr_url: str = ""
    error: str = ""
    user: dict | None = None


def _user_dict(me) -> dict:
    return {
        "telegram_user_id": me.id,
        "username": me.username or "",
        "first_name": me.first_name or "",
        "last_name": me.last_name or "",
    }


# ----------------------------------------------------------------------------
# Phone + code
# ----------------------------------------------------------------------------
def start_phone_login(phone: str, api_id: int, api_hash: str) -> LoginResult:
    async def _run() -> LoginResult:
        client = build_client("", api_id, api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            session_string = client.session.save()
            return LoginResult(
                status="code_sent",
                session_string=session_string,
                phone_code_hash=sent.phone_code_hash,
            )
        finally:
            await client.disconnect()

    try:
        return run_async(_run())
    except Exception as exc:  # noqa: BLE001
        return LoginResult(status="error", error=str(exc))


def submit_code(
    session_string: str,
    phone: str,
    phone_code_hash: str,
    code: str,
    api_id: int,
    api_hash: str,
) -> LoginResult:
    async def _run() -> LoginResult:
        client = build_client(session_string, api_id, api_hash)
        await client.connect()
        try:
            try:
                await client.sign_in(
                    phone=phone, code=code, phone_code_hash=phone_code_hash
                )
            except SessionPasswordNeededError:
                # Account has 2FA enabled - need the password next.
                return LoginResult(
                    status="password_needed",
                    session_string=client.session.save(),
                )
            me = await client.get_me()
            return LoginResult(
                status="ok",
                session_string=client.session.save(),
                user=_user_dict(me),
            )
        finally:
            await client.disconnect()

    try:
        return run_async(_run())
    except Exception as exc:  # noqa: BLE001
        return LoginResult(status="error", error=str(exc))


def submit_password(
    session_string: str, password: str, api_id: int, api_hash: str
) -> LoginResult:
    async def _run() -> LoginResult:
        client = build_client(session_string, api_id, api_hash)
        await client.connect()
        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            return LoginResult(
                status="ok",
                session_string=client.session.save(),
                user=_user_dict(me),
            )
        finally:
            await client.disconnect()

    try:
        return run_async(_run())
    except Exception as exc:  # noqa: BLE001
        return LoginResult(status="error", error=str(exc))


# ----------------------------------------------------------------------------
# QR login
# ----------------------------------------------------------------------------
def start_qr_login(api_id: int, api_hash: str) -> LoginResult:
    """Create a session and export a QR login token (tg://login?token=...)."""

    async def _run() -> LoginResult:
        client = build_client("", api_id, api_hash)
        await client.connect()
        try:
            qr = await client.qr_login()
            return LoginResult(
                status="qr_pending",
                session_string=client.session.save(),
                qr_url=qr.url,
            )
        finally:
            await client.disconnect()

    try:
        return run_async(_run())
    except Exception as exc:  # noqa: BLE001
        return LoginResult(status="error", error=str(exc))


def poll_qr_login(session_string: str, api_id: int, api_hash: str) -> LoginResult:
    """
    Check whether the QR code has been approved.

    Returns ``ok`` once authorized, ``password_needed`` if the account has 2FA,
    or ``qr_pending`` with a refreshed token URL if still waiting.
    """

    async def _run() -> LoginResult:
        client = build_client(session_string, api_id, api_hash)
        await client.connect()
        try:
            if await client.is_user_authorized():
                me = await client.get_me()
                return LoginResult(
                    status="ok",
                    session_string=client.session.save(),
                    user=_user_dict(me),
                )

            # Not yet authorized: re-export a fresh token and report it back so
            # the UI can refresh the displayed QR code.
            result = await client(
                functions.auth.ExportLoginTokenRequest(api_id, api_hash, [])
            )
            if isinstance(result, types.auth.LoginToken):
                import base64

                token = base64.urlsafe_b64encode(result.token).decode("utf-8").rstrip("=")
                return LoginResult(
                    status="qr_pending",
                    session_string=client.session.save(),
                    qr_url=f"tg://login?token={token}",
                )
            if isinstance(result, types.auth.LoginTokenSuccess):
                me = await client.get_me()
                return LoginResult(
                    status="ok",
                    session_string=client.session.save(),
                    user=_user_dict(me),
                )
            # LoginTokenMigrateTo and 2FA edge cases.
            return LoginResult(
                status="qr_pending", session_string=client.session.save()
            )
        except SessionPasswordNeededError:
            return LoginResult(
                status="password_needed", session_string=client.session.save()
            )
        finally:
            await client.disconnect()

    try:
        return run_async(_run())
    except Exception as exc:  # noqa: BLE001
        return LoginResult(status="error", error=str(exc))


def validate_session(session_string: str, api_id: int, api_hash: str) -> LoginResult:
    """Confirm a stored session is still authorized and refresh identity."""

    async def _run() -> LoginResult:
        client = build_client(session_string, api_id, api_hash)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return LoginResult(status="error", error="Session is not authorized")
            me = await client.get_me()
            return LoginResult(
                status="ok",
                session_string=client.session.save(),
                user=_user_dict(me),
            )
        finally:
            await client.disconnect()

    try:
        return run_async(_run())
    except Exception as exc:  # noqa: BLE001
        return LoginResult(status="error", error=str(exc))
