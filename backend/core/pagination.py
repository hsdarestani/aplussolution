from rest_framework.pagination import PageNumberPagination


class PathAwarePagination(PageNumberPagination):
    """Keep normal API pages small while allowing the schedule to receive all shifts.

    The current schedule UI renders calendar views client-side and does not follow
    DRF pagination links. With a 50-row page size, valid future shifts can be
    hidden behind historical rows. Shift endpoints therefore use a larger page
    while every other endpoint keeps the existing page size.
    """

    page_size = 50
    max_shift_page_size = 5000

    def get_page_size(self, request):
        path = str(getattr(request, 'path', '') or '')
        if path.startswith('/api/shifts/') or path == '/api/shifts':
            return self.max_shift_page_size
        return self.page_size
