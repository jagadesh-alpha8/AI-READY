"""Routes for user administration.

Separate from `urls.py`, which is mounted under `/api/v1/auth/` for the
authentication endpoints. Administering users is not an auth concern and does
not belong under that prefix, so it gets its own module mounted at
`/api/v1/users`.

Trailing-slash duplicates as everywhere else in this project: APPEND_SLASH is
off, and the frontend is not consistent about them.
"""
from django.urls import path

from .user_admin import UserAdminViewSet

_list = UserAdminViewSet.as_view({'get': 'list', 'post': 'create'})
_detail = UserAdminViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
})

urlpatterns = [
    path('', _list, name='user-list'),
    path('/', _list, name='user-list-slash'),
    path('/<uuid:pk>', _detail, name='user-detail'),
    path('/<uuid:pk>/', _detail, name='user-detail-slash'),
]
