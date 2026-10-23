from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """Page-number pagination that only activates when the client asks for it.

    Without a `page` or `page_size` query param, `paginate_queryset` returns
    None, which tells DRF's ListModelMixin to skip pagination and serialize
    the full queryset as a plain array. Existing callers (this project's
    other list endpoints all return bare arrays, and this project's frontend
    consumes them with `.map()` directly) keep working unmodified;
    `?page=2` or `?page_size=10` opts a request into the paginated
    `{count, next, previous, results}` shape.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        if request.query_params.get(self.page_query_param) or request.query_params.get(self.page_size_query_param):
            return super().paginate_queryset(queryset, request, view=view)
        return None


class DefaultPageNumberPagination(PageNumberPagination):
    """Always paginated: 50 rows per page by default, `?page_size=` up to 100, `?page=` from 1.
    For lists that grow with the sprint (facts, gaps): a client never downloads them whole by accident.
    Response: {count, next, previous, results}."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100
