from django.urls import path

from .views import InstitutionViewSet

institution_list = InstitutionViewSet.as_view({'get': 'list', 'post': 'create'})
institution_detail = InstitutionViewSet.as_view({
    'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy',
})

# Registered with and without a trailing slash: the task spec documents these
# as .../institutions/, but APPEND_SLASH=False (see settings) and this
# project's existing frontend calls '/institutions' without one -- both
# forms resolve to the same viewset actions.
urlpatterns = [
    path('', institution_list, name='institution-list'),
    path('/', institution_list, name='institution-list-slash'),
    path('/<uuid:pk>', institution_detail, name='institution-detail'),
    path('/<uuid:pk>/', institution_detail, name='institution-detail-slash'),
]
