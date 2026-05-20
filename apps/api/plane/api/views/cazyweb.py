# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Cazyweb public-API extensions: workspace create, direct workspace-member
# add/remove, and admin-only magic-link sign-in token mint.
#
# These endpoints are exposed under /api/v1/ and authenticate via the same
# X-API-Key admin-token auth used by the rest of the public API.

# Python imports
import json
import re
import secrets

# Django imports
from django.contrib.auth import login as django_login
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# Third party imports
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView

# Module imports
from .base import BaseAPIView
from plane.db.models import User, Workspace, WorkspaceMember, Profile
from plane.utils.constants import RESTRICTED_WORKSPACE_SLUGS
from plane.utils.url import contains_url
from plane.settings.redis import redis_instance


# Redis prefix for opaque admin-minted sign-in tickets. Each ticket maps to
# an email; consuming the ticket logs that user in. TTL = 10 minutes.
CAZYWEB_TICKET_PREFIX = "cazyweb_magic_ticket:"
CAZYWEB_TICKET_TTL_SECONDS = 600


# Role values mirror plane.db.models.WorkspaceMember.role choices.
# 20 = admin/owner, 15 = member, 10 = viewer, 5 = guest.
ALLOWED_MEMBER_ROLES = {5, 10, 15, 20}


class CazywebWorkspaceCreateAPIEndpoint(BaseAPIView):
    """
    POST /api/v1/workspaces/

    Creates a new workspace owned by the API-token user and adds that user
    as the workspace admin (role 20). Adapted from
    plane.app.views.workspace.base.WorkSpaceViewSet.create.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        slug = (request.data.get("slug") or "").strip()

        if not name or not slug:
            return Response(
                {"error": "Both name and slug are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(name) > 80 or len(slug) > 48:
            return Response(
                {"error": "The maximum length for name is 80 and for slug is 48"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if contains_url(name):
            return Response(
                {"error": "Name cannot contain a URL"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if slug in RESTRICTED_WORKSPACE_SLUGS:
            return Response(
                {"error": "Slug is not valid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not re.match(r"^[a-zA-Z0-9_-]+$", slug):
            return Response(
                {
                    "error": "Slug can only contain letters, numbers, hyphens (-), and underscores (_)"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            workspace = Workspace.objects.create(
                name=name,
                slug=slug,
                owner=request.user,
                created_by=request.user,
                updated_by=request.user,
            )
        except IntegrityError as e:
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                return Response(
                    {"slug": "The workspace with the slug already exists"},
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        WorkspaceMember.objects.create(
            workspace_id=workspace.id,
            member=request.user,
            role=20,
            company_role=request.data.get("company_role", ""),
        )

        return Response(
            {
                "id": str(workspace.id),
                "slug": workspace.slug,
                "name": workspace.name,
                "owner": str(workspace.owner_id),
                "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
            },
            status=status.HTTP_201_CREATED,
        )


class CazywebWorkspaceMemberAPIEndpoint(BaseAPIView):
    """
    POST   /api/v1/workspaces/<slug>/workspace-members/
    DELETE /api/v1/workspaces/<slug>/workspace-members/<user_id>/

    Directly add or remove a user from a workspace without the invitation
    flow. The API-token user must be a workspace admin (role 20).

    POST body: {"member_id": "<plane_user_uuid>", "role": 20|15|10|5}
    Returns the created WorkspaceMember row.

    DELETE: deactivates the membership (matches the internal endpoint
    behaviour) by setting is_active=False.
    """

    permission_classes = [IsAuthenticated]

    def _ensure_admin(self, slug):
        if not Workspace.objects.filter(slug=slug).exists():
            return Response(
                {"error": "Workspace does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )
        is_admin = WorkspaceMember.objects.filter(
            workspace__slug=slug,
            member=self.request.user,
            role=20,
            is_active=True,
        ).exists()
        if not is_admin:
            return Response(
                {"error": "You must be a workspace admin to manage members"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def post(self, request, slug):
        denied = self._ensure_admin(slug)
        if denied is not None:
            return denied

        member_id = request.data.get("member_id")
        role = request.data.get("role")

        if not member_id:
            return Response(
                {"error": "member_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            role = int(role) if role is not None else 15
        except (TypeError, ValueError):
            return Response(
                {"error": "role must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if role not in ALLOWED_MEMBER_ROLES:
            return Response(
                {"error": f"role must be one of {sorted(ALLOWED_MEMBER_ROLES)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=member_id)
        except (User.DoesNotExist, ValidationError, ValueError):
            return Response(
                {"error": "User with the given member_id does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        workspace = Workspace.objects.get(slug=slug)

        existing = WorkspaceMember.objects.filter(workspace=workspace, member=user).first()
        if existing:
            # Re-activate / update role if previously deactivated.
            existing.role = role
            existing.is_active = True
            existing.save(update_fields=["role", "is_active", "updated_at"])
            wm = existing
            created = False
        else:
            wm = WorkspaceMember.objects.create(
                workspace=workspace,
                member=user,
                role=role,
                created_by=request.user,
                updated_by=request.user,
            )
            created = True

        return Response(
            {
                "id": str(wm.id),
                "workspace": str(wm.workspace_id),
                "member": str(wm.member_id),
                "role": wm.role,
                "is_active": wm.is_active,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, slug, user_id):
        denied = self._ensure_admin(slug)
        if denied is not None:
            return denied

        try:
            wm = WorkspaceMember.objects.get(
                workspace__slug=slug,
                member_id=user_id,
                is_active=True,
            )
        except WorkspaceMember.DoesNotExist:
            return Response(
                {"error": "Workspace member not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if str(wm.member_id) == str(request.user.id):
            return Response(
                {"error": "You cannot remove yourself from the workspace"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wm.is_active = False
        wm.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CazywebMagicGenerateAPIEndpoint(BaseAPIView):
    """
    POST /api/v1/auth/magic-generate/

    Mints a one-time opaque sign-in ticket for a given email. Admin-only:
    requires the X-API-Key admin token. The ticket is consumed by hitting
    GET /api/v1/auth/magic-sign-in/?token=<ticket>, which logs the user in
    and redirects to the Plane app home.

    This deliberately does NOT use Plane's MagicCodeProvider because that
    refuses to operate when SMTP is unconfigured. We bypass that since we
    never actually send an email; we hand the ticket back to the caller.

    Body: {"email": "user@example.com"}
    Returns: {"email": "...", "token": "<opaque>",
              "sign_in_url": "<host>/api/v1/auth/magic-sign-in/?token=<opaque>"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()

        try:
            validate_email(email)
        except ValidationError:
            return Response(
                {"error": "A valid email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not User.objects.filter(email=email).exists():
            return Response(
                {"error": "No user with that email exists"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate a high-entropy opaque ticket and stash the target email
        # in Redis under it. The ticket itself is the only thing the caller
        # needs -- email lookup happens on the consume side.
        ticket = secrets.token_urlsafe(32)
        ri = redis_instance()
        ri.set(
            CAZYWEB_TICKET_PREFIX + ticket,
            json.dumps({"email": email}),
            ex=CAZYWEB_TICKET_TTL_SECONDS,
        )

        host = request.build_absolute_uri("/").rstrip("/")
        sign_in_url = f"{host}/api/v1/auth/magic-sign-in/?token={ticket}"

        return Response(
            {
                "email": email,
                "token": ticket,
                "sign_in_url": sign_in_url,
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class CazywebMagicSignInAPIEndpoint(APIView):
    """
    GET  /api/v1/auth/magic-sign-in/?token=<opaque>
    POST /api/v1/auth/magic-sign-in/   body: {"token": "<opaque>"}

    Consumes an admin-minted ticket from CazywebMagicGenerateAPIEndpoint,
    logs the target user in (Django session), and:
      - GET: redirects (302) to the Plane app home `/`
      - POST: returns 200 JSON {"signed_in": true, "redirect": "/"}

    This is a public endpoint (no API key required) because it is meant to
    be the URL the end-user clicks. Security relies on the opacity and TTL
    of the ticket, which is single-use.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def _consume(self, token):
        if not token:
            return None
        ri = redis_instance()
        key = CAZYWEB_TICKET_PREFIX + token
        raw = ri.get(key)
        if not raw:
            return None
        # Delete first to enforce single-use even on concurrent hits.
        ri.delete(key)
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        email = data.get("email")
        if not email:
            return None
        return User.objects.filter(email=email).first()

    def get(self, request):
        token = request.GET.get("token", "").strip()
        user = self._consume(token)
        if user is None:
            return HttpResponseRedirect("/?error_code=INVALID_OR_EXPIRED_TOKEN")
        Profile.objects.get_or_create(user=user)
        django_login(request, user)
        request.session.save()
        return HttpResponseRedirect("/")

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        user = self._consume(token)
        if user is None:
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        Profile.objects.get_or_create(user=user)
        django_login(request, user)
        request.session.save()
        return Response({"signed_in": True, "redirect": "/"}, status=status.HTTP_200_OK)


class CazywebUserFindOrCreateAPIEndpoint(BaseAPIView):
    """
    POST /api/v1/users/find-or-create/

    Look up a Plane user by email. If not found, create one (active, email-verified,
    with a random unguessable password since this user will sign in via admin-minted
    magic-link only). Returns the user's UUID + email.

    Body: { "email": "...", "first_name": "..." (optional) }
    Returns: { "id": "<uuid>", "email": "...", "created": true|false }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        first_name = (request.data.get("first_name") or "").strip()

        if not email:
            return Response({"error": "email is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(email)
        except ValidationError:
            return Response({"error": "invalid email"}, status=status.HTTP_400_BAD_REQUEST)

        existing = User.objects.filter(email=email).first()
        if existing:
            return Response(
                {"id": str(existing.id), "email": existing.email, "created": False},
                status=status.HTTP_200_OK,
            )

        random_pw = secrets.token_urlsafe(32)
        try:
            user = User.objects.create_user(email=email, username=email, password=random_pw)
        except IntegrityError:
            # Race: another request just created it. Re-fetch.
            existing = User.objects.filter(email=email).first()
            if existing:
                return Response(
                    {"id": str(existing.id), "email": existing.email, "created": False},
                    status=status.HTTP_200_OK,
                )
            return Response({"error": "could not create user"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if first_name:
            user.first_name = first_name
        user.is_active = True
        user.is_email_verified = True
        user.save()
        Profile.objects.get_or_create(user=user)

        return Response(
            {"id": str(user.id), "email": user.email, "created": True},
            status=status.HTTP_201_CREATED,
        )
