"""Applies the demo display mask (mask.py) to API responses. Does nothing while DEMO_NAME_MASK is empty."""
import json
import re

from django.http import JsonResponse

from . import mask

TEXT_TYPES = ('application/json', 'text/html', 'text/plain', 'text/csv', 'application/problem+json')
#: Set by a view whose binary body was made from masked data (the capability report PDFs).
APPLIED_HEADER = 'X-Name-Mask'
#: Left unmasked for now (Siddharth, 27 Nov 2026): the facts check and the follow-up questions. People answer these
#: screens, and what they pick or write goes back to the server and on to judging. The masked name is not in the
#: stored data, so choosing "ABC University" as the institution the documents belong to was refused, and an answer
#: written about "ABC University" would be judged against documents that name the real institution.
UNMASKED = re.compile(r'^/api/v\d+/sprints/[0-9a-f-]+/(review-batch'
                      r'|capability-runs/[0-9a-f-]+/(questions|responses|additional-evidence))(/|$)')


def _masked_json(body):
    """A JSON body with only its strings masked, or None when it doesn't parse. Masking the raw text also rewrote
    numbers: a bare 600117 (a postcode term) became 600 000, which is not JSON (25 Nov audit, finding 6)."""
    try:
        value = json.loads(body)
    except ValueError:
        return None
    masked = mask.data(value)
    if masked == value:
        return body
    return json.dumps(masked, ensure_ascii=False, separators=(',', ':'))


class NameMaskMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not mask.active() or not request.path.startswith('/api/') or UNMASKED.match(request.path):
            return response
        if 'Content-Disposition' in response:
            response['Content-Disposition'] = mask.text(response['Content-Disposition'])
        if getattr(response, 'streaming', False) or response.status_code in (204, 304):
            return self._binary(response)
        kind = (response.get('Content-Type') or '').split(';')[0].strip().lower()
        if kind in TEXT_TYPES or kind.endswith('+json'):
            charset = response.charset or 'utf-8'
            body = response.content.decode(charset, errors='replace')
            masked = _masked_json(body) if kind == 'application/json' or kind.endswith('+json') else None
            if masked is None:
                masked = mask.text(body)
            if masked != body:
                response.content = masked.encode(charset)
                if response.has_header('Content-Length'):
                    response['Content-Length'] = str(len(response.content))
            return response
        if not response.content:
            return response
        return self._binary(response)

    @staticmethod
    def _binary(response):
        """A file the mask cannot rewrite (an uploaded document, a stored report file): refused in demo mode, unless the
        view made it from masked data (APPLIED_HEADER) or it is an empty/not-modified answer."""
        if response.get(APPLIED_HEADER) == 'applied' or response.status_code in (204, 304):
            return response
        if not getattr(response, 'streaming', False) and not response.content:
            return response
        # Close the file being served, not the response: HttpResponse.close() sends request_finished, which closes
        # the request's database connection early.
        stream = getattr(response, 'file_to_stream', None)
        if stream is not None and hasattr(stream, 'close'):
            stream.close()
        return JsonResponse({'detail': 'Original files are not available in demo mode.',
                             'code': 'demo_mask_download_blocked'}, status=403)
