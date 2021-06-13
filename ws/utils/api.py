def jwt_token_from_headers(request):
    """Extract a JWT token from the Bearer header."""
    http_auth = request.META.get('HTTP_AUTHORIZATION')
    if not (http_auth and http_auth.startswith('Bearer: ')):
        raise ValueError('token missing')
    return http_auth.split()[1]
