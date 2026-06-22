from __future__ import annotations

import base64
import io
from datetime import timedelta

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import AccountLoginSession, TelegramAccount
from apps.accounts.services import disconnect as svc_disconnect
from apps.accounts.services import finalize_login
from apps.accounts.telegram import auth as tg_auth
from apps.accounts.telegram.actions import create_channel as tg_create_channel
from apps.accounts.telegram.actions import create_group as tg_create_group
from apps.accounts.telegram.actions import (
    fetch_chat as tg_fetch_chat,
)
from apps.accounts.telegram.actions import (
    fetch_dialogs as tg_fetch_dialogs,
)
from apps.accounts.telegram.actions import (
    send_message as tg_send_message,
)
from apps.developers.models import APIKey, APIKeyRequest, Developer
from apps.developers.services import approve_request, reject_request
from apps.logs.models import ActionLog
from apps.logs.services import log_action
from apps.messaging.models import AutoReplyRule, Message, ScheduledMessage
from apps.scraping.models import ScrapedPost, ScrapeSource

from .forms import (
    AccountForm,
    AutoReplyForm,
    CodeForm,
    ConnectStartForm,
    CreateChannelForm,
    KeyRequestReviewForm,
    PasswordForm,
    ScheduledMessageForm,
    ScrapeSourceForm,
    UnlockForm,
)

DEFAULTS = {"api_id": None, "api_hash": ""}


# ---------------------------------------------------------------------------
# Dashboard home
# ---------------------------------------------------------------------------
@login_required
def home(request):
    today = timezone.now() - timedelta(hours=24)
    context = {
        "total_accounts": TelegramAccount.objects.count(),
        "active_accounts": TelegramAccount.objects.filter(status="active").count(),
        "messages_24h": Message.objects.filter(date__gte=today).count(),
        "pending_schedules": ScheduledMessage.objects.filter(status="pending").count(),
        "active_rules": AutoReplyRule.objects.filter(is_active=True).count(),
        "active_sources": ScrapeSource.objects.filter(is_active=True).count(),
        "pending_keys": APIKeyRequest.objects.filter(status="pending").count(),
        "recent_logs": ActionLog.objects.all()[:12],
        "accounts": TelegramAccount.objects.all()[:8],
    }
    return render(request, "dashboard/home.html", context)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@login_required
def accounts(request):
    qs = TelegramAccount.objects.select_related("owner").all()
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    return render(request, "dashboard/accounts.html", {"accounts": qs})


@login_required
def account_detail(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    content_key = _content_key_for_session(request, account)
    msgs = account.messages.all()[:30]
    rendered = [
        {
            "obj": m,
            "text": m.get_content(content_key),
            "locked": m.is_private and m.get_content(content_key) is None,
        }
        for m in msgs
    ]
    return render(
        request,
        "dashboard/account_detail.html",
        {"account": account, "messages": rendered, "unlock_form": UnlockForm()},
    )


@login_required
def account_edit(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    form = AccountForm(request.POST or None, instance=account)
    if request.method == "POST" and form.is_valid():
        changed = form.changed_data
        form.save()
        log_action(
            category="account", action="account_edited", account=account,
            developer=account.owner, actor=request.user, source="panel",
            metadata={"changed": changed}, ip_address=getattr(request, "client_ip", None),
        )
        flash.success(request, "Account updated.")
        return redirect("dashboard:account_detail", pk=account.pk)
    return render(request, "dashboard/account_form.html", {"form": form, "account": account})


@login_required
def account_presence(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    if request.method == "POST":
        account.presence = request.POST.get("presence", account.presence)
        account.save(update_fields=["presence", "updated_at"])
        log_action(
            category="account", action="presence_changed", account=account,
            actor=request.user, source="panel", metadata={"presence": account.presence},
        )
        flash.success(request, f"Presence set to {account.get_presence_display()}.")
    return redirect("dashboard:account_detail", pk=pk)


@login_required
def account_disconnect(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    if request.method == "POST":
        svc_disconnect(account, actor=request.user)
        flash.success(request, "Account disconnected.")
    return redirect("dashboard:accounts")


# ---- connect wizard -------------------------------------------------------
@login_required
def connect_start(request):
    form = ConnectStartForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        account = TelegramAccount.objects.create(
            label=data["label"],
            phone=data.get("phone", ""),
            api_id=data.get("api_id") or None,
            api_hash=data.get("api_hash") or "",
            owner=data.get("owner"),
            is_private=data.get("is_private", False),
            created_by=request.user,
            status=TelegramAccount.Status.PENDING,
        )
        if data["method"] == "phone":
            result = tg_auth.start_phone_login(
                data["phone"], account.effective_api_id, account.effective_api_hash
            )
            if result.status != "code_sent":
                flash.error(request, f"Could not send code: {result.error}")
                account.delete()
                return redirect("dashboard:connect_start")
            session = AccountLoginSession.objects.create(
                account=account,
                method=AccountLoginSession.Method.PHONE,
                stage=AccountLoginSession.Stage.CODE,
                phone=data["phone"],
                phone_code_hash=result.phone_code_hash,
            )
            session.set_session(result.session_string)
            session.save()
            return redirect("dashboard:connect_code", session_id=session.pk)

        # QR
        result = tg_auth.start_qr_login(
            account.effective_api_id, account.effective_api_hash
        )
        if result.status != "qr_pending":
            flash.error(request, f"Could not start QR login: {result.error}")
            account.delete()
            return redirect("dashboard:connect_start")
        session = AccountLoginSession.objects.create(
            account=account,
            method=AccountLoginSession.Method.QR,
            stage=AccountLoginSession.Stage.QR,
            qr_url=result.qr_url,
        )
        session.set_session(result.session_string)
        session.save()
        return redirect("dashboard:connect_qr", session_id=session.pk)

    return render(request, "dashboard/connect_start.html", {"form": form})


@login_required
def connect_code(request, session_id):
    session = get_object_or_404(AccountLoginSession, pk=session_id)
    account = session.account
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = tg_auth.submit_code(
            session.get_session(),
            session.phone,
            session.phone_code_hash,
            form.cleaned_data["code"],
            account.effective_api_id,
            account.effective_api_hash,
        )
        if result.status == "ok":
            finalize_login(account, result, actor=request.user,
                           ip_address=getattr(request, "client_ip", None))
            session.stage = AccountLoginSession.Stage.DONE
            session.save(update_fields=["stage", "updated_at"])
            flash.success(request, "Account connected successfully.")
            return redirect("dashboard:account_detail", pk=account.pk)
        if result.status == "password_needed":
            account.is_2fa_enabled = True
            account.save(update_fields=["is_2fa_enabled", "updated_at"])
            session.stage = AccountLoginSession.Stage.PASSWORD
            session.set_session(result.session_string)
            session.save()
            return redirect("dashboard:connect_password", session_id=session.pk)
        flash.error(request, f"Login failed: {result.error}")
    return render(request, "dashboard/connect_code.html", {"form": form, "session": session})


@login_required
def connect_password(request, session_id):
    session = get_object_or_404(AccountLoginSession, pk=session_id)
    account = session.account
    form = PasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = tg_auth.submit_password(
            session.get_session(),
            form.cleaned_data["password"],
            account.effective_api_id,
            account.effective_api_hash,
        )
        if result.status == "ok":
            finalize_login(account, result, actor=request.user,
                           ip_address=getattr(request, "client_ip", None))
            session.stage = AccountLoginSession.Stage.DONE
            session.save(update_fields=["stage", "updated_at"])
            flash.success(request, "Account connected (2FA verified).")
            return redirect("dashboard:account_detail", pk=account.pk)
        flash.error(request, f"2FA failed: {result.error}")
    return render(request, "dashboard/connect_password.html", {"form": form, "session": session})


@login_required
def connect_qr(request, session_id):
    session = get_object_or_404(AccountLoginSession, pk=session_id)
    return render(
        request,
        "dashboard/connect_qr.html",
        {"session": session, "qr_data_uri": _qr_data_uri(session.qr_url)},
    )


@login_required
def connect_qr_poll(request, session_id):
    """AJAX endpoint: check QR scan progress and refresh the token."""
    session = get_object_or_404(AccountLoginSession, pk=session_id)
    account = session.account
    result = tg_auth.poll_qr_login(
        session.get_session(), account.effective_api_id, account.effective_api_hash
    )
    if result.status == "ok":
        finalize_login(account, result, actor=request.user,
                       ip_address=getattr(request, "client_ip", None))
        session.stage = AccountLoginSession.Stage.DONE
        session.save(update_fields=["stage", "updated_at"])
        return JsonResponse({"status": "ok", "redirect": f"/accounts/{account.pk}/"})
    if result.status == "password_needed":
        account.is_2fa_enabled = True
        account.save(update_fields=["is_2fa_enabled", "updated_at"])
        session.stage = AccountLoginSession.Stage.PASSWORD
        session.set_session(result.session_string)
        session.save()
        return JsonResponse(
            {"status": "password_needed", "redirect": f"/accounts/connect/password/{session.pk}/"}
        )
    if result.status == "qr_pending":
        if result.session_string:
            session.set_session(result.session_string)
        if result.qr_url:
            session.qr_url = result.qr_url
        session.save()
        return JsonResponse({"status": "waiting", "qr": _qr_data_uri(session.qr_url)})
    return JsonResponse({"status": "error", "error": result.error})


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@login_required
def messages_view(request):
    qs = Message.objects.select_related("account", "account__owner").all()
    account_id = request.GET.get("account")
    if account_id:
        qs = qs.filter(account_id=account_id)
    direction = request.GET.get("direction")
    if direction:
        qs = qs.filter(direction=direction)
    kind = request.GET.get("kind")
    if kind:
        qs = qs.filter(kind=kind)
    qs = qs[:100]

    rendered = []
    for m in qs:
        ck = _content_key_for_session(request, m.account)
        text = m.get_content(ck)
        rendered.append(
            {"obj": m, "text": text, "locked": m.is_private and text is None}
        )
    return render(
        request,
        "dashboard/messages.html",
        {
            "messages": rendered,
            "accounts": TelegramAccount.objects.all(),
            "unlock_form": UnlockForm(),
            "filters": {"account": account_id, "direction": direction, "kind": kind},
        },
    )


@login_required
def unlock_messages(request):
    """Verify a developer API key and cache its content key in the session."""
    if request.method == "POST":
        form = UnlockForm(request.POST)
        if form.is_valid():
            raw_key = form.cleaned_data["api_key"]
            key = APIKey.find_valid(raw_key)
            if key is None:
                flash.error(request, "Invalid or inactive API key.")
            else:
                unlocked = request.session.get("unlocked_devs", {})
                unlocked[str(key.developer_id)] = key.developer.get_content_key()
                request.session["unlocked_devs"] = unlocked
                log_action(
                    category="developer", action="content_unlocked",
                    developer=key.developer, actor=request.user, source="panel",
                    metadata={"key_prefix": key.prefix},
                )
                flash.success(
                    request,
                    f"Unlocked private content for {key.developer}.",
                )
    return redirect(request.META.get("HTTP_REFERER", "dashboard:messages"))


def _content_key_for_session(request, account: TelegramAccount):
    if not (account.is_private and account.owner_id):
        return None
    unlocked = request.session.get("unlocked_devs", {})
    return unlocked.get(str(account.owner_id))


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
@login_required
def schedules(request):
    return render(
        request,
        "dashboard/schedules.html",
        {"schedules": ScheduledMessage.objects.select_related("account").all()},
    )


@login_required
def schedule_create(request):
    form = ScheduledMessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        schedule = form.save()
        log_action(
            category="schedule", action="schedule_created", account=schedule.account,
            developer=schedule.owner, actor=request.user, source="panel",
            metadata={"title": schedule.title, "targets": schedule.targets},
        )
        flash.success(request, "Schedule created.")
        return redirect("dashboard:schedules")
    return render(request, "dashboard/schedule_form.html", {"form": form})


@login_required
def schedule_send_now(request, pk):
    schedule = get_object_or_404(ScheduledMessage, pk=pk)
    if request.method == "POST":
        from apps.messaging.tasks import send_scheduled_message

        result = send_scheduled_message(schedule.pk)  # run synchronously
        flash.info(request, f"Dispatch result: {result}")
    return redirect("dashboard:schedules")


@login_required
def schedule_cancel(request, pk):
    schedule = get_object_or_404(ScheduledMessage, pk=pk)
    if request.method == "POST":
        schedule.status = ScheduledMessage.Status.CANCELLED
        schedule.save(update_fields=["status", "updated_at"])
        flash.success(request, "Schedule cancelled.")
    return redirect("dashboard:schedules")


# ---------------------------------------------------------------------------
# Auto-reply
# ---------------------------------------------------------------------------
@login_required
def autoreplies(request):
    return render(
        request,
        "dashboard/autoreplies.html",
        {"rules": AutoReplyRule.objects.select_related("account").all()},
    )


@login_required
def autoreply_create(request):
    form = AutoReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        rule = form.save()
        log_action(
            category="autoreply", action="autoreply_created", account=rule.account,
            developer=rule.owner, actor=request.user, source="panel",
            metadata={"name": rule.name, "mode": rule.mode},
        )
        flash.success(request, "Auto-reply rule created.")
        return redirect("dashboard:autoreplies")
    return render(request, "dashboard/autoreply_form.html", {"form": form})


@login_required
def autoreply_toggle(request, pk):
    rule = get_object_or_404(AutoReplyRule, pk=pk)
    if request.method == "POST":
        rule.is_active = not rule.is_active
        rule.save(update_fields=["is_active", "updated_at"])
    return redirect("dashboard:autoreplies")


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
@login_required
def scrape_sources(request):
    return render(
        request,
        "dashboard/scrape_sources.html",
        {"sources": ScrapeSource.objects.select_related("account").all()},
    )


@login_required
def scrape_source_create(request):
    form = ScrapeSourceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        source = form.save()
        log_action(
            category="scrape", action="scrape_source_created", account=source.account,
            developer=source.owner, actor=request.user, source="panel",
            metadata={"source": source.source, "keywords": source.keywords},
        )
        flash.success(request, "Scrape source created.")
        return redirect("dashboard:scrape_sources")
    return render(request, "dashboard/scrape_source_form.html", {"form": form})


@login_required
def scrape_run(request, pk):
    source = get_object_or_404(ScrapeSource, pk=pk)
    if request.method == "POST":
        from apps.scraping.tasks import scrape_source as run_scrape

        result = run_scrape(source.pk)  # synchronous run
        flash.info(request, f"Scrape result: {result}")
    return redirect("dashboard:scrape_posts", pk=pk)


@login_required
def scrape_posts(request, pk):
    source = get_object_or_404(ScrapeSource, pk=pk)
    return render(
        request,
        "dashboard/scrape_posts.html",
        {"source": source, "posts": source.posts.all()[:100]},
    )


# ---------------------------------------------------------------------------
# Channels / groups
# ---------------------------------------------------------------------------
@login_required
def create_channel(request):
    form = CreateChannelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.cleaned_data["account"]
        title = form.cleaned_data["title"]
        about = form.cleaned_data.get("about", "")
        if form.cleaned_data["kind"] == "group":
            result = tg_create_group(
                account.get_session(), account.effective_api_id,
                account.effective_api_hash, title,
            )
        else:
            result = tg_create_channel(
                account.get_session(), account.effective_api_id,
                account.effective_api_hash, title, about,
            )
        log_action(
            category="channel", action="channel_created", account=account,
            developer=account.owner, actor=request.user, source="panel",
            metadata={"title": title, "kind": form.cleaned_data["kind"], "ok": result.get("ok")},
        )
        if result.get("ok"):
            flash.success(request, f"Created: {result}")
        else:
            flash.error(request, f"Failed: {result.get('error')}")
        return redirect("dashboard:create_channel")
    return render(request, "dashboard/create_channel.html", {"form": form})


# ---------------------------------------------------------------------------
# Developers & API keys
# ---------------------------------------------------------------------------
@login_required
def developers(request):
    devs = Developer.objects.annotate(
        key_count=Count("api_keys"), account_count=Count("accounts")
    )
    return render(request, "dashboard/developers.html", {"developers": devs})


@login_required
def key_requests(request):
    return render(
        request,
        "dashboard/key_requests.html",
        {
            "requests": APIKeyRequest.objects.select_related("developer").all(),
            "review_form": KeyRequestReviewForm(),
        },
    )


@login_required
def key_request_approve(request, pk):
    req = get_object_or_404(APIKeyRequest, pk=pk)
    if request.method == "POST" and req.status == APIKeyRequest.Status.PENDING:
        key, raw_key = approve_request(req, reviewer=request.user)
        flash.warning(
            request,
            f"API key issued and delivered. Shown once: {raw_key}",
        )
    return redirect("dashboard:key_requests")


@login_required
def key_request_reject(request, pk):
    req = get_object_or_404(APIKeyRequest, pk=pk)
    if request.method == "POST" and req.status == APIKeyRequest.Status.PENDING:
        note = request.POST.get("note", "")
        reject_request(req, reviewer=request.user, note=note)
        flash.success(request, "Request rejected.")
    return redirect("dashboard:key_requests")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
@login_required
def logs(request):
    qs = ActionLog.objects.select_related("account", "developer", "actor").all()
    category = request.GET.get("category")
    if category:
        qs = qs.filter(category=category)
    account_id = request.GET.get("account")
    if account_id:
        qs = qs.filter(account_id=account_id)
    return render(
        request,
        "dashboard/logs.html",
        {
            "logs": qs[:200],
            "categories": ActionLog.Category.choices,
            "accounts": TelegramAccount.objects.all(),
            "filters": {"category": category, "account": account_id},
        },
    )


# ---------------------------------------------------------------------------
# API docs
# ---------------------------------------------------------------------------
@login_required
def api_docs(request):
    return render(request, "dashboard/api_docs.html", {})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _qr_data_uri(url: str) -> str:
    if not url:
        return ""
    try:
        import qrcode

        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:  # noqa: BLE001
        return ""



# ---------------------------------------------------------------------------
# Chat (Telegram-style conversations: read & reply)
# ---------------------------------------------------------------------------
def _chat_locked(request, account: TelegramAccount) -> bool:
    """Private (developer-owned) accounts stay locked until unlocked by key."""
    return account.is_private and _content_key_for_session(request, account) is None


@login_required
def chat(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    return render(
        request,
        "dashboard/chat.html",
        {
            "account": account,
            "locked": _chat_locked(request, account),
            "connected": account.status == TelegramAccount.Status.ACTIVE
            and bool(account.session_enc),
        },
    )


@login_required
def chat_dialogs(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    if _chat_locked(request, account):
        return JsonResponse({"ok": False, "locked": True}, status=403)
    result = tg_fetch_dialogs(
        account.get_session(), account.effective_api_id, account.effective_api_hash,
        limit=int(request.GET.get("limit", 100)),
    )
    return JsonResponse(result)


@login_required
def chat_history(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    if _chat_locked(request, account):
        return JsonResponse({"ok": False, "locked": True}, status=403)
    target = request.GET.get("target")
    if not target:
        return JsonResponse({"ok": False, "error": "target required"}, status=400)
    result = tg_fetch_chat(
        account.get_session(), account.effective_api_id, account.effective_api_hash,
        target, limit=int(request.GET.get("limit", 60)),
    )
    if result.get("ok"):
        from .sanitize import sanitize_html

        for m in result["messages"]:
            m["html"] = sanitize_html(m.get("html", ""))
    return JsonResponse(result)


@login_required
def chat_send(request, pk):
    account = get_object_or_404(TelegramAccount, pk=pk)
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    if _chat_locked(request, account):
        return JsonResponse({"ok": False, "locked": True}, status=403)

    import json

    from .sanitize import html_to_telegram, sanitize_html

    try:
        data = json.loads(request.body.decode() or "{}")
    except ValueError:
        data = request.POST

    target = (data.get("target") or "").strip()
    raw_html = data.get("html") or ""
    reply_to = data.get("reply_to") or None
    if not target:
        return JsonResponse({"ok": False, "error": "target required"}, status=400)

    text = html_to_telegram(raw_html)
    if not text:
        return JsonResponse({"ok": False, "error": "empty message"}, status=400)

    result = tg_send_message(
        account.get_session(),
        account.effective_api_id,
        account.effective_api_hash,
        target,
        text,
        reply_to=int(reply_to) if reply_to else None,
        parse_mode="html",
    )
    log_action(
        category="message", action="chat_reply_sent", account=account,
        developer=account.owner, actor=request.user, source="panel",
        metadata={"target": target, "ok": result.get("ok"),
                  "preview": "" if account.is_private else text[:120]},
        ip_address=getattr(request, "client_ip", None),
    )
    if result.get("ok"):
        result["html"] = sanitize_html(raw_html)
    code = 200 if result.get("ok") else 400
    return JsonResponse(result, status=code)
