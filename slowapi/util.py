def get_remote_address(request):
    if hasattr(request, 'client') and request.client is not None:
        return request.client.host or "127.0.0.1"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return "127.0.0.1"
