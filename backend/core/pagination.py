from rest_framework.pagination import PageNumberPagination


class PathAwarePagination(PageNumberPagination):
    """Use large pages for schedule data and picker directory metadata.

    The mobile schedule renders its pickers client-side and does not follow DRF
    pagination links. If workers, customers or locations are paginated before the UI
    filters inactive legacy rows or Zeitplan groups, valid active entries can
    disappear from the picker (for example a Service worker sorted after page 1).
    """

    page_size = 50
    max_shift_page_size = 5000
    max_directory_page_size = 5000

    def get_page_size(self, request):
        path = str(getattr(request, 'path', '') or '')
        if path.startswith('/api/shifts/') or path == '/api/shifts':
            return self.max_shift_page_size
        if path in {'/api/workers/', '/api/workers', '/api/clients/', '/api/clients', '/api/locations/', '/api/locations'}:
            return self.max_directory_page_size
        return self.page_size
