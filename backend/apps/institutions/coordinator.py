"""A college's IQAC Coordinator: named at Institution DNA creation, invited by email, activated by the person.

Flow
1. `assign(institution, name, email, actor)` -- inside the caller's transaction: stores the name and email on the
   institution, revokes any other pending invitation, prepares the account and creates ONE pending invitation
   with a fresh token (only its SHA-256 hash is stored). Returns the invitation and the raw token, which exists
   only in memory until it is emailed.
2. `deliver(invitation, token)` -- after the transaction committed (nothing is emailed for records that were
   rolled back). A failed send keeps the institution and the invitation; the result says so and
   `resend(institution, actor)` tries again on the same row with a new token (the old link dies).
3. `accept(token, password)` -- public, through the emailed link. Single use, expires after
   COORDINATOR_INVITATION_HOURS. The token is cleared on success.

Accounts (one college per account in this platform):
- No account with that email: a new IQAC Coordinator account of this college is created DEACTIVATED with an
  unusable password; it becomes active only when the person chooses a password through the link.
- An account of this college, or an IQAC Coordinator account with no college: linked to this college only when
  its owner accepts through the link (proving the mailbox is theirs). Its password is never changed.
- Any other account (another college, InGage staff, an account an administrator deactivated): never moved or
  reactivated. The person gets an email without a link explaining whom to contact.
The person creating the institution sees the same "invitation sent" either way: nothing here reveals whether an
email address already has an account.

Changing the coordinator later (`assign` again with a different email) revokes the pending invitation and
invites the new person; the previous coordinator's account is NOT changed or removed (that is a separate,
explicit step in User administration), and the new person gets access only by accepting. Correcting the name of
the same email only updates the institution's record.
"""
import hashlib
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import CoordinatorEvent, CoordinatorInvitation, Institution

logger = logging.getLogger(__name__)
Invitation = CoordinatorInvitation
Event = CoordinatorEvent.Action

#: Names in any script (Tamil vowel signs are combining marks, not "word" characters), but no digits or symbols.
NAME_FORBIDDEN = re.compile(r'[\d<>{}\[\]()@#$%^&*=+|\/;:"!?~`_,]')


class CoordinatorError(Exception):
    """A rule was broken; the message is safe to show. `field` names the input it is about, when there is one."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.field = field


class EmailUnavailable(CoordinatorError):
    """The email belongs to an account that may not become this college's coordinator (another college, InGage
    staff, or an account an administrator deactivated). Nothing was changed and no link was created."""

    def __init__(self):
        super().__init__(UNAVAILABLE_MESSAGE, field='coordinator_email')


#: What staff are told when an email cannot be used -- what to do next, never which account or where.
UNAVAILABLE_MESSAGE = ("No activation link was created: this email address can't be used for this college's IQAC Coordinator. Use the coordinator's own college email address, or ask a Super Admin to review it in User administration.")


class InvalidToken(CoordinatorError):
    pass


# -- validation ---------------------------------------------------------------------------------------

def clean_name(value):
    name = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not name:
        raise CoordinatorError('Enter the IQAC Coordinator\'s name.', 'coordinator_name')
    if len(name) < 2 or len(name) > 150:
        raise CoordinatorError('The name must be 2 to 150 characters.', 'coordinator_name')
    if NAME_FORBIDDEN.search(name) or sum(ch.isalpha() for ch in name) < 2:
        raise CoordinatorError('The name may contain letters, spaces, dots, hyphens and apostrophes only.',
                               'coordinator_name')
    return name


def clean_email(value):
    email = str(value or '').strip().lower()
    if not email:
        raise CoordinatorError('Enter the IQAC Coordinator\'s email address.', 'coordinator_email')
    try:
        validate_email(email)
    except DjangoValidationError:
        raise CoordinatorError('Enter a valid email address.', 'coordinator_email') from None
    return email


# -- tokens -------------------------------------------------------------------------------------------

def _hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _new_token(invitation):
    """A fresh 256-bit token for this invitation; only its hash is kept. Returns the raw token."""
    token = secrets.token_urlsafe(32)
    invitation.token_hash = _hash(token)
    invitation.expires_at = timezone.now() + timedelta(hours=settings.COORDINATOR_INVITATION_HOURS)
    return token


def _event(institution, action, actor=None, invitation=None, note='', **data):
    return CoordinatorEvent.objects.create(institution=institution, invitation=invitation, action=action,
                                           user=actor, note=note, data=data)


# -- accounts ----------------------------------------------------------------------------------------

def _unique_username(email):
    base = re.sub(r'[^\w.@+-]', '', email.split('@')[0])[:120] or 'coordinator'
    candidate, n = base, 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f'{base}{n}'
    return candidate


def _split_name(name):
    first, _, last = name.partition(' ')
    return first[:150], last[:150]


def eligible(institution, email):
    """False when the email belongs to an account that may not become this college's coordinator. Read-only."""
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        return True
    pending_new = (not user.is_active and not user.has_usable_password()
                   and user.role == User.Role.IQAC_COORDINATOR and user.institution_id == institution.id)
    return pending_new or (user.is_active and user.role == User.Role.IQAC_COORDINATOR
                           and user.institution_id in (None, institution.id))


def _prepare_account(institution, name, email):
    """(account_state, user) for this email -- see the module docstring. Never changes a password."""
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        first, last = _split_name(name)
        user = User(email=email, username=_unique_username(email), first_name=first, last_name=last,
                    role=User.Role.IQAC_COORDINATOR, institution=institution, is_active=False)
        user.set_unusable_password()
        user.save()
        return Invitation.AccountState.NEW, user
    pending_new = (not user.is_active and not user.has_usable_password()
                   and user.role == User.Role.IQAC_COORDINATOR and user.institution_id == institution.id)
    if pending_new:  # created by an earlier invitation of this college and never activated
        return Invitation.AccountState.NEW, user
    if (user.is_active and user.role == User.Role.IQAC_COORDINATOR
            and user.institution_id in (None, institution.id)):
        return Invitation.AccountState.EXISTING, user
    return Invitation.AccountState.UNAVAILABLE, None


# -- assign / change ---------------------------------------------------------------------------------

def assign(institution, name, email, actor, *, refuse_unavailable=False):
    """Name (or change) the institution's coordinator. Call inside a transaction; then `deliver` the returned
    (invitation, token) after it commits. Returns (None, None) when only the name was corrected.

    refuse_unavailable: raise EmailUnavailable -- before anything is changed -- when the email belongs to an
    account that may not become this college's coordinator (the Institution DNA coordinator panel). At creation
    the institution is still saved and that person is told by email instead (no link)."""
    name, email = clean_name(name), clean_email(email)
    same_email = institution.coordinator_email.lower() == email
    if refuse_unavailable and not same_email and not eligible(institution, email):
        raise EmailUnavailable()
    pending = institution.coordinator_invitations.filter(status=Invitation.Status.PENDING).first()
    if same_email and institution.has_coordinator and (pending or institution.coordinator_user_id):
        if name != institution.coordinator_name:
            _event(institution, Event.NAME_UPDATED, actor, pending, previous_name=institution.coordinator_name,
                   new_name=name)
            institution.coordinator_name = name
            institution.save(update_fields=['coordinator_name', 'updated_at'])
            if pending:
                pending.name = name
                pending.save(update_fields=['name'])
        return None, None
    previous = {'name': institution.coordinator_name, 'email': institution.coordinator_email,
                'user_id': str(institution.coordinator_user_id) if institution.coordinator_user_id else None}
    if pending:
        pending.status, pending.token_hash = Invitation.Status.REVOKED, ''
        pending.save(update_fields=['status', 'token_hash'])
        _event(institution, Event.REVOKED, actor, pending, 'A new coordinator was named.')
    if previous['email']:
        # The previous coordinator's account keeps whatever access it has -- removing it is an explicit step in
        # User administration, never a side effect of renaming a contact.
        _event(institution, Event.CHANGED, actor, note='Coordinator changed.', previous=previous,
               current={'name': name, 'email': email})
    institution.coordinator_name, institution.coordinator_email, institution.coordinator_user = name, email, None
    institution.save(update_fields=['coordinator_name', 'coordinator_email', 'coordinator_user', 'updated_at'])
    state, user = _prepare_account(institution, name, email)
    invitation = Invitation(institution=institution, name=name, email=email, user=user, account_state=state,
                            created_by=actor)
    token = _new_token(invitation) if state != Invitation.AccountState.UNAVAILABLE else None
    invitation.save()
    _event(institution, Event.INVITED, actor, invitation, name=name, email=email)
    return invitation, token


# -- email ----------------------------------------------------------------------------------------------

def _link(token):
    return f'{settings.FRONTEND_BASE_URL}/activate-account?token={token}'


def _message(invitation, token):
    institution = invitation.institution
    hours = settings.COORDINATOR_INVITATION_HOURS
    hello = f'Hello {invitation.name},'
    intro = (f'You have been named the IQAC Coordinator of {institution.name} on the InGage AI Readiness '
             'platform.')
    if invitation.account_state == Invitation.AccountState.UNAVAILABLE:
        text = ('Your email address is already used by an account that belongs to another organisation, so it '
                'could not be added to this college. Please contact your InGage consultant to set up access.')
        body = f'{hello}\n\n{intro}\n\n{text}\n\nInGage Technologies'
        html = f'<p>{hello}</p><p>{intro}</p><p>{text}</p><p>InGage Technologies</p>'
        return f'IQAC Coordinator of {institution.name}', body, html
    link = _link(token)
    if invitation.account_state == Invitation.AccountState.NEW:
        action = 'Activate your account and choose your password'
    else:
        action = 'Accept with your existing account (your password stays the same)'
    body = (f'{hello}\n\n{intro}\n\n{action}:\n\n{link}\n\n'
            f'The link works once and expires in {hours} hours. If you did not expect this, ignore this email.'
            '\n\nInGage Technologies')
    html = (f'<p>{hello}</p><p>{intro}</p>'
            f'<p><a href="{link}" style="background:#0f766e;color:#fff;padding:10px 16px;border-radius:6px;'
            f'text-decoration:none;display:inline-block">{action}</a></p>'
            f'<p>The link works once and expires in {hours} hours. If you did not expect this, ignore this '
            'email.</p><p>InGage Technologies</p>')
    return f'Your IQAC Coordinator invitation for {institution.name}', body, html


def deliver(invitation, token, actor=None):
    """Email the invitation (after the records are committed). Never raises; returns True when sent."""
    subject, body, html = _message(invitation, token)
    now = timezone.now()
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [invitation.email], html_message=html)
    except Exception as exc:  # SMTP down, bad credentials, timeout ... -- the institution stays
        reason = f'{type(exc).__name__}: the email server did not accept the message.'
        Invitation.objects.filter(pk=invitation.pk).update(delivery=Invitation.Delivery.FAILED,
                                                           delivery_error=reason)
        invitation.delivery, invitation.delivery_error = Invitation.Delivery.FAILED, reason
        _event(invitation.institution, Event.EMAIL_FAILED, actor, invitation, reason)
        logger.warning('institutions.coordinator.email_failed invitation=%s error=%s', invitation.pk,
                       type(exc).__name__)
        return False
    Invitation.objects.filter(pk=invitation.pk).update(
        delivery=Invitation.Delivery.SENT, delivery_error='', last_sent_at=now, send_count=invitation.send_count + 1)
    invitation.delivery, invitation.delivery_error = Invitation.Delivery.SENT, ''
    invitation.last_sent_at, invitation.send_count = now, invitation.send_count + 1
    _event(invitation.institution, Event.EMAIL_SENT, actor, invitation)
    logger.info('institutions.coordinator.email_sent invitation=%s', invitation.pk)
    return True


def resend(institution, actor):
    """Send the pending invitation again with a NEW token (the previous link stops working). Same row: never a
    duplicate account or invitation. Returns the invitation."""
    with transaction.atomic():
        invitation = (Invitation.objects.select_for_update()
                      .filter(institution=institution, status=Invitation.Status.PENDING).first())
        if invitation is None:
            if institution.coordinator_user_id:
                raise CoordinatorError('The coordinator has already accepted the invitation.')
            raise CoordinatorError('There is no pending invitation. Name the coordinator first.')
        if invitation.account_state == Invitation.AccountState.UNAVAILABLE:
            raise EmailUnavailable()  # resending would create no link: a different email is needed
        token = _new_token(invitation)
        invitation.save(update_fields=['token_hash', 'expires_at'])
        _event(institution, Event.RESENT, actor, invitation)
    deliver(invitation, token, actor)
    return invitation


def resend_for_email(email):
    """"Forgot password" from an invited coordinator who never activated (their account is deactivated with no
    password, so a reset link cannot apply): email a fresh activation link -- rotating the token, the old link
    dies -- to that same address. Does nothing otherwise. Returns True when an invitation was resent."""
    email = str(email or '').strip().lower()
    invitation = (Invitation.objects.select_related('institution')
                  .filter(email=email, status=Invitation.Status.PENDING,
                          account_state=Invitation.AccountState.NEW).first())
    if invitation is None:
        return False
    resend(invitation.institution, None)
    return True


# -- acceptance (public) -------------------------------------------------------------------------------

def _find(token):
    if not token or len(token) > 128:
        raise InvalidToken('This invitation link is invalid or has expired. Ask InGage to resend it.')
    invitation = (Invitation.objects.select_related('institution', 'user')
                  .filter(token_hash=_hash(token), status=Invitation.Status.PENDING).first())
    if invitation is None or invitation.expires_at is None or invitation.expires_at <= timezone.now():
        raise InvalidToken('This invitation link is invalid or has expired. Ask InGage to resend it.')
    return invitation


def describe(token):
    """What the activation page shows for a valid link: the college, the person, and whether to set a password."""
    invitation = _find(token)
    return {'institution_name': invitation.institution.name, 'name': invitation.name,
            'email': invitation.email,
            'needs_password': invitation.account_state == Invitation.AccountState.NEW}


def accept(token, password=None):
    """Activate / link the coordinator's account. Single use: the token is cleared. Returns the user."""
    with transaction.atomic():
        found = _find(token)
        invitation = Invitation.objects.select_for_update().get(pk=found.pk)
        if invitation.status != Invitation.Status.PENDING or invitation.token_hash != _hash(token):
            raise InvalidToken('This invitation link is invalid or has expired. Ask InGage to resend it.')
        institution = Institution.objects.select_for_update().get(pk=invitation.institution_id)
        user = User.objects.select_for_update().get(pk=invitation.user_id) if invitation.user_id else None
        if user is None or user.email.lower() != invitation.email:
            raise InvalidToken('This invitation link is invalid or has expired. Ask InGage to resend it.')
        if invitation.account_state == Invitation.AccountState.NEW:
            if user.is_active or user.has_usable_password():
                raise InvalidToken('This invitation link is invalid or has expired. Ask InGage to resend it.')
            if not password:
                raise CoordinatorError('Choose a password.')
            try:
                validate_password(password, user=user)
            except DjangoValidationError as exc:
                raise CoordinatorError(' '.join(exc.messages)) from None
            user.set_password(password)
            user.is_active = True
            user.institution = institution
            user.role = User.Role.IQAC_COORDINATOR
            user.save(update_fields=['password', 'is_active', 'institution', 'role', 'updated_at'])
        else:  # an existing account: never touch its password; join only this college
            if not (user.is_active and user.role == User.Role.IQAC_COORDINATOR
                    and user.institution_id in (None, institution.id)):
                raise InvalidToken('This invitation link is invalid or has expired. Ask InGage to resend it.')
            if user.institution_id is None:
                user.institution = institution
                user.save(update_fields=['institution', 'updated_at'])
        invitation.status, invitation.token_hash = Invitation.Status.ACCEPTED, ''
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['status', 'token_hash', 'accepted_at'])
        institution.coordinator_user = user
        institution.save(update_fields=['coordinator_user', 'updated_at'])
        _event(institution, Event.ACTIVATED, user, invitation,
               'Account activated with a new password.' if invitation.account_state == Invitation.AccountState.NEW
               else 'Accepted with an existing account.')
    logger.info('institutions.coordinator.accepted invitation=%s', invitation.pk)
    return user


# -- status for the UI ------------------------------------------------------------------------------------

def status_of(institution, *, for_staff=False):
    """The coordinator's state for the UI -- never a token. Only InGage staff (`for_staff`) are told that the
    email cannot be used (state 'account_unavailable', with what to do next); nobody is told which account or
    where it belongs."""
    if not institution.has_coordinator:
        return {'configured': False, 'name': '', 'email': '', 'state': 'missing', 'state_label': 'Not configured',
                'can_resend': False}
    invitation = institution.coordinator_invitations.filter(status=Invitation.Status.PENDING).first()
    if institution.coordinator_user_id and invitation is None:
        state, label = 'active', 'Active'
    elif invitation is None:
        state, label = 'not_invited', 'Not invited yet'
    elif invitation.account_state == Invitation.AccountState.UNAVAILABLE:
        if for_staff:
            state, label = 'account_unavailable', UNAVAILABLE_MESSAGE
        else:
            state, label = 'pending_setup', 'Being set up by InGage'
    elif invitation.delivery == Invitation.Delivery.FAILED:
        state, label = 'email_failed', 'Invitation email failed -- resend it'
    elif invitation.delivery == Invitation.Delivery.SENT and invitation.expires_at \
            and invitation.expires_at <= timezone.now() \
            and invitation.account_state != Invitation.AccountState.UNAVAILABLE:
        state, label = 'expired', 'Invitation expired -- resend it'
    elif invitation.delivery == Invitation.Delivery.SENT:
        state, label = 'invited', 'Invitation sent, awaiting acceptance'
    else:
        state, label = 'not_sent', 'Invitation not sent yet'
    return {'configured': True, 'name': institution.coordinator_name, 'email': institution.coordinator_email,
            'state': state, 'state_label': label,
            # A resend produces a new link -- never for an email that cannot be used.
            'can_resend': invitation is not None
            and invitation.account_state != Invitation.AccountState.UNAVAILABLE,
            'last_sent_at': invitation.last_sent_at if invitation else None,
            'send_count': invitation.send_count if invitation else 0}
