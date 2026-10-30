from django.urls import path

from .views import (
    DepartmentDetailView,
    DepartmentListCreateView,
    InstitutionCoordinatorResendView,
    InstitutionCoordinatorView,
    InstitutionLeaderDetailView,
    InstitutionLeaderListCreateView,
    InstitutionSystemDetailView,
    InstitutionSystemListCreateView,
    InstitutionViewSet,
)

institution_list = InstitutionViewSet.as_view({'get': 'list', 'post': 'create'})
institution_detail = InstitutionViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
})
institution_deletion_preview = InstitutionViewSet.as_view({'get': 'deletion_preview'})
institution_archive = InstitutionViewSet.as_view({'post': 'archive'})
institution_unarchive = InstitutionViewSet.as_view({'post': 'unarchive'})

# Registered with and without a trailing slash: the task spec documents these
# as .../institutions/, but APPEND_SLASH=False (see settings) and this
# project's existing frontend calls '/institutions' without one -- both
# forms resolve to the same viewset actions.
#
# The Institution DNA sub-resources below are nested under their institution
# rather than given top-level prefixes of their own: they have no meaning
# apart from it, and nesting is what lets one access check in
# InstitutionScopedMixin cover every one of them.
urlpatterns = [
    path('', institution_list, name='institution-list'),
    path('/', institution_list, name='institution-list-slash'),
    path('/<uuid:pk>', institution_detail, name='institution-detail'),
    path('/<uuid:pk>/', institution_detail, name='institution-detail-slash'),
    path('/<uuid:pk>/deletion-preview', institution_deletion_preview, name='institution-deletion-preview'),
    path('/<uuid:pk>/deletion-preview/', institution_deletion_preview, name='institution-deletion-preview-slash'),
    path('/<uuid:pk>/delete-preview', institution_deletion_preview, name='institution-delete-preview'),
    path('/<uuid:pk>/delete-preview/', institution_deletion_preview, name='institution-delete-preview-slash'),
    path('/<uuid:pk>/archive', institution_archive, name='institution-archive'),
    path('/<uuid:pk>/archive/', institution_archive, name='institution-archive-slash'),
    path('/<uuid:pk>/unarchive', institution_unarchive, name='institution-unarchive'),
    path('/<uuid:pk>/unarchive/', institution_unarchive, name='institution-unarchive-slash'),
    path('/<uuid:institution_id>/coordinator', InstitutionCoordinatorView.as_view(), name='institution-coordinator'),
    path('/<uuid:institution_id>/coordinator/resend', InstitutionCoordinatorResendView.as_view(),
         name='institution-coordinator-resend'),

    path(
        '/<uuid:institution_id>/leaders',
        InstitutionLeaderListCreateView.as_view(), name='institution-leaders',
    ),
    path(
        '/<uuid:institution_id>/leaders/',
        InstitutionLeaderListCreateView.as_view(), name='institution-leaders-slash',
    ),
    path(
        '/<uuid:institution_id>/leaders/<uuid:pk>',
        InstitutionLeaderDetailView.as_view(), name='institution-leader-detail',
    ),
    path(
        '/<uuid:institution_id>/leaders/<uuid:pk>/',
        InstitutionLeaderDetailView.as_view(), name='institution-leader-detail-slash',
    ),

    path(
        '/<uuid:institution_id>/departments',
        DepartmentListCreateView.as_view(), name='institution-departments',
    ),
    path(
        '/<uuid:institution_id>/departments/',
        DepartmentListCreateView.as_view(), name='institution-departments-slash',
    ),
    path(
        '/<uuid:institution_id>/departments/<uuid:pk>',
        DepartmentDetailView.as_view(), name='institution-department-detail',
    ),
    path(
        '/<uuid:institution_id>/departments/<uuid:pk>/',
        DepartmentDetailView.as_view(), name='institution-department-detail-slash',
    ),

    path(
        '/<uuid:institution_id>/systems',
        InstitutionSystemListCreateView.as_view(), name='institution-systems',
    ),
    path(
        '/<uuid:institution_id>/systems/',
        InstitutionSystemListCreateView.as_view(), name='institution-systems-slash',
    ),
    path(
        '/<uuid:institution_id>/systems/<uuid:pk>',
        InstitutionSystemDetailView.as_view(), name='institution-system-detail',
    ),
    path(
        '/<uuid:institution_id>/systems/<uuid:pk>/',
        InstitutionSystemDetailView.as_view(), name='institution-system-detail-slash',
    ),
]
