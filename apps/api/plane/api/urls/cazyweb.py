# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Cazyweb-specific public-API URL patterns (workspace create, direct
# workspace member add/remove, admin magic-link mint).

from django.urls import path

from plane.api.views.cazyweb import (
    CazywebWorkspaceCreateAPIEndpoint,
    CazywebWorkspaceMemberAPIEndpoint,
    CazywebMagicGenerateAPIEndpoint,
    CazywebMagicSignInAPIEndpoint,
    CazywebUserFindOrCreateAPIEndpoint,
)

urlpatterns = [
    path(
        "users/find-or-create/",
        CazywebUserFindOrCreateAPIEndpoint.as_view(http_method_names=["post"]),
        name="cazyweb-user-find-or-create",
    ),
    path(
        "workspaces/",
        CazywebWorkspaceCreateAPIEndpoint.as_view(http_method_names=["post"]),
        name="cazyweb-workspace-create",
    ),
    path(
        "workspaces/<str:slug>/workspace-members/",
        CazywebWorkspaceMemberAPIEndpoint.as_view(http_method_names=["post"]),
        name="cazyweb-workspace-member-add",
    ),
    path(
        "workspaces/<str:slug>/workspace-members/<uuid:user_id>/",
        CazywebWorkspaceMemberAPIEndpoint.as_view(http_method_names=["delete"]),
        name="cazyweb-workspace-member-remove",
    ),
    path(
        "auth/magic-generate/",
        CazywebMagicGenerateAPIEndpoint.as_view(http_method_names=["post"]),
        name="cazyweb-magic-generate",
    ),
    path(
        "auth/magic-sign-in/",
        CazywebMagicSignInAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="cazyweb-magic-sign-in",
    ),
]
