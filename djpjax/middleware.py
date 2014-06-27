import ast
from collections import deque
import re
from django.core.exceptions import ImproperlyConfigured

from djpjax import pjax_block, pjax_template
from djpjax.utils import strip_pjax_parameter
from django.conf import settings


def _depth_limited_ast_bfs(node, limit):
    todo = deque([(node, 1)])
    while todo:
        node, depth = todo.popleft()
        if depth < limit:
            todo.extend((child, depth+1)
                        for child in ast.iter_child_nodes(node))
        yield node


class DjangoPJAXMiddleware(object):

    def __init__(self, config=None):
        djpjax_setting = (config or
                          getattr(settings, 'DJPJAX_DECORATED_URLS', None))
        self.decorated_urls = self.parse_configuration(djpjax_setting or [])

    @staticmethod
    def parse_decorator(decorator_string):

        error = lambda msg: ImproperlyConfigured(
            '"%s" does not define a valid PJAX decorator: %s'
            % (decorator_string, msg))

        if not decorator_string.startswith('@'):
            raise error("expression should start with '@'")

        expr = ast.parse(decorator_string[1:], '<string>', mode='eval')
        if not isinstance(expr.body, ast.Call):
            raise error("decorator expression must be a single call "
                        "to pjax_block or pjax_template")

        call = expr.body
        if call.func.id not in ('pjax_block', 'pjax_template'):
            raise error("decorator expression must be a single call "
                        "to pjax_block or pjax_template")

        if not (call.starargs is None and call.kwargs is None):
            raise error("unpacking * and ** arguments is not supported")

        if not all(isinstance(arg, ast.Str) for arg
                   in call.args + [kw.value for kw in call.keywords]):
            raise error("only string arguments are allowed")

        return eval(compile(expr, '<string>', mode='eval'))

    @staticmethod
    def parse_configuration(config_tuple):
        listify = lambda d: d if isinstance(d, (list, tuple)) else [d]
        parse_fn = DjangoPJAXMiddleware.parse_decorator
        return tuple(
            (re.compile(url_regex),
             [parse_fn(d) for d in reversed(listify(decorators))])
            for url_regex, decorators in reversed(config_tuple))

    def process_request(self, request):
        strip_pjax_parameter(request)

    def process_template_response(self, request, response):
        for url_regex, decorators in self.decorated_urls:
            if url_regex.match(request.path):
                fake_view = lambda _: response
                for decorator in decorators:
                    response = decorator(fake_view)(request)
        return response
